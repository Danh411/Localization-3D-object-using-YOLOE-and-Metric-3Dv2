import json,re,sys
from pathlib import Path
root=Path(sys.argv[1])
old=root.parent/'metric3d_depth_calibration_20261110_184655'
for name in ('aws','tiffany'):
    target=root/name
    target.mkdir()
    src=old/f'holdout_{name}'
    cfg=json.loads((src/'design.json').read_text())
    del cfg['props']['book_1']
    cfg['camera_xyz_yaw'][2]=.36
    cfg['conditions']=[[d,y] for d in (1.25,1.60,2.00) for y in (0,45,90)]+[[d,y] for d in (1.42,2.15) for y in (15,55,105)]
    cfg['test_distances']=[1.42,2.15]
    cfg['training_distances']=[1.25,1.60,2.00]
    (target/'design.json').write_text(json.dumps(cfg,indent=2)+'\n')
    sdf=(src/'world.sdf').read_text()
    pat=r'(<model name="camera_rig">\s*<pose>)[^<]+(</pose>)'
    pose=' '.join(map(str,[*cfg['camera_xyz_yaw'][:3],0,0,cfg['camera_xyz_yaw'][3]]))
    sdf,n=re.subn(pat,lambda m:m[1]+pose+m[2],sdf,count=1)
    assert n==1
    (target/'world.sdf').write_text(sdf)

