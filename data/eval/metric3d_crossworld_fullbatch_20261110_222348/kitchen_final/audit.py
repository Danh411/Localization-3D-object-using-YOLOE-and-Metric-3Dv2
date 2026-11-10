import hashlib
import json
import math
import sys
import time
from collections import OrderedDict
from pathlib import Path
from threading import local

import numpy as np
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image, JointState
from perception.node import perception_node as node

root = Path(__file__).resolve().parent
original_init = node.PerceptionNode.__init__
original_rgb = node.PerceptionNode._on_img
original_info = node.PerceptionNode._on_info
original_capture = node.PerceptionNode._on_capture
original_process = node.process
context = local()

def stamp_ns(msg):
    return msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec

def cache_sample(cache, msg, limit):
    cache[stamp_ns(msg)] = msg
    while len(cache) > limit:
        cache.popitem(last=False)

def initialize(self):
    self.audit_rgb = OrderedDict()
    self.audit_info = OrderedDict()
    original_init(self)
    self.audit_depth = OrderedDict()
    self.audit_labels = OrderedDict()
    self.audit_joints = OrderedDict()
    group = ReentrantCallbackGroup()
    for topic, msg_type, cache, limit in (
        ('/camera/depth_image', Image, self.audit_depth, 80),
        ('/camera/segmentation/labels_map', Image, self.audit_labels, 80),
        ('/joint_states', JointState, self.audit_joints, 12000),
    ):
        self.create_subscription(msg_type, topic, lambda m,c=cache,n=limit: cache_sample(c,m,n),
                                 qos_profile_sensor_data, callback_group=group)

def rgb_callback(self, msg):
    original_rgb(self,msg)
    cache_sample(self.audit_rgb,msg,80)

def info_callback(self, msg):
    original_info(self,msg)
    cache_sample(self.audit_info,msg,80)

def grab(self, n_frames, timeout_s=10.0):
    # A measurement frame is eligible only after all three source stamps match.
    first_stamp = next(reversed(self.audit_rgb),-1)
    deadline = time.monotonic() + 24.0
    triplets = []
    while len(triplets)<n_frames and time.monotonic()<deadline:
        for stamp, rgb in self.audit_rgb.copy().items():
            if stamp<=first_stamp:
                continue
            depth = self.audit_depth.get(stamp)
            labels = self.audit_labels.get(stamp)
            info = self.audit_info.get(stamp)
            if depth is None or labels is None or info is None:
                continue
            triplets.append((rgb,depth,labels,info))
            first_stamp=stamp
            if len(triplets)==n_frames:
                break
        time.sleep(0.02)
    if len(triplets)!=n_frames:
        self.get_logger().error(f'audit sync: obtained {len(triplets)}/{n_frames} exact RGB/depth/panoptic triplets')
        return []
    context.triplets=triplets
    return [rgb for rgb,_,_,_ in triplets]

