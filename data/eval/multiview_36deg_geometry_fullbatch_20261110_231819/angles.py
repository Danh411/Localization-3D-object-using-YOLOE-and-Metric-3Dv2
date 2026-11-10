from common import *
import itertools

def pose(scan,f):
    R=scan.rot(f)
    t=np.array(f['tf']['translation'])
    K=f['K']
    M=np.array([[K[0],0,K[2]],[0,K[1],K[3]],[0,0,1]])
    P=M@np.column_stack((R.T,-R.T@t))
    return R,t,M,P

def project(P,x):
    q=P@np.r_[x,1]
    return q[:2]/q[2],q[2]

def triangulate(P,Q,u,v):
    h=cv2.triangulatePoints(P,Q,np.asarray(u).reshape(2,1),np.asarray(v).reshape(2,1)).reshape(4)
    return h[:3]/h[3] if abs(h[3])>1e-10 else np.full(3,np.nan)

def kp_data(scan,f,d):
    with scan.frame_archive(f) as z:
        rgb=z['rgb']
        mask=np.unpackbits(z[d['mask']],axis=1,count=1280).astype(np.uint8)*255
    orb=cv2.ORB_create(nfeatures=450,edgeThreshold=12,fastThreshold=14)
    return orb.detectAndCompute(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),mask)

def angles(scan):
    v=load_csv(scan.path/'visibility_by_frame.csv')
    rows=[]
    base={(int(r['stamp_ns']),r['instance_gt']):r for r in load_csv(scan.path/'depth_scores.csv') if r['method']=='A'}
    for row in v:
        stamp=int(row['stamp_ns'])
        f=scan.frames[stamp]
        label=next((r for r in scan.det_by_frame[stamp] if r['instance_gt']==row['instance_gt'] and r['status']=='true'),None)
        depth=base.get((stamp,row['instance_gt']))
        o=scan.original[int(label['A_obs_id'])-1] if label and label['A_obs_id'] else None
        d=f['detections'][int(label['det_index'])] if label else None
        gt_visible_median=None
        if int(row['visible_pixels'])>0:
            with scan.frame_archive(f) as packet:
                valid=packet['labels_rgb'][...,2]==scan.gt[row['instance_gt']]['semantic_label']
                z=packet['gt_depth']
                z=z[valid & np.isfinite(z) & (z>.1) & (z<10)]
                if len(z):
                    gt_visible_median=float(np.median(z))
        center_occlusion=None
        pixel_x=pixel_y=None
        if f['tf']:
            _,_,_,P=pose(scan,f)
            uv,z=project(P,scan.centers[row['instance_gt']])
            if z>0 and 0<=uv[0]<1280 and 0<=uv[1]<720:
                pixel_x,pixel_y=map(float,uv)
                x,y=np.rint(uv).astype(int)
                if x<1280 and y<720:
                    with scan.frame_archive(f) as packet:
                        ground=packet['gt_depth'][y,x]
                        sem=packet['labels_rgb'][y,x,2]
                    r=scan.gt[row['instance_gt']]
                    margin=.5*np.linalg.norm([r['size_'+axis] for axis in 'xyz'])
                    center_occlusion=bool(np.isfinite(ground) and ground<z-margin-.02 and sem!=r['semantic_label'])
        rows.append(dict(scan=scan.path.name,**row,yaw_deg=math.degrees(f['joint_yaw_rad'])%360,
             in_fov=None if row['visibility']=='frustum_uncertain' else row['visibility']!='outside_fov',center_foreground_evidence=center_occlusion,gt_visible_median_z=gt_visible_median,
            gt_center_u=pixel_x,gt_center_v=pixel_y,mask_area_px=d['mask_area_px'] if d else None,
            detected_u=d.get('u') if d else None,detected_v=d.get('v') if d else None,
            mask_iou=float(label['matched_iou']) if label else None,confidence=float(label['confidence']) if label else None,
            db_status=label['A_final_status'] if label else None,
            world_xyz=row_xyz(o).tolist() if o else None,
            z_pred=float(depth['z_m']) if depth else None,z_gt=float(depth['gt_z_m']) if depth else None,
            z_error_m=float(depth['bias_m']) if depth else None,xy_error_m=float(depth['xy_m']) if depth else None,
            xyz_error_m=float(depth['xyz_m']) if depth else None))
    return rows

