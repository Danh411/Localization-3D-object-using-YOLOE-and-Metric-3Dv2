from common import *
from unittest.mock import patch
from ultralytics.models.yolo.segment.predict import SegmentationPredictor
from ultralytics.utils import nms,ops
from perception.core.yolo import YoloeDetector
import torch
import hashlib

scan=Scan('scan_36x1')
rows=load_csv(scan.path/'visibility_by_frame.csv')
visible=[r for r in rows if r['instance_gt']=='book_1' and int(r['visible_pixels'])>=1000]
true=[r for r in visible if r['detected']=='True']
if true:
    csv_write(ROOT/'book_angle_probe.csv',[dict(status='correct_detection',**r) for r in true])
    raise SystemExit(0)
if not visible:
    csv_write(ROOT/'book_angle_probe.csv',[dict(status='NOT TESTED',reason='no visible book with at least 1000 GT pixels')])
    raise SystemExit(0)
indices=np.linspace(0,len(visible)-1,min(6,len(visible)),dtype=int)
manifest=read(ROOT.parent/'kitchen_reference_20261110_134600_sync'/'manifest.json')
for item in manifest['model_checkpoints']:
    with Path(item['original_path']).open('rb') as fp:
        assert hashlib.file_digest(fp,'sha256').hexdigest()==item['sha256']
cfg=scan.cfg['yoloe']
names=yaml.safe_load((scan.path/'classes.yaml').read_text())['classes']
torch.set_num_threads(2)
detector=YoloeDetector(names,str(REPO/(cfg['model']+'.pt')),cfg['conf'],cfg['iou'],cfg['imgsz'],'cpu')
post=SegmentationPredictor.postprocess
original_nms=nms.non_max_suppression
raw={}
def capture_post(self,pred,img,orig,**kwargs):
    raw['shape']=img.shape[2:]
    return post(self,pred,img,orig,**kwargs)
def capture_nms(pred,*args,**kwargs):
    value=pred[0] if isinstance(pred,(list,tuple)) else pred
    assert value.shape[0]==1 and not kwargs.get('end2end')
    raw['pred']=value[0,:4+len(names)].transpose(0,1).detach().clone()
    return original_nms(pred,*args,**kwargs)
result=[]
for i in indices:
    r=visible[i]
    f=scan.frames[int(r['stamp_ns'])]
    with scan.frame_archive(f) as z:
        rgb=z['rgb']
    with patch.object(SegmentationPredictor,'postprocess',capture_post),patch.object(nms,'non_max_suppression',capture_nms):
        detector.detect(rgb)
    pred=raw['pred']
    boxes=ops.scale_boxes(raw['shape'],ops.xywh2xyxy(pred[:,:4]),rgb.shape[:2]).numpy()
    scores=pred[:,4:].numpy()
    gt_box=np.array(json.loads(r['gt_bbox']))+[0,0,1,1]
    wh=np.maximum(np.minimum(boxes[:,2:],gt_box[2:])-np.maximum(boxes[:,:2],gt_box[:2]),0)
    intersection=wh.prod(1)
    union=(boxes[:,2:]-boxes[:,:2]).prod(1)+(gt_box[2:]-gt_box[:2]).prod()-intersection
    ious=intersection/union
    valid=np.flatnonzero(ious>=.5)
    best=valid[np.argmax(scores[valid,names.index('book')])] if len(valid) else None
    result.append(dict(status='raw_probe',stop=f['stop'],yaw_deg=math.degrees(f['joint_yaw_rad']),stamp_ns=f['stamp_ns'],
        raw_book_score=float(scores[best,names.index('book')]) if best is not None else None,
        raw_top_class=names[int(scores[best].argmax())] if best is not None else None,
        box_iou=float(ious[best]) if best is not None else None,visible_pixels=r['visible_pixels']))
csv_write(ROOT/'book_angle_probe.csv',result)

