import csv,json,math,sqlite3,sys,time
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
import yaml
import cv2
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
sys.path[:0]=[str(REPO/'src/perception'),str(REPO/'src/object_db')]
from object_db import association,db,queries
from perception.core.fusion import erode_mask

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
def load_csv(path):
    with path.open(newline='',encoding='utf-8') as f:
        return list(csv.DictReader(f))
def csv_write(path, rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
def put(path,d):
    path.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def connect(path):
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    return c
def stats(v):
    return dict(mean=float(np.mean(v)),median=float(np.median(v)),p90=float(np.quantile(v,.9))) if len(v) else {}
def diff_angle(a,b):
    return abs((a-b+math.pi)%(2*math.pi)-math.pi)
def points(K):
    x,y=np.meshgrid(np.arange(1280,dtype=np.float32),np.arange(720,dtype=np.float32))
    return np.stack(((x-K[2])/K[0],(y-K[3])/K[1],np.ones_like(x)),axis=-1)

class Scan:
    def __init__(self,name):
        self.path=ROOT/name
        self.cfg=yaml.safe_load((self.path/'config.yaml').read_text())
        self.gt_all=yaml.safe_load((self.path/'gt.yaml').read_text())['objects']
        self.gt={o['model_name']:o for o in self.gt_all if 'semantic_label' in o}
        self.classes={o['class_name'] for o in self.gt.values()}
        self.centers={key:np.array([o[k] for k in 'xyz']) for key,o in self.gt.items()}
        self.stops=sorted((read(f) for f in self.path.glob('audit_scan_*.json')),key=lambda s:s['stop_index'])
        self.id=self.stops[0]['scan_id']
        self.frames={f['stamp_ns']:{**f,'stop':s['stop_index'],'yaw':s['command_yaw_rad']}
                     for s in self.stops for f in s['frames']}
        self.annotations=load_csv(self.path/'detection_audit.csv')
        self.det_by_frame=defaultdict(list)
        for a in self.annotations:
            self.det_by_frame[int(a['stamp_ns'])].append(a)
        self.labels={int(a['A_obs_id']):a for a in self.annotations if a['A_obs_id']}
        with connect(self.path/'replay_A.sqlite') as c:
            self.original=[dict(o) for o in c.execute('SELECT * FROM observations ORDER BY obs_id')]
            self.objects=[dict(o) for o in c.execute('SELECT * FROM objects ORDER BY object_id')]
        self.objects_by_id={o['object_id']:o for o in self.objects}
        self.members=defaultdict(list)
        for o in self.original:
            self.members[o['object_id']].append(o)
    def evaluate(self,objects,members,labels):
        clean=defaultdict(list)
        wrong=unscored=0
        for o in objects:
            if o['status']!='confirmed':
                continue
            evidence=[labels.get(row['obs_id'],{}) for row in members[o['object_id']]]
            names={e.get('instance_gt') for e in evidence if e.get('status')=='true'}
            if len(names)==1 and all(e.get('status')=='true' for e in evidence):
                target=next(iter(names))
                xyz=np.array([o[k] for k in 'xyz'])
                err=xyz-self.centers[target]
                clean[target].append(dict(target=target,id=o['object_id'],xyz=xyz.tolist(),error=err.tolist(),
                    xy=float(np.linalg.norm(err[:2])),xyz_error=float(np.linalg.norm(err)),n=len(evidence),
                    independent_angles=len({row['stop_index'] for row in members[o['object_id']]})))
            elif any(e.get('instance_gt') for e in evidence):
                wrong+=1
            else:
                unscored+=1
        best=[max(rows,key=lambda r:(r['n'],-r['id'])) for rows in clean.values()]
        dup=sum(len(rows)-1 for rows in clean.values())
        xy=stats([o['xy'] for o in best])
        xyz=stats([o['xyz_error'] for o in best])
        return dict(confirmed=len(best),missing=len(self.gt)-len(best),wrong=wrong,unscored=unscored,duplicate=dup,
            recall=len(best)/len(self.gt),localized=sum(o['xy']<self.cfg['eval']['match_radius_m'] for o in best),
            precision=len(best)/(len(best)+wrong+dup) if best or wrong or dup else None,
            **{'xy_'+k:v for k,v in xy.items()},**{'xyz_'+k:v for k,v in xyz.items()},objects=best)
    def replay(self,name,rows):
        path=ROOT/f'{name}.sqlite'
        assert not path.exists(),path
        con=db.open_db(path)
        db.create_scan(con,self.id,self.cfg,'Kitchen multiview '+name)
        db.load_gt_objects(con,self.gt_all)
        tags={}
        for o,tag in rows:
            item={k:o[k] for k in ('class_name','confidence','truncated','depth_m','range_m','stop_index','frame_idx','yaw_rad','stamp_ns')}
            item.update(bbox_xyxy=[o['bbox_'+k] for k in ('x1','y1','x2','y2')],
                valid_depth_ratio=o['valid_ratio'],p_cam=[o['cam_'+k] for k in 'xyz'],p_world=[o['world_'+k] for k in 'xyz'])
            oid=association.add_observation(con,self.id,item,self.cfg['assoc'],self.cfg['fusion'])['obs_id']
            tags[oid]=tag
        association.run_association_pass(con,self.id,self.cfg['assoc'])
        db.finish_scan(con,self.id)
        assert con.execute('pragma integrity_check').fetchone()[0]=='ok'
        oo=[dict(o) for o in con.execute('select * from objects')]
        members=defaultdict(list)
        for r in con.execute('select * from observations'):
            members[r['object_id']].append(dict(r))
        con.close()
        return self.evaluate(oo,members,tags)
    def with_positions(self,name,positions):
        path=ROOT/f'{name}.sqlite'
        assert not path.exists()
        with connect(self.path/'replay_A.sqlite') as source,sqlite3.connect(path) as dest:
            source.backup(dest)
            dest.row_factory=sqlite3.Row
            for oid,xyz in positions.items():
                dest.execute('update objects set x=?,y=?,z=? where object_id=?',(*xyz,oid))
            dest.commit()
            assert dest.execute('pragma integrity_check').fetchone()[0]=='ok'
            rows=[dict(o) for o in dest.execute('select * from objects')]
        return self.evaluate(rows,self.members,self.labels)
    def rot(self,f):
        return Rotation.from_quat(f['tf']['quaternion']).as_matrix()
    def frame_archive(self,f):
        return np.load(self.path/'frames'/f['file'],allow_pickle=False)

def row_xyz(o):
    return np.array([o['world_'+k] for k in 'xyz'])

def gt_stats(scan, selector=lambda f:True):
    rows=load_csv(scan.path/'visibility_by_frame.csv')
    filtered=[r for r in rows if selector(r)]
    vis=[r for r in filtered if int(r['visible_pixels'])>0]
    true=sum(r['detected']=='True' for r in vis)
    return dict(visible=len(vis),true=true,missed=len(vis)-true,
                detection_wrong=sum(int(r['wrong_class']) for r in vis),truncated=sum(int(r['truncated']) for r in vis),
                detection_recall=true/len(vis) if vis else None)

