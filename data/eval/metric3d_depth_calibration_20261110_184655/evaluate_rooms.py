import csv, hashlib, json, math, sys, time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import torch
import yaml

root=Path(__file__).resolve().parent
repo=root.parents[2]
baseline=root.parent/'kitchen_reference_20261110_134600_sync'
sys.path.insert(0,str(repo/'src/perception'))
from perception.core.depth import Metric3DDepth
from perception.core.fusion import erode_mask, object_depth, is_truncated
from perception.core.geometry import backproject_optical, optical_to_world
from perception.core.yolo import YoloeDetector

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(path,obj):
    path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csvfile(path,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

lock=root/'locked.json'
assert sha(lock)==(root/'locked.sha256').read_text().strip()
locked=read(lock)
cfg=yaml.safe_load((baseline/'config.yaml').read_text())
prompt=yaml.safe_load((baseline/'classes.yaml').read_text())['classes']
cam,dc,fc,yc=(cfg[k] for k in ('camera','depth','fusion','yoloe'))
near,far=cam['clip_near'],dc['max_m']
for info in read(baseline/'manifest.json')['model_checkpoints']:
    assert sha(Path(info['original_path']))==info['sha256']
torch.set_num_threads(1)
assert torch.cuda.is_available()
cache=Path.home()/'.cache/torch/hub'
model=torch.hub.load(str(cache/'yvanyin_metric3d_main'),'metric3d_vit_small',source='local',pretrain=False)
weights=torch.load(cache/'checkpoints/metric_depth_vit_small_800k.pth',map_location='cpu',weights_only=True)
keys=model.load_state_dict(weights['model_state_dict'],strict=False)
assert not keys.unexpected_keys and set(keys.missing_keys)<={'depth_model.encoder.mask_token'}
del weights
with patch('torch.hub.load',return_value=model):
    estimator=Metric3DDepth('cuda:0',tuple(dc['input_size']),dc['fp16'],dc['canonical_focal'],dc['max_m'])
detector=YoloeDetector(prompt,str(repo/(yc['model']+'.pt')),yc['conf'],yc['iou'],yc['imgsz'],'cuda:0')
print('Production models ready; coefficient lock',sha(lock),flush=True)

def norm(x):
    return float(np.linalg.norm(x))
def valid(z):
    return np.isfinite(z)&(z>near)&(z<far)
def tf(point,frame):
    return optical_to_world(point,frame['optical_heading_rad'],frame['rig_pose_observed'][0],(.05,0,0))
def apply(z,method):
    a,b=locked['models'][method]
    x=a*z+b
    return np.clip(x,*locked['output_clip_m'])
def representative(array,mask):
    return object_depth(array,mask,fc['mask_erode_ratio'],fc['min_valid_ratio'],near,far)
def measure(pred,gt):
    e=pred-gt
    return float(np.mean(np.abs(e))),float(np.mean(np.abs(e)/gt)),float(np.mean(e))
def evidence(frame,lab,gt,rgb):
    support=lab[...,2]==frame['label']
    y,x=np.where(support)
    if not len(x):
        return {'target_pixels':0,'target_luma_median':None}
    return {'target_pixels':len(x),'target_luma_median':float(np.median(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)[support])),
            'target_bbox':[int(x.min()),int(y.min()),int(x.max()),int(y.max())],
            'gt_support_fraction':float(valid(gt[support]).mean())}

def summarize(rows, methods='ABC'):
    groups=[]
    for method in methods:
        entries=[r for r in rows if r['method']==method]
        if not entries:
            continue
        base={(r['room'],r['file']):r for r in rows if r['method']=='A'}
        delta=np.array([r['xy_m']-base[r['room'],r['file']]['xy_m'] for r in entries])
        result={'method':method,'n':len(entries),'xy_better':int((delta < -1e-6).sum()),
                'xy_worse':int((delta > 1e-6).sum()),'xy_equal':int((np.abs(delta)<=1e-6).sum())}
        for f in ('representative_abs_error_m','representative_absrel','representative_bias_m',
                  'dense_mae_m','dense_absrel','dense_bias_m','xy_m','xyz_m'):
            data=np.array([r[f] for r in entries])
            result.update({f+'_mean':float(data.mean()),f+'_median':float(np.median(data)),f+'_p90':float(np.quantile(data,.90))})
        for metric in ('representative_abs_error_m','xyz_m'):
            dd=np.array([r[metric]-base[r['room'],r['file']][metric] for r in entries])
            result[metric+'_better']=int((dd< -1e-6).sum())
            result[metric+'_worse']=int((dd> 1e-6).sum())
        result['clipped_representative']=sum(r['rep_clipped'] for r in entries)
        result['clipped_pixels']=sum(r['dense_clipped_pixels'] for r in entries)
        groups.append(result)
    return groups

