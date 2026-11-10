from common import *
import ast

def textnum(x,n=1):
    return '—' if x is None else f'{x:.{n}f}'.replace('.',',')
def cm(x):
    return '—' if x is None else textnum(100*x)
def pct(x):
    return '—' if x is None else textnum(100*x)+'%'
def fmt_pair(a,b):
    return f'{cm(a)} / {cm(b)}'
def status(x):
    return ast.literal_eval(x)[1] if isinstance(x,str) else x[1]
def floor_table(r):
    groups=defaultdict(list)
    for row in r:
        groups[(row.get('world') or row['scan'])].append(row)
    return [[k,len(v),sum(status(t['rgb'])=='accepted' for t in v),
             sum(status(t['oracle'])=='accepted' for t in v),
             int(np.median([int(t['gt_floor_pixels']) for t in v])),
             textnum(np.mean([float(t['floor_iou']) for t in v]),3)] for k,v in groups.items()]
def depth_table(data):
    groups=defaultdict(list)
    original={}
    for r in data:
        g=r['world'],r['method']
        groups[g].append(r)
        if r['method']=='original':
            original[r['world'],r['file'],r['target']]=r
    result=[]
    for (world,method),group in groups.items():
        x=np.array([float(r['xy']) for r in group])
        xyz=np.array([float(r['xyz']) for r in group])
        diff=[float(r['abs_error_m'])-float(original[r['world'],r['file'],r['target']]['abs_error_m']) for r in group]
        result.append([world,method,len(group),cm(np.mean([float(r['abs_error_m']) for r in group])),
             pct(np.mean([float(r['absrel']) for r in group])),cm(np.mean([float(r['bias']) for r in group])),
             fmt_pair(np.median(x),np.quantile(x,.9)),fmt_pair(np.median(xyz),np.quantile(xyz,.9)),
             f'{sum(v<-1e-8 for v in diff)} / {sum(v>1e-8 for v in diff)}'])
    return result
def table(header,body):
    return '\n'.join(['| '+' | '.join(header)+' |','| '+' | '.join(['---']*len(header))+' |',
              *['| '+' | '.join(str(v) for v in row)+' |' for row in body]])
def section(parts,title,body):
    parts.extend(['## '+title,'',body,''])

s=read(ROOT/'methods_summary.json')
pipeline=read(ROOT/'pipeline_summary.json')
p={r['branch']:r for r in pipeline['branches']}
a,a2,b=s['baselines']
ar,br=pipeline['runtime']
parts=['# Quét 360°, hình học và gộp quan sát','']
direction=lambda x,y:'tăng' if x<y else 'giảm' if x>y else 'giữ nguyên'
parts += [f"Lượt 36×1 {direction(a['recall'],b['recall'])} recall xác nhận ({a['confirmed']}/4 → {b['confirmed']}/4). XY trung vị của các vật được xác nhận là {cm(a.get('xy_median'))} cm ở 8×3 và {cm(b.get('xy_median'))} cm ở 36×1. So sánh ghép cùng vật nằm bên dưới. Thời gian RunScan thật lần lượt {textnum(ar['scan_s'])} và {textnum(br['scan_s'])} s.",'']
bt=table(['Chỉ số','A1 8×3','A2 8×1','B1 36×1'],[
 ['Detection đúng / instance–khung thấy',*[f"{r['true']}/{r['visible']} ({pct(r['detection_recall'])})" for r in (a,a2,b)]],
 ['Sai lớp / bỏ sót / truncated',*[f"{r['detection_wrong']} / {r['missed']} / {r['truncated']}" for r in (a,a2,b)]],
 ['Confirmed / định vị trong 0,5 m',*[f"{r['confirmed']}/4 / {r['localized']}/4" for r in (a,a2,b)]],
 ['Precision',*[pct(r.get('precision')) for r in (a,a2,b)]],
 ['Depth AbsRel',*[pct(r.get('depth_absrel')) for r in (a,a2,b)]],
 ['XY trung vị / P90 (cm)',*[fmt_pair(r.get('xy_median'),r.get('xy_p90')) for r in (a,a2,b)]],
 ['XYZ trung vị / P90 (cm)',*[fmt_pair(r.get('xyz_median'),r.get('xyz_p90')) for r in (a,a2,b)]],
 ['Sai association / trùng',*[f"{r['wrong']} / {r['duplicate']}" for r in (a,a2,b)]],
 ['RunScan thực (s)',textnum(ar['scan_s']),'NOT TESTED, lấy frame đầu',textnum(br['scan_s'])]])
