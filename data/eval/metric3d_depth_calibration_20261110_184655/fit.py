import csv,hashlib,json,itertools
from pathlib import Path
from datetime import datetime,timezone
import cv2
import numpy as np
root=Path(__file__).resolve().parent
src=root.parent/'metric3d_hypotheses_20261110_144943'
baseline=root.parent/'kitchen_reference_20261110_134600_sync'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for path,h in json.loads((src/'sample_sha256.json').read_text()).items():
    assert sha(src/path)==h,path
m=json.loads((baseline/'manifest.json').read_text())
assert all(sha(baseline/name)==info['sha256'] for name,info in m['files'].items())
assert sha(baseline/m['source_archive']['path'])==m['source_archive']['sha256']
cases=json.loads((src/'capture_index.json').read_text())
assert len(cases)==27
data=[]
for case in cases:
    f=case['file']
    with np.load(src/'controlled_frames'/f,allow_pickle=False) as a:
        mask=a['labels_rgb'][...,2]==case['label']
        gt=a['gt_depth']
        assert int(a['stamp_ns'])==case['stamp_ns']
        assert np.allclose(a['K'],[914.0147013559828,914.0147013559828,640,360],rtol=0,atol=1e-8)
    k=max(3,int(round(.05*np.sqrt(mask.sum()))))
    support=cv2.erode(mask.astype(np.uint8),np.ones((k,k),np.uint8))>0
    pred=np.load(src/'predictions'/f.replace('.npz','.npy'),allow_pickle=False)
    keep=support&np.isfinite(pred)&np.isfinite(gt)&(pred>.1)&(pred<10)&(gt>.1)&(gt<10)
    x,y=pred[keep].astype(float),gt[keep].astype(float)
    assert len(x)
    data.append((case,x,y))
def train(data):
    # Each condition has equal total weight regardless of mask size.
    moments=np.mean([[x.mean(),y.mean(),(x*x).mean(),(x*y).mean()] for _,x,y in data],axis=0)
    mx,my,xx,xy=moments
    a=(xy-mx*my)/(xx-mx*mx)
    b=my-a*mx
    k=xy/xx
    assert min(k,a)>0
    return {'A':[1.,0.],'B':[float(k),0.],'C':[float(a),float(b)]}
bounds=[.100001,9.999999]
def evaluate(data,models):
    return [{**{k:case[k] for k in ('file','target','nominal_axial_origin_m','relative_object_yaw_deg')},
             'method':name,'mae_m':float(np.abs(np.clip(a*x+b,*bounds)-y).mean())}
            for case,x,y in data for name,(a,b) in models.items()]
cv=[]
for d in sorted({c['nominal_axial_origin_m'] for c,_,_ in data}):
    training=[r for r in data if r[0]['nominal_axial_origin_m']!=d]
    test=[r for r in data if r[0]['nominal_axial_origin_m']==d]
    cv+=evaluate(test,train(training))
scores={k:float(np.mean([r['mae_m'] for r in cv if r['method']==k])) for k in 'ABC'}
with (root/'kitchen_group_cv.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(cv[0]));w.writeheader();w.writerows(cv)
locked={'locked_utc':datetime.now(timezone.utc).isoformat(),'training_cases':27,
        'source':src.name,'training_sha256_manifest':sha(src/'sample_sha256.json'),
        'fit':'least squares, each physical condition equal weight; only valid pixels of eroded GT instance',
        'cv':'leave one nominal distance out, select B/C by mean per-case depth MAE',
        'cv_mae_m':scores,'selected_before_holdouts':min('BC',key=scores.get),
        'models':train(data),'output_clip_m':bounds,
        'clip_note':'positive slope; fixed saturating guard in open camera range; report saturation'}
with (root/'locked.json').open('x',encoding='utf-8') as f:json.dump(locked,f,indent=2)
(root/'locked.sha256').write_text(sha(root/'locked.json')+'\n')
print(json.dumps(locked,indent=2))
