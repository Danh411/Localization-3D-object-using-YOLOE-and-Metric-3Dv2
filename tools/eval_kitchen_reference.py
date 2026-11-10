import argparse
import csv
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation
import yaml

parser = argparse.ArgumentParser(description='Evaluate a captured kitchen reference dataset with instance GT.')
parser.add_argument('dataset', type=Path, help='Directory containing the frozen scan, SQLite and audit files')
root = parser.parse_args().dataset.resolve()
texture_baseline=root.parent/'kitchen_textured_20261110_132916'
frozen_inputs=('config.yaml','classes.yaml','gt.yaml','kitchen_controlled.sdf')
same_scene_configuration=(all((root/name).read_bytes()==(texture_baseline/name).read_bytes() for name in frozen_inputs)
                          if all((texture_baseline/name).is_file() for name in frozen_inputs) else None)
cfg = yaml.safe_load((root/'config.yaml').read_text())
targets = {obj['semantic_label']: obj for obj in yaml.safe_load((root/'gt.yaml').read_text())['objects']
           if 'semantic_label' in obj}
assert len(targets) == 4
classes = {obj['class_name'] for obj in targets.values()}
mesh_centers=json.loads((root/'mesh_centers.json').read_text())
audit = sorted((json.loads(p.read_text()) for p in root.glob('audit_scan_*.json')),key=lambda s:s['stop_index'])
assert [s['stop_index'] for s in audit] == list(range(8))
assert all(len(s['frames'])==3 for s in audit)
assert all(f['depth_exact_stamp'] and f['label_exact_stamp'] for s in audit for f in s['frames'])
scan_id = audit[0]['scan_id']
path = root/'db'/f'{scan_id}.sqlite'
with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
    conn.row_factory = sqlite3.Row
    assert conn.execute('pragma integrity_check').fetchone()[0]=='ok'
    scan = dict(conn.execute('select * from scans').fetchone())
    assert scan['finished_at'] is not None
    rows = [dict(row) for row in conn.execute('select * from observations')]
    objects = [dict(row) for row in conn.execute('select * from objects')]
db_frames = defaultdict(list)
for row in rows:
    db_frames[row['stop_index'],row['frame_idx'],row['stamp_ns']].append(row)
object_status = {obj["object_id"]:obj["status"] for obj in objects}
by_object = defaultdict(list)
measurements, per_detection, frame_rows, used_db_ids = [], [], [], set()

def norm(v):
    return float(np.linalg.norm(v))

def camera_point(u, v, z, K):
    fx, fy, cx, cy = K
    return np.array([(u-cx)*z/fx,(v-cy)*z/fy,z])

def metrics(mask, predicted, ground):
    valid_gt = mask & np.isfinite(ground) & (ground > 0)
    ok = valid_gt & np.isfinite(predicted) & (predicted > 0)
    count = int(ok.sum())
    invalid = int(valid_gt.sum())-count
    if not count:
        return {'pixels':0,'invalid_predictions':invalid}
    a,b = predicted[ok].astype(float),ground[ok].astype(float)
    e = a-b
    return {'pixels':count,'invalid_predictions':invalid,'mae_m':float(np.abs(e).mean()),
            'rmse_m':float(np.sqrt((e**2).mean())),'bias_m':float(e.mean()),
            'absrel':float((np.abs(e)/b).mean()),'median_gt_m':float(np.median(b)),
            'median_pred_m':float(np.median(a))}

