from common import *

def weighted_mean(x,w):
    return np.average(x,axis=0,weights=w)
def geomedian(x,w):
    center=weighted_mean(x,w)
    for _ in range(100):
        dist=np.linalg.norm(x-center,axis=1)
        nxt=weighted_mean(x,w/np.maximum(dist,1e-7))
        if np.linalg.norm(nxt-center)<1e-7:
            return nxt
        center=nxt
    return center
def huber(x,w):
    center=geomedian(x,w)
    for _ in range(60):
        r=np.linalg.norm(x-center,axis=1)
        nxt=weighted_mean(x,w*np.minimum(1.,.10/np.maximum(r,1e-7)))
        if np.linalg.norm(nxt-center)<1e-7:
            return nxt
        center=nxt
    return center
def consensus(x,w,angles):
    # Minimal point model: hypotheses are all observed centers, sampled exhaustively.
    distances=np.linalg.norm(x[:,None,:]-x[None,:,:],axis=-1)
    voters=distances<=.12
    counts=voters.sum(axis=1)
    best=int(np.argmax(counts))
    mask=voters[best]
    independent=len({int((a%(2*math.pi))/math.radians(20)) for a in angles[mask]})
    rivals=(distances[best]>.12)&(counts==counts[best])
    if independent<3 or counts[best]<math.ceil(.6*len(x)) or rivals.any():
        return None,int(mask.sum()),independent
    return weighted_mean(x[mask],w[mask]),int(mask.sum()),independent

def quality(scan,o):
    f=scan.frames[o['stamp_ns']]
    d=f['detections'][int(scan.labels[o['obs_id']]['det_index'])]
    with scan.frame_archive(f) as z:
        mask=np.unpackbits(z[d['mask']],axis=1,count=1280).astype(bool)
        support=erode_mask(mask,scan.cfg['fusion']['mask_erode_ratio'])
        depth=z['pred_depth']
        good=support&np.isfinite(depth)&(depth>.1)&(depth<10)
        values=depth[good]
        med=float(np.median(values))
        mad=float(np.median(np.abs(values-med)))/med
        gy,gx=np.gradient(depth)
        discontinuity=float(np.count_nonzero(np.hypot(gy[good],gx[good])>.05)/good.sum())
    u,v=d['u'],d['v']
    radial=((u-640)/640)**2+((v-360)/360)**2
    return math.sqrt(min(1.,good.sum()/8000))/(1+radial+5*mad+discontinuity)

def fusion(scan, baseline):
    rows=[]; diag=[]
    methods=('F1_geomedian','F2_huber','F3_RANSAC','F4_quality','F5_angle_equal','F5_angle_one')
    positions={m:{} for m in methods}
    runtime=defaultdict(float)
    for oid,members in scan.members.items():
        if oid is None or scan.objects_by_id[oid]['status']=='rejected':
            continue
        x=np.array([row_xyz(o) for o in members])
        angles=np.array([scan.frames[o['stamp_ns']]['joint_yaw_rad'] for o in members])
        w=np.array([float(scan.labels[o['obs_id']]['A_weight']) for o in members])
        start=time.perf_counter()
        q=np.array([quality(scan,o) for o in members])
        runtime['F4_quality']+=time.perf_counter()-start
        bins=np.floor((angles+math.radians(15))%(2*math.pi)/math.radians(30)).astype(int)
        equal=w/np.array([w[bins==i].sum() for i in bins])
        chosen=np.array([idx[np.argmax((w*q)[idx])] for i in np.unique(bins) for idx in [np.flatnonzero(bins==i)]])
        prior=np.array([scan.objects_by_id[oid][k] for k in 'xyz'])
        for m in methods:
            start=time.perf_counter()
            if m=='F1_geomedian':
                result=geomedian(x,w)
            elif m=='F2_huber':
                result=huber(x,w)
            elif m=='F3_RANSAC':
                result,n,unique=consensus(x,w,angles)
                diag.append(dict(object_id=oid,n_obs=len(x),inliers=n,independent_bins=unique,accepted=result is not None))
                if result is None:
                    result=prior
            elif m=='F4_quality':
                result=weighted_mean(x,w*q)
            elif m=='F5_angle_equal':
                result=weighted_mean(x,equal)
            else:
                result=weighted_mean(x[chosen],w[chosen])
            runtime[m]+=time.perf_counter()-start
            positions[m][oid]=result
    for m in methods:
        metric=scan.with_positions(m,positions[m])
        rows.append(comparison(m,metric,baseline,runtime[m]))
    csv_write(ROOT/'ransac_diagnostics.csv',diag)
    return rows

def comparison(name,result,base,seconds):
    p={o['target']:o for o in base['objects']}
    dx=[o['xy']-p[o['target']]['xy'] for o in result['objects'] if o['target'] in p]
    return dict(method=name,**result,seconds=seconds,paired=len(dx),
                xy_better=sum(x<-1e-8 for x in dx),xy_worse=sum(x>1e-8 for x in dx))