def run_room(name,folder):
    index=read(folder/'capture_index.json')
    design=read(folder/'design.json')
    assert len({r['stamp_ns'] for r in index})==len(index)
    output=folder/'outputs'
    output.mkdir(exist_ok=False)
    details,scores=[],[]
    previews={}
    for frame in index:
        with np.load(folder/'frames'/frame['file'],allow_pickle=False) as f:
            assert int(f['stamp_ns'])==frame['stamp_ns']
            rgb,gt,lab,K=[f[x] for x in ('rgb','gt_depth','labels_rgb','K')]
        assert rgb.shape==lab.shape==(cam['height'],cam['width'],3)
        assert gt.shape==rgb.shape[:2] and gt.dtype==np.float32
        assert np.allclose(K,[914.0147013559828,914.0147013559828,640,360],atol=1e-5,rtol=0)
        cls=frame['target'].removesuffix('_1')
        d={'room':name,'file':frame['file'],'target':cls,'stamp_ns':frame['stamp_ns'],
           'distance_m':frame['distance_m'],'relative_yaw_deg':frame['relative_yaw_deg'],
           'issues':'|'.join(frame['issues']),**evidence(frame,lab,gt,rgb)}
        target=(lab[...,2]==frame['label']) & ((lab[...,0]>0)|(lab[...,1]>0))
        pred=estimator.estimate(rgb,K[0])
        dets=detector.detect(rgb)
        pred_data={'pred_depth':pred}
        candidates=[]
        for i,det in enumerate(dets):
            mask=det['mask']
            pred_data[f'mask_{i}']=np.packbits(mask,axis=1)
            denom=np.count_nonzero(mask|target)
            iou=np.count_nonzero(mask&target)/denom if denom else 0.
            candidates.append((iou,i,det))
        np.savez_compressed(output/frame['file'],**pred_data)
        put(output/(Path(frame['file']).stem+'_detections.json'),[
            {'mask':f'mask_{i}','iou':iou,'class_name':det['class_name'],'confidence':det['confidence'],
             'bbox_xyxy':det['bbox_xyxy']} for iou,i,det in candidates])
        best=max(candidates,key=lambda r:r[0],default=(0,None,None))
        correct=[x for x in candidates if x[0]>=.5 and x[2]['class_name']==cls]
        wrong=[x for x in candidates if x[0]>=.5 and x[2]['class_name']!=cls]
        d.update({'detections_all':len(dets),'best_class':best[2]['class_name'] if best[2] else None,
                  'best_iou':best[0],'correct_instance':bool(correct),'wrong_class_on_instance':len(wrong),
                  'missed_visible_instance':bool(target.any() and not correct),'geometry_scored':False})
        details.append(d)
        if not frame['issues'] and cls not in previews and target.any():
            vis=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
            x0,y0,x1,y1=d['target_bbox']
            cv2.rectangle(vis,(x0,y0),(x1,y1),(30,230,255),2)
            cv2.putText(vis,f'{name} | {cls} | {frame["distance_m"]:.2f} m', (18,35),
                        cv2.FONT_HERSHEY_SIMPLEX,.8,(30,230,255),2,cv2.LINE_AA)
            previews[cls]=cv2.resize(vis,(640,360),interpolation=cv2.INTER_AREA)
        elif cls not in previews and target.any():
            pass
        if not correct:
            d['not_scored_reason']='no correct instance'
        elif frame['issues']:
            d['not_scored_reason']='capture QA'
        else:
            iou,_,det=max(correct,key=lambda r:r[0])
            r=representative(pred,det['mask'])
            d['confidence']=det['confidence'];d['truncated']=is_truncated(det['bbox_xyxy'],rgb.shape[1],rgb.shape[0],fc['border_px'])
            d['valid_depth_ratio']=r['valid_ratio']
            support=erode_mask(det['mask'],fc['mask_erode_ratio'])&target&valid(pred)&valid(gt)
            if r['reason'] or not support.any() or d['truncated']:
                d['not_scored_reason']=r['reason'] or ('truncated detection' if d['truncated'] else 'no shared depth support')
            else:
                d['geometry_scored']=True
                u,v=r['u'],r['v']
                zpred=r['depth_m']
                zg=float(np.median(gt[support]))
                gt_vec=gt[support].astype(float)
                pred_vec=pred[support].astype(float)
                observed,quat=frame['target_pose_observed']
                prior=Rotation.from_euler('xyz',design['props'][frame['target']]['pose_rpy'])
                actual=Rotation.from_quat(quat)
                center=np.array(observed)+(actual*prior.inv()).apply(design['props'][frame['target']]['center_offset'])
                yy,xx=np.where(support)
                j=int(np.argmin((xx-u)**2+(yy-v)**2))
                gt_surface=tf(backproject_optical(xx[j],yy[j],float(gt[yy[j],xx[j]]),*K),frame)
                for m,(a,b) in locked['models'].items():
                    raw_z=a*zpred+b
                    z=float(apply(zpred,m))
                    xyzw=tf(backproject_optical(u,v,z,*K),frame)-center
                    adjusted=apply(pred_vec,m)
                    mae,ar,bias=measure(adjusted,gt_vec)
                    scores.append({'room':name,'file':frame['file'],'target':cls,'method':m,
                                   'distance_m':frame['distance_m'],'relative_yaw_deg':frame['relative_yaw_deg'],
                                   'z_pred_m':zpred,'z_scored_m':z,'z_gt_median_m':zg,
                                   'representative_abs_error_m':abs(z-zg),'representative_absrel':abs(z-zg)/zg,
                                   'representative_bias_m':z-zg,'dense_mae_m':mae,'dense_absrel':ar,'dense_bias_m':bias,
                                   'xy_m':norm(xyzw[:2]),'xyz_m':norm(xyzw),
                                   'gt_surface_to_center_xy_m':norm((gt_surface-center)[:2]),
                                   'gt_surface_to_center_xyz_m':norm(gt_surface-center),'scored_pixels':len(gt_vec),
                                   'rep_clipped':not math.isclose(raw_z,z,abs_tol=1e-12),
                                   'dense_clipped_pixels':int(np.count_nonzero(adjusted!=a*pred_vec+b))})
        print(name,frame['file'],'correct',bool(correct),'geometry',d['geometry_scored'],frame['issues'],flush=True)
    csvfile(folder/'detection.csv',details)
    if scores: csvfile(folder/'scores.csv',scores)
    if previews:
        ordered=list(previews.values())
        blank=np.zeros_like(ordered[0])
        while len(ordered)<4: ordered.append(blank)
        cv2.imwrite(str(folder/'render.jpg'),np.vstack((np.hstack(ordered[:2]),np.hstack(ordered[2:4]))))
    group=[]
    for k in ('target','distance_m','relative_yaw_deg'):
        for v in sorted({r[k] for r in scores}):
            group.extend({k:v,'group':k,**r} for r in summarize([r for r in scores if r[k]==v]))
    if group: csvfile(folder/'by_condition.csv',group)
    orig_scores=[s for s in scores if s['method']=='A']
    return {'room':name,'planned':16,'captured':len(index),'visible':sum(d['target_pixels']>0 for d in details),
            'clear_capture':sum(not d['issues'] for d in details),'true_detection':sum(d['correct_instance'] for d in details),
            'missed_visible':sum(d['missed_visible_instance'] for d in details),'wrong_class':sum(d['wrong_class_on_instance'] for d in details),
            'scored':len(orig_scores),'capture_issues':dict(Counter(i for row in index for i in row['issues'])),
            'not_scored_reasons':dict(Counter(d['not_scored_reason'] for d in details if 'not_scored_reason' in d)),
            'methods':summarize(scores)}

result=[]
for spec in sys.argv[1:]:
    name,folder=spec.split('=',1)
    path=root/folder
    deadline=time.monotonic()+440
    while not (path/'capture_exit.txt').exists() and time.monotonic()<deadline:time.sleep(2)
    if (path/'capture_index.json').exists():
        result.append(run_room(name,path))
    else:
        result.append({'room':name,'status':'NOT TESTED','planned':16,'captured':0,'log':folder+'/capture.log'})
    put(root/'holdout_summary.json',result)
print('Evaluation complete',flush=True)