for stop in audit:
    i=stop['stop_index']
    for frame in stop['frames']:
        index,stamp=frame['frame_idx'],frame['stamp_ns']
        fkey=(i,index,stamp)
        detections=frame['detections']
        packet=root/'frames'/frame['file']
        with np.load(packet,allow_pickle=False) as archive:
            data={key:archive[key] for key in archive.files}
        h,w=data['rgb'].shape[:2]
        masks=[np.unpackbits(data[d['mask']],axis=1,count=w).astype(bool) for d in detections]
        visible=[]
        if 'labels_rgb' in data:
            lab=data['labels_rgb']
            inst=lab[...,0].astype(np.uint16) | (lab[...,1].astype(np.uint16)<<8)
            for label, obj in targets.items():
                semantic=lab[...,2]==label
                for instance in np.unique(inst[semantic]):
                    if instance:
                        m=semantic & (inst==instance)
                        visible.append((obj,int(instance),m))
        iou=np.zeros((len(detections),len(visible)))
        for j, mask in enumerate(masks):
            for k,(_,_,gtmask) in enumerate(visible):
                union=np.count_nonzero(mask|gtmask)
                if union:
                    iou[j,k]=np.count_nonzero(mask & gtmask)/union
        correct=np.zeros_like(iou)
        for j,det in enumerate(detections):
            for k,(obj,_,_) in enumerate(visible):
                if obj['class_name']==det['class_name'] and iou[j,k]>=0.5:
                    correct[j,k]=iou[j,k]
        jr,kr=linear_sum_assignment(np.where(correct>0,1-correct,1e6))
        matches={int(j):int(k) for j,k in zip(jr,kr) if correct[j,k]>0}
        frame_rows.append({'stop':i,'frame':index,'stamp_ns':stamp,'exact_gt_depth':'gt_depth' in data,
                           'exact_panoptic':'labels_rgb' in data,'tf':frame['tf'] is not None,
                           'joint_skew_ns':frame['joint_skew_ns'],
                           'visible':[(obj['model_name'],inst_id,int(mask.sum())) for obj,inst_id,mask in visible],
                           'missed':[obj['model_name'] for k,(obj,_,_) in enumerate(visible) if k not in matches.values()]})
        for j,(det,mask) in enumerate(zip(detections,masks)):
            name=det['class_name']
            k=matches.get(j)
            best=int(np.argmax(iou[j])) if visible else None
            best_iou=float(iou[j,best]) if best is not None else 0.0
            status='unscored'
            evidence=None
            if 'labels_rgb' in data:
                if k is not None:
                    status='true_detection'
                    evidence=visible[k][0]['model_name']
                elif best is not None and best_iou>=0.5:
                    ref=visible[best][0]
                    status='duplicate_detection' if ref['class_name']==name else 'false_class'
                    evidence=ref['model_name']
                elif name in classes:
                    status='unmatched_target_prediction'
            choices=[row for row in db_frames[fkey] if row['class_name']==name
                     and abs(row['confidence']-det['confidence'])<1e-6 and row['obs_id'] not in used_db_ids]
            if len(choices)>1:
                raise ValueError(f'ambiguous DB evidence: {fkey}, {name}, {det["confidence"]}')
            row=choices[0] if choices else None
            item={'stop':i,'frame':index,'stamp_ns':stamp,'class':name,'confidence':det['confidence'],
                  'semantic_status':status,'instance_gt':evidence,
                  'mask_iou':float(iou[j,k]) if k is not None else best_iou,
                  'truncated':det['truncated'],'depth_filter_pass':det['depth_filter_pass'],
                  'depth_reject_reason':det.get('reason'),'valid_depth_ratio':det['valid_depth_ratio'],
                  'obs_id':row['obs_id'] if row else None,'object_id':row['object_id'] if row else None,
                  'sqlite_status':object_status.get(row['object_id']) if row else None}
            if row:
                used_db_ids.add(row['obs_id'])
                if row['object_id'] is not None:
                    by_object[row['object_id']].append(item)
            per_detection.append(item)
            if k is None or not det['depth_filter_pass'] or 'gt_depth' not in data:
                continue
            obj,_,gt_mask=visible[k]
            pred,gt=data['pred_depth'],data['gt_depth']
            erosion=cfg['fusion']['mask_erode_ratio']
            kernel=max(3,int(round(erosion*np.sqrt(mask.sum()))))
            support=cv2.erode(mask.astype(np.uint8),np.ones((kernel,kernel),np.uint8))>0
            same=metrics(support,pred,gt)
            clean=metrics(support & gt_mask,pred,gt)
            result={**item,'same_mask':same,'instance_intersection':clean,
                    'instance_pixel_fraction':float((support & gt_mask).sum()/support.sum()) if support.any() else None}
            measurements.append(result)
            if not row or not frame['tf'] or frame['joint_yaw_rad'] is None or abs(frame['joint_skew_ns'])>2_000_000 or not clean['pixels']:
                continue
            u,v=det['u'],det['v']
            pp=camera_point(u,v,det['depth_m'],frame['K'])
            pred_clean=camera_point(u,v,clean['median_pred_m'],frame['K'])
            pg=camera_point(u,v,clean['median_gt_m'],frame['K'])
            actual=np.array([row['world_x'],row['world_y'],row['world_z']])
            ref=np.array([obj['x'],obj['y'],obj['z']])
            center=np.array(mesh_centers[obj['model_name']]['mesh_aabb_center_world_m'])
            tf=frame['tf']
            rtf=Rotation.from_quat(tf['quaternion']).as_matrix()
            ttf=np.array(tf['translation'])
            yaw=frame['joint_yaw_rad']
            c,s=math.cos(yaw),math.sin(yaw)
            rgeo=np.array([[s,0,c],[-c,0,s],[0,-1,0]])
            tgeo=np.array(cfg['camera']['base_xyz'])+cfg['camera']['t_offset_m']*np.array([c,s,0])
            sy,sx=np.where(support & gt_mask & np.isfinite(gt) & (gt>0))
            nearest=int(np.argmin((sx-u)**2+(sy-v)**2))
            surface=camera_point(float(sx[nearest]),float(sy[nearest]),float(gt[sy[nearest],sx[nearest]]),frame["K"])
            components={
                'production_tf_replay':actual-(rtf@pp+ttf),
                'tf_vs_rig_joint_geometry':(rtf@pp+ttf)-(rgeo@pp+tgeo),
                'production_support_vs_instance_support':rgeo@(pp-pred_clean),
                'depth_along_same_ray':rgeo@(pred_clean-pg),
                'median_proxy_vs_gt_surface_sample':rgeo@(pg-surface),
                'gt_surface_sample_vs_mesh_center':rgeo@surface+tgeo-center,
                'mesh_center_vs_yaml_reference':center-ref,
            }
            error=actual-ref
            assert np.allclose(sum(components.values()),error,atol=1e-9)
            cx,cy=round(u),round(v)
            at_uv=float(gt[cy,cx]) if 0<=cx<w and 0<=cy<h and gt_mask[cy,cx] and np.isfinite(gt[cy,cx]) and gt[cy,cx]>0 else None
            result.update({
                'pred_depth_m':det['depth_m'],'gt_median_same_mask_m':same.get('median_gt_m'),
                'gt_surface_depth_m':clean['median_gt_m'],'gt_depth_at_representative_pixel_m':at_uv,
                'p_cam_pred_m':pp.tolist(),'p_cam_gt_surface_proxy_m':pg.tolist(),
                'p_cam_gt_surface_sample_m':surface.tolist(),'reference_world_m':ref.tolist(),
                'actual_world_m':actual.tolist(),'camera_backprojection_delta_m':norm(pp-np.array(det['p_cam'])),
                'tf_translation_delta_m':norm(ttf-tgeo),
                'tf_rotation_delta_deg':float(np.degrees(Rotation.from_matrix(rtf.T@rgeo).magnitude())),
                'world_xyz_error_m':norm(error),'world_xy_error_m':norm(error[:2]),
                'components_world_m':{key:value.tolist() for key,value in components.items()},
                'components_xyz_norm_m':{key:norm(value) for key,value in components.items()},
                'components_xy_norm_m':{key:norm(value[:2]) for key,value in components.items()},
            })

