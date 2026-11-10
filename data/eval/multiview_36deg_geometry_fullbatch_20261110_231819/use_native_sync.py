from pathlib import Path
import sys
from textwrap import dedent
folder=Path(sys.argv[1])
p=folder/'audit.py'
s=p.read_text(encoding='utf-8')
s=s.replace('from threading import local','from threading import Condition, local\nfrom array import array')
s=s.replace('from sensor_msgs.msg import CameraInfo, Image, JointState',
'''from sensor_msgs.msg import CameraInfo, Image, JointState
from std_msgs.msg import Header
from builtin_interfaces.msg import Time
from gz.msgs10.image_pb2 import Image as GzImage
from gz.msgs10.camera_info_pb2 import CameraInfo as GzCameraInfo
from gz.transport13 import Node as GzNode''')
start=s.index('def grab(')
end=s.index('def model_frame(',start)
s=s[:start]+dedent('''
def native_initialize(self):
    self.audit_gz = GzNode()
    self.audit_native_condition = Condition()
    self.audit_native_frames = OrderedDict()
    def callback(msg, key):
        stamp = msg.header.stamp.sec*10**9 + msg.header.stamp.nsec
        if key=='K':
            if len(msg.intrinsics.k)!=9:
                return
            value = (msg.width,msg.height,list(msg.intrinsics.k))
        else:
            value = (msg.width,msg.height,msg.step,msg.pixel_format_type,bytes(msg.data))
        with self.audit_native_condition:
            self.audit_native_frames.setdefault(stamp,{})[key]=value
            while len(self.audit_native_frames)>20:
                self.audit_native_frames.popitem(last=False)
            self.audit_native_condition.notify_all()
    for key,topic,kind in (
        ('rgb','/camera/image',GzImage),('depth','/camera/depth_image',GzImage),
        ('labels','/camera/segmentation/labels_map',GzImage),('K','/camera/camera_info',GzCameraInfo),
    ):
        assert self.audit_gz.subscribe(kind,topic,lambda m,k=key:callback(m,k)),topic

def grab(self, n_frames, timeout_s=10.0):
    # Capture uses native Gazebo transport for exact sensor groups. ROS still
    # runs controller, perception, TF2, publishing and SQLite unchanged.
    with self.audit_native_condition:
        first_stamp=max(self.audit_native_frames,default=-1)
    deadline=time.monotonic()+36.0
    captures=[]
    with self.audit_native_condition:
        while len(captures)<n_frames and time.monotonic()<deadline:
            for stamp,packet in sorted(self.audit_native_frames.items()):
                if stamp<=first_stamp or len(packet)!=4:
                    continue
                captures.append((stamp,packet.copy()))
                first_stamp=stamp
                if len(captures)==n_frames:
                    break
            if len(captures)<n_frames:
                self.audit_native_condition.wait(.10)
    if len(captures)!=n_frames:
        self.get_logger().error(f'native audit sync: {len(captures)}/{n_frames} exact RGB/depth/panoptic/K groups')
        return []
    triplets=[]
    for stamp,data in captures:
        header=Header(stamp=Time(sec=stamp//10**9,nanosec=stamp%10**9),frame_id='camera_optical_frame')
        images=[]
        for key,encoding,fmt,channels in (('rgb','rgb8',3,3),('depth','32FC1',13,4),('labels','rgb8',3,3)):
            w,h,step,actual,payload=data[key]
            assert (w,h,step,actual,len(payload))==(1280,720,1280*channels,fmt,1280*720*channels)
            images.append(Image(header=header,height=h,width=w,encoding=encoding,is_bigendian=0,
                                step=step,data=array('B',payload)))
        w,h,k=data['K']
        info=CameraInfo(header=header,height=h,width=w,k=k)
        triplets.append((*images,info))
    context.triplets=triplets
    return [rgb for rgb,_,_,_ in triplets]

''')+s[end:]
s=s.replace('    original_init(self)','    original_init(self)\n    native_initialize(self)')
s=s.replace("'camera_info_stamp_ns':stamp_ns(info)","'sensor_transport':'gazebo_native_exact','camera_info_stamp_ns':stamp_ns(info)")
p.write_text(s,encoding='utf-8',newline='\n')

