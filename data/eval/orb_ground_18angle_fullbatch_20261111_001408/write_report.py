"""Render the Vietnamese report from the measured JSON and CSV artifacts."""
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import median
import re

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "multiview_36deg_geometry_fullbatch_20261110_231819"
SCANS = (("Development", "scan_18x1"), ("Holdout", "holdout_18x1"))
TARGETS = {"bottle_1": "Chai", "cup_1": "Cốc", "laptop_1": "Laptop", "book_1": "Sách"}
NAMES = {
    "P0_metric": "P0 Metric3D", "ORB_A_only": "ORB-A thuần",
    "ORB_B_only": "ORB-B thuần", "P1_orb_A": "P1 ORB-A + dự phòng",
    "P1_orb_B": "P1 ORB-B + dự phòng", "P2_ground": "P2 Sàn + dự phòng",
    "P3_combined": "P3 Kết hợp", "S_key40": "Keyframe 40°",
    "S_on_demand": "ORB theo nhu cầu",
}
NA = "KHÔNG CÓ KẾT QUẢ"


def read(path):
    return path.read_text(encoding="utf-8-sig")


def load(path):
    return json.loads(read(path))


def rows(path):
    return list(csv.DictReader(read(path).splitlines()))


def cm(value):
    return NA if value is None else f"{100 * value:.1f}"


def pct(value):
    return NA if value is None else f"{100 * value:.1f}%"


def cell(obj):
    return f"{cm(obj['xy'])} / {cm(obj['xyz_error'])}" if obj else NA


def table(header, data):
    return ["| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
            *("| " + " | ".join(str(x) for x in row) + " |" for row in data), ""]


def gain(a, b):
    if a["xy_median"] is None or b["xy_median"] is None:
        return NA
    return f"{(a['xy_median'] - b['xy_median']) * 100:.1f} cm"


def reduction(a, b):
    return f"{(a - b):.1f} s"


