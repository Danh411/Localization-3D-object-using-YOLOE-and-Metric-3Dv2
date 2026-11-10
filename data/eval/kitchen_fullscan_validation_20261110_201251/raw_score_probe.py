import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
import yaml
from ultralytics.models.yolo.segment.predict import SegmentationPredictor
from ultralytics.utils import nms, ops

root=Path(__file__).resolve().parent
repo=root.parents[2]
sys.path.insert(0,str(repo/'src/perception'))
from perception.core.yolo import YoloeDetector

with (root/'visibility_by_frame.csv').open(newline='',encoding='utf-8') as f:
    entries=list(csv.DictReader(f))
cases={}
for entry in entries:
    if int(entry['visible_pixels'])>=1000 and entry['detected']=='False':
        cases.setdefault((entry['stop'],entry['instance_gt']),entry)
if not cases:
    print('No visible missed cases require the raw score probe')
    raise SystemExit(0)
stops={str(data['stop_index']):data for p in root.glob('audit_scan_*.json')
       for data in [json.loads(p.read_text())]}
by_frame=defaultdict(list)
for e in cases.values():
    frame=next(f for f in stops[e['stop']]['frames'] if f['frame_idx']==int(e['frame']))
    by_frame[frame['file']].append(e)

cfg=yaml.safe_load((root/'config.yaml').read_text())['yoloe']
classes=yaml.safe_load((root/'classes.yaml').read_text())['classes']
torch.set_num_threads(1)
model=YoloeDetector(classes,str(repo/(cfg['model']+'.pt')),cfg['conf'],cfg['iou'],cfg['imgsz'],'cuda:0')
origin_post=SegmentationPredictor.postprocess
origin_nms=nms.non_max_suppression
captured={}
def capture_post(self, pred, img, orig_imgs, **kwargs):
    captured['net_size']=img.shape[2:]
    return origin_post(self,pred,img,orig_imgs,**kwargs)
def capture_nms(pred,*args,**kwargs):
    x=pred[0] if isinstance(pred,(tuple,list)) else pred
    assert not kwargs.get('end2end') and x.shape[0]==1 and x.shape[1]>4+len(classes)
    captured['raw']=x[0,:4+len(classes)].transpose(0,1).detach().clone()
    return origin_nms(pred,*args,**kwargs)

results=[]
for filename, group in by_frame.items():
    with np.load(root/'frames'/filename,allow_pickle=False) as data:
        rgb=data['rgb']
    captured.clear()
    with patch.object(SegmentationPredictor,'postprocess',capture_post),patch.object(nms,'non_max_suppression',capture_nms):
        model.detect(rgb)
    raw=captured['raw']
    boxes=ops.scale_boxes(captured['net_size'],ops.xywh2xyxy(raw[:,:4]),rgb.shape[:2]).cpu().numpy()
    scores=raw[:,4:].cpu().numpy()
    for e in group:
        cls=e['instance_gt'].removesuffix('_1')
        label=classes.index(cls)
        gt=np.array(json.loads(e['gt_bbox']),dtype=float)+[0,0,1,1]
        wh=np.maximum(np.minimum(boxes[:,2:],gt[2:])-np.maximum(boxes[:,:2],gt[:2]),0)
        intersection=wh.prod(1)
        union=(boxes[:,2:]-boxes[:,:2]).prod(1)+(gt[2:]-gt[:2]).prod()-intersection
        ious=intersection/union
        indices=np.flatnonzero(ious>=.5)
        r=dict(instance_gt=e['instance_gt'],stop=int(e['stop']),frame=int(e['frame']),
               box_candidates=len(indices),max_box_iou=float(ious.max()),threshold=cfg['conf'])
        if len(indices):
            top=indices[np.argmax(scores[indices,label])]
            winner=int(scores[top].argmax())
            r.update(best_target_score=float(scores[top,label]),box_iou_of_best_score=float(ious[top]),
                top_class_at_that_box=classes[winner],top_class_score=float(scores[top,winner]),
                above_threshold_for_target=int((scores[indices,label]>cfg['conf']).sum()),
                above_threshold_and_target_argmax=int(((scores[indices,label]>cfg['conf'])&(scores[indices].argmax(1)==label)).sum()))
        results.append(r)
(root/'raw_score_probe.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(results,indent=2))

