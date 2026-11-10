import hashlib,json,math,struct,sys
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path(sys.argv[1])
source=root.parent/'kitchen_fullscan_validation_20261110_201251'
room=root/'kitchen_probe'
room.mkdir()
book=root/'asset'/'stack-of-books.glb'
blob=book.read_bytes()
size,kind=struct.unpack_from('<I4s',blob,12)
assert blob[:4]==b'glTF' and kind==b'JSON'
doc=json.loads(blob[20:20+size])
assert all(n['name'].startswith('Lower bound volume') for n in doc['nodes'][:9])
# Select the lower volume only. Undo its stack yaw and stand it upright.
doc['nodes'][27]={'name':'Single upright lower volume','children':list(range(9)),
    'rotation':[-.5,-.5,-.5,.5],'translation':[-.01136,.098335,0],'scale':[.71]*3}
yaw=-math.radians(7)
c,s=math.cos(yaw),math.sin(yaw)
for node in doc['nodes'][:9]:
    x,y,z=node['translation']
    node['translation']=[c*x-s*z,y,s*x+c*z]
    node.pop('rotation')
raw=json.dumps(doc,separators=(',',':')).encode()
raw+=b' '*(-len(raw)%4)
other=blob[20+size:]
glb=struct.pack('<4sII',b'glTF',2,20+len(raw)+len(other))+struct.pack('<I4s',len(raw),b'JSON')+raw+other
asset=root/'asset'/'single-book.glb'
asset.write_bytes(glb)
(root/'asset'/'source.json').write_text(json.dumps({'source':'https://www.innerscene.com/tools/library/3d-parts/bound-three-books-b266be0c',
    'license':'CC0','download_sha256':hashlib.sha256(blob).hexdigest(),'modified_sha256':hashlib.sha256(glb).hexdigest(),
    'adaptation':'Lower volume only, stood upright, scale 0.71, preserved materials'},indent=2)+'\n')
tree=ET.parse(source/'kitchen_controlled.sdf')
world=tree.getroot().find('world')
for i in world.findall('include'):
    if i.findtext('name') in ('book_1','cup_1','laptop_1','bottle_1'):
        if i.findtext('name') in ('book_1','cup_1'):
            i.find('pose').text='0 0 -5 0 0 0'
        else:
            world.remove(i)
entry=ET.fromstring(f'''<model name="book_alt"><static>true</static><pose>0 0 -5 0 0 0</pose>
<link name="body"><visual name="book"><geometry><mesh><uri>{asset.as_posix().replace('D:', '/mnt/d')}</uri></mesh></geometry></visual></link>
<plugin filename="gz-sim-label-system" name="gz::sim::systems::Label"><label>5</label></plugin></model>''')
world.append(entry)
tree.write(room/'world.sdf',encoding='utf-8',xml_declaration=True)
cfg={'camera_xyz_yaw':[-1.5,-.5,1.1,0],'surface_z_m':.74,
     'resource_path':'/mnt/d/loc3d_ws/src/room_sim/models',
     'props':{'book_1':{'label':4,'pose_rpy':[0,0,0]},'book_alt':{'label':5,'pose_rpy':[0,0,0]},
              'cup_1':{'label':1,'pose_rpy':[0,0,0]}},
     'cases':[]}
for i,angle in enumerate((0,24,-24)):
    for name in ('book_1','book_alt'):
        cfg['cases'].append({'target':name,'condition':name,'rep':i,'xy':[.02,-.70],'angle':angle})
for i in range(3):
    for phase,xy in [('cup_edge',[-.48,-.26]),('cup_full',[-.03,-.23])]:
        cfg['cases'].append({'target':'cup_1','condition':phase,'rep':i,'xy':xy,'angle':0})
(room/'design.json').write_text(json.dumps(cfg,indent=2)+'\n')
collector=(root/'collect.py').read_text()
collector=collector.replace("design=list(itertools.product(props,cfg['conditions']))\nrandom.Random(73).shuffle(design)","design=cfg['cases']")
collector=collector.replace("for i,(name,(dist,angle)) in enumerate(design):","for i,case in enumerate(design):\n    name,angle=case['target'],case['angle']")
start=collector.index('    x=cx+')
end=collector.index('    applied=',start)
collector=collector[:start]+'''    x,y=case['xy']
    dist=x-cx-.05
    z=cfg['surface_z_m']
    angles=[0,0,math.radians(angle)]
'''+collector[end:]
collector=collector.replace("'file':fname,'target':name","'condition':case['condition'],'rep':case['rep'],'file':fname,'target':name")
(root/'collect_kitchen.py').write_text(collector)

