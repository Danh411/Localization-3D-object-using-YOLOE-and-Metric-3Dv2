from common import *
from methods import comparison,summarize_depth
import hashlib,re
from datetime import datetime
from zoneinfo import ZoneInfo

def action_time(scan):
    text=(scan.path/'action.log').read_text()
    assert 'status: SUCCEEDED' in text
    return float(re.search(r'duration_s:\s*([\d.]+)',text)[1])

def verify_queries(scan):
    start=time.perf_counter()
    with connect(scan.path/'replay_A.sqlite') as c:
        confirmed=queries.list_objects(c,scan.id,None,'confirmed')
        base=tuple(scan.cfg['camera']['base_xyz'][:2])
        for o in confirmed:
            cls=o['class_name']
            assert o['object_id'] in {r['object_id'] for r in queries.list_objects(c,scan.id,cls,'confirmed')}
            nearby=queries.objects_in_radius(c,scan.id,o['x'],o['y'],.01,cls)
            assert o['object_id'] in {q['object_id'] for q in nearby}
            near=queries.nearest_object(c,scan.id,o['x'],o['y'],cls)
            assert math.dist((near['x'],near['y']),(o['x'],o['y']))<1e-10
            expected=[r['confidence'] for r in scan.members[o['object_id']]]
            assert math.isclose(o['conf_sum'],sum(expected),abs_tol=1e-10)
            assert math.isclose(o['conf_mean'],sum(expected)/len(expected),abs_tol=1e-10)
            approach=queries.get_approach_point(c,o['object_id'],base,.6)
            point=(approach['x'],approach['y'])
            assert math.isclose(math.dist(point,(o['x'],o['y'])),min(.6,math.dist(base,(o['x'],o['y']))),abs_tol=1e-8)
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('PRAGMA foreign_key_check').fetchone() is None
    return len(confirmed),time.perf_counter()-start

def geometry(scan,base):
    scales=read(ROOT/'floor_wire.json')
    rows=[]
    start=time.perf_counter()
    for o in scan.original:
        f=scan.frames[o['stamp_ns']]
        k=scales.get(str(o['stamp_ns']),{}).get('rgb',1.)
        pc=np.array([o['cam_'+axis] for axis in 'xyz'])
        z=pc[2]*k
        if .1<z<10. and k!=1.:
            pc*=k
            w=scan.rot(f)@pc+np.array(f['tf']['translation'])
            r={**o,'depth_m':float(np.float32(z)),'range_m':float(np.float32(np.linalg.norm(pc)))}
            r.update({f'cam_{a}':float(v) for a,v in zip('xyz',pc)})
            r.update({f'world_{a}':float(v) for a,v in zip('xyz',w)})
        else:
            r=o
        rows.append((r,scan.labels[o['obs_id']]))
    result=scan.replay('P3_ground_rgb',rows)
    metric=[r for r in load_csv(ROOT/'ground_plane_correction.csv')
            if r['world']=='scan_36x1' and r['method']=='rgb']
    score=summarize_depth([{**r,'bias_m':r['bias']} for r in metric])
    floor_s=sum(float(r['rgb_floor_s']) for r in load_csv(ROOT/'ground_plane_feasibility.csv') if r['scan']=='scan_36x1')
    return {**comparison('P3_ground_rgb',result,base,time.perf_counter()-start),**score,'floor_extra_cpu_s':floor_s}

def pass_metric(r):
    return (r['depth_absrel'] if r.get('depth_absrel') is not None else 1.)<=.15 and r.get('xy_median',99)<=.30 and r.get('xy_p90',99)<=.60 and r['recall']>=.8 and (r.get('precision') or 0)>=.85 and r['duplicate']/max(1,r['confirmed']+r['duplicate'])<=.10

def model_pick(rows,base):
    viable=[r for r in rows if r['confirmed']>=base['confirmed'] and r.get('xy_median',99)<=base.get('xy_median',0)-.02
        and r['wrong']<=base['wrong'] and r['duplicate']<=base['duplicate']]
    return min(viable,key=lambda r:r['xy_median']) if viable else None