y=load_csv(ROOT/'detection_by_angle.csv')
objects=sorted({r['instance_gt'] for r in y})
paired=[]
for target in objects:
    v=[]
    for branch,result in [('scan_8x3',a),('scan_36x1',b)]:
        rows=[r for r in y if r['scan']==branch and r['instance_gt']==target]
        d=sum(r['detected']=='True' for r in rows)
        visible=sum(int(r['visible_pixels'])>0 for r in rows)
        confirmed=next((r for r in result['objects'] if r['target']==target),{})
        views=len({r['stop'] for r in rows if r['detected']=='True'})
        v += [f'{d}/{visible} ({views} góc)',cm(confirmed.get('xy'))]
    paired.append([target,*v])
pt=table(['Vật','Đúng/thấy 8×3','XY 8×3 (cm)','Đúng/thấy 36×1','XY 36×1 (cm)'],paired)
book=load_csv(ROOT/'book_angle_probe.csv')
raw=[float(r['raw_book_score']) for r in book if r.get('raw_book_score')]
book_note=f"Probe trước lọc có điểm book tối đa {textnum(max(raw),3)} trên {len(raw)} mẫu có box IoU ≥0,5." if raw else "Kết quả đầu ra hoặc trạng thái probe được ghi trong CSV."
section(parts,'1. RunScan và thông tin theo góc',bt+'\n\n'+pt+'\n\n'+book_note+
    '\n\nCùng scene đã khóa, camera, checkpoint và quy tắc lọc. Lượt 8×3 đầu thiếu quartet ở 225°, lượt 36×1 đầu bị hủy sau khi thiếu ở 40° và 180°. Hai lượt chính đồng bộ quartet qua Gazebo native, còn ROS thực hiện RunScan, perception, TF2, association và ghi SQLite. Lượt 8×3 chính bỏ một observation ghế nền thiếu XYZ trong phản hồi ROS, đồng nhất với SQLite live. Lượt 36×3 NOT TESTED. B1 chạy ROS thật bằng 10° và một frame mỗi điểm. A2 lấy frame index 0. Bốn góc 0°, 90°, 180°, 270° có đối chiếu riêng, các bộ thu ở thời điểm khác nhau. Bằng chứng che khuất trong CSV kiểm tra tia tới tâm với GT mặt trước, nên không diễn giải thành diện tích phần bị che. Cả ba số recall là trên bốn vật hoặc các instance–khung của một bố trí. [Góc và detection](detection_by_angle.csv) · [Depth theo góc](depth_by_angle.csv) · [Góc trùng](shared_angles.csv) · [Probe sách](book_angle_probe.csv) · [Biểu đồ](angle_diagnostics.png) · [Ảnh 8 góc](scan_8x3/all_stops.jpg) · [Ảnh 36 góc](scan_36x1/all_stops.jpg)')
ft=table(['Fusion','XY trung vị/P90 (cm)','XYZ trung vị/P90 (cm)','Confirmed','Sai/trùng','Tốt/xấu','Tính (ms)'],
  [[r['method'],fmt_pair(r.get('xy_median'),r.get('xy_p90')),fmt_pair(r.get('xyz_median'),r.get('xyz_p90')),r['confirmed'],
    f"{r['wrong']}/{r['duplicate']}",f"{r['xy_better']}/{r['xy_worse']}",
    'xem runtime DB' if r['method']=='F0_production' else textnum(1000*r['seconds'])]
    for r in s['fusion']])
rd=load_csv(ROOT/'ransac_diagnostics.csv')
section(parts,'2. Gộp robust',ft+
   f"\n\nRANSAC thử tâm điểm 3D, kiểm tra khoảng cách inlier và độ phủ yaw. {sum(r['accepted']=='True' for r in rd)}/{len(rd)} cụm đủ điều kiện; phần còn lại dùng kết quả gốc. F1–F5 dùng membership và trạng thái sau association F0, nên chỉ đánh giá ảnh hưởng lên vị trí cuối. F5 phân biệt ảnh lặp và các ô yaw, giữ nhóm để so công bằng. [CSV fusion](fusion_comparison.csv) · [RANSAC](ransac_diagnostics.csv)")
g=load_csv(ROOT/'ground_plane_feasibility.csv')+load_csv(ROOT/'crossworld_floor_frames.csv')
dt=load_csv(ROOT/'ground_plane_correction.csv')+load_csv(ROOT/'crossworld_check.csv')
gtab=table(['Tập','n frame','RGB áp dụng','ORACLE áp dụng','Pixel sàn GT trung vị','IoU floor trung bình'],floor_table(g))
dtab=table(['Tập','Phương án','n','Depth MAE cm','AbsRel','Bias cm','XY trung vị/P90 cm','XYZ trung vị/P90 cm','Depth tốt/xấu'],
    depth_table([r for r in dt if r['method'] in ('original','rgb','oracle','kitchen_locked')]))
