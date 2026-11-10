"""ORB estimators only consume RGB, YOLOE masks and TF/CameraInfo."""
import sys,math,time,itertools
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
import cv2

ROOT=Path(__file__).resolve().parent
PREV=ROOT.parent/'multiview_36deg_geometry_fullbatch_20261110_231819'
sys.path.insert(0,str(PREV))
from angles import pose,project,triangulate,kp_data
from common import erode_mask

TARGET_CLASSES=frozenset(('bottle','cup','laptop','book'))
MIN_BASELINE=.012
MAX_REPROJECTION=1.
MAX_Z_UNCERTAINTY=.25
MIN_POINTS=8
MIN_SPREAD=12.

@dataclass
class Match:
    xyz: np.ndarray
    feature: tuple
    uv: tuple
    reprojection: float
    parallax_deg: float

def check_point(P,Q,t,u,pixel_a,pixel_b,fx):
    xyz=triangulate(P,Q,np.asarray(pixel_a,dtype=float),np.asarray(pixel_b,dtype=float))
    if not np.isfinite(xyz).all():
        return None,'nonfinite'
    pa,za=project(P,xyz)
    pb,zb=project(Q,xyz)
    if not (.2<za<8 and .2<zb<8):
        return None,'depth_or_cheirality'
    reprojection=max(np.linalg.norm(pa-pixel_a),np.linalg.norm(pb-pixel_b))
    if reprojection>MAX_REPROJECTION:
        return None,'reprojection'
    va,vb=xyz-t,xyz-u
    sine=np.linalg.norm(np.cross(va,vb))/(np.linalg.norm(va)*np.linalg.norm(vb))
    if sine<.002 or max(za,zb)/(fx*sine)>MAX_Z_UNCERTAINTY:
        return None,'ill_conditioned'
    return (xyz,float(reprojection),math.degrees(math.asin(min(1.,sine)))),'ok'

def mutual_matches(a,b):
    if a is None or b is None or min(len(a),len(b))<2:
        return []
    matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
    def best(x,y):
        return {m.queryIdx:m.trainIdx for m,n in matcher.knnMatch(x,y,k=2) if m.distance<.72*n.distance}
    f=best(a,b)
    rev=best(b,a)
    return [(i,j) for i,j in f.items() if rev.get(j)==i]

def uv_spread(uv):
    return float(np.max(np.ptp(np.asarray(uv),axis=0)))

def representative(matches,R,t,K,mask):
    # One vote per anchor feature even if more than one pair sees that feature.
    unique={}
    for match in sorted(matches,key=lambda m:m.reprojection):
        unique.setdefault(match.feature,match)
    vals=list(unique.values())
    if len(vals)<MIN_POINTS:
        return None,'insufficient_unique_features'
    points=np.stack([m.xyz for m in vals])
    axial=(points-t)@R[:,2]
    med=float(np.median(axial))
    mad=float(np.median(np.abs(axial-med)))
    keep=np.abs(axial-med)<=max(.08,3*mad)
    if keep.sum()<MIN_POINTS or uv_spread([m.uv for m,k in zip(vals,keep) if k])<MIN_SPREAD:
        return None,'insufficient_spread_or_consensus'
    yy,xx=np.where(erode_mask(mask))
    if not len(yy):
        return None,'empty_mask'
    z=float(np.median(axial[keep]))
    fx,fy,cx,cy=K
    # Equivalent back-projection rule, using the eroded RGB mask centroid.
    pc=np.array([(xx.mean()-cx)*z/fx,(yy.mean()-cy)*z/fy,z])
    return dict(A=np.median(points[keep],axis=0),B=R@pc+t,z=z,n=int(keep.sum()),
                axial_mad=mad,uv=(float(xx.mean()),float(yy.mean()))),'accepted'

def key(f,index):
    return f['stamp_ns'],index

def estimate(scan):
    started=time.perf_counter()
    pair_rows=[]; point_rows=[]; estimates={}; causal={}; reasons={}
    features={}; poses={}; incident=defaultdict(list); earlier=defaultdict(list)
    for f in scan.frames.values():
        if not f['tf']:
            continue
        poses[f['stamp_ns']]=pose(scan,f)
        for j,d in enumerate(f['detections']):
            if d['class_name'] in TARGET_CLASSES:
                features[key(f,j)]=kp_data(scan,f,d)
    by_class=defaultdict(list)
    for k in features:
        by_class[scan.frames[k[0]]['detections'][k[1]]['class_name']].append(k)
    for cls,keys in by_class.items():
        for a,b in itertools.combinations(sorted(keys),2):
            f,g=scan.frames[a[0]],scan.frames[b[0]]
            ra,t,ka,P=poses[a[0]]
            rb,u,kb,Q=poses[b[0]]
            baseline=float(np.linalg.norm(t-u))
            row=dict(class_name=cls,stamp_a=a[0],stamp_b=b[0],det_a=a[1],det_b=b[1],stop_a=f['stop'],stop_b=g['stop'],
                yaw_delta_deg=math.degrees(abs((f['joint_yaw_rad']-g['joint_yaw_rad']+math.pi)%(2*math.pi)-math.pi)),
                baseline_m=baseline,matched=0,valid_points=0,status='baseline')
            pair_rows.append(row)
            if baseline<MIN_BASELINE:
                continue
            ak,ad=features[a]
            bk,bd=features[b]
            matching=mutual_matches(ad,bd)
            row['matched']=len(matching)
            accepted=[]
            rejected=defaultdict(int)
            for i,j in matching:
                pa,pb=ak[i].pt,bk[j].pt
                found,reason=check_point(P,Q,t,u,pa,pb,min(ka[0,0],kb[0,0]))
                if found is None:
                    rejected[reason]+=1
                    continue
                xyz,r,p=found
                accepted.append((i,j,pa,pb,xyz,r,p))
            row['valid_points']=len(accepted)
            row['rejections']=dict(rejected)
            if len(accepted)<MIN_POINTS:
                row['status']='few_matches'
                continue
            if min(uv_spread([x[2] for x in accepted]),uv_spread([x[3] for x in accepted]))<MIN_SPREAD:
                row['status']='poor_spread'
                continue
            row['status']='accepted'
            for i,j,pa,pb,xyz,r,p in accepted:
                incident[a].append(Match(xyz,i,pa,r,p))
                m=Match(xyz,j,pb,r,p)
                incident[b].append(m)
                earlier[b].append(m)
                point_rows.append(dict(class_name=cls,stamp_a=a[0],stamp_b=b[0],det_a=a[1],det_b=b[1],
                    u_a=pa[0],v_a=pa[1],u_b=pb[0],v_b=pb[1],x=float(xyz[0]),y=float(xyz[1]),z=float(xyz[2]),
                    reprojection_px=r,parallax_deg=p))
    for k in features:
        f=scan.frames[k[0]]
        d=f['detections'][k[1]]
        with scan.frame_archive(f) as packet:
            mask=np.unpackbits(packet[d['mask']],axis=1,count=1280).astype(bool)
        R,t,_,_=poses[k[0]]
        e,reason=representative(incident[k],R,t,f['K'],mask)
        c,_=representative(earlier[k],R,t,f['K'],mask)
        reasons[k]=reason
        if e is not None:
            estimates[k]=e
        if c is not None:
            causal[k]=c
    return estimates,causal,reasons,pair_rows,point_rows,time.perf_counter()-started

