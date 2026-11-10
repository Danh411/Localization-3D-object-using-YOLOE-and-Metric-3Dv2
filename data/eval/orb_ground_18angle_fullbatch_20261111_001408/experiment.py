import math,sys,time,re
from collections import Counter
import numpy as np
import cv2
from orb import ROOT,PREV,TARGET_CLASSES,estimate
import common,ground
from common import Scan,csv_write,put,read,load_csv,stats,gt_stats,connect,queries,erode_mask,diff_angle
from angles import angles,project,pose

def make_scan(path,mesh=False):
    s=Scan(str(path))
    if mesh:
        s.centers={key:np.array(v['mesh_aabb_center_world_m'])
                   for key,v in read(path/'mesh_centers.json').items()}
    return s

def optical(scan,f,xyz):
    return scan.rot(f).T@(xyz-np.array(f['tf']['translation']))

def observation(scan,f,d,xyz,valid_ratio=None):
    p=optical(scan,f,xyz)
    if not np.isfinite(p).all() or not .1<p[2]<10:
        return None
    o=dict(class_name=d['class_name'],confidence=d['confidence'],truncated=int(d['truncated']),
           depth_m=float(p[2]),range_m=float(np.linalg.norm(p)),stop_index=f['stop'],
           frame_idx=f['frame_idx'],yaw_rad=f['yaw'],stamp_ns=f['stamp_ns'],valid_ratio=valid_ratio)
    o.update({f'bbox_{k}':v for k,v in zip(('x1','y1','x2','y2'),d['bbox_xyxy'])})
    o.update({f'cam_{k}':float(v) for k,v in zip('xyz',p)})
    o.update({f'world_{k}':float(v) for k,v in zip('xyz',xyz)})
    return o

def pick(orb,corrected,base,orb_reason,ground_status):
    if orb is not None:
        return orb,'ORB',''
    if corrected is not None:
        return corrected,'GROUND','orb:'+orb_reason
    if base is not None:
        return base,'METRIC3D','orb:'+orb_reason+';ground:'+ground_status
    return None,'UNAVAILABLE','orb:'+orb_reason+';ground:'+ground_status+';metric3d:missing'

def run_floor(s,model):
    fits={}; rows=[]
    for f in s.frames.values():
        if not f['tf']:
            rows.append(dict(stop=f['stop'],stamp_ns=f['stamp_ns'],status='GROUND_UNAVAILABLE',reason='TF'))
            continue
        with s.frame_archive(f) as z:
            info=ground.check_frame(model,z['rgb'],z['gt_depth'],z['pred_depth'],f['K'],s.rot(f),
                np.array(f['tf']['translation']))
        k,status=info['rgb']
        if status=='accepted':
            fits[f['stamp_ns']]=float(k)
        rows.append(dict(stop=f['stop'],stamp_ns=f['stamp_ns'],status='accepted' if status=='accepted' else 'GROUND_UNAVAILABLE',
                         reason=status,**info))
    csv_write(s.path/'ground_plane_feasibility.csv',rows)
    return fits,rows

def score_surface(s,points):
    # Only after geometry selection. Both semantic pixels must match the same GT instance.
    cached={}
    tags={(int(r['stamp_ns']),int(r['det_index'])):r for r in s.annotations}
    for r in points:
        a,b=r['stamp_a'],r['stamp_b']
        row_a=tags[(a,r['det_a'])]
        row_b=tags[(b,r['det_b'])]
        if row_a['status']!='true' or row_b['status']!='true' or row_a['instance_gt']!=row_b['instance_gt']:
            r['score_status']='not_same_gt_instance'
            continue
        target=row_a['instance_gt']
        values=[]
        for stamp,suffix in ((a,'a'),(b,'b')):
            if stamp not in cached:
                with s.frame_archive(s.frames[stamp]) as z:
                    cached[stamp]=(z['gt_depth'],z['labels_rgb'][...,2])
            z,lab=cached[stamp]
            u,v=int(round(r['u_'+suffix])),int(round(r['v_'+suffix]))
            if not (0<=u<1280 and 0<=v<720 and lab[v,u]==s.gt[target]['semantic_label'] and .1<z[v,u]<10):
                break
            pc=optical(s,s.frames[stamp],np.array([r[k] for k in 'xyz']))
            values.append(abs(float(pc[2])-float(z[v,u])))
        if len(values)!=2:
            r['score_status']='feature_pixel_gt_unavailable'
            continue
        r.update(score_status='scored',target=target,abs_axial_a_m=values[0],abs_axial_b_m=values[1])
    csv_write(s.path/'orb_points.csv',points)
    return {name:stats([r[k] for r in points if r.get('target')==name for k in ('abs_axial_a_m','abs_axial_b_m')])
            for name in s.gt}