section(parts,'3. Mặt sàn và metric scale',gtab+'\n\n'+dtab+
    '\n\nTia đơn vị axial được tạo từ K, xoay bằng TF rồi giao mặt phẳng ngang. Loại tia sau camera, gần chân trời và ngoài dải. Hệ số RGB dùng mask YOLOE floor và depth dự đoán, rồi median theo ô ảnh. ORACLE chỉ dùng để chẩn đoán giới hạn, nhận diện sàn bằng depth GT gần mặt phẳng. Thiếu pixel/ô, ratio phân tán hoặc ngoài dải thì trả về gốc. Nhiễu chiều cao ±2 cm và pitch ±1° có trong CSV với các nhánh riêng. AWS/Tiffany là dữ liệu chẩn đoán có sẵn, mỗi điều kiện camera đứng yên, không dùng để fit hệ số GT hay xác nhận fusion nhiều góc. [Sàn Kitchen](ground_plane_feasibility.csv) · [Hiệu chỉnh Kitchen](ground_plane_correction.csv) · [Sàn ngoại phòng](crossworld_floor_frames.csv) · [Depth ngoại phòng](crossworld_check.csv)')
tri=read(ROOT/'triangulation_summary.json')
matches=tri['tested']
sens=table(['Vật','Stop A/B','Baseline cm','ΔZ 0,5 / 1 / 2 px cm','ORB match / qua hình học','n GT / median cm'],
  [[r['target'],f"{r['first']}/{r['second']}",cm(r['baseline_m']),' / '.join(cm(r[k]) for k in ('d05','d1','d2')),
    f"{r['ratio_matches']}/{r['accepted']}",f"{r['gt_scored']} / {cm(r.get('gt_abs_error_median'))}"] for r in matches])
tri_body=f"Baseline quang học lớn nhất {cm(tri['max_baseline_m'])} cm trong {tri['pairs']} cặp TF. {tri['candidate_pairs_under_10cm_per_px']}/{tri['candidate_same_object_pairs']} cặp chồng quan sát có độ nhạy dưới 10 cm ở nhiễu 1 px. Chọn cặp chẩn đoán theo association cùng lớp và baseline. Correspondence ORB dùng RGB và mask YOLOE, rồi kiểm cheirality và reprojection ≤1 px. Nhãn GT và depth GT chỉ chấm sau đó. Độ nhạy nhiễu dùng cùng một điểm giả định chiếu vào hai camera, tránh giả định hai tâm mask là cùng điểm.\n\n"+sens
(ROOT/'triangulation_feasibility.md').write_text('# Khả thi triangulation\n\n'+tri_body+'\n',encoding='utf-8')
section(parts,'4. Triangulation',tri_body+'\n\n[Chi tiết](triangulation_feasibility.md) · [Tâm quang học](optical_trajectory.csv) · [Các cặp baseline](optical_baselines.csv)')
tem=table(['Keyframe','Gọi depth / tiết kiệm','Confirmed','AbsRel','XY median/P90 cm','Propagation / ID sai có GT','Tuổi P90 s','Depth dự kiến s'],
  [[r['method'],f"{r['depth_calls']}/{r['depth_calls_saved']}",r['confirmed'],pct(r.get('depth_absrel')),fmt_pair(r.get('xy_median'),r.get('xy_p90')),
    f"{r.get('propagated',0)} / {r.get('propagated_wrong_known_id',0)}",textnum(r.get('depth_age_p90_s')),textnum(r['depth_inference_est_s'])]
    for r in s['temporal']])
view=table(['Góc','Gọi depth','Confirmed','AbsRel','XY median/P90 cm','Sai/trùng','Depth dự kiến s'],
  [[r['method'],r['depth_calls'],r['confirmed'],pct(r.get('depth_absrel')),fmt_pair(r.get('xy_median'),r.get('xy_p90')),
    f"{r['wrong']}/{r['duplicate']}",textnum(r['depth_inference_est_s'])] for r in s['view']])
section(parts,'5. Temporal và chọn góc',tem+'\n\n'+view+
    '\n\nỞ non-key, dùng track điểm world gần nhất nếu projection lọt mask, khớp lớp duy nhất và đủ điều kiện tuổi/góc. Các observation lan truyền là bằng chứng nhận diện mới cho vị trí cũ, không phải đo depth độc lập. Chi phí depth dự kiến tính bằng thời gian Metric3D đã đo của chính keyframe, còn việc chọn góc chất lượng vẫn đòi xem RGB/YOLOE của các góc. Runtime của các nhánh là offline, ROS end-to-end chỉ đo A1 và B1. [Temporal](temporal_keyframe_results.csv) · [Viewpoint](viewpoint_selection.csv)')
