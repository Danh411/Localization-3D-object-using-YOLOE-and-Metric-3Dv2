"""Export observation sources and their final association outcome without changing SQLite."""
from collections import defaultdict
import json
import math
from pathlib import Path
import sqlite3

import yaml
from verify import csvrows,csvwrite,load

ROOT=Path(__file__).resolve().parent
rows=[]
for room in ("aws","tiffany"):
    path=ROOT/room
    sources=defaultdict(list)
    for item in csvrows(path/"fallback_trace.csv"):
        sources[(item["branch"],int(item["stamp_ns"]),item["class_name"])].append(item)
    centers=load(path/"mesh_centers.json")
    for branch in ("P0_metric","ORB_B_only","P3_combined"):
        with sqlite3.connect((path/(branch+".sqlite")).as_uri()+"?mode=ro",uri=True) as con:
            con.row_factory=sqlite3.Row
            objects={o["object_id"]:dict(o) for o in con.execute("select * from objects")}
            for observation in con.execute("select * from observations order by obs_id"):
                if observation["class_name"] not in {"bottle","cup","laptop","book"}:
                    continue
                candidates=sources[(branch,observation["stamp_ns"],observation["class_name"])]
                item=candidates[0] if len(candidates)==1 else {}
                target=item.get("target_gt")
                xyz=[observation["world_"+axis] for axis in "xyz"]
                center=centers[target]["mesh_aabb_center_world_m"] if target in centers else None
                obj=objects.get(observation["object_id"],{})
                rows.append(dict(room=room,branch=branch,obs_id=observation["obs_id"],
                                 stop=observation["stop_index"],stamp_ns=observation["stamp_ns"],
                                 class_name=observation["class_name"],target_gt=target,
                                 match=item.get("match"),source=item.get("source","AMBIGUOUS"),
                                 confidence=observation["confidence"],truncated=observation["truncated"],
                                 world_x=xyz[0],world_y=xyz[1],world_z=xyz[2],
                                 xy_error_m=math.dist(xyz[:2],center[:2]) if center else None,
                                 xyz_error_m=math.dist(xyz,center) if center else None,
                                 object_id=observation["object_id"],object_status=obj.get("status","UNASSIGNED"),
                                 object_n_obs=obj.get("n_obs",0)))
csvwrite(ROOT/"association_sources.csv",rows)
bottle=[r for r in rows if r["room"]=="tiffany" and r["branch"]=="P3_combined" and r["target_gt"]=="bottle_1"]
first=next(r for r in bottle if r["source"]=="ORB")
fallback=next(r for r in bottle if r["source"]=="METRIC3D")
cfg=yaml.safe_load((ROOT/"tiffany/config.yaml").read_text())
distance=math.dist([first["world_"+k] for k in "xyz"],[fallback["world_"+k] for k in "xyz"])
diagnostic=dict(room="tiffany",target="bottle_1",observations=bottle,
                distance_fallback_to_existing_orb_m=distance,
                assoc_radius_m=cfg["assoc"]["radius_m"],
                min_conf_to_create=cfg["assoc"]["min_conf_to_create"],
                min_obs=cfg["assoc"]["min_obs"],
                fallback_outside_radius=distance>cfg["assoc"]["radius_m"],
                fallback_below_creation_conf=fallback["confidence"]<cfg["assoc"]["min_conf_to_create"])
assert diagnostic["fallback_outside_radius"] and diagnostic["fallback_below_creation_conf"]
assert len(bottle)==3 and fallback["object_status"]=="UNASSIGNED"
(ROOT/"tiffany_bottle_association.json").write_text(json.dumps(diagnostic,indent=2)+"\n")
print("Exported",len(rows),"observations; Tiffany bottle fallback distance",distance,flush=True)