def image_quality(f,classes):
    weight=0.
    for d in f['detections']:
        if d['class_name'] not in classes:
            continue
        x1,y1,x2,y2=d['bbox_xyxy']
        u,v=(x1+x2)/2,(y1+y2)/2
        radial=((u-640)/640)**2+((v-360)/360)**2
        area=max(0.,(x2-x1)*(y2-y1))
        weight+=d['confidence']*math.sqrt(area/10000)/(1+radial)*(.25 if d['truncated'] else 1.)
    return weight

def timings(scan,selected):
    d=sum(f['timings_ms']['depth_ms'] for f in scan.frames.values())/1000
    k=sum(f['timings_ms']['depth_ms'] for f in scan.frames.values() if f['stop'] in selected)/1000
    return dict(depth_calls=len(selected),depth_calls_saved=len(scan.frames)-len(selected),depth_inference_est_s=k,
                depth_inference_saved_est_s=d-k)

def summarize_depth(rows):
    fields=('abs_error_m','absrel','bias_m')
    return dict(depth_n=len(rows),**{('depth_'+k):float(np.mean([float(r[k]) for r in rows]))
        if rows else None for k in fields})

def base_depth(scan,stops=None,frame=None):
    rows=[r for r in load_csv(scan.path/'depth_scores.csv') if r['method']=='A' and
          (stops is None or int(r['stop']) in stops) and (frame is None or int(r['frame'])==frame)]
    return summarize_depth(rows)

def temporal(scan,selected,name,base):
    start=time.perf_counter()
    entries=[]
    details=[]
    depth_rows=[r for r in load_csv(scan.path/'depth_scores.csv')
                if r['method']=='A' and int(r['stop']) in selected]
    tracks=[]
    for stamp,f in scan.frames.items():
        if not f['tf']:
            continue
        if f['stop'] in selected:
            for o in (o for o in scan.original if o['stamp_ns']==stamp):
                label=scan.labels[o['obs_id']]
                entries.append((o,label))
                if o['truncated']:
                    continue
                xyz=row_xyz(o)
                matches=[t for t in tracks if t['class']==o['class_name'] and np.linalg.norm(xyz-t['p'])<.35]
                if len(matches)==1:
                    t=matches[0]
                else:
                    t=dict(id=len(tracks),class_name=o['class_name'])
                    tracks.append(t)
                t.update(p=xyz,stamp=stamp,yaw=f['joint_yaw_rad'],label=label.get('instance_gt'),**{'class':o['class_name']})
            continue
        R,t=scan.rot(f),np.array(f['tf']['translation'])
        fx,fy,cx,cy=f['K']
        with scan.frame_archive(f) as packet:
            # Reconstruct a depth-independent order for non-key detections.
            candidates=sorted(scan.det_by_frame[stamp],key=lambda r:(
                -f['detections'][int(r['det_index'])]['confidence'],
                f['detections'][int(r['det_index'])]['bbox_xyxy'],r['predicted_class']))
            for label in candidates:
                d=f['detections'][int(label['det_index'])]
                cls=d['class_name']
                if d['truncated']:
                    continue
                mask=np.unpackbits(packet[d['mask']],axis=1,count=1280)
                choices=[]
                for tr in tracks:
                    age=(stamp-tr['stamp'])/1e9
                    if tr['class']!=cls or age>30 or diff_angle(f['joint_yaw_rad'],tr['yaw'])>math.radians(30):
                        continue
                    pc=R.T@(tr['p']-t)
                    if not .1<pc[2]<10.:
                        continue
                    u,v=int(round(fx*pc[0]/pc[2]+cx)),int(round(fy*pc[1]/pc[2]+cy))
                    if 0<=u<1280 and 0<=v<720 and mask[v,u]:
                        choices.append((tr,age,pc))
                if len(choices)!=1:
                    details.append(dict(stamp_ns=stamp,class_name=cls,decision='unmatched' if not choices else 'ambiguous'))
                    continue
                tr,age,pc=choices[0]
                o=dict(class_name=cls,confidence=d['confidence'],truncated=False,depth_m=float(pc[2]),
                    range_m=float(np.linalg.norm(pc)),stop_index=f['stop'],frame_idx=f['frame_idx'],
                    yaw_rad=f['joint_yaw_rad'],stamp_ns=stamp,valid_ratio=None)
                o.update({f'bbox_{k}':v for k,v in zip(('x1','y1','x2','y2'),d['bbox_xyxy'])})
                o.update({f'cam_{k}':float(v) for k,v in zip('xyz',pc)})
                o.update({f'world_{k}':float(v) for k,v in zip('xyz',tr['p'])})
                entries.append((o,label))
                if label['status']=='true':
                    # Assessment only, after the propagation decision is fixed.
                    gt=packet['gt_depth']
                    tag=scan.gt[label['instance_gt']]['semantic_label']
                    valid=erode_mask(mask.astype(bool))&(packet['labels_rgb'][...,2]==tag)
                    valid &= np.isfinite(gt)&(gt>.1)&(gt<10)
                    if valid.any():
                        truth=float(np.median(gt[valid]))
                        error=float(pc[2])-truth
                        depth_rows.append(dict(abs_error_m=abs(error),absrel=abs(error)/truth,bias_m=error))
                details.append(dict(stamp_ns=stamp,class_name=cls,decision='propagated',track_id=tr['id'],
                    source_stamp_ns=tr['stamp'],age_s=age,instance_gt=label.get('instance_gt'),
                    wrong_id=bool(label.get('instance_gt') and tr['label'] and label['instance_gt']!=tr['label'])))
    metric=scan.replay(name,entries)
    elapsed=time.perf_counter()-start
    csv_write(ROOT/f'{name}_trace.csv',details)
    propagated=[r for r in details if r['decision']=='propagated']
    return {**comparison(name,metric,base,elapsed),**timings(scan,selected),**summarize_depth(depth_rows),
        'propagated':len(propagated),'propagated_wrong_known_id':sum(r['wrong_id'] for r in propagated),
        'propagated_unknown_gt':sum(not r.get('instance_gt') for r in propagated),
        'depth_age_p90_s':stats([r['age_s'] for r in propagated]).get('p90'),
        'ambiguous_rejected':sum(r['decision']=='ambiguous' for r in details),
        'fresh_observations':len(entries)-len(propagated),'stops':sorted(selected)}