def triangulation(scan):
    frames=[f for f in scan.frames.values() if f['tf']]
    traj=[dict(stamp_ns=f['stamp_ns'],stop=f['stop'],yaw_deg=math.degrees(f['joint_yaw_rad']),
               x=f['tf']['translation'][0],y=f['tf']['translation'][1],z=f['tf']['translation'][2]) for f in frames]
    csv_write(ROOT/'optical_trajectory.csv',traj)
    pairs=[]
    for a,b in itertools.combinations(frames,2):
        baseline=math.dist(a['tf']['translation'],b['tf']['translation'])
        angle=math.degrees(diff_angle(a['joint_yaw_rad'],b['joint_yaw_rad']))
        pairs.append(dict(first=a['stop'],second=b['stop'],yaw_delta_deg=angle,baseline_m=baseline))
    csv_write(ROOT/'optical_baselines.csv',pairs)
    candidates=[]
    for target in scan.gt:
        tags=[r for r in scan.annotations if r['predicted_class']==scan.gt[target]['class_name']
              and r['A_obs_id'] and r['truncated']=='False' and r['A_final_object_id']]
        if len(tags)<2:
            continue
        for a,b in itertools.combinations(tags,2):
            if a['A_final_object_id']!=b['A_final_object_id']:
                continue
            f,g=[scan.frames[int(r['stamp_ns'])] for r in (a,b)]
            if not f['tf'] or not g['tf']:
                continue
            R,t,M,P=pose(scan,f); S,u,N,Q=pose(scan,g)
            baseline=np.linalg.norm(t-u)
            if baseline<.005:
                continue
            xyz=row_xyz(scan.original[int(a['A_obs_id'])-1])
            px,za=project(P,xyz); py,zb=project(Q,xyz)
            if min(za,zb)<=0:
                continue
            sensitivity=[]
            for sigma in (.5,1,2):
                alternatives=[triangulate(P,Q,px,py+sigma*offset) for offset in np.array([[1,0],[-1,0],[0,1],[0,-1]])]
                errors=[float(abs((R.T@(v-xyz))[2])) for v in alternatives if np.isfinite(v).all()]
                sensitivity.append(max(errors,default=None))
            candidates.append(dict(target=target,first=f['stop'],second=g['stop'],baseline_m=float(baseline),
                yaw_delta_deg=math.degrees(diff_angle(f['joint_yaw_rad'],g['joint_yaw_rad'])),
                d05=sensitivity[0],d1=sensitivity[1],d2=sensitivity[2],a=a,b=b))
    out=[]
    for target in scan.gt:
        cases=sorted((r for r in candidates if r['target']==target),key=lambda r:-r['baseline_m'])
        for r in cases[:4]:
            a,b=r['a'],r['b']
            f,g=[scan.frames[int(z['stamp_ns'])] for z in (a,b)]
            R,t,M,P=pose(scan,f); S,u,N,Q=pose(scan,g)
            ka,da=kp_data(scan,f,f['detections'][int(a['det_index'])])
            kb,dd=kp_data(scan,g,g['detections'][int(b['det_index'])])
            matching=[]
            if da is not None and dd is not None and len(dd)>1:
                matching=[m for m,n in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da,dd,k=2) if m.distance<.72*n.distance]
            accepted=[]
            geometry_accepted=0
            with scan.frame_archive(f) as sample, scan.frame_archive(g) as second:
                ground=sample['gt_depth']
                for match in matching:
                    px,py=np.array(ka[match.queryIdx].pt),np.array(kb[match.trainIdx].pt)
                    x=triangulate(P,Q,px,py)
                    if not np.isfinite(x).all():
                        continue
                    aa,z1=project(P,x); bb,z2=project(Q,x)
                    if min(z1,z2)<=0 or max(np.linalg.norm(aa-px),np.linalg.norm(bb-py))>1.:
                        continue
                    geometry_accepted+=1
                    xt,yt=np.rint(px).astype(int)
                    x2,y2=np.rint(py).astype(int)
                    if not (0<=xt<1280 and 0<=x2<1280 and 0<=yt<720 and 0<=y2<720):
                        continue
                    tag=scan.gt[target]['semantic_label']
                    if sample['labels_rgb'][yt,xt,2]!=tag or second['labels_rgb'][y2,x2,2]!=tag:
                        continue
                    truth=ground[yt,xt]
                    if np.isfinite(truth) and .1<truth<10.:
                        accepted.append(abs(float(z1-truth)))
            out.append(dict(**{k:v for k,v in r.items() if k not in ('a','b')},orb_a=len(ka),orb_b=len(kb),
                ratio_matches=len(matching),accepted=geometry_accepted,gt_scored=len(accepted),gt_abs_error_median=stats(accepted).get('median')))
    csv_write(ROOT/'triangulation_matches.csv',out)
    put(ROOT/'triangulation_summary.json',dict(max_baseline_m=max(p['baseline_m'] for p in pairs),pairs=len(pairs),
        candidate_same_object_pairs=len(candidates),candidate_pairs_under_10cm_per_px=sum(
            r['d1'] is not None and r['d1']<=.10 for r in candidates),tested=out))

def plot(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(5,1,figsize=(12,11),sharex=True)
    targets=sorted({r['instance_gt'] for r in rows})
    for name in targets:
        data=[r for r in rows if r['instance_gt']==name and r['scan']=='scan_36x1']
        for ax,key,scale in zip(axes,['confidence','z_error_m','xyz_error_m','visible_pixels','truncated'],[1,100,100,1,1]):
            visible=[r for r in data if r[key] is not None and (key!='truncated' or r['detected']=='True')]
            ax.scatter([r['yaw_deg'] for r in visible],[float(r[key])*scale for r in visible],label=name,s=12)
    for ax,title in zip(axes,['YOLOE confidence','Depth signed error (cm)','World XYZ error (cm)','GT visible pixels','Truncated (matched)']):
        ax.set_ylabel(title); ax.grid(alpha=.2)
    axes[0].axhline(.35,color='k',ls='--',alpha=.3)
    axes[0].legend(ncol=4)
    axes[-1].set_xlabel('Actual pan yaw (deg)')
    fig.tight_layout()
    fig.savefig(ROOT/'angle_diagnostics.png',dpi=150)

if __name__=='__main__':
    a,b=Scan('scan_8x3'),Scan('scan_36x1')
    rows=angles(a)+angles(b)
    csv_write(ROOT/'detection_by_angle.csv',rows)
    csv_write(ROOT/'depth_by_angle.csv',[r for r in rows if r['z_pred'] is not None])
    shared=[r for r in rows if (r['scan']=='scan_8x3' and int(r['stop'])%2==0)
             or (r['scan']=='scan_36x1' and int(r['stop'])%9==0)]
    csv_write(ROOT/'shared_angles.csv',shared)
    triangulation(b)
    plot(rows)

