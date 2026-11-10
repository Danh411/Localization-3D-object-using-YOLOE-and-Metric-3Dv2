from pathlib import Path
from collections import Counter
import csv, hashlib, json, math, time, xml.etree.ElementTree as ET
import cv2, numpy as np

root=Path(r'D:\loc3d_ws\data\eval\metric3d_depth_calibration_20261110_184655')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
meta=json.loads((root/'rooms.json').read_text())
lock=json.loads((root/'locked.json').read_text())
assert sha(root/'locked.json')==(root/'locked.sha256').read_text().strip()
rooms={}
all_hashes={}
for name,cfg in meta['worlds'].items():
    room=root/('holdout_'+name)
    index=json.loads((room/'capture_index.json').read_text())
    native=ET.parse(room/'world.sdf').getroot().find('world')
    original=ET.parse(Path('D:/'+cfg['source_world'].removeprefix('/mnt/d/'))).getroot().find('world')
    assert len(index)==16
    canvas=[]
    for row in sorted(index,key=lambda r:(r['target'],r['distance_m'])):
        path=room/'frames'/row['file']
        all_hashes[path.relative_to(root).as_posix()]=sha(path)
        with np.load(path,allow_pickle=False) as z:
            rgb=z['rgb']
            lab=z['labels_rgb']
            gt=z['gt_depth']
            k=z['K']
            assert row['stamp_ns']==int(z['stamp_ns'])
        y,x=np.where(lab[...,2]==row['label'])
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        assert np.count_nonzero(lab[...,2]==row['label'])==row['visible_pixels']
        assert int(((lab[...,2]==row['label'])&np.isfinite(gt)&(gt>.1)&(gt<10)).sum())==row['gt_valid_pixels']
        if len(y):
            row['preflight_median_luma']=float(np.median(gray[y,x]))
        else: row['preflight_median_luma']=None
        im=rgb[...,::-1].copy()
        if len(y):
            cv2.rectangle(im,(int(x.min()),int(y.min())),(int(x.max()),int(y.max())),(25,200,255),2)
        msg=f"{row['target']} {row['distance_m']:.2f} m {row['relative_yaw_deg']} deg"
        if row['issues']: msg+=' QA: '+','.join(row['issues'])
        cv2.rectangle(im,(0,0),(1280,36),(25,25,25),-1)
        cv2.putText(im,msg,(16,26),cv2.FONT_HERSHEY_SIMPLEX,.8,(240,240,240),2,cv2.LINE_AA)
        canvas.append(cv2.resize(im,(480,270)))
    cv2.imwrite(str(room/'qa_contact_sheet.jpg'),np.vstack([np.hstack(canvas[i:i+4]) for i in range(0,16,4)]))
    for f in ('world.sdf','design.json','capture_index.json'):
        all_hashes[(room/f).relative_to(root).as_posix()]=sha(room/f)
    rooms[name]={'camera_base_xyz_yaw':cfg['camera_xyz_yaw'],'conditions':cfg['conditions'],
                 'world_sha256':sha(room/'world.sdf'),'local_source_sha256':sha(Path('D:/'+cfg['source_world'].removeprefix('/mnt/d/'))),
                 'source_plugins':[e.get('filename') for e in original.findall('plugin')],
                 'source_sensors':len(original.findall('.//sensor')),
                 'problems':dict(Counter(i for row in index for i in row['issues'])),
                 'n':len(index),'all_exact_sensor_quadruplets':True,
                 'max_pan_stamp_gap_ms':max(abs(r['stamp_ns']-r['pan_stamp_ns']) for r in index)/1e6,
                 'min_median_target_luma':min(r['preflight_median_luma'] for r in index if r['preflight_median_luma'] is not None),
                 'camera_K':k.tolist()}
save(root/'capture_qa.json',rooms)
save(root/'capture_hashes.json',all_hashes)
# Isolate scalar math cost from model, rendering and I/O.
clock={}
lo,hi=lock['output_clip_m']
values=(.61,.93,1.37,2.08,1.67,2.2)
n=250000
for name,(a,b) in lock['models'].items():
    rounds=[]
    for _ in range(5):
        start=time.perf_counter_ns()
        for j in range(n):
            z=values[j%len(values)]
            if name!='A':
                z=min(hi,max(lo,a*z+b))
        rounds.append((time.perf_counter_ns()-start)/n)
    clock[name]={'median_ns_per_z':float(np.median(rounds)),'repeats':5,'iterations_per_repeat':n}
save(root/'scalar_timing.json',clock)
print(json.dumps(rooms,indent=2))
print(clock)
