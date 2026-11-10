from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
root=Path(__file__).resolve().parent
previous=root.parent/'metric3d_depth_calibration_20261110_184655'
path=previous/'evaluate_rooms.py'
src=path.read_text()
exec(compile(src[:src.index('lock=root/')],str(path),'exec'))
exec(compile(src[src.index('cfg=yaml'):src.index("print('Production models ready")],str(path),'exec'))
fit_path=previous/'fit.py'
fit=fit_path.read_text()
exec(compile(fit[fit.index('def train('):fit.index('bounds=')],str(fit_path),'exec'))
kitchen=root/'kitchen_locked.json'
assert sha(kitchen)==(root/'kitchen_locked.sha256').read_text().strip()
original=read(kitchen)
bounds=original['output_clip_m']
worlds=('aws','tiffany')
targets=('bottle_1','cup_1','laptop_1')
dims=('distance_m','relative_yaw_deg','target')
cal_rows, group_rows, cv_rows, coverage, scores, dense = [], [], [], [], [], []
models={'kitchen':{'B':original['models']['B'],'C':original['models']['C']}}
decisions={'kitchen':original['selected_before_holdouts']}
designs={}
indexes={}
datasets={}

def samples(gt, pred, mask):
    good=mask & np.isfinite(gt)&np.isfinite(pred)&(gt>.1)&(gt<10)&(pred>.1)&(pred<10)
    return pred[good].astype(float),gt[good].astype(float)

def fit_mask(mask):
    kernel=max(3,int(round(.05*np.sqrt(mask.sum()))))
    return cv2.erode(mask.astype(np.uint8),np.ones((kernel,kernel),np.uint8))>0

def errors(x,y,coeff):
    a,b=coeff
    raw=a*x+b
    value=np.clip(raw,*bounds) if [a,b]!=[1.,0.] else raw
    e=value-y
    return {'mae_m':float(np.abs(e).mean()),'absrel':float((np.abs(e)/y).mean()),'bias_m':float(e.mean()),
            'clipped':int(np.count_nonzero(value!=raw))}

def basic(f):
    return {k:f[k] for k in ('file',*dims,'stamp_ns','gt_median_z_m','issues')}

def preflight(f, npz):
    assert int(npz['stamp_ns'])==f['stamp_ns']
    assert np.allclose(npz['K'],[914.0147013559828,914.0147013559828,640,360],rtol=0,atol=1e-5)
    lab=npz['labels_rgb']
    mask=(lab[...,2]==f['label'])&((lab[...,0]>0)|(lab[...,1]>0))
    assert mask.sum()==f['visible_pixels']
    return mask

for name in worlds:
    room=root/name
    designs[name]=read(room/'design.json')
    index=read(room/'capture_index.json')
    assert len(index)==45
    indexes[name]=index
    (room/'predictions').mkdir()
    data=[]
    for f in index:
        if f['distance_m'] not in designs[name]['training_distances']:
            continue
        row={'world':name,**basic(f),'valid':not f['issues']}
        cal_rows.append(row)
        if f['issues']:
            continue
        with np.load(room/'frames'/f['file'],allow_pickle=False) as z:
            mask=preflight(f,z)
            pred=estimator.estimate(z['rgb'],z['K'][0])
            x,y=samples(z['gt_depth'],pred,fit_mask(mask))
        assert x.size
        np.save(room/'predictions'/f['file'].replace('.npz','.npy'),pred)
        data.append((f,x,y))
        row.update(n_pixels=len(x),mean_pred_z_m=float(x.mean()),mean_gt_z_m=float(y.mean()),
                   ratio_median=float(np.median(y/x)),**errors(x,y,[1.,0.]))
        print('calibration',name,f['file'],flush=True)
    assert {d[0]['target'] for d in data}==set(targets)
    datasets[name]=data
    fit_values=train(data)
    models[name]={m:list(fit_values[m]) for m in ('B','C')}
    for axis in dims:
        groups=sorted({f[axis] for f,_,_ in data})
        for g in groups:
            group=[r for r in data if r[0][axis]==g]
            other=[r for r in data if r[0][axis]!=g]
            sub=train(group)
            fold=train(other)
            ratios=[float(np.median(y/x)) for _,x,y in group]
            group_rows.append(dict(world=name,axis=axis,group=g,n=len(group),group_k=sub['B'][0],
                k_deviation_rel=(sub['B'][0]/fit_values['B'][0]-1),group_ratio_median=float(np.median(ratios)),
                leave_out_k=fold['B'][0]))
            for f,x,y in group:
                for method, coeff in fold.items():
                    cv_rows.append(dict(world=name,axis=axis,group=g,method=method,**basic(f),**errors(x,y,coeff)))
    cv={m:float(np.mean([r['mae_m'] for r in cv_rows if r['world']==name and r['axis']=='distance_m' and r['method']==m])) for m in 'ABC'}
    decisions[name]=min('BC',key=cv.get)
    models[name]['cv_mae_m']=cv

