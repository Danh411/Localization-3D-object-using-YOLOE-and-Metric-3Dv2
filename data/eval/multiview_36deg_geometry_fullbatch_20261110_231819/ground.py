from common import *
from perception.core.yolo import YoloeDetector
from perception.core.fusion import object_depth, is_truncated
from perception.core.geometry import backproject_optical, optical_to_world
import hashlib

def floor_z(ray, vertical, height):
    direction=ray@vertical
    with np.errstate(divide='ignore',invalid='ignore'):
        z=-height/direction
    good=(direction<0)&(direction/np.linalg.norm(ray,axis=-1)<-math.sin(math.radians(5)))&(z>.1)&(z<10.)
    return z,good

def fit_scale(mask,pred,z,eligible):
    ok=mask&eligible&np.isfinite(pred)&(pred>.1)&(pred<10)
    yy,xx=np.nonzero(ok)
    if len(yy)<400:
        return 1.,len(yy),0,None,'pixels'
    ratio=z[ok]/pred[ok]
    blocks=(yy//40)*32+xx//40
    med=np.array([np.median(ratio[blocks==i]) for i in np.unique(blocks) if (blocks==i).sum()>=25])
    if len(med)<4:
        return 1.,len(yy),len(med),None,'blocks'
    k=float(np.median(med))
    mad=float(np.median(np.abs(med-k))/k)
    if mad>.12 or not .5<=k<=2.5:
        return 1.,len(yy),len(med),mad,'dispersion_or_scale'
    return k,len(yy),len(med),mad,'accepted'

def floor_model():
    prior=ROOT.parent/'kitchen_reference_20261110_134600_sync'
    checkpoints=read(prior/'manifest.json')['model_checkpoints']
    for item in checkpoints:
        with Path(item['original_path']).open('rb') as fp:
            assert hashlib.file_digest(fp,'sha256').hexdigest()==item['sha256']
    import torch
    torch.set_num_threads(2)
    # Use the same weights, with a diagnostic-only vocabulary.
    return YoloeDetector(['floor'],str(REPO/'yoloe-v8s-seg.pt'),.35,.5,640,'cpu')

def check_frame(model,rgb,gt,pred,K,R,origin,floor_height=0.):
    ray=points(K)
    vertical=R[2,:].astype(np.float32)
    height=origin[2]-floor_height
    z,eligible=floor_z(ray,vertical,height)
    physical=(np.abs(gt*(ray@vertical)+height)<.02)&np.isfinite(gt)&(gt>.1)&(gt<10)&eligible
    started=time.perf_counter()
    detected=model.detect(rgb)
    mask=np.zeros(gt.shape,bool)
    for d in detected:
        mask|=d['mask']
    result={}
    for key,selected in [('rgb',mask),('oracle',physical)]:
        scale,count,blocks,mad,status=fit_scale(selected,pred,z,eligible)
        result[key]=(scale,status)
        if key=='rgb':
            result['rgb_floor_s']=time.perf_counter()-started
        result[key+'_pixel_n']=count
        result[key+'_blocks']=blocks
        result[key+'_mad']=mad
    result.update(gt_floor_pixels=int(physical.sum()),rgb_floor_pixels=int(mask.sum()),ray_eligible=int(eligible.sum()),
                  near_horizon_px=int((np.abs(ray@vertical)/np.linalg.norm(ray,axis=-1)<math.sin(math.radians(5))).sum()),
                  floor_iou=float(np.count_nonzero(mask&physical)/max(1,np.count_nonzero(mask|physical))),
                  floor_precision=float(np.count_nonzero(mask&physical)/mask.sum()) if mask.any() else None,
                  floor_conf=max((d['confidence'] for d in detected),default=None))
    for name,shift,pitch in [('height_low',-.02,0),('height_high',.02,0),('pitch_low',0,-1),('pitch_high',0,1)]:
        tilted=vertical@Rotation.from_euler('x',pitch,degrees=True).as_matrix()
        zz,gg=floor_z(ray,tilted,height+shift)
        result[name]=fit_scale(mask,pred,zz,gg)[0]
    return result

def score_row(name,f,target,z_pred,z_gt,pc,R,t,center,scales):
    rows=[]
    for method,k in scales.items():
        z=z_pred*k
        if not .1<z<10:
            z=z_pred
        error=R@(pc*(z/z_pred))+t-center
        rows.append(dict(world=name,file=f['file'],target=target,method=method,scale=k,z=z,z_gt=z_gt,
            abs_error_m=abs(z-z_gt),absrel=abs(z-z_gt)/z_gt,bias=z-z_gt,
            xy=float(np.linalg.norm(error[:2])),xyz=float(np.linalg.norm(error))))
    return rows

def analyze_external(model):
    prior=ROOT.parent/'metric3d_crossworld_fullbatch_20261110_222348'
    source=load_csv(prior/'holdout_scores_external.csv')
    original={(r['world'],r['file']):r for r in source if r['method']=='original'}
    rows=[]; feasibility=[]
    for name in ('aws','tiffany'):
        room=prior/name
        design=read(room/'design.json')
        for f in read(room/'capture_index.json'):
            if f['distance_m'] not in design['test_distances']:
                continue
            key=Path(f['file']).stem
            with np.load(room/'frames'/f['file'],allow_pickle=False) as packet, np.load(room/'predictions'/(key+'_holdout.npz'),allow_pickle=False) as output:
                rgb,gt,K=[packet[k] for k in ('rgb','gt_depth','K')]
                pred=output['pred_depth']
                a=f['optical_heading_rad']
                c,s=math.cos(a),math.sin(a)
                R=np.array([[s,0,c],[-c,0,s],[0,-1,0]])
                t=np.array(f['optical_origin_world_m'])
                info=check_frame(model,rgb,gt,pred,K,R,t,design['surface_z_m'])
                feasibility.append(dict(world=name,file=f['file'],**info))
                base=original.get((name,f['file']))
                if base:
                    dets=read(room/'predictions'/(key+'_detections.json'))
                    d=max((d for d in dets if d['class_name']==f['target'].removesuffix('_1') and d['iou']>=.5),key=lambda d:d['iou'])
                    mask=np.unpackbits(output[d['mask']],axis=1,count=1280).astype(bool)
                    z=object_depth(pred,mask)
                    pc=np.array(backproject_optical(z['u'],z['v'],z['depth_m'],*K))
                    o,q=f['target_pose_observed']
                    prior_rotation=Rotation.from_euler('xyz',design['props'][f['target']]['pose_rpy'])
                    center=np.array(o)+(Rotation.from_quat(q)*prior_rotation.inv()).apply(design['props'][f['target']]['center_offset'])
                    rows+=score_row(name,f,f['target'],z['depth_m'],float(base['z_gt_m']),pc,R,t,center,
                        dict(original=1.,kitchen_locked=1.3720333573615522,rgb=info['rgb'][0],oracle=info['oracle'][0],
                            **{key:info[key] for key in ('height_low','height_high','pitch_low','pitch_high')}))
            print(name,key,info['rgb'],info['oracle'],flush=True)
    csv_write(ROOT/'crossworld_floor_frames.csv',feasibility)
    csv_write(ROOT/'crossworld_check.csv',rows)

def analyze_kitchen(model):
    feasibility=[]; correction=[]; wire={}
    for name in ('scan_8x3','scan_36x1'):
        scan=Scan(name)
        base={int(r['stamp_ns']):[] for r in load_csv(scan.path/'depth_scores.csv')}
        for r in load_csv(scan.path/'depth_scores.csv'):
            if r['method']=='A':
                base[int(r['stamp_ns'])].append(r)
        for stamp,f in scan.frames.items():
            if not f['tf']:
                continue
            with scan.frame_archive(f) as z:
                rgb,gt,pred=[z[k] for k in ('rgb','gt_depth','pred_depth')]
            R,t=scan.rot(f),np.array(f['tf']['translation'])
            info=check_frame(model,rgb,gt,pred,f['K'],R,t)
            feasibility.append(dict(scan=name,stamp_ns=stamp,stop=f['stop'],frame=f['frame_idx'],**info))
            if name=='scan_36x1':
                wire[stamp]={key:info[key][0] for key in ('rgb','oracle')}
            for row in base.get(stamp,[]):
                tag=next(a for a in scan.det_by_frame[stamp] if a['status']=='true' and a['instance_gt']==row['instance_gt'] and a['A_obs_id'])
                d=f['detections'][int(tag['det_index'])]
                correction+=score_row(name,f,row['instance_gt'],d['depth_m'],float(row['gt_z_m']),np.array(d['p_cam']),R,t,
                    scan.centers[row['instance_gt']],
                    dict(original=1.,kitchen_locked=1.3720333573615522,rgb=info['rgb'][0],oracle=info['oracle'][0],
                         **{key:info[key] for key in ('height_low','height_high','pitch_low','pitch_high')}))
            print(name,stamp,info['rgb'],info['oracle'],flush=True)
    csv_write(ROOT/'ground_plane_feasibility.csv',feasibility)
    csv_write(ROOT/'ground_plane_correction.csv',correction)
    put(ROOT/'floor_wire.json',wire)

if __name__=='__main__':
    model=floor_model()
    if sys.argv[1]=='external':
        analyze_external(model)
    else:
        analyze_kitchen(model)

