import hashlib,json,re,shutil,sys
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml

root=Path(sys.argv[1])
source=root.parent/'kitchen_fullscan_validation_20261110_201251'
run=root/'kitchen_final'
run.mkdir(exist_ok=False)
(run/'frames').mkdir()
(run/'db').mkdir()
for name in ('classes.yaml','config.yaml','audit.py','replay.py','query_live.py','pose_check.py','locked.json','locked.sha256'):
    shutil.copyfile(source/name,run/name)
summary=json.loads((root/'kitchen_probe_summary.json').read_text())
tree=ET.parse(source/'kitchen_controlled.sdf')
world=tree.getroot().find('world')
gt=yaml.safe_load((source/'gt.yaml').read_text())
centers=json.loads((source/'mesh_centers.json').read_text())
placements={}
if summary['cup_full']['confirmed'] and not summary['cup_edge']['confirmed']:
    placements['cup_1']=[-.18,-.28]
candidate=summary['book_alt']['correct']
old=summary['book_1']['correct']
alt=candidate>=2 and candidate>old
if alt or old>=2:
    placements['book_1']=[.02,-.70]
for name,xy in placements.items():
    include=next(i for i in world.findall('include') if i.findtext('name')==name)
    p=list(map(float,include.findtext('pose').split()))
    delta=[xy[0]-p[0],xy[1]-p[1],0.]
    pose=[*xy,*p[2:]]
    include.find('pose').text=' '.join(map(str,pose))
    o=next(o for o in gt['objects'] if o['model_name']==name)
    center=centers[name]
    for field in ('aabb_min_m','aabb_max_m','mesh_aabb_center_world_m','yaml_ref_world_m'):
        center[field]=[a+b for a,b in zip(center[field],delta,strict=True)]
    o.update(dict(zip('xyz',center['mesh_aabb_center_world_m'],strict=True)))
    if alt and name=='book_1':
        world.remove(include)
        probe=ET.parse(root/'kitchen_probe'/'world.sdf')
        model=probe.find('./world/model[@name="book_alt"]')
        model.set('name','book_1')
        model.find('pose').text=' '.join(map(str,pose))
        model.find('plugin/label').text='4'
        world.append(model)
        o.update(x=xy[0],y=xy[1],z=.838335,size_x=.024,size_y=.15123,size_z=.19667,
                 asset_uri='https://www.innerscene.com/tools/library/3d-parts/bound-three-books-b266be0c')
        center['method']='Bound Three lower volume upright, resized; GT from transformed dimensions'
        center['mesh_aabb_center_world_m']=[o[k] for k in 'xyz']
        center['yaml_ref_world_m']=center['mesh_aabb_center_world_m']
        center['aabb_min_m']=[o[k]-o['size_'+k]/2 for k in 'xyz']
        center['aabb_max_m']=[o[k]+o['size_'+k]/2 for k in 'xyz']
tree.write(run/'kitchen_controlled.sdf',encoding='utf-8',xml_declaration=True)
(run/'gt.yaml').write_text(yaml.safe_dump(gt,sort_keys=False),encoding='utf-8')
(run/'mesh_centers.json').write_text(json.dumps(centers,indent=2)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
(run/'selection.json').write_text(json.dumps(dict(cup_book_changes=placements,alternate_book=alt,
    cup_final_pose_reason='Moved within full-frame band to avoid overlap with laptop footprint',
    world_sha256=sha(run/'kitchen_controlled.sdf'),probe_sha256=sha(root/'kitchen_probe_summary.json')),indent=2)+'\n')
# Prior audit assumes a sibling reference folder. Locate it independently of batch nesting.
audit=run/'audit.py'
audit.write_text(audit.read_text().replace(
    "root.parent/'kitchen_reference_20261110_134600_sync'",
    "root.parent.parent/'kitchen_reference_20261110_134600_sync'"))
launch=(source/'reference.launch.py').read_text()
base_wsl=source.as_posix().replace('D:', '/mnt/d')
run_wsl=run.as_posix().replace('D:', '/mnt/d')
(run/'reference.launch.py').write_text(launch.replace(base_wsl+'/audit.py',run_wsl+'/audit.py'))
ready=(source/'run_ready.sh').read_text()
ready=ready.replace('ROS_DOMAIN_ID=76','ROS_DOMAIN_ID=81')
ready=ready.replace('GZ_PARTITION="loc3d_$(basename "$run")_retry"','GZ_PARTITION="crossworld_$(basename "$(dirname "$run")")_final"')
ready=ready.replace('ros2 launch', 'mkdir -p "$run/tmp" "$run/cache" "$run/ultralytics" "$run/ros"\nros2 launch',1)
(run/'run_ready.sh').write_bytes(ready.encode())