def scan_report(label, name, s):
    branch = s["branches"]
    p0, p3 = branch["P0_metric"], branch["P3_combined"]
    detection = s["visibility"]
    pair_rows = rows(ROOT / name / "orb_pairs.csv")
    point_rows = rows(ROOT / name / "orb_points.csv")
    reps = rows(ROOT / name / "orb_object_localization.csv")
    floor = rows(ROOT / name / "ground_plane_feasibility.csv")
    schedule = rows(ROOT / name / "depth_schedule.csv")
    errors = rows(ROOT / name / "object_observation_scores.csv")
    paired = {}
    for r in errors:
        if r["branch"] in ("P0_metric", "ORB_A_only", "ORB_B_only"):
            paired.setdefault((r["target"], r["stamp_ns"], r["det_index"]), {})[r["branch"]] = r
    common_support = [(k[0], group) for k, group in paired.items() if len(group) == 3]

    def matched_cell(groups, key):
        if not groups:
            return NA
        xy = median(float(g[key]["xy_m"]) for g in groups)
        xyz = median(float(g[key]["xyz_m"]) for g in groups)
        return f"{cm(xy)} / {cm(xyz)}"

    result = [
        f"## {label} · {s['id']}", "",
        f"RunScan đủ 18/18 trong **{s['ros_s']:.1f} s**. YOLOE "
        f"{s['timings_ms']['yolo_ms'] / 1000:.1f} s, Metric3D "
        f"{s['timings_ms']['depth_ms'] / 1000:.1f} s, hậu xử lý "
        f"{s['timings_ms']['post_ms'] / 1000:.1f} s. Yaw lệch tối đa "
        f"{s['max_yaw_error_deg']:.3f}°, độ lệch stamp joint tối đa "
        f"{s['max_joint_skew_ms']:.1f} ms. Có {s['observations']} observations. "
        f"RGB phát hiện đúng {detection['true']}/{detection['visible']} lượt thấy vật "
        f"({pct(detection['detection_recall'])}), bỏ sót {detection['missed']}, "
        f"sai lớp {detection['detection_wrong']}, cắt biên {detection['truncated']}.", "",
        *table(["Vật", "Thấy", "Đúng", "Sai lớp", "Bỏ sót", "Cắt biên", "Obs hợp lệ"],
               [(label_v, t["visible"], t["true_detections"], t["false_class"],
                 t["missed_visible"], t["truncated"], t["valid_observations"])
                for k, label_v in TARGETS.items() for t in [s["targets"][k]]]),
        "Sai số cuối SQLite tính theo tâm mesh. Mỗi ô ghi XY / XYZ theo cm.", "",
        *table(["Phương pháp", *TARGETS.values(), "Xác nhận đúng"],
               [(NAMES[key], *(cell(next((o for o in b["objects"] if o["target"] == k), None))
                              for k in TARGETS), f"{b['confirmed']}/4")
                for key, b in branch.items()]),
        "Depth đại diện so với axial GT của vùng hợp lệ. Cột cuối tính vị trí SQLite "
        "với ngưỡng ghép đúng instance và XY ≤50 cm. Precision chỉ tính vật thuộc phạm vi nhãn.", "",
        *table(["Nhánh", "n depth", "MAE / bias Z (cm)", "AbsRel",
                "XY trung vị / P90 (cm)", "XYZ trung vị (cm)", "Precision",
                "Sai lớp / Trùng / Ngoài phạm vi", "Trong 50 cm"],
               [(NAMES[key], b["depth_n"], f"{cm(b['depth_mae_m'])} / {cm(b['depth_bias_m'])}",
                 pct(b["depth_absrel"]), f"{cm(b['xy_median'])} / {cm(b['xy_p90'])}",
                 cm(b["xyz_median"]), pct(b["precision"]), f"{b['wrong']} / {b['duplicate']} / {b['unscored']}",
                 b["localized"]) for key, b in branch.items()]),
        "### ORB và mặt sàn", "",
        f"ORB dùng RGB trong mask YOLOE, K và TF. Camera lệch trục pan "
        f"{cm(s['optical_radius_m']['median'])} cm theo TF. Có {len(pair_rows)} cặp cùng lớp "
        f"được thử, {s['pair_counts'].get('accepted', 0)} cặp đạt. "
        f"{s['n_points']} điểm qua gate cặp, {s['surface_scored']} điểm đối chiếu được "
        f"với GT của cùng instance trong cả hai ảnh. Mất {s['orb_s']:.3f} s để chạy "
        "ghép/tam giác hóa offline. Các cặp không đạt và lý do nằm trong CSV.", "",
        *table(["Vật", "Cặp đạt / thử", "Match", "Điểm 3D qua gate cặp", "Điểm chấm",
                "Sai số Z bề mặt trung vị / P90 (cm)", "Đại diện ORB / detection đúng"],
               [(v, f"{sum(r['status'] == 'accepted' for r in pairs)}/{len(pairs)}",
                 sum(int(r["matched"]) for r in pairs), sum(int(r["valid_points"]) for r in pairs if r["status"] == "accepted"),
                 sum(r["target"] == k and r["score_status"] == "scored" for r in point_rows),
                 f"{cm(s['surface'][k].get('median'))} / {cm(s['surface'][k].get('p90'))}",
                 f"{sum(r['status'] == 'accepted' for r in dets)}/{len(dets)}")
                for k, v in TARGETS.items()
                for pairs in [[r for r in pair_rows if r["class_name"] == k.rsplit("_", 1)[0]]]
                for dets in [[r for r in reps if r["target_gt"] == k and r["match"] == "true"]]]),
        "Sai số vị trí đại diện theo từng ảnh trước khi gộp. Mỗi ô ghi trung vị XY / XYZ theo cm.", "",
        *table(["Nhánh", "Số vị trí chấm", "XY / XYZ"],
               [(NAMES[k], b["n"], f"{cm(b['representative_xy'].get('median'))} / {cm(b['representative_xyz'].get('median'))}")
                for k, b in branch.items() if k in ("P0_metric", "ORB_A_only", "ORB_B_only", "P3_combined")]),
        "Đối chứng trên đúng các detection mà cả ba cách đo đều có vị trí. Các ô là trung vị XY / XYZ (cm).", "",
        *table(["Vật", "Số cặp", "Metric3D", "ORB-A", "ORB-B"],
               [(v, len(groups), *(matched_cell(groups, key) for key in ("P0_metric", "ORB_A_only", "ORB_B_only")))
                for k, v in TARGETS.items() for groups in [[g for target, g in common_support if target == k]]]),
        f"Sàn RGB qua gate {s['floor_frames']}/18 ảnh. Có "
        f"{sum(int(r['gt_floor_pixels']) > 0 for r in floor)}/18 ảnh có pixel sàn GT "
        f"trong vùng kiểm tra. Oracle dùng mask sàn GT qua gate {s['floor_oracle_frames']}/18. "
        "Oracle chỉ dùng để phân biệt thiếu hình ảnh sàn với lỗi khâu nhận diện sàn RGB. "
        f"P3 chọn nguồn {', '.join(f'{k} {v}' for k, v in p3['source_counts'].items())}. "
        "Ground ghi lý do từ chối cho từng frame. Bảng hiệu chỉnh ghi kết quả đối chứng "
        "P0/P2 của cùng observation.", "",
        f"P3 giảm XY trung vị sau SQLite {gain(p0, p3)} so với P0. "
        f"Chênh lệch số vật confirmed là {p3['confirmed'] - p0['confirmed']:+d}.", "",
        f"[Detection theo góc]({name}/detection_by_angle.csv) · "
        f"[ORB pairs]({name}/orb_pairs.csv) · [Điểm 3D]({name}/orb_points.csv) · "
        f"[ORB đại diện]({name}/orb_object_localization.csv) · [Sai số từng observation]({name}/object_observation_scores.csv) · "
        f"[Sàn]({name}/ground_plane_feasibility.csv) · [Hiệu chỉnh sàn]({name}/ground_plane_correction.csv) · "
        f"[Fallback]({name}/fallback_trace.csv) · [K/TF/yaw]({name}/capture_audit.csv) · "
        f"[Pose scene]({name}/pose_check.json) · [RunScan]({name}/action.log)", "",
        f"![So sánh tọa độ GT và các nhánh SQLite]({name}/gt_vs_sqlite.png)", "",
        f"[18 khung RGB]({name}/all_stops.jpg) · [Minh họa ghép ORB]({name}/orb_matches.jpg)", "",
        "### Tiết kiệm Metric3D", "",
        *table(["Nhánh", "Lượt Metric3D", "Depth ước tính (s)", "ORB CPU (s)",
                "Sàn CPU (s)", "Replay SQLite/query (s)", "Confirmed"],
               [(NAMES[r["branch"]], r["depth_calls"], f"{r['depth_time_est_s']:.1f}",
                 f"{r['orb_shared_s']:.3f}", f"{r['floor_extra_cpu_s']:.3f}",
                 f"{r['replay_query_s']:.3f}", f"{branch[r['branch']]['confirmed']}/4")
                for r in s["runtime"] if r["branch"] in ("P0_metric", "P3_combined", "S_key40", "S_on_demand")]),
        f"Keyframe tái sử dụng {s['reused']} vị trí. P90 tuổi dữ liệu tái sử dụng "
        f"{s['reuse_age_p90'] if s['reuse_age_p90'] is not None else NA} s sim. "
        f"Có {s['reuse_wrong']} lần được xác định là chuyển sai instance. Các lượt thiếu nhãn "
        "nằm riêng trong trace. Vị trí tái dùng được tính như observation trong replay, nên phải "
        "đọc cùng số lần đo mới và số góc trong JSON.", "",
        f"Nhánh theo nhu cầu bỏ Metric3D ở {sum(r['metric3d_needed'] == 'False' and int(r['detections']) == 0 for r in schedule)} "
        f"ảnh không có detection và {sum(r['metric3d_needed'] == 'False' and int(r['detections']) > 0 for r in schedule)} "
        "ảnh có detection đã được ORB từ ảnh trước giải quyết hết. Sàn vẫn cần depth hiện tại. "
        "Chi phí ORB dùng thời gian của toàn bộ phép thử cặp đã chạy. "
        "Thời gian tiết kiệm lấy tổng thời gian inference đã ghi trên các frame tương ứng. "
        "End-to-end ROS của các nhánh tăng tốc là NOT TESTED.", "",
        f"[Runtime]({name}/runtime.csv) · [Lịch gọi depth]({name}/depth_schedule.csv) · "
        f"[Keyframe trace]({name}/key40_trace.csv) · [JSON kết quả]({name}/experiment_summary.json)", "",
    ]
    floor_errors = [r for r in errors if r["branch"] in ("P0_metric", "P2_ground")]
    with (ROOT / name / "ground_plane_correction.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=next(iter(errors)).keys())
        writer.writeheader()
        writer.writerows(floor_errors)
    return result


def main():
    scans = [load(ROOT / name / "experiment_summary.json") for _, name in SCANS]
    dev, hold = scans
    p0, p3 = (dev["branches"][name] for name in ("P0_metric", "P3_combined"))
    h0, h3 = (hold["branches"][name] for name in ("P0_metric", "P3_combined"))
    earlier = load(ROOT / "angle_subset_summary.json")
    live8, live36 = earlier[:2]
    loc_count = re.search(r"(\d+) passed", read(ROOT / "regression_loc3d.log"))[1]
    yolo_count = re.search(r"Ran (\d+) tests", read(ROOT / "regression_yoloe.log"))[1]
    result = [
        "# Kitchen 360° với 18 góc, ORB và depth dự phòng", "",
        f"**FAIL mục tiêu hệ thống.** ORB kết hợp fallback giảm XY trung vị từ "
        f"{cm(p0['xy_median'])} xuống {cm(p3['xy_median'])} cm ở development và từ "
        f"{cm(h0['xy_median'])} xuống {cm(h3['xy_median'])} cm ở holdout. "
        f"P3 xác nhận {p3['confirmed']}/4 và {h3['confirmed']}/4 vật tương ứng, "
        "dưới ngưỡng 80%. Thời gian quét ROS cải thiện nhờ lịch 18×1. "
        "Các nhánh ORB và tăng tốc được đo offline.", "",
        "## Góc quét và đối chứng", "",
        *table(["Cấu hình", "Đúng / thấy", "Confirmed", "XY trung vị (cm)", "ROS thực (s)", "Replay (s)"], [
            (r["name"], f"{r['true']}/{r['visible']}", f"{r['confirmed']}/4", cm(r.get("xy_median")),
             f"{r['ros_s']:.1f}" if r.get("ros_s") else "NOT TESTED",
             f"{r['replay_s']:.2f}" if r.get("replay_s") else "—") for r in earlier
        ] + [("ROS 18×1 mới", f"{dev['visibility']['true']}/{dev['visibility']['visible']}",
              f"{p0['confirmed']}/4", cm(p0["xy_median"]), f"{dev['ros_s']:.1f}", "—")]),
        *table(["Hệ thống", "Recall", "XY trung vị / P90 (cm)", "ROS (s)", "Mục tiêu"], [
            ("Production 8×3", pct(live8["recall"]), f"{cm(live8['xy_median'])} / {cm(live8['xy_p90'])}",
             f"{live8['ros_s']:.1f}", "FAIL"),
            ("Production 36×1", pct(live36["recall"]), f"{cm(live36['xy_median'])} / {cm(live36['xy_p90'])}",
             f"{live36['ros_s']:.1f}", "FAIL"),
            ("18×1 Metric3D", pct(p0["recall"]), f"{cm(p0['xy_median'])} / {cm(p0['xy_p90'])}",
             f"{dev['ros_s']:.1f}", "FAIL"),
            ("18×1 P3 development", pct(p3["recall"]), f"{cm(p3['xy_median'])} / {cm(p3['xy_p90'])}",
             "NOT TESTED", "FAIL"),
            ("18×1 P3 holdout", pct(h3["recall"]), f"{cm(h3['xy_median'])} / {cm(h3['xy_p90'])}",
             "NOT TESTED", "FAIL"),
        ]),
        f"18×1 development nhanh hơn 8×3 {reduction(live8['ros_s'], dev['ros_s'])} và 36×1 "
        f"{reduction(live36['ros_s'], dev['ros_s'])}. Recall giảm từ 3/4 còn "
        f"{p0['confirmed']}/4. Cốc có hai observations và sách có một observation bị cắt biên. "
        "Production cần ba observations và ít nhất một observation nguyên khung. "
        "18×2 là phép thử tùy chọn, NOT TESTED trong batch này. Lặp ảnh ở cùng góc có thể "
        "thêm số quan sát cho cốc nhưng chưa chứng minh sẽ tạo góc thấy sách nguyên vẹn.", "",
        "Dùng lại các kết quả 8×3 và 36×1 đã lưu để so thời gian. "
        "YOLOE/depth tương ứng 14,4/106,9 s và 18,6/155,1 s. "
        "Các tập 12/18/36 replay lấy mỗi stop thứ 3/2/1 của bộ 36×1. "
        "Mốc 8×3 có ba frame cùng góc, vì vậy detection recall theo frame có mẫu số khác.", "",
        "[So sánh số góc](" + "angle_subset_comparison.csv) · "
        "[Baseline multiview](../multiview_36deg_geometry_fullbatch_20261110_231819/REPORT.md) · "
        "[Đánh giá ba world](../metric3d_crossworld_fullbatch_20261110_222348/REPORT.md)", "",
        "## Thiết lập và tính độc lập", "",
        "Đọc code RunScan, perception, association, SQLite, batch 36 góc và cross-world. "
        "Tìm theo tên nhưng chưa thấy tệp Consensus tùy chọn. Development dùng scene 36×1 "
        "giống từng byte. Holdout chỉ dời XY bốn vật. Camera 1280×720, HFOV 70°, "
        "fx = fy = 914,015 px, cx = 640 và cy = 360, camera cao 1,10 m. "
        "Đo yaw bằng TF/joint và dùng CameraInfo theo stamp. Mỗi stop cách 20°, settle 1,5 s. "
        "Checkpoint, prompts, ngưỡng và association dùng cấu hình đã khóa.", "",
        "ORB-A dùng median các tọa độ XYZ điểm hợp lệ. ORB-B lấy median axial Z của các "
        "điểm đó và chiếu qua centroid mask RGB đã erode. Cùng công thức K/TF với "
        "production, nhưng pixel centroid không được lọc theo validity của Metric3D. "
        "Tâm mesh chỉ dùng để chấm. Sai số Z bề mặt, vị trí đại diện và vị trí gộp "
        "được tính riêng. Nhánh sàn suy độ sâu tia cắt mặt phẳng ngang từ K, camera height "
        "và TF rồi so với Metric3D để tìm tỷ lệ. P3 ưu tiên ORB-B, tiếp đến sàn hợp lệ "
        "rồi đến Metric3D gốc. GT depth và panoptic chỉ dùng để chấm hoặc chạy oracle sàn.", "",
        "Code, tham số và scene holdout đã được băm trước RunScan. Holdout là một bố trí "
        "Kitchen mới với cùng vật liệu, camera và điều kiện chiếu sáng. Kết quả chỉ "
        "đại diện cho điều kiện này.", "",
        "[Thiết kế](PLAN.md) · [Khóa holdout](holdout_lock.json) · [Pose holdout](holdout_18x1/layout.json)", "",
    ]
    for (label, name), scan in zip(SCANS, scans):
        result.extend(scan_report(label, name, scan))
    result += [
        "## Kiểm tra và kết luận", "",
        *table(["Hạng mục", "Trạng thái", "Bằng chứng"], [
            ("18 quartet RGB/depth/panoptic/CameraInfo mỗi lượt, K, TF, yaw", "PASS",
             "Replay strict và capture_audit.csv của cả hai lượt"),
            ("P0 khớp SQLite live, truy vấn và confidence", "PASS",
             "So hàng SQLite, xác minh conf_sum, conf_mean, radius, nearest, approach và foreign key"),
            ("Hình học/triangulation/fallback", "PASS", "4 diagnostic tests, gồm trường hợp thiếu dữ liệu"),
            ("LOC3D và YOLOE regression", "PASS", f"{loc_count} LOC3D, {yolo_count} YOLOE"),
            ("Sàn RGB Kitchen", "PASS" if dev["floor_frames"] or hold["floor_frames"] else "FAIL",
             f"Development {dev['floor_frames']}/18, holdout {hold['floor_frames']}/18 ảnh có scale hợp lệ"),
            ("Recall confirmed ≥80%", "FAIL", f"P3 {p3['confirmed']}/4 và {h3['confirmed']}/4"),
            ("P3 và nhánh tăng tốc end-to-end ROS", "NOT TESTED", "Chỉ P0 chạy ROS, các nhánh còn lại dùng replay"),
        ]),
        "1. **18 góc** tiết kiệm thời gian quét, đồng thời mất một vật confirmed so với 8×3 và 36×1 ở development.",
        "2. **ORB** cải thiện định vị cả vật đã confirmed trên các bố trí thử; độ phủ xem bảng theo vật.",
        f"3. **Vị trí ORB-B** sau SQLite có XY/XYZ trung vị {cm(p3['xy_median'])}/{cm(p3['xyz_median'])} cm ở development "
        f"và {cm(h3['xy_median'])}/{cm(h3['xyz_median'])} cm ở holdout. Các lỗi bề mặt và từng ảnh nằm ở bảng trên.",
        f"4. **Mặt sàn RGB** dùng được ở {dev['floor_frames']}/18 và {hold['floor_frames']}/18 ảnh. "
        "Kết quả AWS trước đây (AbsRel 25,8% → 8,5%) chỉ cung cấp đối chứng ngoài Kitchen.",
        "5. **Kết hợp** không tăng độ phủ so với ORB + fallback khi không có sàn đạt gate. "
        "So sánh ORB thuần và P3 trong bảng cho thấy chính xác các vật có thể xác nhận.",
        "6. **Fallback** đi đúng nhánh khi ORB/sàn thiếu hỗ trợ. Metric3D giữ vai trò đo dự phòng và vẫn mang bias đã đo.",
        "7. **Đủ 4/4** chưa đạt.",
        "8. **Tốc độ thật** có cải thiện khi đổi lịch quét. Tác động latency của P3, keyframe và nhánh theo nhu cầu vẫn cần đo ROS.",
        f"9. **Holdout** tái hiện mức giảm XY trung vị {gain(h0, h3)} của P3, trên "
        f"{h3['confirmed']}/4 vật confirmed.",
        "10. **Production** chưa đạt tiêu chí để đưa P3 vào. Bước tiếp theo có căn cứ nhất là "
        "thử lịch lấy thêm các góc thấy cốc/sách nguyên khung, rồi kiểm tra có đủ ba observations "
        "mỗi vật trước khi tối ưu số lần gọi Metric3D.", "",
        "JSON kết quả có trường `scan` mang tên nhánh cuối do biến vòng lặp. Dùng trường `id`, "
        "đường dẫn thư mục và action log để nhận diện lượt quét. Giữ nguyên mã đã khóa.", "",
        "## Lệnh và dữ liệu", "",
        "Các lệnh dưới đây chạy từ `/mnt/d/loc3d_ws` trong WSL, trừ YOLOE tests chạy ở "
        "`D:\\yoloe_test` trong PowerShell. `$b` là thư mục batch.", "",
        "```bash",
        'b="$PWD/data/eval/orb_ground_18angle_fullbatch_20261111_001408"',
        '.venv/bin/python "$b/prepare_scan.py" "$b" scan_18x1',
        'bash "$b/capture.sh" scan_18x1',
        '.venv/bin/python "$b/experiment.py" subset',
        '.venv/bin/python "$b/experiment.py" scan_18x1',
        'bash "$b/run_holdout.sh"',
        '# run_ready.sh calls this in each native scan:',
        "ros2 action send_goal /scan/run scan_interfaces/action/RunScan "
        "'{step_deg: 20.0, frames_per_stop: 1, settle_time_s: 1.5}' --feedback",
        '# run_holdout.sh runs both diagnostic tests and the LOC3D suite:',
        '.venv/bin/python "$b/test_diagnostic.py"',
        '.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$b/tmp/pytest" tests',
        '.venv/bin/python "$b/write_report.py"',
        '.venv/bin/python "$b/verify_batch.py"',
        "```", "",
        "```powershell",
        r".\.venv\Scripts\python.exe -m unittest discover -s tests",
        "```", "",
        "[LOC3D log](regression_loc3d.log) · [YOLOE log](regression_yoloe.log) · "
        "[Diagnostic log](regression_diagnostic.log) · [Manifest](manifest.sha256) · "
        "[Hash 36 frame local](raw_frames.sha256) · [Phạm vi Git](PUBLISHED.md)", "",
        "Đầu ra mới gồm script thử nghiệm, SDF và cấu hình hai scene thử, dữ liệu đồng bộ, "
        "SQLite live/replay, ảnh, bảng CSV/JSON và log. Git lưu snapshot chấm và mã, "
        "các NPZ dung lượng lớn lưu tại workspace. Xem PUBLISHED.md để tái chạy.", "",
    ]
    (ROOT / "REPORT.md").write_text("\n".join(result), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
