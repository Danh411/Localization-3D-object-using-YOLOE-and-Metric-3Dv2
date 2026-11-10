import csv,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np,torch,yaml
from ultralytics.models.yolo.segment.predict import SegmentationPredictor
from ultralytics.utils import nms,ops
root=Path(__file__).resolve().parent
repo=root.parents[2]
sys.path.insert(0,str(repo/'src/perception'))
from perception.core.yolo import YoloeDetector
folder=root/'kitchen_book_retry'
ref=root.parent/'kitchen_reference_20261110_134600_sync'
manifest=json.loads((ref/'manifest.json').read_text())
for f in manifest['model_checkpoints']:
    with Path(f['original_path']).open('rb') as data:
        assert hashlib.file_digest(data,'sha256').hexdigest()==f['sha256']
cfg=yaml.safe_load((ref/'config.yaml').read_text())['yoloe']
classes=yaml.safe_load((ref/'classes.yaml').read_text())['classes']
torch.set_num_threads(2)
detector=YoloeDetector(classes,str(repo/(cfg['model']+'.pt')),cfg['conf'],cfg['iou'],cfg['imgsz'],'cpu')
post=SegmentationPredictor.postprocess
original_nms=nms.non_max_suppression
raw={}
def hook_post(self,pred,img,orig,**kwargs):
    raw['shape']=img.shape[2:]
    return post(self,pred,img,orig,**kwargs)
def hook_nms(pred,*args,**kwargs):
    value=pred[0] if isinstance(pred,(list,tuple)) else pred
    assert value.shape[0]==1 and not kwargs.get('end2end')
    raw['pred']=value[0,:4+len(classes)].transpose(0,1).detach().clone()
    return original_nms(pred,*args,**kwargs)
rows=[]
records=json.loads((folder/'capture_index.json').read_text())
assert len(records)==6
for f in records:
    with np.load(folder/'frames'/f['file']) as z:
        rgb=z['rgb']
        mask=z['labels_rgb'][...,2]==f['label']
        gt=z['gt_depth']
        K=z['K']
    yy,xx=np.where(mask)
    w_z=1.1-(yy-360)*gt[mask]/K[1]
    assert np.min(w_z)>.725 and not f['issues'], (w_z.min(),f)
    with patch.object(SegmentationPredictor,'postprocess',hook_post),patch.object(nms,'non_max_suppression',hook_nms):
        dets=detector.detect(rgb)
    relevant=[]
    for d in dets:
        iou=np.count_nonzero(mask&d['mask'])/np.count_nonzero(mask|d['mask'])
        if iou>=.5:
            relevant.append((iou,d['class_name'],d['confidence']))
    pred=raw['pred']
    boxes=ops.scale_boxes(raw['shape'],ops.xywh2xyxy(pred[:,:4]),rgb.shape[:2]).numpy()
    scores=pred[:,4:].numpy()
    gt_box=np.array([xx.min(),yy.min(),xx.max()+1,yy.max()+1])
    area=np.maximum(np.minimum(boxes[:,2:],gt_box[2:])-np.maximum(boxes[:,:2],gt_box[:2]),0).prod(1)
    union=(boxes[:,2:]-boxes[:,:2]).prod(1)+(gt_box[2:]-gt_box[:2]).prod()-area
    iou_box=area/union
    viable=np.flatnonzero(iou_box>=.5)
    candidate=viable[np.argmax(scores[viable,classes.index('book')])] if len(viable) else None
    row=dict(condition=f['condition'],yaw_deg=f['relative_yaw_deg'],gt_bbox=gt_box.tolist(),visible_px=len(xx),
        gt_world_z_min_m=float(w_z.min()),gt_world_z_max_m=float(w_z.max()),
        correct=sum(m[1]=='book' for m in relevant),wrong=sum(m[1]!='book' for m in relevant),matches=relevant,
        raw_book_conf=float(scores[candidate,classes.index('book')]) if candidate is not None else None,
        raw_best_class=classes[int(scores[candidate].argmax())] if candidate is not None else None,
        raw_box_iou=float(iou_box[candidate]) if candidate is not None else None)
    rows.append(row)
    im=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
    cv2.rectangle(im,(xx.min(),yy.min()),(xx.max(),yy.max()),(0,220,255),2)
    cv2.putText(im,f"{f['condition']} yaw {f['relative_yaw_deg']}",(20,38),0,1,(0,220,255),2)
    cv2.imwrite(str(folder/(Path(f['file']).stem+'.jpg')),cv2.resize(im,(640,360)))
    print(row,flush=True)
with (root/'book_asset_test_valid.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