# Compare Kitchen subgroup ratios without refitting the locked Kitchen coefficient.
prior=root.parent/'metric3d_hypotheses_20261110_144943'
for f in read(prior/'capture_index.json'):
    with np.load(prior/'controlled_frames'/f['file'],allow_pickle=False) as z:
        mask=fit_mask(z['labels_rgb'][...,2]==f['label'])
        x,y=samples(z['gt_depth'],np.load(prior/'predictions'/f['file'].replace('.npz','.npy'),allow_pickle=False),mask)
    cal_rows.append(dict(world='kitchen',file=f['file'],target=f['target'],distance_m=f['nominal_axial_origin_m'],
        relative_yaw_deg=f['relative_object_yaw_deg'],stamp_ns=f['stamp_ns'],valid=True,n_pixels=len(x),
        mean_pred_z_m=float(x.mean()),mean_gt_z_m=float(y.mean()),ratio_median=float(np.median(y/x)),**errors(x,y,[1.,0.])))
for axis in dims:
    groups=sorted({r[axis] for r in cal_rows if r['world']=='kitchen'})
    for g in groups:
        values=[r['ratio_median'] for r in cal_rows if r['world']=='kitchen' and r[axis]==g]
        group_rows.append(dict(world='kitchen',axis=axis,group=g,n=len(values),group_ratio_median=float(np.median(values))))
csvfile(root/'calibration_by_world.csv',cal_rows)
csvfile(root/'calibration_stability.csv',group_rows)
csvfile(root/'calibration_cv.csv',cv_rows)
lockfile=root/'crossworld_locked.json'
with lockfile.open('x',encoding='utf-8') as fp:
    json.dump(dict(locked_utc=datetime.now(timezone.utc).isoformat(),models=models,selected_by_distance_cv=decisions,
                   clip=bounds,kitchen_lock_sha256=sha(kitchen),
                   design_sha256={n:sha(root/n/'design.json') for n in worlds}),fp,indent=2)
(root/'crossworld_locked.sha256').write_text(sha(lockfile)+'\n')
print('Locked before evaluating test RGB or GT',sha(lockfile),flush=True)

def coefficients(name):
    return {'original':[1.,0.],**{k:models[k]['B'] for k in models},
            'linear_local':models[name]['C']}

