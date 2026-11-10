import hashlib,json,subprocess,sys,re
from pathlib import Path
import yaml
root=Path(__file__).resolve().parent
repo=root.parents[2]
prior=root.parent/'metric3d_crossworld_fullbatch_20261110_222348'/'kitchen_final'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as file: return hashlib.file_digest(file,'sha256').hexdigest()
for name,n,k in [('scan_8x3',24,8),('scan_36x1',36,36)]:
    folder=root/name
    files=('kitchen_controlled.sdf','gt.yaml','classes.yaml','locked.json')
    assert all(sha(folder/f)==sha(prior/f) for f in files)
    old=yaml.safe_load((prior/'config.yaml').read_text())
    new=yaml.safe_load((folder/'config.yaml').read_text())
    assert {k:v for k,v in old.items() if k!='scan'}=={k:v for k,v in new.items() if k!='scan'}
    assert (folder/'capture_exit.txt').read_text().strip()==(folder/'replay_exit.txt').read_text().strip()=='0'
    assert len(list((folder/'frames').glob('*.npz')))==n
    stops=[read(p) for p in folder.glob('audit_scan_*.json')]
    assert len(stops)==k and sum(len(s['frames']) for s in stops)==n
    assert read(folder/'summary.json')['a_matches_live']
    assert 'Goal finished with status: SUCCEEDED' in (folder/'action.log').read_text()
    assert read(folder/'pose_check.json')['final_gazebo_pose.txt']['models']
for name in ('methods','angles','book_probe','ground','pipeline_summary'):
    assert (root/f'{name}.exit').read_text().strip()=='0'
for name in ('PLAN.md','REPORT.md','detection_by_angle.csv','depth_by_angle.csv','fusion_comparison.csv',
             'ground_plane_feasibility.csv','ground_plane_correction.csv','triangulation_feasibility.md',
             'temporal_keyframe_results.csv','viewpoint_selection.csv','pipeline_comparison.csv',
             'crossworld_check.csv','runtime_summary.csv','angle_diagnostics.png'):
    assert (root/name).is_file() and (root/name).stat().st_size>0,name
for link in re.findall(r'\]\(([^)]+)\)',(root/'REPORT.md').read_text(encoding='utf-8')):
    if not link.startswith('https://') and link!='manifest.json':
        assert (root/link).exists(),link
status=subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).splitlines()
assert status==(root/'git_initial.txt').read_text(encoding='utf-8-sig').splitlines(),status
excluded={'tmp','tmp-win','cache','ultralytics','ros','manifest.json','manifest.log','__pycache__','native_cache','native_tmp','native_ultralytics'}
files=[]
for p in root.rglob('*'):
    if any(s in excluded for s in p.relative_to(root).parts):
        continue
    if p.is_file():
        files.append(p)
out=dict(scene_sha256=sha(prior/'kitchen_controlled.sdf'),git_status=status,
    files={p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)})
(root/'manifest.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print('Verified two full captures, replay, scene/config invariants, report links, git scope; hashed',len(files),'artifacts.')