pt=table(['Nhánh','Phương pháp','Recall','AbsRel','XY median/P90 cm','Sai/trùng','Thời gian','Trạng thái'],[
 [r['branch'],r.get('method','—'),pct(r.get('recall')),pct(r.get('depth_absrel')),fmt_pair(r.get('xy_median'),r.get('xy_p90')),
  f"{r['wrong']}/{r['duplicate']}" if 'wrong' in r else '—',
  f"{textnum(ar['scan_s'])} s ROS" if r['branch']=='P0' else
  f"{textnum(br['scan_s'])} s ROS" if r['branch']=='P1' else
  f"{textnum(r.get('seconds'),3)} s replay + {textnum(r.get('floor_extra_cpu_s'),1)} s CPU floor" if r['branch']=='P3' else
  f"{textnum(r.get('seconds'),3)} s offline" if r.get('seconds') is not None else '—',
  r['classification']] for r in pipeline['branches']])
rt=table(['Scan','RunScan s','Settle s','Capture service s','YOLOE s','Metric3D s','Replay+DB s','Query offline s','Peak MiB','Thiếu XYZ live'],[
  [r['scan'],*[textnum(r[k],3) for k in ('scan_s','configured_settle_s','capture_service_s','yolo_s','depth_s',
    'replay_assoc_sqlite_s','offline_query_checks_s')],r.get('device_peak_sampled_mib') or '—',r['wire_projection_missing']] for r in pipeline['runtime']])
gpu=load_csv(ROOT/'gpu_samples.csv')
peak=max((int(r['memory_used_mib'].strip()) for r in gpu),default=None)
section(parts,'6. Toàn pipeline và thời gian',pt+'\n\n'+rt+
    f"\n\nGPU GTX 1650, peak lấy mẫu thiết bị {peak if peak is not None else 'NOT TESTED'} MiB, bao gồm Gazebo và tiến trình khác nếu có. Jetson Xavier và navigation tránh vật cản NOT TESTED. Query và approach 0,6 m được kiểm tra hình học. Regression 59 LOC3D, 79 YOLOE, 4 test diagnostic hình học/robust đều qua. [Phương án](pipeline_comparison.csv) · [Runtime](runtime_summary.csv) · [LOC3D](regression_loc3d_final.log) · [YOLOE](regression_yoloe_final.log) · [Hình học](regression_geometry_final.log)")
