import copy,json,math,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parent
repo=root.parents[2]
sdf=repo/'src/room_sim/worlds/kitchen_reference.sdf'
base=ET.parse(sdf).getroot().find('world')
aws=root/'easynav/playground_kobuki/easynav_playground_kobuki_worlds'
tiffany=root/'tiffany/src/hexapod_ws'
definitions={
 'kitchen':(sdf,repo/'src/room_sim/models',[-1.67,-.35,1.11,.015],.740),
 'tiffany':(tiffany/'worlds/living_room.sdf',tiffany/'models',[-1.85,1.38,.46,0],.003),
 'aws':(aws/'worlds/small_house.world',aws/'models',[-2.0,.75,.46,math.pi/2],.006),
}
props={part.findtext('name'):part for part in base.findall('include') if part.findtext('name','').endswith('_1')}
assert len(props)==4
geometry=json.loads((root.parent/'kitchen_reference_20261110_134600_sync/mesh_centers.json').read_text())
configs={}
for key,(source,assets,camera,support) in definitions.items():
    output=root/('run_'+key)
    output.mkdir(exist_ok=False)
    tree=ET.parse(source)
    world=tree.getroot().find('world')
    if key!='kitchen':
        rig=copy.deepcopy(base.find("model[@name='camera_rig']"))
        world.append(rig)
        for p in props.values():
            world.append(copy.deepcopy(p))
    rig=world.find("model[@name='camera_rig']")
    rig.find('pose').text=' '.join(map(str,[*camera[:3],0,0,camera[3]]))
    records={}
    for name in props:
        node=world.find(f"include[name='{name}']")
        origin=list(map(float,node.findtext('pose').split()))
        aabb=geometry[name]
        records[name]={'label':int(node.findtext('plugin/label')),'pose_rpy':origin[3:],
                        'z_origin_above_support':origin[2]-aabb['aabb_min_m'][2],
                        'center_offset':[v-x for v,x in zip(aabb['mesh_aabb_center_world_m'],origin[:3])]}
        node.find('pose').text=' '.join(map(str,[0,0,-5,*origin[3:]]))
    tree.write(output/'world.sdf',encoding='utf-8',xml_declaration=True)
    configs[key]={'source_world':str(source),'resource_path':str(assets)+':'+str(repo/'src/room_sim/models'),
                  'camera_xyz_yaw':camera,'surface_z_m':support,'props':records,
                  'conditions':[(1.27,20),(1.68,65),(2.16,20),(2.23,65)]}
    (output/'design.json').write_text(json.dumps(configs[key],indent=2)+'\n')
meta={'tiffany_sha':subprocess.check_output(['git','-C',str(root/'tiffany'),'rev-parse','HEAD'],text=True).strip(),
      'aws_jazzy_sha':subprocess.check_output(['git','-C',str(root/'easynav'),'rev-parse','HEAD'],text=True).strip(),
      'tiffany_license':'Apache-2.0 declared in package.xml; no separate root LICENSE in checkout',
      'aws_license':'package Apache-2.0; world/models MIT-0 per package.xml and models/LICENSE',
      'worlds':configs}
(root/'rooms.json').write_text(json.dumps(meta,indent=2)+'\n')