def main():
    a,b=Scan('scan_8x3'),Scan('scan_36x1')
    raw=read(ROOT/'methods_summary.json')
    base=raw['baselines'][2]
    ground=geometry(b,base)
    f=model_pick([r for r in raw['fusion'][1:] if r['method']!='F3_RANSAC'],base)
    t=model_pick(raw['temporal'][1:],base)
    v=model_pick(raw['view'][1:],base)
    f_display=f or min(raw['fusion'][1:],key=lambda r:r.get('xy_median',99))
    v_display=v or min(raw['view'][1:],key=lambda r:(-r['confirmed'],r.get('xy_median',99),r['depth_calls']))
    rows=[]
    for key,r in [('P0',raw['baselines'][0]),('A2',raw['baselines'][1]),('P1',base),('P2',f_display),('P3',ground),('P4',t),('P5',v_display)]:
        if r is None:
            rows.append(dict(branch=key,classification='FAIL',reason='no reduction of at least 2 cm in final median XY without degrading recall or records'))
        else:
            classification='PASS_TARGET' if pass_metric(r) else 'MEASURED_BELOW_TARGET'
            if key=='P2' and not f:
                classification='FAIL_GAIN_GATE'
            if key=='P3' and not any("accepted" in x['rgb'] for x in load_csv(ROOT/'ground_plane_feasibility.csv') if x['scan']=='scan_36x1'):
                classification='FALLBACK_ALL_FRAMES'
            if key=='P5' and not v and r['confirmed']==base['confirmed'] and r['xy_median']==base['xy_median']:
                classification='MEASURED_COST_SAVINGS'
            rows.append(dict(branch=key,**r,classification=classification))
    positive=[r['method'] for r in (f,t,v) if r]
    if ground['confirmed']>=base['confirmed'] and ground.get('xy_median',99)<=base.get('xy_median',0)-.02:
        positive.append(ground['method'])
    rows.append(dict(branch='P6',classification='NOT TESTED',reason='only one branch passed the locked XY-gain gate; no nonconflicting pair advanced to an independent layout',
                     candidates=positive))
    runtimes=[]
    gpu=load_csv(ROOT/'gpu_samples.csv')
    timezone=ZoneInfo('Asia/Ho_Chi_Minh')
    samples=[(datetime.strptime(r['timestamp'].strip(),'%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone).timestamp(),
              int(r['memory_used_mib'].strip())) for r in gpu if r.get('memory_used_mib')]
    for scan in (a,b):
        s=read(scan.path/'summary.json')
        frames=list(scan.frames.values())
        capture=sum(st['elapsed_s'] for st in scan.stops)
        settle=1.5*len(scan.stops)
        total=action_time(scan)
        confirmed,query_time=verify_queries(scan)
        started=int(scan.id.split('_')[-1])
        device=[mem for epoch,mem in samples if started<=epoch<=started+total]
        runtimes.append(dict(scan=scan.path.name,stops=len(scan.stops),frames=len(frames),scan_s=total,
            configured_settle_s=settle,capture_service_s=capture,controller_other_s=total-capture-settle,
            yolo_s=s['timings_ms']['yolo_ms']/1000,depth_s=s['timings_ms']['depth_ms']/1000,
            post_s=s['timings_ms']['post_ms']/1000,replay_assoc_sqlite_s=s['branches']['A']['association_sqlite_s'],
            offline_query_checks_s=query_time,confirmed_unscoped=confirmed,device_peak_sampled_mib=max(device,default=None),
            wire_projection_missing=len(s['wire_tf_missing']),observations=s['live_observations']))
    csv_write(ROOT/'runtime_summary.csv',runtimes)
    csv_write(ROOT/'pipeline_comparison.csv',rows)
    put(ROOT/'pipeline_summary.json',dict(branches=rows,runtime=runtimes,positive=positive))
    print('Validated both SQLite, confidence, query and approach',flush=True)

if __name__=='__main__':
    main()

