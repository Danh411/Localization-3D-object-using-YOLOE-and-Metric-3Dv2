import sys
from pathlib import Path
root=Path(__file__).resolve().parent
previous=root.parent/'metric3d_depth_calibration_20261110_184655'
src=(previous/'evaluate_rooms.py').read_text()
# Reuse the previously verified checkpoint loader and production imports.
src=src[src.index('import csv'):src.index('lock=root/')]
exec(compile(src,str(previous/'evaluate_rooms.py'),'exec'))
src=(previous/'evaluate_rooms.py').read_text()
exec(compile(src[src.index('cfg=yaml'):src.index("print('Production models ready")],str(previous/'evaluate_rooms.py'),'exec'))
sys.path.insert(0,str(repo/'src/object_db'))
from object_db import association, db
from perception.core.pipeline import process

folder=root/'kitchen_probe'
design=read(folder/'design.json')
records=read(folder/'capture_index.json')
assert len(records)==12
rows=[]
cup_dbs={}
for name in ('cup_edge','cup_full'):
    con=db.open_db(folder/(name+'.sqlite'))
    db.create_scan(con,name,cfg,'Kitchen probe')
    cup_dbs[name]=con
for f in records:
    cond=f['condition']
    cls='cup' if cond.startswith('cup') else 'book'
    with np.load(folder/'frames'/f['file'],allow_pickle=False) as data:
        rgb,lab,K=[data[k] for k in ('rgb','labels_rgb','K')]
        assert int(data['stamp_ns'])==f['stamp_ns']
    if cls=='cup':
        out=process(rgb,K,detector,estimator,cfg)
        dets=out['observations']+out['rejected']
    else:
        dets=detector.detect(rgb)
    target=lab[...,2]==f['label']
    assert target.any()
    yy,xx=np.where(target)
    ious=[np.count_nonzero(d['mask']&target)/np.count_nonzero(d['mask']|target) for d in dets]
    best=max(zip(ious,dets),key=lambda item:item[0],default=(0,None))
    true=[(iou,d) for iou,d in zip(ious,dets) if d['class_name']==cls and iou>=.5]
    wrong=[d['class_name'] for iou,d in zip(ious,dets) if d['class_name']!=cls and iou>=.5]
    d=max(true,key=lambda item:item[0])[1] if true else None
    row={'condition':cond,'rep':f['rep'],'yaw_deg':f['relative_yaw_deg'],'file':f['file'],'visible_px':int(target.sum()),
        'gt_bbox':[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],'issues':','.join(f['issues']),
        'correct':bool(true),'wrong_classes':wrong,'missed':not true,'best_iou':best[0],
        'best_class':best[1]['class_name'] if best[0]>0 else None,
        'best_conf':best[1]['confidence'] if best[0]>0 else None,
        'true_conf':d['confidence'] if d else None,'bbox':d['bbox_xyxy'] if d else None,
        'truncated':is_truncated(d['bbox_xyxy'],1280,720,cfg['fusion']['border_px']) if d else None,
        'valid_depth_ratio':d.get('valid_depth_ratio') if d else None}
    if cls=='cup':
        for det in out['observations']:
            # Replay the complete probe observation stream. GT is used only in scoring above.
            p=optical_to_world(det['p_cam'],f['optical_heading_rad'],f['rig_pose_observed'][0],(.05,0,0))
            association.add_observation(cup_dbs[cond],cond,{**det,'p_world':p.tolist(),
                'stamp_ns':f['stamp_ns'],'stop_index':0,'frame_idx':f['rep']},cfg['assoc'],cfg['fusion'])
    view=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
    cv2.rectangle(view,(xx.min(),yy.min()),(xx.max(),yy.max()),(0,220,255),2)
    cv2.putText(view,f"{cond} yaw {f['relative_yaw_deg']} correct {bool(true)}",(20,38),0,1,(0,220,255),2)
    cv2.imwrite(str(folder/(Path(f['file']).stem+'.jpg')),cv2.resize(view,(640,360)))
    print(row,flush=True)
    rows.append(row)
summary={}
for cond,con in cup_dbs.items():
    result=association.run_association_pass(con,cond,cfg['assoc'])
    db.finish_scan(con,cond)
    objects=[dict(o) for o in con.execute("SELECT * FROM objects WHERE class_name='cup'")]
    summary[cond]={'result':result,'objects':objects,
        'confirmed':any(o['status']=='confirmed' and o['n_obs']>=3 for o in objects)}
    con.close()
for cond in ('book_1','book_alt'):
    selected=[r for r in rows if r['condition']==cond]
    summary[cond]={'n':len(selected),'correct':sum(r['correct'] for r in selected),
                   'wrong':sum(bool(r['wrong_classes']) for r in selected)}
csvfile(root/'book_asset_test.csv',[r for r in rows if r['condition'].startswith('book')])
csvfile(root/'cup_visibility_test.csv',[r for r in rows if r['condition'].startswith('cup')])
put(root/'kitchen_probe_summary.json',summary)