def model_frame(rgb, K, detector, depth_model, cfg):
    frame_index = len(context.frames)
    image,depth_msg,labels_msg,info = context.triplets[frame_index]
    stamp = stamp_ns(image)
    assert stamp_ns(depth_msg)==stamp_ns(labels_msg)==stamp
    k = info.k
    K = (k[0],k[4],k[2],k[5])
    assert stamp_ns(info)==stamp and (info.width,info.height)==(1280,720)
    assert np.allclose(K,[914.0147013559828,914.0147013559828,640,360],rtol=0,atol=1e-5)
    self = context.owner
    joints = self.audit_joints.get(stamp)
    if joints is None and self.audit_joints:
        snapshot = self.audit_joints.copy()
        key = min(snapshot, key=lambda n: abs(n-stamp))
        joints = snapshot[key]
    yaw = None
    if joints is not None and 'pan_joint' in joints.name:
        yaw = float(joints.position[joints.name.index('pan_joint')])
    tf = None
    try:
        transform = self.tf_buffer.lookup_transform(
            'world','camera_optical_frame',node.Time.from_msg(image.header.stamp),node.Duration(seconds=1.0)).transform
        tf = {'translation':[transform.translation.x,transform.translation.y,transform.translation.z],
              'quaternion':[transform.rotation.x,transform.rotation.y,transform.rotation.z,transform.rotation.w]}
    except node.tf2_ros.TransformException:
        pass
    result = original_process(rgb,K,detector,depth_model,cfg)
    detections, arrays = [], {'rgb': rgb, 'pred_depth': result['depth']}
    if depth_msg is not None:
        arrays['gt_depth'] = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding='32FC1')
    if labels_msg is not None:
        arrays['labels_rgb'] = self.bridge.imgmsg_to_cv2(labels_msg, desired_encoding='rgb8')
    for key in ('observations','rejected'):
        for item in result[key]:
            mask_name = f'mask_{len(detections)}'
            arrays[mask_name] = np.packbits(item['mask'], axis=-1)
            fields=('class_name','confidence','bbox_xyxy','truncated','mask_area_px','valid_depth_ratio','depth_m','u','v','p_cam','range_m','reason')
            detections.append({k:item[k] for k in fields if k in item} | {'mask':mask_name, 'depth_filter_pass':key=='observations'})
    name=f"{context.scan_id}_{context.stop}_{frame_index}.npz"
    np.savez_compressed(root/'frames'/name, **arrays)
    context.frames.append({'frame_idx':frame_index,'stamp_ns':stamp,'file':name,'K':list(K),'tf':tf,
                            'camera_info_stamp_ns':stamp_ns(info),'timings_ms':result['timings_ms'],
                           'joint_yaw_rad':yaw,'joint_skew_ns':stamp_ns(joints)-stamp if joints is not None else None,
                           'depth_exact_stamp':depth_msg is not None,'label_exact_stamp':labels_msg is not None,
                           'detections':detections})
    return result

def capture(self, request, response):
    start = time.perf_counter()
    context.owner, context.scan_id, context.stop, context.frames = self, request.scan_id, request.stop_index, []
    result = original_capture(self, request, response)
    for f in context.frames:
        f['world'] = [{'class_name':o.class_name,'confidence':o.confidence,
                       'xyz':[float(v) for v in o.p_world] if all(math.isfinite(v) for v in o.p_world) else None}
                      for o in result.observations.observations if o.frame_idx==f['frame_idx']]
    path=root/f'audit_{request.scan_id}_{request.stop_index}.json'
    path.write_text(json.dumps({'scan_id':request.scan_id,'stop_index':request.stop_index,'command_yaw_rad':request.yaw_rad,'elapsed_s':time.perf_counter()-start,'frames':context.frames},
                               indent=2,allow_nan=False))
    return result

node.PerceptionNode.__init__=initialize
node.PerceptionNode._grab_frames=grab
node.PerceptionNode._on_img=rgb_callback
node.PerceptionNode._on_info=info_callback
node.PerceptionNode._on_capture=capture
node.process=model_frame
sys.argv=sys.argv[1:]
# Load the same verified local weights as the calibration batch.
import torch
from unittest.mock import patch
manifest = json.loads((root.parent.parent/'kitchen_reference_20261110_134600_sync'/'manifest.json').read_text())
for item in manifest['model_checkpoints']:
    with Path(item['original_path']).open('rb') as file:
        assert hashlib.file_digest(file,'sha256').hexdigest() == item['sha256']
torch.set_num_threads(1)
hub = Path.home()/'.cache/torch/hub'
model = torch.hub.load(str(hub/'yvanyin_metric3d_main'),'metric3d_vit_small',source='local',pretrain=False)
weights = torch.load(hub/'checkpoints/metric_depth_vit_small_800k.pth',map_location='cpu',weights_only=True)
keys = model.load_state_dict(weights['model_state_dict'],strict=False)
assert not keys.unexpected_keys and set(keys.missing_keys) <= {'depth_model.encoder.mask_token'}
del weights
with patch('torch.hub.load',return_value=model):
    node.main()

