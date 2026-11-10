import hashlib,json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
eval_root=root.parent
repo=root.parents[2]
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def check(base,entries):
    for rel,value in entries.items():
        if isinstance(value,dict): value=value['sha256']
        assert sha(base/rel)==value,rel
    return len(entries)
baseline=eval_root/'kitchen_reference_20261110_134600_sync'
old=read(baseline/'manifest.json')
sizes={'reference':check(baseline,{**old['files'],old['source_archive']['path']:old['source_archive']})}
hyp=eval_root/'metric3d_hypotheses_20261110_144943'
sizes['hypotheses']=check(hyp,read(hyp/'sample_sha256.json'))
cal=eval_root/'metric3d_depth_calibration_20261110_184655'
sizes['calibration']=check(cal,read(cal/'capture_hashes.json'))
full=eval_root/'kitchen_fullscan_validation_20261110_201251'
sizes['prior_fullscan']=check(full,read(full/'manifest.json')['files'])
assert sha(root/'kitchen_locked.json')==sha(cal/'locked.json')
for world in ('aws','tiffany'):
    assert (root/world/'capture_exit.txt').read_text().strip()=='0'
    assert len(read(root/world/'capture_index.json'))==45
status=subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).splitlines()
assert set(status)=={' M src/object_db/object_db/association.py',' M src/object_db/object_db/db.py',
                     ' M tests/test_association.py','?? tools/run_scan_live.py'},status
if '--inputs-only' in sys.argv:
    print(json.dumps(sizes))
    raise SystemExit(0)
assert len(list((root/'kitchen_final'/'frames').glob('*.npz')))==24
assert sha(root/'crossworld_locked.json')==(root/'crossworld_locked.sha256').read_text().strip()
ignore={'cache','ultralytics','tmp','tmp-win','ros','manifest.json','manifest.log'}
paths=[]
for p in root.rglob('*'):
    if any(s in ignore for s in p.relative_to(root).parts):
        continue
    if p.is_file():
        paths.append(p)
out=dict(baseline_entries=sizes,working_tree=status,checkpoints=old['model_checkpoints'],
         files={p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(paths)})
(root/'manifest.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(f"Verified {sum(sizes.values())} prior files and hashed {len(paths)} new artifacts.")