for name in worlds:
    room=root/name
    design=designs[name]
    index=[f for f in indexes[name] if f['distance_m'] in design['test_distances']]
    assert len(index)==18
    previews={}
    for f in index:
        with np.load(room/'frames'/f['file'],allow_pickle=False) as z:
            mask=preflight(f,z)
            rgb,gt,K=[z[k] for k in ('rgb','gt_depth','K')]
        pred=estimator.estimate(rgb,K[0])
        dets=detector.detect(rgb)
        key=Path(f['file']).stem
        packed={f'mask_{i}':np.packbits(d['mask'],axis=1) for i,d in enumerate(dets)}
        np.savez_compressed(room/'predictions'/(key+'_holdout.npz'),pred_depth=pred,**packed)
        ious=[np.count_nonzero(mask&d['mask'])/np.count_nonzero(mask|d['mask']) for d in dets]
        cls=f['target'].removesuffix('_1')
        correct=[(iou,d) for iou,d in zip(ious,dets) if iou>=.5 and d['class_name']==cls]
        wrong=[d['class_name'] for iou,d in zip(ious,dets) if iou>=.5 and d['class_name']!=cls]
        best=max(zip(ious,dets),key=lambda p:p[0],default=(0,None))
        put(room/'predictions'/(key+'_detections.json'),[
            {**{k:v for k,v in d.items() if k!='mask'},'mask':f'mask_{i}','iou':ious[i]} for i,d in enumerate(dets)])
        r=None
        note='no_correct_instance' if not correct else ''
        if f['issues']:
            note='capture_QA'
        elif correct:
            iou,d=max(correct,key=lambda p:p[0])
            r=object_depth(pred,d['mask'],fc['mask_erode_ratio'],fc['min_valid_ratio'],near,far)
            note=r['reason'] or ('truncated' if is_truncated(d['bbox_xyxy'],1280,720,fc['border_px']) else '')
        row=dict(world=name,**basic(f),visible=bool(mask.any()),correct=bool(correct),wrong_classes=wrong,
                 missed=bool(mask.any() and not correct),best_iou=best[0],
                 best_conf=best[1]['confidence'] if best[1] else None,excluded_reason=note)
        coverage.append(row)
        if not f['issues']:
            x,y=samples(gt,pred,fit_mask(mask))
            if len(x):
                for m,coeff in coefficients(name).items():
                    dense.append(dict(world=name,method=m,**basic(f),pixels=len(x),ratio_median=float(np.median(y/x)),**errors(x,y,coeff)))
            if f['target'] not in previews:
                yy,xx=np.where(mask)
                im=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
                cv2.rectangle(im,(xx.min(),yy.min()),(xx.max(),yy.max()),(0,220,255),2)
                cv2.putText(im,f"{name} | {cls} | {f['distance_m']} m",(20,38),0,1,(0,220,255),2)
                previews[f['target']]=cv2.resize(im,(640,360))
        if note:
            continue
        support=erode_mask(d['mask'],fc['mask_erode_ratio'])&mask
        x,y=samples(gt,pred,support)
        if not len(x):
            row['excluded_reason']='no_shared_depth_support'
            continue
        o,q=f['target_pose_observed']
        prior_rotation=Rotation.from_euler('xyz',design['props'][f['target']]['pose_rpy'])
        center=np.array(o)+(Rotation.from_quat(q)*prior_rotation.inv()).apply(design['props'][f['target']]['center_offset'])
        z_gt=float(np.median(y))
        for m,coeff in coefficients(name).items():
            a,b=coeff
            raw=a*r['depth_m']+b
            z=float(np.clip(raw,*bounds)) if m!='original' else raw
            pc=backproject_optical(r['u'],r['v'],z,*K)
            pw=optical_to_world(pc,f['optical_heading_rad'],f['rig_pose_observed'][0],(.05,0,0))
            e=pw-center
            scores.append(dict(world=name,method=m,**basic(f),z_pred_m=r['depth_m'],z_gt_m=z_gt,z_scored_m=z,
                abs_error_m=abs(z-z_gt),absrel=abs(z-z_gt)/z_gt,bias_m=z-z_gt,xy_m=float(np.linalg.norm(e[:2])),
                xyz_m=float(np.linalg.norm(e)),clipped=z!=raw,mask_iou=iou,confidence=d['confidence']))
        print('test',name,key,flush=True)
    if previews:
        cv2.imwrite(str(room/'render.jpg'),np.hstack(list(previews.values())))
csvfile(root/'holdout_scores_external.csv',scores)
csvfile(root/'holdout_dense_gt_mask.csv',dense)
csvfile(root/'holdout_coverage_external.csv',coverage)
print('External phases complete',flush=True)

