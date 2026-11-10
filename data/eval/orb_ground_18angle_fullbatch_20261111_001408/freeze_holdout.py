import hashlib,sys,json
from pathlib import Path
from datetime import datetime,timezone
import xml.etree.ElementTree as ET
import numpy as np
root=Path(sys.argv[1]).resolve()
dev=root/'scan_18x1'
test=root/'holdout_18x1'
old=root.parent/'multiview_36deg_geometry_fullbatch_20261110_231819'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
files=[root/'orb.py',root/'experiment.py',root/'PLAN.md',old/'angles.py',old/'common.py',old/'ground.py']
assert (dev/'experiment_summary.json').is_file()
assert sha(dev/'kitchen_controlled.sdf')==sha(old/'scan_36x1'/'kitchen_controlled.sdf')
assert sha(dev/'config.yaml')==sha(test/'config.yaml')
assert sha(dev/'classes.yaml')==sha(test/'classes.yaml')
places=json.loads((test/'layout.json').read_text())
a=ET.parse(dev/'kitchen_controlled.sdf').getroot()
b=ET.parse(test/'kitchen_controlled.sdf').getroot()
for target,xy in places.items():
    pattern=f"./world/include[name='{target}']/pose"
    p,q=a.find(pattern),b.find(pattern)
    ppos,qpos=list(map(float,p.text.split())),list(map(float,q.text.split()))
    assert ppos[:2]!=qpos[:2] and qpos[:2]==xy and ppos[2:]==qpos[2:]
    q.text=p.text
assert ET.tostring(a)==ET.tostring(b)
meshes=json.loads((test/'mesh_centers.json').read_text())
for i,x in enumerate(places):
    for y in list(places)[i+1:]:
        lo=np.maximum(meshes[x]['aabb_min_m'],meshes[y]['aabb_min_m'])
        hi=np.minimum(meshes[x]['aabb_max_m'],meshes[y]['aabb_max_m'])
        assert np.any(lo>=hi),(x,y)
files.extend(test/f for f in ('kitchen_controlled.sdf','config.yaml','gt.yaml','mesh_centers.json','classes.yaml','layout.json'))
files.extend(dev/f for f in ('kitchen_controlled.sdf','experiment_summary.json'))
from os.path import relpath
with (root/'holdout_lock.json').open('x',encoding='utf-8') as out:
    json.dump(dict(utc=datetime.now(timezone.utc).isoformat(),files={
        relpath(p,root).replace('\\','/'):sha(p) for p in files}),out,indent=2)
    out.write('\n')
print('Frozen before holdout capture, and verified only four object XY changed')