def replay_validate(s,name,entries):
    result=s.replay(name,[(o,label) for o,label,mode in entries])
    with connect(s.path/f'{name}.sqlite') as c:
        assert c.execute('pragma foreign_key_check').fetchone() is None
        obs=list(c.execute('select * from observations order by obs_id'))
        assert len(obs)==len(entries)
        objects=queries.list_objects(c,s.id,None,'confirmed')
        source_counts=Counter()
        for o in objects:
            members=[x for x in obs if x['object_id']==o['object_id']]
            assert len(members)==o['n_obs']
            expected=sum(x['confidence'] for x in members)
            assert math.isclose(o['conf_sum'],expected,abs_tol=1e-10)
            assert math.isclose(o['conf_mean'],expected/len(members),abs_tol=1e-10)
            for x in members:
                source_counts[entries[x['obs_id']-1][2]]+=1
            cls=o['class_name']
            nearest=queries.nearest_object(c,s.id,o['x'],o['y'],cls)
            assert math.dist((nearest['x'],nearest['y']),(o['x'],o['y']))<1e-9
            nearby=queries.objects_in_radius(c,s.id,o['x'],o['y'],.01,cls)
            assert o['object_id'] in {q['object_id'] for q in nearby}
            base=tuple(s.cfg['camera']['base_xyz'][:2])
            p=queries.get_approach_point(c,o['object_id'],base,.6)
            assert math.isclose(math.dist((p['x'],p['y']),(o['x'],o['y'])),
                                min(.6,math.dist(base,(o['x'],o['y']))),abs_tol=1e-8)
        result.update(all_confirmed=len(objects),confirmed_observation_sources=dict(source_counts))
        if name=='P0_metric':
            with connect(s.path/'replay_A.sqlite') as live:
                for table in ('observations','objects'):
                    fields=[r['name'] for r in c.execute('pragma table_info('+table+')')
                            if r['name'] not in ('created_at','updated_at')]
                    q=f"select {','.join(fields)} from {table} order by {fields[0]}"
                    assert list(c.execute(q))==list(live.execute(q)),table
    return result

def score_entries(s,branches):
    truth={}
    observations=[]
    summary={}
    for name,entries in branches.items():
        errors=[]
        for o,label,mode in entries:
            if label['status']!='true':
                continue
            target=label['instance_gt']
            k=(o['stamp_ns'],int(label['det_index']))
            if k not in truth:
                f=s.frames[k[0]]
                with s.frame_archive(f) as z:
                    mask=np.unpackbits(z[label['mask']],axis=1,count=1280).astype(bool)
                    valid=erode_mask(mask)&(z['labels_rgb'][...,2]==s.gt[target]['semantic_label'])
                    depth=z['gt_depth']
                    valid &= np.isfinite(depth)&(depth>.1)&(depth<10)
                    truth[k]=float(np.median(depth[valid])) if valid.any() else None
            gt=truth[k]
            e=np.array([o['world_'+v] for v in 'xyz'])-s.centers[target]
            er=None if gt is None else o['depth_m']-gt
            row=dict(branch=name,target=target,stop=o['stop_index'],stamp_ns=k[0],det_index=k[1],source=mode,
                     depth_m=o['depth_m'],gt_surface_z_m=gt,signed_depth_m=er,
                     absrel=abs(er)/gt if gt is not None else None,
                     xy_m=float(np.linalg.norm(e[:2])),xyz_m=float(np.linalg.norm(e)))
            errors.append(row)
        observations.extend(errors)
        valid=[r for r in errors if r['absrel'] is not None]
        summary[name]=dict(n=len(errors),depth_n=len(valid),depth_absrel=float(np.mean([r['absrel'] for r in valid])) if valid else None,
            depth_mae_m=float(np.mean([abs(r['signed_depth_m']) for r in valid])) if valid else None,
            depth_bias_m=float(np.mean([r['signed_depth_m'] for r in valid])) if valid else None,
            representative_xy=stats([r['xy_m'] for r in errors]),representative_xyz=stats([r['xyz_m'] for r in errors]))
    csv_write(s.path/'object_observation_scores.csv',observations)
    return summary

