import csv
import json
import hashlib
import itertools
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation
import yaml

root = Path(__file__).resolve().parent
repo = next(p for p in root.parents if (p/'src/object_db').is_dir())
sys.path[:0] = [str(repo/'src/perception'), str(repo/'src/object_db')]
from perception.core.fusion import erode_mask
from perception.core.geometry import backproject_optical
from object_db import association, db, queries

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(name, data):
    (root/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def csvfile(name, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (root/name).open('w',encoding='utf-8',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def arr(v):
    return np.array(v,dtype=float)

def box_projection(center, ref, transform, translation, K):
    offsets = arr(list(itertools.product(*[(-ref[k]/2,ref[k]/2) for k in ('size_x','size_y','size_z')])))
    corners = (center+offsets-translation) @ transform
    if corners[:,2].max() <= 0:
        return 'outside_fov'
    if corners[:,2].min() <= 0:
        return 'frustum_uncertain'
    fx,fy,cx,cy = K
    u = fx*corners[:,0]/corners[:,2]+cx
    v = fy*corners[:,1]/corners[:,2]+cy
    return 'outside_fov' if u.max()<0 or u.min()>1279 or v.max()<0 or v.min()>719 else 'in_fov_no_instance_pixels'

def geom_summary(values):
    return None if not values else dict(zip(('mean','median','p90'),
        map(float,[np.mean(values),np.median(values),np.quantile(values,.9)]),strict=True))

cfg = yaml.safe_load((root/'config.yaml').read_text())
gt_all = yaml.safe_load((root/'gt.yaml').read_text())['objects']
targets = {o['model_name']:o for o in gt_all if 'semantic_label' in o}
assert len(targets) == 4
centers = {key:arr([v[axis] for axis in 'xyz']) for key,v in targets.items()}
classes = {o['class_name'] for o in targets.values()}
lock = read(root/'locked.json')
assert hashlib.sha256((root/'locked.json').read_bytes()).hexdigest() == (root/'locked.sha256').read_text().strip()
stops = sorted((read(p) for p in root.glob('audit_scan_*.json')),key=lambda s:s['stop_index'])
assert [s['stop_index'] for s in stops] == list(range(8))
assert all(len(s['frames'])==3 for s in stops)
assert len({s['scan_id'] for s in stops})==1
scan_id = stops[0]['scan_id']
with sqlite3.connect((root/'db'/f'{scan_id}.sqlite').as_uri()+'?mode=ro',uri=True) as live:
    live.row_factory = sqlite3.Row
    assert live.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert live.execute('SELECT finished_at FROM scans').fetchone()[0]
    live_obs = [dict(r) for r in live.execute('SELECT * FROM observations ORDER BY obs_id')]
    live_objects = [dict(r) for r in live.execute('SELECT * FROM objects ORDER BY object_id')]
dbs = {}
for method in 'AB':
    path = root/f'replay_{method}.sqlite'
    assert not path.exists()
    con = db.open_db(path)
    db.create_scan(con,scan_id,cfg,'Kitchen','offline replay '+method,repo)
    db.load_gt_objects(con,gt_all)
    dbs[method] = con

frame_rows, detections, visibility, depths, contact = [], [], [], [], []
spans = defaultdict(float)
by_obs = {m:{} for m in dbs}
issue_frames = {}
last_stamp = -1
n_wire = 0
wire_tf_missing = []
for stop in stops:
    k = stop['stop_index']
    for f in stop['frames']:
        stamp = f['stamp_ns']
        assert stamp>last_stamp and stamp == f['camera_info_stamp_ns']
        assert f['depth_exact_stamp'] and f['label_exact_stamp'] and f['tf']
        last_stamp = stamp
        K = f['K']
        rotation = Rotation.from_quat(f['tf']['quaternion'])
        transform = rotation.as_matrix()
        translation = arr(f['tf']['translation'])
        yaw = math.atan2(transform[1,2],transform[0,2])
        angular = abs((yaw-stop['command_yaw_rad']+math.pi)%(2*math.pi)-math.pi)
        expected_t = arr(cfg['camera']['base_xyz'])+cfg['camera']['t_offset_m']*transform[:,2]
        assert np.linalg.norm(translation-expected_t)<1e-6
        joint_error = abs((yaw-f['joint_yaw_rad']+math.pi)%(2*math.pi)-math.pi)
        frame_rows.append(dict(stop=k,frame=f['frame_idx'],stamp_ns=stamp,
            camera_info_stamp_ns=f['camera_info_stamp_ns'],joint_skew_ns=f['joint_skew_ns'],
            tf_heading_deg=math.degrees(yaw),command_error_deg=math.degrees(angular),
            tf_joint_error_deg=math.degrees(joint_error),K=K,**f['timings_ms']))
        with np.load(root/'frames'/f['file'],allow_pickle=False) as packet:
            image,pred,ground,labels = [packet[key] for key in ('rgb','pred_depth','gt_depth','labels_rgb')]
            assert image.shape==labels.shape==(720,1280,3) and pred.shape==ground.shape==(720,1280)
            dets = f['detections']
            masks = [np.unpackbits(packet[d['mask']],axis=1,count=1280).astype(bool) for d in dets]
        instance = labels[...,0].astype(np.uint16) | (labels[...,1].astype(np.uint16)<<8)
        gt_masks = {name:(labels[...,2]==ref['semantic_label']) & (instance!=0) for name,ref in targets.items()}
        for mask in gt_masks.values():
            assert len(np.unique(instance[mask])) <= 1
        names = [name for name,mask in gt_masks.items() if mask.any()]
        ious = np.zeros((len(dets),len(names)))
        for j,mask in enumerate(masks):
            for t,name in enumerate(names):
                gt_mask = gt_masks[name]
                ious[j,t] = np.count_nonzero(mask&gt_mask)/np.count_nonzero(mask|gt_mask)
        cost = np.array([[1-ious[j,t] if ious[j,t]>=.5 and d['class_name']==targets[name]['class_name'] else 1e6
                          for t,name in enumerate(names)] for j,d in enumerate(dets)]).reshape(ious.shape)
        jr,tr = linear_sum_assignment(cost)
        matched = {int(j):names[t] for j,t in zip(jr,tr) if cost[j,t]<1e6}
        rows = []
        wire = iter(f['world'])
        near, far = cfg['camera']['clip_near'], cfg['depth']['max_m']
        good_gt = np.isfinite(ground)&(ground>near)&(ground<far)
        for j,d in enumerate(dets):
            best = int(np.argmax(ious[j])) if names else None
            best_iou = float(ious[j,best]) if best is not None else 0.
            name = matched.get(j)
            witness = name or (names[best] if best_iou>=.5 else None)
            status = ('true' if name else
                      ('duplicate_detection' if d['class_name']==targets[witness]['class_name'] else 'wrong_class')
                       if witness else 'unresolved')
            rec = dict(stop=k,frame=f['frame_idx'],stamp_ns=stamp,det_index=j,predicted_class=d['class_name'],
                confidence=d['confidence'],mask=d['mask'],instance_gt=witness,best_iou=best_iou,
                matched_iou=float(ious[j,names.index(name)]) if name else None,status=status,
                truncated=d['truncated'],depth_pass=d['depth_filter_pass'],
                depth_reject_reason=d.get('reason'),valid_depth_ratio=d['valid_depth_ratio'])
            rows.append(rec)
            detections.append(rec)
            if not d['depth_filter_pass']:
                continue
            live_projection = next(wire)
            assert live_projection['class_name']==d['class_name']
            assert abs(live_projection['confidence']-d['confidence'])<1e-7
            if live_projection['xyz'] is None:
                wire_tf_missing.append(dict(stop=k,frame=f['frame_idx'],stamp_ns=stamp,
                                            class_name=d['class_name'],det_index=j))
                rec['wire_skip_reason']='live_projection_unavailable'
                continue
            support = None
            if name:
                support = erode_mask(masks[j],cfg['fusion']['mask_erode_ratio']) & gt_masks[name] & good_gt
                support &= np.isfinite(pred)&(pred>near)&(pred<far)
            for m, con in dbs.items():
                a,b = lock['models'][m]
                raw_z = a*d['depth_m']+b
                z = raw_z if m=='A' else float(np.clip(raw_z,*lock['output_clip_m']))
                pc = backproject_optical(d['u'],d['v'],z,*K)
                world = transform@pc+translation
                if m=='A':
                    assert np.allclose(world,live_projection['xyz'],atol=1e-9,rtol=0)
                    n_wire += 1
                obs = dict(class_name=d['class_name'],confidence=float(np.float32(d['confidence'])),
                    bbox_xyxy=list(arr(d['bbox_xyxy']).astype(np.float32)),truncated=d['truncated'],
                    depth_m=float(np.float32(z)),range_m=float(np.float32(np.linalg.norm(pc))),
                    valid_depth_ratio=float(np.float32(d['valid_depth_ratio'])),
                    p_cam=list(pc),p_world=world.tolist(),stop_index=k,frame_idx=f['frame_idx'],
                    yaw_rad=stop['command_yaw_rad'],stamp_ns=stamp)
                start=time.perf_counter()
                result=association.add_observation(con,scan_id,obs,cfg['assoc'],cfg['fusion'])
                spans[m]+=time.perf_counter()-start
                by_obs[m][result['obs_id']]=rec
                rec[m+'_obs_id']=result['obs_id']
                rec[m+'_initial_object_id']=result['object_id']
                rec[m+'_created']=result['created']
                rec[m+'_weight']=result['weight']
                if support is not None and support.any():
                    gt_z=float(np.median(ground[support]))
                    error=world-centers[name]
                    depths.append(dict(method=m,stop=k,frame=f['frame_idx'],stamp_ns=stamp,instance_gt=name,
                        z_m=z,gt_z_m=gt_z,pixels=int(support.sum()),abs_error_m=abs(z-gt_z),
                        absrel=abs(z-gt_z)/gt_z,bias_m=z-gt_z,xy_m=float(np.linalg.norm(error[:2])),
                        xyz_m=float(np.linalg.norm(error)),clipped=z!=raw_z))
            if rec['A_initial_object_id'] is None:
                rec['A_association_note']='no_nearby_object_and_below_create_conf'
            if rec['B_initial_object_id'] is None:
                rec['B_association_note']='no_nearby_object_and_below_create_conf'
        assert next(wire,None) is None

        vis_img = cv2.cvtColor(image,cv2.COLOR_RGB2BGR)
        for name,mask in gt_masks.items():
            yy,xx = np.where(mask)
            if len(yy):
                edge=xx.min()==0 or xx.max()==1279 or yy.min()==0 or yy.max()==719
                visibility_state = 'edge_cut_gt' if edge else 'visible'
                bbox = [int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())]
                assert (mask & good_gt).any()
                cv2.rectangle(vis_img,tuple(bbox[:2]),tuple(bbox[2:]),(0,225,255),2)

            else:
                visibility_state = box_projection(centers[name],targets[name],transform,translation,K)
                bbox = None
            evidence = [d for d in rows if d['instance_gt']==name]
            if bbox:
                true = [d for d in evidence if d['status']=='true']
                cause = 'wrong class' if any(d['status']=='wrong_class' for d in evidence) else 'missed'
                if true:
                    cause = 'depth rejected' if not true[0]['depth_pass'] else 'truncated' if true[0]['truncated'] else 'correct'
                color = (0,225,255) if cause == 'correct' else (35,125,255)
                text_y = max(27,bbox[1]-6)
                text_x = min(1010,bbox[0])
                cv2.putText(vis_img,f'{name} {cause}',(text_x,text_y),cv2.FONT_HERSHEY_SIMPLEX,.65,color,2)
                if cause!='correct':
                    issue_frames.setdefault((k,name,cause),f['frame_idx'])
            near_evidence = [(d['class_name'],float(ious[j,names.index(name)]),d['confidence'])
                             for j,d in enumerate(dets) if name in names and ious[j,names.index(name)]>0]
            best_overlap = max(near_evidence,key=lambda r:r[1],default=(None,0.,None))
            visibility.append(dict(stop=k,frame=f['frame_idx'],stamp_ns=stamp,instance_gt=name,
                visibility=visibility_state,visible_pixels=int(len(xx)),gt_valid_pixels=int((mask&good_gt).sum()),
                gt_bbox=bbox,detected=any(d['status']=='true' for d in evidence),
                wrong_class=sum(d['status']=='wrong_class' for d in evidence),
                duplicate_detection=sum(d['status']=='duplicate_detection' for d in evidence),
                passed_depth=sum(d['status']=='true' and d['depth_pass'] for d in evidence),
                truncated=sum(d['status']=='true' and d['truncated'] for d in evidence),
                best_overlap_class=best_overlap[0],best_overlap_iou=best_overlap[1],best_overlap_conf=best_overlap[2]))
        if any(key[0]==k and idx==f['frame_idx'] for key,idx in issue_frames.items()):
            assert cv2.imwrite(str(root/f'issue_stop_{k:02d}_frame_{f["frame_idx"]}.jpg'),vis_img)
        if f['frame_idx']==0:
            cv2.putText(vis_img,f'Stop {k} | yaw {math.degrees(yaw):.1f} deg | GT yellow',(16,36),
                        cv2.FONT_HERSHEY_SIMPLEX,.8,(0,225,255),2)
            thumb=cv2.resize(vis_img,(640,360),interpolation=cv2.INTER_AREA)
            assert cv2.imwrite(str(root/f'stop_{k:02d}.jpg'),thumb)
            contact.append(thumb)
assert cv2.imwrite(str(root/'all_stops.jpg'),np.vstack([np.hstack(contact[i:i+4]) for i in (0,4)]))
assert n_wire==len(live_obs)


branches, audit_objects, query_audit = {}, [], {}
for m,con in dbs.items():
    t=time.perf_counter()
    result=association.run_association_pass(con,scan_id,cfg['assoc'])
    db.finish_scan(con,scan_id)
    spans[m]+=time.perf_counter()-t
    assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert con.execute('PRAGMA foreign_key_check').fetchone() is None
    db_obs = [dict(r) for r in con.execute('SELECT * FROM observations ORDER BY obs_id')]
    objects = [dict(r) for r in con.execute('SELECT * FROM objects ORDER BY object_id')]
    assert len(db_obs)==n_wire
    assert [r['stamp_ns'] for r in db_obs]==[r['stamp_ns'] for r in live_obs]
    if m=='A':
        for expected,actual in [(live_obs,db_obs),(live_objects,objects)]:
            assert len(expected)==len(actual)
            for e,a in zip(expected,actual,strict=True):
                for key,x in e.items():
                    if key in ('created_at','updated_at'):
                        continue
                    y=a[key]
                    if isinstance(x,float):
                        assert math.isclose(x,y,abs_tol=2e-7,rel_tol=1e-7),(key,x,y)
                    else:
                        assert x==y,(key,x,y)
    members=defaultdict(list)
    for obs in db_obs:
        rec=by_obs[m][obs['obs_id']]
        rec[m+'_final_object_id']=obs['object_id']
        members[obs['object_id']].append(rec)
    valid = defaultdict(list)
    for o in objects:
        evidence=members[o['object_id']]
        witnesses=Counter(d['instance_gt'] for d in evidence if d['instance_gt'])
        truth=Counter(d['instance_gt'] for d in evidence if d['status']=='true')
        pure=len(truth)==1 and sum(truth.values())==len(evidence)
        name=next(iter(truth)) if pure else None
        note='clean_instance' if pure else 'impure_gt_evidence' if witnesses else 'out_of_scope_or_unresolved'
        if o['object_id'] in {pair[0] for pair in result['merged_pairs']}:
            disposition='merged_away'
        elif o['status']=='rejected':
            disposition='min_obs' if o['n_obs']<cfg['assoc']['min_obs'] else 'only_truncated'
        else:
            disposition=o['status']
        delta=arr([o['x'],o['y'],o['z']])-centers[name] if name else None
        confs=[d['confidence'] for d in evidence]
        conf_sum_error=o['conf_sum']-sum(confs) if confs else None
        conf_mean_error=o['conf_mean']-float(np.mean(confs)) if confs else None
        row=dict(method=m,**o,disposition=disposition,semantic_status=note,instance_gt=name,
            xy_m=float(np.linalg.norm(delta[:2])) if name else None,
            xyz_m=float(np.linalg.norm(delta)) if name else None,obs_linked=len(evidence),
            instance_votes=dict(witnesses),true_votes=dict(truth),
            conf_sum_error=conf_sum_error,conf_mean_error=conf_mean_error)
        audit_objects.append(row)
        if o['status']=='confirmed' and pure:
            valid[name].append(row)
    primary={}
    for name, candidates in valid.items():
        primary[name]=max(candidates,key=lambda o:(o['n_obs'],o['weight_sum'],-o['object_id']))
    confirmed=[o for o in audit_objects if o['method']==m and o['status']=='confirmed']
    dup=sum(len(group)-1 for group in valid.values())
    wrong=sum(o['semantic_status']=='impure_gt_evidence' for o in confirmed)
    scoped=sum(o['semantic_status']!='out_of_scope_or_unresolved' for o in confirmed)
    assert scoped==len(primary)+wrong+dup
    unresolved=[o for o in confirmed if o['semantic_status']=='out_of_scope_or_unresolved' and o['class_name'] in classes]
    localized=sum(o['xy_m'] < cfg['eval']['match_radius_m'] for o in primary.values())
    branch_depth=[d for d in depths if d['method']==m]
    queries_at_base=queries.query_objects(con,scan_id,center_xy=tuple(cfg['camera']['base_xyz'][:2]))
    assert {r['object_id'] for r in queries_at_base}=={o['object_id'] for o in confirmed}
    assert not queries.query_objects(con,scan_id,'_nonexistent_')
    approaches=[]
    for obj in queries_at_base:
        key=obj['object_id']
        cname=obj['class_name']
        by_class=queries.query_objects(con,scan_id,cname)
        assert {r['object_id'] for r in by_class}=={r['object_id'] for r in queries_at_base if r['class_name']==cname}
        xy=(obj['x'],obj['y'])
        nearest=queries.nearest_object(con,scan_id,*xy,class_name=cname)
        assert math.dist((nearest['x'],nearest['y']),xy)<1e-9
        assert key in {r['object_id'] for r in queries.objects_in_radius(con,scan_id,*xy,1e-7,cname)}
        base=tuple(cfg['camera']['base_xyz'][:2])
        standoff=cfg['approach']['standoff_m']
        approach=queries.get_approach_point(con,key,base,standoff)
        p=(approach['x'],approach['y'])
        delta=math.dist(xy,p)
        assert math.isclose(delta,min(standoff,math.dist(xy,base)),abs_tol=1e-8)
        assert math.isclose(math.dist(base,p)+delta,math.dist(base,xy),abs_tol=1e-8)
        heading=math.atan2(xy[1]-p[1],xy[0]-p[0])
        assert math.isclose(math.cos(approach['yaw_rad']-heading),1,abs_tol=1e-8)
        approaches.append(dict(object_id=key,point=approach,standoff_measured_m=delta))
    assert queries.get_approach_point(con,-1,(0,0)) is None
    query_audit[m]={'rows':queries_at_base,'approaches':approaches,'checked_filters':True}
    def mean_metric(key):
        return float(np.mean([d[key] for d in branch_depth])) if branch_depth else None
    branches[m]=dict(association=result,final_confirmed=len(confirmed),scoped_confirmed=scoped,
        unique_clean_instances=len(primary),localized_under_match_radius=localized,
        wrong_confirmed=wrong,duplicate_confirmed=dup,
        unresolved_target_predictions=[o['object_id'] for o in unresolved],
        recall=len(primary)/4,localized_recall=localized/4,
        precision=len(primary)/scoped if scoped else None, localized_precision=localized/scoped if scoped else None,
        precision_conservative=len(primary)/(scoped+len(unresolved)) if scoped+len(unresolved) else None,
        duplicate_rate=dup/scoped if scoped else None,
        xy_m=geom_summary([o['xy_m'] for o in primary.values()]),xyz_m=geom_summary([o['xyz_m'] for o in primary.values()]),
        depth=dict(n=len(branch_depth),absrel=mean_metric('absrel'),mae_m=mean_metric('abs_error_m'),bias_m=mean_metric('bias_m'),
                   clipped=sum(d['clipped'] for d in branch_depth)),
        primary=primary,association_sqlite_s=spans[m])
    con.close()
for m in 'AB':
    by_oid={o['object_id']:o for o in audit_objects if o['method']==m}
    for row in detections:
        obj=by_oid.get(row.get(m+'_final_object_id'))
        row[m+'_final_status']=obj['status'] if obj else None
        if obj:
            row[m+'_association_note']=obj['disposition']
all_targets={}
for name in targets:
    v=[r for r in visibility if r['instance_gt']==name]
    linked=[r for r in detections if r['instance_gt']==name and r['status']=='true']
    all_targets[name]=dict(
        visible=sum(r['visible_pixels']>0 for r in v),true_detections=sum(r['detected'] for r in v),
        false_class=sum(r['wrong_class'] for r in v),
        missed_visible=sum(r['visible_pixels']>0 and not r['detected'] for r in v),
        depth_rejected=sum(not r['depth_pass'] for r in linked),
        truncated=sum(r['truncated'] for r in linked),
        valid_observations=sum(r['depth_pass'] for r in linked),
        visible_stops=sorted({r['stop'] for r in v if r['visible_pixels']}),
        visibility_status=dict(Counter(r['visibility'] for r in v)))
csvfile('capture_audit.csv',frame_rows)
csvfile('detection_audit.csv',detections)
csvfile('visibility_by_frame.csv',visibility)
csvfile('association_audit.csv',audit_objects)
csvfile('depth_scores.csv',depths)
write('query_audit.json',query_audit)
write('summary.json',dict(scan_id=scan_id,frames=len(frame_rows),live_observations=n_wire,
    a_matches_live=True,wire_tf_missing=wire_tf_missing,bbox_blob_columns=sum(isinstance(o[k],bytes) for o in live_obs
        for k in ('bbox_x1','bbox_y1','bbox_x2','bbox_y2')),targets=all_targets,branches=branches,timings_ms={
        key:sum(r[key] for r in frame_rows) for key in ('yolo_ms','depth_ms','post_ms')},
    max_joint_skew_ms=max(abs(r['joint_skew_ns']) for r in frame_rows)/1e6,
    max_command_error_deg=max(r['command_error_deg'] for r in frame_rows),
    max_tf_joint_error_deg=max(r['tf_joint_error_deg'] for r in frame_rows)))
print(f'{scan_id}: verified A against live, {len(frame_rows)} frames, {n_wire} observations')

