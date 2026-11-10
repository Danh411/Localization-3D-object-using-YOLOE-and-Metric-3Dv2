import sys, shutil, math, json
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml
root=Path(sys.argv[1])
old=root.parent/'multiview_36deg_geometry_fullbatch_20261110_231819'/'scan_36x1'
name=sys.argv[2]
dest=root/name
for folder in ('frames','db'):
    (dest/folder).mkdir(parents=True,exist_ok=False)
for f in ('config.yaml','classes.yaml','gt.yaml','kitchen_controlled.sdf','mesh_centers.json','locked.json','locked.sha256','query_live.py','audit.py','pose_check.py'):
    shutil.copyfile(old/f,dest/f)
cfg=dest/'config.yaml'
cfg.write_bytes(cfg.read_bytes().replace(b'step_deg: 10',b'step_deg: 20'))
wsl=lambda p:p.as_posix().replace('D:','/mnt/d')
launch=(old/'reference.launch.py').read_text(encoding='utf-8').replace(wsl(old)+'/audit.py',wsl(dest)+'/audit.py')
(dest/'reference.launch.py').write_text(launch,encoding='utf-8',newline='\n')
command=(old/'run_ready.sh').read_text(encoding='utf-8').replace('ROS_DOMAIN_ID=89','ROS_DOMAIN_ID=91' if name=='scan_18x1' else 'ROS_DOMAIN_ID=92')
command=command.replace('step_deg: 10.0','step_deg: 20.0')
(dest/'run_ready.sh').write_bytes(command.encode())
replay=(old/'replay.py').read_text(encoding='utf-8').replace('list(range(36))','list(range(18))')
replay=replay.replace('range(0,36,4)','range(0,18,6)').replace('contact[i:i+4]','contact[i:i+6]')
(dest/'replay.py').write_text(replay,encoding='utf-8',newline='\n')
if name=='holdout_18x1':
    placements={'bottle_1':(.03,-.87),'cup_1':(-.31,-.19),'laptop_1':(.18,-.49),'book_1':(-.04,-.73)}
    tree=ET.parse(dest/'kitchen_controlled.sdf')
    gt=yaml.safe_load((dest/'gt.yaml').read_text())
    centers=json.loads((dest/'mesh_centers.json').read_text())
    world=tree.getroot().find('world')
    for obj in world.findall('include'):
        key=obj.findtext('name')
        if key not in placements:
            continue
        pose=obj.find('pose')
        x,y,*rest=map(float,pose.text.split())
        a,b=placements[key]
        pose.text=' '.join(map(str,[a,b,*rest]))
        dx,dy=a-x,b-y
        ref=next(o for o in gt['objects'] if o['model_name']==key)
        ref['x']+=dx
        ref['y']+=dy
        for field in ('aabb_min_m','aabb_max_m','mesh_aabb_center_world_m','yaml_ref_world_m'):
            v=centers[key][field]
            centers[key][field]=[v[0]+dx,v[1]+dy,v[2]]
    tree.write(dest/'kitchen_controlled.sdf',encoding='utf-8',xml_declaration=True)
    (dest/'gt.yaml').write_text(yaml.safe_dump(gt,sort_keys=False),encoding='utf-8')
    (dest/'mesh_centers.json').write_text(json.dumps(centers,indent=2)+'\n')
    (dest/'layout.json').write_text(json.dumps(placements,indent=2)+'\n')

