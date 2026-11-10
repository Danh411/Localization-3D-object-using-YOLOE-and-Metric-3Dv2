import csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
import sys
import cv2,numpy as np
from scipy.spatial.transform import Rotation
import yaml

root=Path(__file__).resolve().parent
repo=root.parents[2]
sys.path.insert(0,str(repo/'src/perception'))
from perception.core.geometry import backproject_optical
from perception.core.fusion import erode_mask

def read(path): return json.loads(path.read_text())
def rows(path):
    with path.open(newline='',encoding='utf-8') as f:
        return list(csv.DictReader(f))
def csvfile(name,data):
    fields=list(dict.fromkeys(k for r in data for k in r))
    with (root/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(data)
def put(name,data):
    (root/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def real(row,keys):
    return {**row,**{k:float(row[k]) for k in keys}}

lock=root/'crossworld_locked.json'
assert hashlib.sha256(lock.read_bytes()).hexdigest()==(root/'crossworld_locked.sha256').read_text().strip()
lock=read(lock)
clip=lock['clip']
models=lock['models']
def coeffs(name):
    return {'original':[1.,0.],**{k:models[k]['B'] for k in models},
            'linear_local':models[name]['C']}
metrics=('abs_error_m','absrel','bias_m','xy_m','xyz_m')
dense_metrics=('mae_m','absrel','bias_m','ratio_median')
scores=[real(d,metrics) for d in rows(root/'holdout_scores_external.csv')]
dense=[real(d,dense_metrics) for d in rows(root/'holdout_dense_gt_mask.csv')]
coverage=rows(root/'holdout_coverage_external.csv')
folder=root/'kitchen_final'
summary=read(folder/'summary.json')
assert summary['a_matches_live'] and summary['frames']==24
gt={o['model_name']:o for o in yaml.safe_load((folder/'gt.yaml').read_text())['objects']
    if 'semantic_label' in o}
cfg=yaml.safe_load((folder/'config.yaml').read_text())
wanted={'bottle_1','cup_1','laptop_1'}
detection=rows(folder/'detection_audit.csv')
for p in sorted(folder.glob('audit_scan_*.json')):
    s=read(p)
    for f in s['frames']:
        meta=dict(world='kitchen',file=f['file'],stamp_ns=f['stamp_ns'],stop=s['stop_index'],frame=f['frame_idx'])
        with np.load(folder/'frames'/f['file'],allow_pickle=False) as z:
            pred,ground,lab=[z[k] for k in ('pred_depth','gt_depth','labels_rgb')]
            K=f['K']
            for target in sorted(wanted):
                ref=gt[target]
                mask=(lab[...,2]==ref['semantic_label'])&((lab[...,0]>0)|(lab[...,1]>0))
                if not mask.any():
                    continue
                yy,xx=np.where(mask)
                cut=xx.min()<8 or xx.max()>1271 or yy.min()<8 or yy.max()>711
                ds=[d for d in detection if int(d['stamp_ns'])==f['stamp_ns'] and d['instance_gt']==target]
                true=next((d for d in ds if d['status']=='true'),None)
                note='capture_QA' if cut else 'no_correct_instance' if not true else ''
                if true and not note:
                    if true['truncated']=='True' or true['depth_pass']!='True':
                        note='truncated' if true['truncated']=='True' else 'depth_filter'
                coverage.append(dict(**meta,target=target,visible=True,correct=bool(true),
                    wrong_classes=[d['predicted_class'] for d in ds if d['status']=='wrong_class'],missed=not true,excluded_reason=note))
                if cut:
                    continue
                kernel=max(3,int(round(.05*np.sqrt(mask.sum()))))
                eroded=cv2.erode(mask.astype(np.uint8),np.ones((kernel,kernel),np.uint8))>0
                valid=np.isfinite(ground)&np.isfinite(pred)&(ground>.1)&(ground<10)&(pred>.1)&(pred<10)
                x,y=pred[eroded&valid].astype(float),ground[eroded&valid].astype(float)
                if len(x):
                    for method,(a,b) in coeffs('kitchen').items():
                        raw=a*x+b
                        scored=raw if method=='original' else np.clip(raw,*clip)
                        e=scored-y
                        dense.append(dict(**meta,method=method,target=target,pixels=len(x),ratio_median=float(np.median(y/x)),
                             mae_m=float(np.abs(e).mean()),absrel=float((np.abs(e)/y).mean()),bias_m=float(e.mean()),
                             clipped=int(np.count_nonzero(scored!=raw))))
                if note:
                    continue
                d=f['detections'][int(true['det_index'])]
                support=erode_mask(np.unpackbits(z[d['mask']],axis=1,count=1280).astype(bool),cfg['fusion']['mask_erode_ratio'])&mask&valid
                assert support.any()
                zg=float(np.median(ground[support]))
                rot=Rotation.from_quat(f['tf']['quaternion'])
                t=np.asarray(f['tf']['translation'])
                center=np.array([ref[k] for k in 'xyz'])
                for method,(a,b) in coeffs('kitchen').items():
                    raw=a*d['depth_m']+b
                    value=raw if method=='original' else float(np.clip(raw,*clip))
                    pw=rot.apply(backproject_optical(d['u'],d['v'],value,*K))+t
                    error=pw-center
                    scores.append(dict(**meta,method=method,target=target,z_pred_m=d['depth_m'],z_gt_m=zg,z_scored_m=value,
                        abs_error_m=abs(value-zg),absrel=abs(value-zg)/zg,bias_m=value-zg,xy_m=float(np.linalg.norm(error[:2])),
                        xyz_m=float(np.linalg.norm(error)),mask_iou=float(true['matched_iou']),confidence=d['confidence'],
                        clipped=raw!=value))
csvfile('holdout_scores.csv',scores)
csvfile('holdout_dense_all.csv',dense)
csvfile('holdout_coverage.csv',coverage)
base={(r['world'],r['target'],r['file']):r for r in scores if r['method']=='original'}
def aggregate(group):
    stat={k:float(np.mean([r[k] for r in group])) for k in metrics}
    for k in ('xy_m','xyz_m'):
        stat[k+'_median']=float(np.median([r[k] for r in group]))
        stat[k+'_p90']=float(np.quantile([r[k] for r in group],.9))
    for k in ('abs_error_m','xy_m','xyz_m'):
        diff=[r[k]-base[r['world'],r['target'],r['file']][k] for r in group]
        stat[k+'_better']=sum(x<-1e-8 for x in diff)
        stat[k+'_worse']=sum(x>1e-8 for x in diff)
    return dict(n=len(group),**stat)
grouped=[]
matrix=[]
dense_groups=[]
for world in ('kitchen','aws','tiffany'):
    for method in coeffs(world):
        for target in ('all',*sorted(wanted)):
            group=[r for r in scores if r['world']==world and r['method']==method and (target=='all' or r['target']==target)]
            result=dict(world=world,method=method,target=target,**(aggregate(group) if group else {'n':0}))
            grouped.append(result)
            if target=='all' and method in models:
                matrix.append(result)
            dd=[r for r in dense if r['world']==world and r['method']==method and (target=='all' or r['target']==target)]
            if dd:
                dense_groups.append(dict(world=world,method=method,target=target,n=len(dd),
                    **{k:float(np.mean([r[k] for r in dd])) for k in dense_metrics}))
for world in ('aws','tiffany'):
    for axis in ('distance_m','relative_yaw_deg','target'):
        for value in sorted({r[axis] for r in dense if r['world']==world}):
            for method in coeffs(world):
                group=[r for r in dense if r['world']==world and r['method']==method and r[axis]==value]
                if group:
                    dense_groups.append(dict(world=world,method=method,axis=axis,group=value,n=len(group),
                        ratio_min=float(min(r['ratio_median'] for r in group)),ratio_max=float(max(r['ratio_median'] for r in group)),
                        **{k:float(np.mean([r[k] for r in group])) for k in dense_metrics}))
csvfile('holdout_summary.csv',grouped)
csvfile('crossworld_matrix.csv',matrix)
csvfile('holdout_dense_summary.csv',dense_groups)

final=[]
for target,v in summary['targets'].items():
    a=summary['branches']['A']['primary'].get(target)
    b=summary['branches']['B']['primary'].get(target)
    final.append(dict(target=target,**v,A_confirmed=bool(a),B_confirmed=bool(b),
        A_XY_m=a['xy_m'] if a else None,B_XY_m=b['xy_m'] if b else None,
        A_XYZ_m=a['xyz_m'] if a else None,B_XYZ_m=b['xyz_m'] if b else None,
        A_conf_mean=a['conf_mean'] if a else None,B_conf_mean=b['conf_mean'] if b else None))
csvfile('kitchen_fullscan_summary.csv',final)
new_observations=rows(folder/'association_audit.csv')
for entry in new_observations:
    if int(entry['obs_linked'])>0:
        assert abs(float(entry['conf_sum_error']))<1e-10
        assert abs(float(entry['conf_mean_error']))<1e-10
query=read(folder/'query_audit.json')
live=read(folder/'query_live.log')
assert {r['object_id'] for r in query['A']['rows']}=={r['object_id'] for r in live}
put('batch_summary.json',dict(grouped=grouped,matrix=matrix,dense=dense_groups,kitchen=summary,final=final,
    coverage={world:dict(captured=sum(r['world']==world for r in coverage),
      visible=sum(r['world']==world and str(r['visible'])=='True' for r in coverage),
      correct=sum(r['world']==world and str(r['correct'])=='True' for r in coverage),
      excluded=dict(Counter(r['excluded_reason'] for r in coverage if r['world']==world and r['excluded_reason'])))
      for world in models}))
print('Batch summary generated and confidence/query parity verified')

