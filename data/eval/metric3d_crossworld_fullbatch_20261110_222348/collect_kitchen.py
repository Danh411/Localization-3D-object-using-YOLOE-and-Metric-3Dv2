import itertools,json,math,random,sys,time
from collections import OrderedDict
from pathlib import Path
from threading import Condition
import numpy as np
from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.camera_info_pb2 import CameraInfo
from gz.msgs10.image_pb2 import Image
from gz.msgs10.model_pb2 import Model
from gz.msgs10.pose_pb2 import Pose
from gz.msgs10.pose_v_pb2 import Pose_V
from gz.transport13 import Node

root=Path(sys.argv[1])
cfg=json.loads((root/'design.json').read_text())
dest=root/'frames'
dest.mkdir(exist_ok=True)
props=cfg['props']
cx,cy,cz,heading=cfg['camera_xyz_yaw']
node=Node()
cv=Condition()
frames=OrderedDict()
poses=OrderedDict()
joints=OrderedDict()
seen={key:0 for key in ('rgb','depth','labels','K','pose','joint')}
def stamp(m):
    return m.header.stamp.sec*10**9+m.header.stamp.nsec
def callback(kind,msg):
    t=stamp(msg)
    with cv:
        seen[kind]+=1
        if kind=='pose':
            d={p.name:([p.position.x,p.position.y,p.position.z],[p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w])
               for p in msg.pose if p.name in {'camera_rig',*props}}
            poses[t]=d
            while len(poses)>2000:poses.popitem(last=False)
        elif kind=='joint':
            for j in msg.joint:
                if j.name.split('::')[-1]=='pan_joint':
                    joints[t]=j.axis1.position
            while len(joints)>2000:joints.popitem(last=False)
        else:
            item=frames.setdefault(t,{})
            if kind=='K':
                k=msg.intrinsics.k
                if len(k)==9:
                    item[kind]=[k[0],k[4],k[2],k[5]]
            else:
                item[kind]=(bytes(msg.data),msg.width,msg.height,msg.pixel_format_type,msg.step)
            while len(frames)>24: frames.popitem(last=False)
        cv.notify_all()
for kind,topic,msg in [
    ('rgb','/camera/image',Image),('depth','/camera/depth_image',Image),
    ('labels','/camera/segmentation/labels_map',Image),('K','/camera/camera_info',CameraInfo),
    ('pose','/world/default/pose/info',Pose_V),('joint','/joint_states',Model)]:
    node.subscribe(msg,topic,lambda m,kind=kind:callback(kind,m))

def wait(after,timeout=50):
    deadline=time.monotonic()+timeout
    with cv:
        while time.monotonic()<deadline:
            for t in sorted(frames):
                if t>after and len(frames[t])==4:
                    return t,frames[t].copy()
            cv.wait(.15)
    raise RuntimeError(f'No exact RGB/depth/panoptic/K frame after {after}; counts={seen}')

def rpy(roll,pitch,yaw):
    cr,sr=math.cos(roll/2),math.sin(roll/2)
    cp,sp=math.cos(pitch/2),math.sin(pitch/2)
    cy,sy=math.cos(yaw/2),math.sin(yaw/2)
    return (sr*cp*cy-cr*sp*sy,cr*sp*cy+sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy)
def set_pose(name,xyz,angles):
    req=Pose(name=name)
    req.position.x,req.position.y,req.position.z=xyz
    req.orientation.x,req.orientation.y,req.orientation.z,req.orientation.w=rpy(*angles)
    with cv:
        request_after=max(poses,default=0)
    ok,response=node.request('/world/default/set_pose',req,Pose,Boolean,500)
    deadline=time.monotonic()+6
    expected_q=rpy(*angles)
    with cv:
        while time.monotonic()<deadline:
            for stamp_ns,values in reversed(poses.items()):
                if stamp_ns<=request_after:
                    break
                if name in values:
                    p,q=values[name]
                    if np.allclose(p,xyz,rtol=0,atol=1e-5) and np.allclose(q,expected_q,rtol=0,atol=1e-5):
                        return stamp_ns
            cv.wait(.05)
    raise RuntimeError(f'Pose command not observed: {name}, request={ok}, response={response}')
def decode(data,kind):
    b,w,h,fmt,step=data
    assert (w,h)==(1280,720)
    if kind=='depth':
        assert (fmt,step,len(b))==(13,4*w,4*w*h)
        return np.frombuffer(b,'<f4').reshape(h,w)
    assert (fmt,step,len(b))==(3,3*w,3*w*h)
    return np.frombuffer(b,np.uint8).reshape(h,w,3)
