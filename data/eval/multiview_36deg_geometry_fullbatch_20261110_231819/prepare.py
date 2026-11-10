import shutil,sys
from pathlib import Path
root=Path(sys.argv[1])
old=root.parent/'metric3d_crossworld_fullbatch_20261110_222348'/'kitchen_final'
for name,step,count,domain in [('scan_8x3',45,3,88),('scan_36x1',10,1,89)]:
    if len(sys.argv)>2 and name!=sys.argv[2]: continue
    dest=root/name
    for folder in ('frames','db'): (dest/folder).mkdir(parents=True,exist_ok=True)
    for f in ('config.yaml','classes.yaml','gt.yaml','kitchen_controlled.sdf','mesh_centers.json','locked.json','locked.sha256','query_live.py','audit.py','pose_check.py'):
        shutil.copyfile(old/f,dest/f)
    cfg=dest/'config.yaml'
    if count==1:
        config=cfg.read_text(encoding='utf-8').replace('step_deg: 45','step_deg: 10').replace('frames_per_stop: 3','frames_per_stop: 1')
        cfg.write_text(config,encoding='utf-8')
    wsl=lambda p:p.as_posix().replace('D:','/mnt/d')
    launch=(old/'reference.launch.py').read_text(encoding='utf-8').replace(wsl(old)+'/audit.py',wsl(dest)+'/audit.py')
    (dest/'reference.launch.py').write_text(launch,encoding='utf-8')
    command=(old/'run_ready.sh').read_text(encoding='utf-8').replace('ROS_DOMAIN_ID=81',f'ROS_DOMAIN_ID={domain}')
    command=command.replace('$(basename "$(dirname "$run")")_final','$(basename "$(dirname "$run")")_$(basename "$run")')
    command=command.replace('timeout 640','timeout 1700').replace('step_deg: 45.0, frames_per_stop: 3',f'step_deg: {step}.0, frames_per_stop: {count}')
    (dest/'run_ready.sh').write_bytes(command.encode())
    replay=(old/'replay.py').read_text(encoding='utf-8').replace('list(range(8))',f'list(range({360//step}))').replace("len(s['frames'])==3",f"len(s['frames'])=={count}")
    replay=replay.replace('for i in (0,4)',f'for i in range(0,{360//step},4)')
    (dest/'replay.py').write_text(replay,encoding='utf-8')