def main():
    a,b=Scan('scan_8x3'),Scan('scan_36x1')
    base_a=a.evaluate(a.objects,a.members,a.labels)
    base_b=b.evaluate(b.objects,b.members,b.labels)
    started=time.perf_counter()
    a2=a.replay('A2_8x1',[(o,a.labels[o['obs_id']]) for o in a.original if o['frame_idx']==0])
    a2_time=time.perf_counter()-started
    baselines=[
        dict(method='A1_8x3',**base_a,**gt_stats(a),**base_depth(a)),
        dict(method='A2_8x1',**a2,**gt_stats(a,lambda f:f['frame']=='0'),**base_depth(a,frame=0),seconds=a2_time),
        dict(method='B1_36x1',**base_b,**gt_stats(b),**base_depth(b))]
    fusion_rows=[comparison('F0_production',base_b,base_b,0.)]+fusion(b,base_b)
    for row in fusion_rows:
        row.update(base_depth(b))
    score={f['stop']:image_quality(f,b.classes) for f in b.frames.values()}
    equal=set(range(0,36,3))
    quality_set=set(sorted(score,key=lambda k:(-score[k],k))[:12])
    diverse={max(range(k,k+3),key=lambda s:(score[s],-s)) for k in range(0,36,3)}
    adaptive={0}
    last=0
    for k in range(1,36):
        if k-last>=3 or (k-last>=2 and score[k]>1.25*max(.25,score[last])):
            adaptive.add(k)
            last=k
    temp=[dict(method='T1_full',**base_b,**timings(b,set(range(36))),**base_depth(b))]
    for m,sel in [('T2_every20',set(range(0,36,2))),('T2_every30',equal),('T2_adaptive',adaptive)]:
        temp.append(temporal(b,sel,m,base_b))
    view=[dict(method='full',**base_b,**timings(b,set(range(36))),**base_depth(b),stops=list(range(36)))]
    for m,sel in [('V_equal',equal),('V_quality',quality_set),('V_diverse',diverse)]:
        start=time.perf_counter()
        res=b.replay(m,[(o,b.labels[o['obs_id']]) for o in b.original if o['stop_index'] in sel])
        view.append(dict(**comparison(m,res,base_b,time.perf_counter()-start),**timings(b,sel),**base_depth(b,stops=sel),stops=sorted(sel),
                         **gt_stats(b,lambda f:int(f['stop']) in sel)))
    bias=[]
    for measured in base_b['objects']:
        center=b.centers[measured['target']]
        member=b.members[measured['id']]
        err=np.array([row_xyz(o)[:2]-center[:2] for o in member])
        dominant=np.mean(err,axis=0)
        length=np.linalg.norm(dominant)
        projection=err@dominant/max(length,1e-12)
        bias.append(dict(target=measured['target'],n=len(member),angles=len({o['stop_index'] for o in member}),
            min_xy_error_m=float(np.linalg.norm(err,axis=1).min()),
            max_xy_error_m=float(np.linalg.norm(err,axis=1).max()),
            all_on_mean_error_side=bool((projection>0).all()),
            signed_projection_min_m=float(projection.min()),signed_projection_max_m=float(projection.max())))
    csv_write(ROOT/'fusion_bias_diagnostics.csv',bias)
    csv_write(ROOT/'fusion_comparison.csv',fusion_rows)
    csv_write(ROOT/'temporal_keyframe_results.csv',temp)
    csv_write(ROOT/'viewpoint_selection.csv',view)
    csv_write(ROOT/'baseline_comparison.csv',baselines)
    put(ROOT/'methods_summary.json',dict(baselines=baselines,fusion=fusion_rows,temporal=temp,view=view))
if __name__=='__main__':
    main()

