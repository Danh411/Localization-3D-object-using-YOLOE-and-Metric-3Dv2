import hashlib
import json
import re
import sys
from pathlib import Path
import yaml

run = Path(sys.argv[1])
ref = run.parent / 'kitchen_reference_20261110_134600_sync'
cal = run.parent / 'metric3d_depth_calibration_20261110_184655'
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
lock = cal / 'locked.json'
assert sha(lock) == (cal / 'locked.sha256').read_text().strip()
assert json.loads(lock.read_text())['models']['B'] == [1.3720333573615522, 0.0]
for name in ('locked.json', 'locked.sha256'):
    (run/name).write_bytes((cal/name).read_bytes())
manifest = json.loads((ref/'manifest.json').read_text())
for name in ('config.yaml','classes.yaml','gt.yaml','kitchen_controlled.sdf','mesh_centers.json'):
    assert sha(ref/name) == manifest['files'][name]['sha256'], name
for name in ('config.yaml','classes.yaml'):
    (run/name).write_bytes((ref/name).read_bytes())
world = (ref/'kitchen_controlled.sdf').read_text()
gt = yaml.safe_load((ref/'gt.yaml').read_text())
centers = json.loads((ref/'mesh_centers.json').read_text())
placements = {'laptop_1':(0.10,-0.38), 'book_1':(-0.56,-0.64),
              'cup_1':(-0.48,-0.26), 'bottle_1':(-0.16,-0.88)}
for obj in gt['objects']:
    name = obj['model_name']
    if name not in placements:
        continue
    match = re.search(r'(<name>'+name+r'</name>\s*<pose>)([^<]+)(</pose>)', world)
    assert match, name
    original = list(map(float, match[2].split()))
    revised = [*placements[name], *original[2:]]
    world = world[:match.start(2)] + ' '.join(map(str,revised)) + world[match.end(2):]
    delta = [revised[i] - original[i] for i in range(3)]
    entry = centers[name]
    for field in ('aabb_min_m','aabb_max_m','mesh_aabb_center_world_m','yaml_ref_world_m'):
        entry[field] = [a + b for a,b in zip(entry[field],delta,strict=True)]
    obj.update(dict(zip('xyz', entry['mesh_aabb_center_world_m'],strict=True)))
(run/'kitchen_controlled.sdf').write_text(world,encoding='utf-8')
(run/'gt.yaml').write_text(yaml.safe_dump(gt,sort_keys=False),encoding='utf-8')
(run/'mesh_centers.json').write_text(json.dumps(centers,indent=2)+'\n',encoding='utf-8')
(run/'design.json').write_text(json.dumps({'planned_xy':placements,'lock_sha256':sha(lock),
    'source_sha256':sha(ref/'kitchen_controlled.sdf'),'world_sha256':sha(run/'kitchen_controlled.sdf'),
    'stops':8,'frames_per_stop':3,'settle_s':1.5},indent=2)+'\n',encoding='utf-8')