confirmed=[]
for obj in objects:
    if obj['status']!='confirmed':
        continue
    items=by_object[obj['object_id']]
    truth=Counter(item['instance_gt'] for item in items if item['semantic_status']=='true_detection')
    false=Counter(item['instance_gt'] for item in items if item['semantic_status']=='false_class')
    scored=obj['class_name'] in classes or bool(truth or false)
    accepted=None
    if scored and len(truth)==1 and sum(truth.values())==len(items) and len(items)>=cfg['assoc']['min_obs']:
        accepted=next(iter(truth))
    error=None
    if accepted:
        ref=next(o for o in targets.values() if o['model_name']==accepted)
        error=norm(np.array([obj['x']-ref['x'],obj['y']-ref['y']]))
    confirmed.append({'id':obj['object_id'],'class':obj['class_name'],'n_observations':len(items),
                      'true_instance_votes':dict(truth),'wrong_label_instance_votes':dict(false),
                      'unresolved_observations':len(items)-sum(truth.values())-sum(false.values()),
                      'scored':scored,'semantic_instance':accepted,'xy_error_m':error,
                      'localized_within_0p5m':False})
groups=defaultdict(list)
for obj in confirmed:
    if obj['semantic_instance']:
        groups[obj['semantic_instance']].append(obj)
        obj['match_status']='outside_0p5m' if obj['xy_error_m']>=0.5 else 'duplicate_confirmed'
    elif obj['wrong_label_instance_votes']:
        obj['match_status']='wrong_class_evidence'
    else:
        obj['match_status']='insufficient_instance_evidence' if obj['scored'] else 'unscored'
for objects_of_instance in groups.values():
    eligible=[obj for obj in objects_of_instance if obj['xy_error_m']<0.5]
    if eligible:
        best=min(eligible,key=lambda obj:(obj['xy_error_m'],-obj['n_observations'],obj['id']))
        best['match_status']='localized'
        best['localized_within_0p5m']=True