section(parts,'7. Kết luận', '1. **36 góc tăng nhận diện nhưng chưa cải thiện định vị nhất quán.** Detection recall theo instance–khung tăng từ 12/21 lên 20/30, tương đương 57,1% → 66,7%. Cả hai xác nhận đúng 3/4 vật. XY trung vị giảm khoảng 1,0 cm nhưng P90 tăng khoảng 1,6 cm. Lượt 36×1 mất thêm 128,4 s trên GTX 1650. Đối chứng 8×1 xác nhận 0/4 vì số quan sát mỗi vật không đủ điều kiện hiện hành.\n2. **Sách có tín hiệu mới.** Hai mask đúng ở 330° và 340°, confidence 0,381 và 0,399, IoU 0,968 và 0,948. Cả hai truncated, dưới cả ngưỡng confidence tạo cụm mới 0,40. Với chỉ hai quan sát, sách cũng chưa đạt min_obs = 3.\n3. **Giữ weighted mean làm mốc gộp.** F5 cân bằng góc có XY trung vị 36,4 cm thay vì 37,7 cm, nhưng P90 tăng từ 45,1 lên 47,1 cm. F1 và F2 làm cả ba vật xấu đi. F3 nhận 4/7 cụm toàn cảnh, trong ba vật chấm XY có một tốt hơn, một xấu hơn và một không đổi. Trung vị F3 tăng lên 40,3 cm. Tất cả observations của từng vật nằm về một phía của tâm GT theo hướng sai số trung bình. [Audit sai lệch cụm](fusion_bias_diagnostics.csv)\n4. **Geometry sàn có điều kiện.** YOLOE floor không cho scale được chấp nhận ở cả 60 khung Kitchen. Oracle đủ điều kiện ở 6/24 và 5/36. Trên AWS, RGB áp dụng được ở 16/18 khung, IoU sàn trung bình khoảng 0,84 và AbsRel trên detection được chấm giảm khoảng 25,8% → 9%. Trên Tiffany RGB áp dụng 0/18 dù oracle có thể hiệu chỉnh. Ở AWS, sai lệch pose thử nghiệm đưa AbsRel khoảng 6–15%. Chiều cao và phép chiếu có thể cung cấp tham chiếu metric khi nhận diện được sàn và có tia hợp lệ.\n5. **Triangulation khả thi ở một số cặp Gazebo.** Các cặp ORB được thử có baseline 0,87–4,22 cm. Sai số axial trung vị theo cặp là 2,35–9,89 cm trên các điểm được chấm. Nhiễu 1 px gây sai số dự kiến 1,9–14,4 cm tùy cặp. Đây là phép đo điểm bề mặt trên vật có texture, chưa đánh giá tâm vật cuối trong SQLite, cảnh động hoặc camera thật.\n6. **Giảm số lượt depth có triển vọng về chi phí.** Keyframe 30° dùng 12 thay vì 36 lần chạy, thời gian Metric3D dự kiến 52,2 thay vì 155,1 s. Giữ 3/4 vật, XY trung vị 36,0 cm, P90 44,4 cm. Một trong ba vật xấu đi. V_quality cũng dùng 12 lượt và tái lập kết quả B1 trên bố trí này; cần YOLOE qua toàn lượt để chọn. Cả hai đều là replay offline.\n7. **Kết hợp P6 và kiểm chứng độc lập.** Chỉ T2 mỗi 20° qua ngưỡng cải thiện trung vị 2 cm đã khóa. Nhánh này làm hai trong ba vật xấu đi. F5 không qua ngưỡng, P3 fallback toàn lượt Kitchen, và viewpoint chất lượng là lựa chọn giảm chi phí cùng loại với keyframe. Không có cặp thành phần phù hợp để tiến tới holdout P6. P6 và Xavier là NOT TESTED. Các nhánh Kitchen đã đo chưa đạt đồng thời AbsRel ≤15%, XY trung vị ≤30 cm và recall ≥80%. Nút thắt định vị hiện là depth lệch có hệ thống; nút thắt recall là sách chỉ được thấy đúng ở góc bị cắt.\n\n**Ưu tiên tiếp theo duy nhất** là khóa các kiểm tra match và reprojection ORB đã dùng, rồi kiểm chứng triangulation trên một bố trí Kitchen mới. Chấm cả độ chính xác điểm bề mặt lẫn XY tâm vật cuối, với số vật và số cặp đủ điều kiện được báo riêng.')
section(parts,'Artifact và lệnh chạy','[Thiết kế khóa](PLAN.md) · [SQLite A1](scan_8x3/replay_A.sqlite) · [SQLite A2](A2_8x1.sqlite) · [SQLite B1](scan_36x1/replay_A.sqlite) · [Log 8×3 lần thiếu](scan_8x3_incomplete/launch.log) · [Log 36×1 lần hủy](scan_36x1_incomplete/launch.log) · [Manifest](manifest.json)\n\nChạy trong WSL tại /mnt/d/loc3d_ws. Thư mục batch chứa run_scans.sh, analyze_complete.sh và các script từng nhánh. Dùng môi trường LOC3D hiện có để replay, venv Windows yoloe_test để chạy unittest. Tìm theo tên Consensus và log nghiên cứu trong hai workspace đã nêu, không tìm thấy tài liệu tương ứng.'+'\n\n'+'Lệnh thực tế (WSL, từ /mnt/d/loc3d_ws; $BATCH là đường dẫn thư mục báo cáo).\n\n~~~bash\nbash "$BATCH/run_scans.sh"                 # hai lượt đầu, giữ log thiếu/hủy\nros2 service call /scan/run/_action/cancel_goal action_msgs/srv/CancelGoal \'{}\'\nbash "$BATCH/run_native_retries.sh"        # hai lượt đầy đủ, qua ROS RunScan\n.venv/bin/python "$BATCH/ground.py" external\nbash "$BATCH/analyze_complete.sh"          # methods, angles, book_probe, ground, pipeline_summary\nbash "$BATCH/post_batch.sh"                # pose Gazebo, hình học diagnostic, pytest LOC3D\n.venv/bin/python "$BATCH/write_report.py"\n~~~\n\nTrên Windows chạy D:\\yoloe_test\\.venv\\Scripts\\python.exe -m unittest discover -s D:\\yoloe_test\\tests. Xác minh SHA-256 bằng verify_batch.py. Việc sửa thu đồng bộ nằm trong use_native_sync.py, chỉ áp dụng lên audit.py bản sao trong batch.')
(ROOT/'REPORT.md').write_text('\n'.join(parts),encoding='utf-8')