def cached40(s,base,tags):
    tracks=[]; rows=[]; trace=[]
    for stamp,f in s.frames.items():
        if not f['tf']:
            continue
        if f['stop']%2==0:
            for key,o in base.items():
                if key[0]!=stamp:
                    continue
                label=tags[key]
                rows.append((o,label,'METRIC3D'))
                if o['truncated']:
                    continue
                xyz=np.array([o['world_'+k] for k in 'xyz'])
                options=[t for t in tracks if t['cls']==o['class_name'] and np.linalg.norm(xyz-t['xyz'])<.35]
                if len(options)>1:
                    continue
                if options:
                    t=options[0]
                else:
                    t={'cls':o['class_name'],'id':len(tracks)}
                    tracks.append(t)
                t.update(xyz=xyz,stamp=stamp,yaw=f['joint_yaw_rad'],label=label)
            continue
        R,t,_,P=pose(s,f)
        with s.frame_archive(f) as z:
            for j,d in enumerate(f['detections']):
                if d['truncated']:
                    continue
                label=tags[(stamp,j)]
                mask=np.unpackbits(z[d['mask']],axis=1,count=1280)
                options=[]
                for tr in tracks:
                    age=(stamp-tr['stamp'])/1e9
                    if tr['cls']!=d['class_name'] or age>30 or diff_angle(tr['yaw'],f['joint_yaw_rad'])>math.radians(40):
                        continue
                    pixel,depth=project(P,tr['xyz'])
                    if not .1<depth<10. or not np.isfinite(pixel).all():
                        continue
                    u,v=np.rint(pixel).astype(int)
                    if 0<=u<1280 and 0<=v<720 and mask[v,u]:
                        options.append((tr,age))
                if len(options)!=1:
                    trace.append(dict(stamp_ns=stamp,stop=f['stop'],det_index=j,decision='ambiguous' if options else 'no_track'))
                    continue
                tr,age=options[0]
                o=observation(s,f,d,tr['xyz'])
                if o:
                    rows.append((o,label,'REUSED_POSITION'))
                    a,b=tr['label'],label
                    same=a['instance_gt']==b['instance_gt'] if a['status']==b['status']=='true' else None
                    trace.append(dict(stamp_ns=stamp,stop=f['stop'],det_index=j,decision='reused',track=tr['id'],
                        depth_age_s=age,same_gt=same,yaw_delta_deg=math.degrees(diff_angle(tr['yaw'],f['joint_yaw_rad']))))
    csv_write(s.path/'key40_trace.csv',trace)
    return rows,trace

def visuals(s,branches,point_rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,6))
    for key,center in s.centers.items():
        ax.scatter(*center[:2],marker='x',c='black')
        ax.annotate(key,center[:2])
    for name in ('P0_metric','P1_orb_A','P1_orb_B','P2_ground','P3_combined'):
        rows=branches[name]['objects']
        ax.scatter([r['xyz'][0] for r in rows],[r['xyz'][1] for r in rows],label=name,s=22,alpha=.7)
    ax.set_aspect('equal')
    ax.set_xlabel('World X (m)')
    ax.set_ylabel('World Y (m)')
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(s.path/'gt_vs_sqlite.png',dpi=145)
    plt.close(fig)
    pair=Counter((r['stamp_a'],r['stamp_b'],r['det_a'],r['det_b']) for r in point_rows).most_common(1)
    if pair:
        (a,b,i,j),_=pair[0]
        views=[]
        for k in (a,b):
            with s.frame_archive(s.frames[k]) as packet:
                views.append(cv2.cvtColor(packet['rgb'],cv2.COLOR_RGB2BGR))
        merged=np.hstack(views)
        for r in [r for r in point_rows if (r['stamp_a'],r['stamp_b'],r['det_a'],r['det_b'])==(a,b,i,j)][::3]:
            aa=(round(r['u_a']),round(r['v_a']))
            bb=(1280+round(r['u_b']),round(r['v_b']))
            cv2.line(merged,aa,bb,(30,210,240),1)
        cv2.imwrite(str(s.path/'orb_matches.jpg'),cv2.resize(merged,(1600,450)))

