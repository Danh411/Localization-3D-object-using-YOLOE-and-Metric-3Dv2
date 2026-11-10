import hashlib,json,math,sqlite3,sys
from pathlib import Path

root=Path(__file__).resolve().parent
repo=root.parents[2]
sys.path.insert(0,str(repo/'src/object_db'))
from object_db import association,db,queries
import yaml
prior=root.parent/'kitchen_fullscan_validation_20261110_201251'
previous=prior/'replay_A.sqlite'
original_hash=hashlib.sha256(previous.read_bytes()).hexdigest()
src=sqlite3.connect(previous.as_uri()+'?mode=ro',uri=True)
src.row_factory=sqlite3.Row
old_obs=[dict(r) for r in src.execute('SELECT * FROM observations ORDER BY obs_id')]
old_objects=[dict(r) for r in src.execute('SELECT * FROM objects ORDER BY object_id')]
scan=src.execute('SELECT scan_id FROM scans').fetchone()[0]
cfg=yaml.safe_load((prior/'config.yaml').read_text())
target=root/'confidence_after.sqlite'
assert not target.exists()
dest=db.open_db(target)
db.create_scan(dest,scan,cfg,'Kitchen confidence regression')
for r in old_obs:
    obs={k:r[k] for k in ('class_name','confidence','truncated','depth_m','range_m','stop_index','frame_idx','yaw_rad','stamp_ns')}
    obs.update(bbox_xyxy=[r['bbox_'+k] for k in ('x1','y1','x2','y2')],
        valid_depth_ratio=r['valid_ratio'],p_cam=[r['cam_'+k] for k in 'xyz'],p_world=[r['world_'+k] for k in 'xyz'])
    association.add_observation(dest,scan,obs,cfg['assoc'],cfg['fusion'])
association.run_association_pass(dest,scan,cfg['assoc'])
db.finish_scan(dest,scan)
new_obs=[dict(r) for r in dest.execute('SELECT * FROM observations ORDER BY obs_id')]
new_objects=[dict(r) for r in dest.execute('SELECT * FROM objects ORDER BY object_id')]
assert new_obs==old_obs and len(new_objects)==len(old_objects)
report=[]
for old,new in zip(old_objects,new_objects,strict=True):
    excluded={'conf_sum','conf_mean','created_at','updated_at'}
    assert {k:v for k,v in old.items() if k not in excluded}=={k:v for k,v in new.items() if k not in excluded}
    rows=[r['confidence'] for r in new_obs if r['object_id']==new['object_id']]
    if rows:
        assert math.isclose(new['conf_sum'],sum(rows),abs_tol=1e-12)
        assert math.isclose(new['conf_mean'],sum(rows)/len(rows),abs_tol=1e-12)
    report.append(dict(object_id=old['object_id'],class_name=old['class_name'],status=old['status'],n=len(rows),
        sum_before=old['conf_sum'],sum_after=new['conf_sum'],mean_before=old['conf_mean'],mean_after=new['conf_mean']))
assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
src.close()
dest.close()
assert hashlib.sha256(previous.read_bytes()).hexdigest()==original_hash
(root/'sqlite_confidence_parity.json').write_text(json.dumps(dict(rows=len(old_obs),objects=len(old_objects),
    old_sha256=original_hash,details=report),indent=2)+'\n')
print(f'{len(old_obs)} observations identical, {len(old_objects)} objects identical except confidence and write times')

