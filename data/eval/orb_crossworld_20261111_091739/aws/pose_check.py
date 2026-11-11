import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from google.protobuf import text_format
from gz.msgs10.pose_v_pb2 import Pose_V

root=Path(__file__).resolve().parent
world=ET.parse(root/'kitchen_controlled.sdf')
targets={'laptop_1','book_1','cup_1','bottle_1'}
poses={m.findtext('name'):list(map(float,m.findtext('pose').split()))
       for m in world.findall('./world/include') if m.findtext('name') in targets}
poses['camera_rig']=list(map(float,world.find('./world/model[@name="camera_rig"]/pose').text.split()))
def quaternion(angles):
    roll,pitch,yaw=angles
    cr,sr=math.cos(roll/2),math.sin(roll/2)
    cp,sp=math.cos(pitch/2),math.sin(pitch/2)
    cy,sy=math.cos(yaw/2),math.sin(yaw/2)
    return sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy
records={}
for path in map(Path,sys.argv[1:]):
    sample=text_format.Parse(path.read_text(),Pose_V())
    values={}
    for item in sample.pose:
        if item.name not in poses:
            continue
        exp=poses[item.name]
        p=(item.position.x,item.position.y,item.position.z)
        q=(item.orientation.x,item.orientation.y,item.orientation.z,item.orientation.w)
        d=math.dist(p,exp[:3])
        qe=quaternion(exp[3:])
        delta=min(math.dist(q,qe),math.dist(q,[-x for x in qe]))
        assert d<1e-6 and delta<1e-6
        values[item.name]={'position':p,'quaternion':q,'translation_error_m':d}
    assert values.keys()==poses.keys()
    records[path.name]={'stamp_ns':sample.header.stamp.sec*10**9+sample.header.stamp.nsec,'models':values}
print(json.dumps(records,indent=2))