def yaw(q):
    x,y,z,w=q
    return math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
def observed(t,name):
    deadline=time.monotonic()+2
    with cv:
        while time.monotonic()<deadline:
            before=[k for k,v in poses.items() if k<=t and name in v]
            after=[k for k,v in poses.items() if k>=t and name in v]
            if before and after:
                a,b=max(before),min(after)
                if t-a>50_000_000 or b-t>50_000_000: break
                x,y=poses[a][name],poses[b][name]
                if np.allclose(x[0],y[0],atol=1e-5) and np.allclose(x[1],y[1],atol=1e-5):
                    return x,a,b
                break
            cv.wait(.04)
    return None,None,None

first,_=wait(-1,timeout=100)
print('sensors synchronized',seen,flush=True)
design=cfg['cases']
rows=[]
active=None
for i,case in enumerate(design):
    name,angle=case['target'],case['angle']
    if active and active!=name:
        set_pose(active,[0,0,-5],props[active]['pose_rpy'])
    with cv: before=max(frames,default=first)
    x,y=case['xy']
    dist=x-cx-.05
    z=cfg['surface_z_m']
    angles=[0,0,math.radians(angle)]
    applied=set_pose(name,[x,y,z],angles)
    active=name
    t,data=wait(max(before,applied)+400_000_000)
    K=data['K']
    assert np.allclose(K,[914.0147013559828,914.0147013559828,640,360],rtol=0,atol=1e-5),K
    rgb,depth,labels=(decode(data[k],k) for k in ('rgb','depth','labels'))
    tag=props[name]['label']
    mask=labels[...,2]==tag
    ys,xs=np.where(mask)
    issues=[]
    if not len(xs): issues.append('not_visible')
    elif xs.min()<8 or xs.max()>1271 or ys.min()<8 or ys.max()>711:issues.append('cut_frame')
    if np.any((labels[...,2]>0)&(labels[...,2]!=tag)):issues.append('unexpected_semantic_label')
    valid=mask&np.isfinite(depth)&(depth>.1)&(depth<10)
    gt_med=float(np.median(depth[valid])) if valid.any() else None
    if gt_med is None or abs(gt_med-dist)>.32: issues.append('depth_geometry_mismatch')
    r,ra,rb=observed(t,'camera_rig')
    o,oa,ob=observed(t,name)
    with cv:
        joint_key=min(joints,key=lambda k:abs(k-t)) if joints else None
        pan=joints[joint_key] if joint_key is not None else None
    if r is None or o is None or pan is None or abs(joint_key-t)>10_000_000 or abs(pan)>1e-4:
        issues.append('pose_tf_unverified')
    if r is not None and (not np.allclose(r[0],[cx,cy,cz],atol=.002) or abs(yaw(r[1])-heading)>.002):
        issues.append('unexpected_rig_pose')
    if o is not None and not np.allclose(o[0],[x,y,z],atol=.002):
        issues.append('unexpected_target_pose')
    actual_heading=yaw(r[1])+pan if r is not None and pan is not None else None
    optical=None if actual_heading is None else np.array(r[0])+[.05*math.cos(actual_heading),.05*math.sin(actual_heading),0]
    fname=f'{i:02d}_{name}_{dist}_{angle}.npz'
    np.savez_compressed(dest/fname,rgb=rgb,gt_depth=depth,labels_rgb=labels,K=np.array(K),stamp_ns=t)
    row={'condition':case['condition'],'rep':case['rep'],'file':fname,'target':name,'label':tag,'distance_m':dist,'relative_yaw_deg':angle,'stamp_ns':t,
         'target_pose_command':[x,y,z,*angles],'target_pose_observed':o,'rig_pose_observed':r,
         'pose_brackets_ns':[ra,rb,oa,ob],'pan_rad':pan,'pan_stamp_ns':joint_key,
         'optical_origin_world_m':None if optical is None else optical.tolist(),'optical_heading_rad':actual_heading,
         'visible_pixels':int(mask.sum()),'gt_valid_pixels':int(valid.sum()),'gt_median_z_m':gt_med,'issues':issues}
    rows.append(row)
    (root/'capture_index.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(i+1,name,dist,angle,'GT',gt_med,'pixels',len(xs),'issues',issues,flush=True)