assert len(used_db_ids)==len(rows),(len(used_db_ids),len(rows))
naive_refs=list(targets.values())
naive_objects=[obj for obj in objects if obj['status']=='confirmed' and obj['class_name'] in classes]
cost=np.full((len(naive_refs),len(naive_objects)),1e6)
for i,ref in enumerate(naive_refs):
    for j,obj in enumerate(naive_objects):
        distance=math.hypot(obj['x']-ref['x'],obj['y']-ref['y'])
        if obj['class_name']==ref['class_name'] and distance<0.5:
            cost[i,j]=distance
ix,jx=linear_sum_assignment(cost)
naive=[{'instance_gt':naive_refs[i]['model_name'],'object_id':naive_objects[j]['object_id'],
        'xy_m':float(cost[i,j])} for i,j in zip(ix,jx) if cost[i,j]<0.5]
assert all(not row['semantic_instance'] for row in confirmed if row['wrong_label_instance_votes'])

summary={'scan_id':scan_id,'frames':len(frame_rows),'database_observations':len(rows),
         'same_scene_configuration_as_textured_scan':same_scene_configuration,
         'frame_checks':frame_rows,'semantic_iou_threshold':0.5,
         'scope':'Four labeled props; other kitchen objects are not scored unless predicted as a target or overlapping one.',
         'detection_status':dict(Counter(item['semantic_status'] for item in per_detection)),
         'visible_instances':sum(len(f['visible']) for f in frame_rows),
         'missed_instances':sum(len(f['missed']) for f in frame_rows),'confirmed_objects':confirmed,
         'naive_class_and_xy_matches':naive,
         'confirmed_semantically_localized':sum(obj['localized_within_0p5m'] for obj in confirmed),
         'targets':{}}
for name in sorted(classes):
    instance=f'{name}_1'
    true=[d for d in per_detection if d['semantic_status']=='true_detection' and d['instance_gt']==instance]
    wrong=[d for d in per_detection if d['semantic_status']=='false_class' and d['instance_gt']==instance]
    values=[d for d in measurements if d['instance_gt']==instance]
    geo=[d for d in values if 'components_world_m' in d]
    agg={}
    for key in ('same_mask','instance_intersection'):
        groups=[d[key] for d in values if d[key]['pixels']>0]
        n=sum(d['pixels'] for d in groups)
        if n:
            agg[key]={m:sum(d[m]*d['pixels'] for d in groups)/n for m in ('mae_m','bias_m','absrel')}
            agg[key]['rmse_m']=math.sqrt(sum(d['rmse_m']**2*d['pixels'] for d in groups)/n)
            agg[key]['pixels']=n
    summary['targets'][name]={'visible_frames':sum(any(v[0]==instance for v in f['visible']) for f in frame_rows),
                              'true_detections':len(true),'false_class_on_instance':len(wrong),
                              'db_true_observations':sum(d['obs_id'] is not None for d in true),
                              'true_mask_iou_mean':float(np.mean([d['mask_iou'] for d in true])) if true else None,
                              'depth':agg,'xyz_decompositions':len(geo),'false_class_confidence':[d['confidence'] for d in wrong],
                              'false_class_iou':[d['mask_iou'] for d in wrong]}
    if geo:
        summary['targets'][name]['max_tf_rotation_delta_deg']=max(d['tf_rotation_delta_deg'] for d in geo)
        summary['targets'][name]['max_tf_translation_delta_m']=max(d['tf_translation_delta_m'] for d in geo)
        summary['targets'][name]['median_world_xyz_m']=float(np.median([d['world_xyz_error_m'] for d in geo]))
        summary['targets'][name]['median_world_xy_m']=float(np.median([d['world_xy_error_m'] for d in geo]))
        for key in ('components_xyz_norm_m','components_xy_norm_m'):
            summary['targets'][name]['median_'+key]={k:float(np.median([d[key][k] for d in geo])) for k in geo[0][key]}
        summary['targets'][name]['max_cam_backprojection_delta_m']=max(d['camera_backprojection_delta_m'] for d in geo)
        summary['targets'][name]['median_signed_depth_bias_m']=float(np.median([
            d['instance_intersection']['median_pred_m']-d['instance_intersection']['median_gt_m'] for d in geo]))
        summary['targets'][name]['stops_with_true_detections']=sorted({d['stop'] for d in true})

(root/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
(root/'xyz_decomposition.json').write_text(json.dumps(measurements,indent=2,allow_nan=False)+'\n')
with (root/'detection_audit.csv').open('w',newline='') as out:
    writer=csv.DictWriter(out,fieldnames=list(per_detection[0]))
    writer.writeheader()
    writer.writerows(per_detection)
print(json.dumps({k:v for k,v in summary.items() if k!='frame_checks'},indent=2))
