import csv
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def rows(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

lock_path = root / 'locked.json'
lock = read(lock_path)
assert sha(lock_path) == (root / 'locked.sha256').read_text().strip()
# Run the read-only portion of the original fitting script, before it writes its outputs.
fit_path = root / 'fit.py'
fit_input = fit_path.read_text(encoding='utf-8').split("with (root/'kitchen_group_cv.csv')", 1)[0]
namespace = {'__file__': str(fit_path)}
exec(compile(fit_input, str(fit_path), 'exec'), namespace)
assert namespace['train'](namespace['data']) == lock['models']
assert namespace['scores'] == lock['cv_mae_m']
assert sha(namespace['src'] / 'sample_sha256.json') == lock['training_sha256_manifest']
capture_hashes = read(root / 'capture_hashes.json')
assert all(sha(root / f) == expected for f, expected in capture_hashes.items())
outputs = {}
for entry in read(root / 'holdout_summary.json'):
    folder = root / f"holdout_{entry['room']}"
    detections = rows(folder / 'detection.csv')
    index = read(folder / 'capture_index.json')
    scores = rows(folder / 'scores.csv')
    assert len(detections) == len(index) == entry['captured'] == 16
    assert len(scores) == 3 * entry['scored']
    for d, frame in zip(detections, index, strict=True):
        assert d['file'] == frame['file'] and int(d['stamp_ns']) == frame['stamp_ns']
        assert frame['stamp_ns'] == frame['pan_stamp_ns']
        assert frame['pose_brackets_ns'][0] <= frame['stamp_ns'] <= frame['pose_brackets_ns'][1]
        assert frame['pose_brackets_ns'][2] <= frame['stamp_ns'] <= frame['pose_brackets_ns'][3]
        artifacts = (folder / 'outputs' / d['file'],
                     folder / 'outputs' / (Path(d['file']).stem + '_detections.json'))
        for artifact in artifacts:
            outputs[artifact.relative_to(root).as_posix()] = sha(artifact)
    for d in scores:
        a, b = lock['models'][d['method']]
        assert d['rep_clipped'] == 'False'
        assert int(d['dense_clipped_pixels']) == 0
        assert abs(float(d['z_scored_m']) - (a * float(d['z_pred_m']) + b)) < 1e-10
    assert not any(d['target'] == 'book' and d['geometry_scored'] == 'True' for d in detections)
result = {'coefficient_lock_sha256': sha(lock_path),
          'fit_reproduced_exactly': True,
          'training_files_verified': len(read(namespace['src'] / 'sample_sha256.json')),
          'baseline_entries_verified_including_archive': len(namespace['m']['files']) + 1,
          'capture_and_design_files_verified': len(capture_hashes),
          'inference_output_sha256': outputs}
with (root / 'verification.json').open('x', encoding='utf-8') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print('Verified exact fit, captures, score formulas and', len(outputs), 'inference artifacts')