def analyze(name):
    s=make_scan(ROOT/name,mesh=True)
    common.ROOT=s.path
    assert len(s.frames)==18
    estimates,causal,reasons,pairs,points,orb_s=estimate(s)
    csv_write(s.path/'orb_pairs.csv',pairs)
    surface=score_surface(s,points)
    fits,floor_rows=run_floor(s,ground.floor_model())
    tags={(int(r['stamp_ns']),int(r['det_index'])):r for r in s.annotations}
    base={(int(r['stamp_ns']),int(r['det_index'])):s.original[int(r['A_obs_id'])-1]
          for r in s.annotations if r['A_obs_id']}
    branches={key:[] for key in ('P0_metric','ORB_A_only','ORB_B_only','P1_orb_A','P1_orb_B','P2_ground','P3_combined','S_key40','S_on_demand')}
    choices=[]; schedule=[]; orb_availability=[]
    for stamp,f in s.frames.items():
        jobs=[(stamp,j) for j in range(len(f['detections']))]
        require=any(k not in causal for k in jobs)
        schedule.append(dict(stop=f['stop'],stamp_ns=stamp,detections=len(jobs),causal_orb=sum(k in causal for k in jobs),
                             metric3d_needed=require))
        for k in jobs:
            j=k[1]; label=tags[k]; d=f['detections'][j]
            m=base.get(k)
            e=estimates.get(k)
            ecausal=causal.get(k)
            why=reasons.get(k,'not_target_or_no_tf')
            a=observation(s,f,d,e['A']) if e else None
            b=observation(s,f,d,e['B']) if e else None
            c=observation(s,f,d,ecausal['B']) if ecausal else None
            floor=None
            floor_status='GROUND_UNAVAILABLE'
            if m and stamp in fits and f['tf']:
                p=np.array([m['cam_'+axis] for axis in 'xyz'])*fits[stamp]
                xyz=s.rot(f)@p+np.array(f['tf']['translation'])
                floor=observation(s,f,d,xyz,m['valid_ratio'])
                floor_status='accepted' if floor is not None else 'range_reject'
            options={
                'P0_metric':(m,'METRIC3D' if m else 'UNAVAILABLE','' if m else 'metric3d:missing'),
                'ORB_A_only':(a,'ORB' if a else 'UNAVAILABLE',why),
                'ORB_B_only':(b,'ORB' if b else 'UNAVAILABLE',why),
                'P1_orb_A':pick(a,None,m,why,'disabled'),
                'P1_orb_B':pick(b,None,m,why,'disabled'),
                'P2_ground':pick(None,floor,m,'disabled',floor_status),
                'P3_combined':pick(b,floor,m,why,floor_status),
                'S_on_demand':pick(c,floor if require else None,m if require else None,
                                    'no_causal_orb',floor_status)}
            for branch,(o,mode,reason) in options.items():
                choices.append(dict(branch=branch,stamp_ns=stamp,stop=f['stop'],det_index=j,class_name=d['class_name'],
                    target_gt=label['instance_gt'],match=label['status'],source=mode,reason=reason,orb_points=e['n'] if e else 0))
                if o:
                    branches[branch].append((o,label,mode))
            if d['class_name'] in TARGET_CLASSES:
                orb_availability.append(dict(stamp_ns=stamp,stop=f['stop'],det_index=j,class_name=d['class_name'],
                    target_gt=label['instance_gt'],match=label['status'],status=why,causal_available=bool(c),
                    n_points=e['n'] if e else 0,z=e['z'] if e else None,
                    uv=e['uv'] if e else None,axial_mad=e['axial_mad'] if e else None,
                    orb_a=e['A'].tolist() if e else None,orb_b=e['B'].tolist() if e else None))
    branches['S_key40'],trace=cached40(s,base,tags)
    csv_write(s.path/'fallback_trace.csv',choices)
    csv_write(s.path/'orb_object_localization.csv',orb_availability)
    csv_write(s.path/'depth_schedule.csv',schedule)
    csv_write(s.path/'detection_by_angle.csv',angles(s))
    score=score_entries(s,branches)
    summaries={}; runtime=[]
    for name,entries in branches.items():
        start=time.perf_counter()
        metric=replay_validate(s,name,entries)
        replay_s=time.perf_counter()-start
        summaries[name]={**metric,**score[name], 'source_counts':dict(Counter(m for _,_,m in entries))}
        selected={f['stop'] for f in s.frames.values()}
        if name=='S_key40':
            selected={x for x in selected if x%2==0}
        if name=='S_on_demand':
            selected={r['stop'] for r in schedule if r['metric3d_needed']}
        if name in ('ORB_A_only','ORB_B_only'):
            selected=set()
        runtime.append(dict(branch=name,replay_query_s=replay_s,depth_calls=len(selected),
            depth_time_est_s=sum(f['timings_ms']['depth_ms'] for f in s.frames.values() if f['stop'] in selected)/1000,
            orb_shared_s=orb_s if 'orb' in name.lower() or name in ('P3_combined','S_on_demand') else 0,
            floor_extra_cpu_s=sum(r.get('rgb_floor_s',0) for r in floor_rows) if name in ('P2_ground','P3_combined','S_on_demand') else 0))
    t=(s.path/'action.log').read_text()
    replay=read(s.path/'summary.json')
    result=dict(scan=name,id=s.id,frames=len(s.frames),observations=len(s.original),
        ros_s=float(re.search(r'duration_s:\s*([\d.]+)',t)[1]),timings_ms=replay['timings_ms'],
        capture_service_s=sum(r['elapsed_s'] for r in s.stops),max_yaw_error_deg=replay['max_command_error_deg'],
        max_joint_skew_ms=replay['max_joint_skew_ms'],wire_tf_missing=replay['wire_tf_missing'],
        visibility=gt_stats(s),targets=replay['targets'],branches=summaries,runtime=runtime,orb_s=orb_s,
        floor_frames=len(fits),floor_oracle_frames=sum(r.get('oracle',(1.,''))[1]=='accepted' for r in floor_rows),
        optical_radius_m=stats([float(np.linalg.norm(np.array(f['tf']['translation'])[:2]-np.array(s.cfg['camera']['base_xyz'])[:2]))
                                for f in s.frames.values() if f['tf']]),
        reused=sum(r['decision']=='reused' for r in trace),
        reuse_age_p90=stats([r['depth_age_s'] for r in trace if r['decision']=='reused']).get('p90'),
        reuse_wrong=sum(r.get('same_gt') is False for r in trace),surface=surface,
        pair_counts=dict(Counter(r['status'] for r in pairs)),n_points=len(points),
        surface_scored=sum(r.get('score_status')=='scored' for r in points))
    csv_write(s.path/'runtime.csv',runtime)
    csv_write(s.path/'pipeline_comparison.csv',[dict(branch=k,**v) for k,v in summaries.items()])
    visuals(s,summaries,points)
    put(s.path/'experiment_summary.json',result)
    print(name,'done',result['pair_counts'],result['floor_frames'],flush=True)

def subset():
    common.ROOT=ROOT
    old=make_scan(PREV/'scan_36x1')
    historical=read(PREV/'methods_summary.json')['baselines']
    rows=[{'name':'ROS 8x3 prior',**historical[0],'ros_s':180.06824203},
          {'name':'ROS 36x1 prior',**historical[2],'ros_s':308.51004713}]
    for step in (3,2,1):
        start=time.perf_counter()
        name=f'Equal_{360//(step*10)}'
        # 12/18/36 stops, all from the cached 36-view run.
        result=old.replay(name,[(o,old.labels[o['obs_id']]) for o in old.original if o['stop_index']%step==0])
        rows.append(dict(name=name,**result,**gt_stats(old,lambda f:int(f['stop'])%step==0),
                         replay_s=time.perf_counter()-start))
    csv_write(ROOT/'angle_subset_comparison.csv',rows)
    put(ROOT/'angle_subset_summary.json',rows)

if __name__=='__main__':
    if sys.argv[1]=='subset':
        subset()
    else:
        analyze(sys.argv[1])

