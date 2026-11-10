import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
repo = root.parents[2]
reference = root.parent/'kitchen_reference_20261110_134600_sync'
hypotheses = root.parent/'metric3d_hypotheses_20261110_144943'
calibration = root.parent/'metric3d_depth_calibration_20261110_184655'
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

manifest = json.loads((reference/'manifest.json').read_text())
baseline = {name:entry['sha256'] for name,entry in manifest['files'].items()}
baseline[manifest['source_archive']['path']] = manifest['source_archive']['sha256']
assert all(sha(reference/name)==value for name,value in baseline.items())
assert sha(root/'locked.json') == sha(calibration/'locked.json') == (root/'locked.sha256').read_text().strip()
assert all((root/name).read_bytes()==(reference/name).read_bytes() for name in ('classes.yaml','config.yaml'))
design=json.loads((root/'design.json').read_text())
assert sha(root/'kitchen_controlled.sdf')==design['world_sha256']
assert sha(reference/'kitchen_controlled.sdf')==design['source_sha256']
training=json.loads((hypotheses/'sample_sha256.json').read_text())
assert all(sha(hypotheses/name)==value for name,value in training.items())
tracks = subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).splitlines()
assert tracks==['?? tools/run_scan_live.py'],tracks
if '--inputs-only' in sys.argv:
    print(f'Input verification PASS: {len(baseline)} reference files, {len(training)} fit files, unchanged config and lock')
    raise SystemExit(0)
all_files = set(p for p in root.iterdir() if p.is_file() and p.name not in {'manifest.json','manifest.log'})
all_files.update(p for path in ('frames','db','initial_incomplete','production_debug','ros') for p in (root/path).rglob('*')
                 if p.name != 'latest' and p.is_file() and p.suffix not in {'.sqlite-shm','.sqlite-wal'})
assert len(list((root/'frames').glob('*.npz')))==24
result = {'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
          'baseline_verified_entries':len(baseline),'training_verified_entries':len(training),
          'checkpoints_verified_before_ros_inference':manifest['model_checkpoints'],
          'inputs':{'reference_manifest_sha256':sha(reference/'manifest.json'),
                    'training_manifest_sha256':sha(hypotheses/'sample_sha256.json'),
                    'coefficients_sha256':sha(root/'locked.json')},
          'files':{p.relative_to(root).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
                   for p in sorted(all_files)}}
(root/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(f"Integrity PASS: {len(result['files'])} artifacts, {len(baseline)} reference files, {len(training)} fit files.")

