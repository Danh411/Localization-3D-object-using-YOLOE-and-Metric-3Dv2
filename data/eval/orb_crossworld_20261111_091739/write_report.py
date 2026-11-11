"""Write a measured cross-world comparison, reusing the Kitchen report sections."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median
import re

import importlib.util
from verify import csvrows, csvwrite, published, read, sha

ROOT = Path(__file__).resolve().parent
KITCHEN = ROOT.parent / "orb_ground_18angle_fullbatch_20261111_001408"
ROOMS = (("AWS Small House", "aws"), ("Tiffany Living Room", "tiffany"))
spec = importlib.util.spec_from_file_location("kitchen_report_sections", KITCHEN / "write_report.py")
sections = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sections)
sections.ROOT = ROOT
table = sections.table
cm = sections.cm
pct = sections.pct


def load_scan(path):
    data = json.loads(read(path))
    for b in data["branches"].values():
        for metric in ("xy_mean", "xy_median", "xy_p90", "xyz_mean", "xyz_median", "xyz_p90"):
            b.setdefault(metric, None)
    return data


def targets_complete(branch):
    return branch["recall"] >= .8


def accepted(branch):
    return all((branch["depth_absrel"] is not None and branch["depth_absrel"] <= .15,
                branch["xy_median"] is not None and branch["xy_median"] <= .3,
                branch["xy_p90"] is not None and branch["xy_p90"] <= .6,
                branch["recall"] >= .8,
                branch["precision"] is not None and branch["precision"] >= .85,
                branch["duplicate"] / max(1, branch["confirmed"] + branch["wrong"] + branch["duplicate"]) <= .1))


def methods_summary(name, scan):
    out = []
    for key, branch in scan["branches"].items():
        out.append(dict(room=name, branch=key, confirmed=branch["confirmed"],
                        recall=branch["recall"], precision_scoped=branch["precision"],
                        duplicate=branch["duplicate"], wrong=branch["wrong"],
                        unscored=branch["unscored"], xy_median_m=branch["xy_median"],
                        xy_p90_m=branch["xy_p90"], xyz_median_m=branch["xyz_median"],
                        depth_n=branch["depth_n"], depth_mae_m=branch["depth_mae_m"],
                        depth_bias_m=branch["depth_bias_m"], depth_absrel=branch["depth_absrel"],
                        target_pass=accepted(branch), ros_s=scan["ros_s"] if key == "P0_metric" else None))
    return out


def main():
    scans = [(label, key, load_scan(ROOT / key / "experiment_summary.json")) for label, key in ROOMS]
    kitchen = load_scan(KITCHEN / "holdout_18x1/experiment_summary.json")
    combined = [("Kitchen holdout trước", "kitchen", kitchen), *scans]
    summary = [row for label, _, scan in combined for row in methods_summary(label, scan)]
    csvwrite(ROOT / "crossworld_methods.csv", summary)
    paired = []
    for label, _, scan in combined:
        base = {o["target"]: o for o in scan["branches"]["P0_metric"]["objects"]}
        for method in ("ORB_A_only", "ORB_B_only", "P1_orb_A", "P1_orb_B", "P2_ground", "P3_combined"):
            candidates = {o["target"]: o for o in scan["branches"][method]["objects"]}
            shared = sorted(base.keys() & candidates.keys())
            for target in shared:
                a, b = base[target], candidates[target]
                paired.append(dict(room=label, method=method, target=target,
                                   p0_xy_m=a["xy"], method_xy_m=b["xy"],
                                   p0_xyz_m=a["xyz_error"], method_xyz_m=b["xyz_error"],
                                   xy_improvement_m=a["xy"] - b["xy"],
                                   xyz_improvement_m=a["xyz_error"] - b["xyz_error"],
                                   xy_better=b["xy"] < a["xy"]))
    csvwrite(ROOT / "paired_final.csv", paired)

    comparison = []
    for label, key, scan in combined:
        for method in ("P0_metric", "ORB_A_only", "ORB_B_only", "P2_ground", "P3_combined", "S_on_demand"):
            b = scan["branches"][method]
            comparison.append((label, sections.NAMES[method], f"{b['confirmed']}/4",
                               cm(b["xy_median"]), cm(b["xy_p90"]), cm(b["xyz_median"]),
                               pct(b["depth_absrel"]), "PASS" if accepted(b) else "FAIL"))
    new_results = []
    for label, key, scan in scans:
        p0, p3 = (scan["branches"][name] for name in ("P0_metric", "P3_combined"))
        new_results.append(
            f"{label} có {scan['visibility']['true']}/{scan['visibility']['visible']} lượt "
            f"nhận diện đúng. Confirmed P0 → P3 là {p0['confirmed']}/4 → {p3['confirmed']}/4. XY trung vị "
            f"P0 {cm(p0['xy_median'])} cm (n={p0['confirmed']}), P3 {cm(p3['xy_median'])} cm (n={p3['confirmed']}), "
            f"AbsRel {pct(p0['depth_absrel'])} → {pct(p3['depth_absrel'])}."
        )
    report = [
        "# ORB và Metric3D trên AWS Small House và Tiffany Living Room", "",
        *new_results, "",
        "Hai lượt mới chạy ROS đủ 18 stop/phòng. Kết quả ORB, sàn và fallback được replay "
        "trên cùng dữ liệu đã thu. Camera giữ 1280×720 và FOV 70°, fx=fy=914,014701 px, "
        "cx=640, cy=360. Metric3D ViT-Small giữ 616×1064. Các ngưỡng ORB giống từng byte "
        "với Kitchen, đã khóa trước khi chụp ảnh đánh giá. Số đo Kitchen ở bảng dưới lấy từ "
        "holdout đã chạy trước. Hai phòng mới có lượt thu và inference mới.", "",
        *table(["World", "Phương pháp", "Confirmed", "XY TV (cm)", "XY P90 (cm)",
                "XYZ TV (cm)", "Depth AbsRel", "Đủ tiêu chí đồ án"], comparison),
        "Tiêu chí đồng thời gồm AbsRel ≤15%, XY trung vị ≤30 cm, XY P90 ≤60 cm, "
        "recall confirmed ≥80%, precision có nhãn ≥85% và duplicate ≤10%. "
        "Với bốn vật, confirmed 3/4 tương ứng 75%. Sai số tọa độ được báo cùng số vật "
        "có kết quả, các vật thất bại vẫn ở mẫu số recall. Precision chỉ áp dụng vùng có "
        "instance GT. Các vật nội thất khác chưa có GT được ghi ngoài phạm vi.", "",
        "Đối chứng cuối SQLite trên các vật có kết quả ở cả P0 và P3. "
        "Các số trung vị trước/sau ở đây dùng cùng tập vật.", "",
        *table(["World", "Số vật ghép cặp", "P0 XY TV (cm)", "P3 XY TV (cm)", "Tốt / xấu hơn"],
               [(label, len(samples),
                 cm(median(float(r["p0_xy_m"]) for r in samples)) if samples else sections.NA,
                 cm(median(float(r["method_xy_m"]) for r in samples)) if samples else sections.NA,
                 f"{sum(r['xy_better'] for r in samples)}/{sum(not r['xy_better'] for r in samples)}")
                for label, _, _ in combined
                for samples in [[r for r in paired if r["room"] == label and r["method"] == "P3_combined"]]]),
        "[Từng vật ghép cặp](paired_final.csv)", "",

        "## Điều kiện thử và dữ liệu đầu vào", "",
        "Các bộ calibration AWS/Tiffany cũ thay vị trí hoặc vật giữa các lần chụp, nên "
        "chưa cung cấp các cặp nhìn cùng vật đứng yên cần cho phép thử này. Batch mới "
        "đặt đồng thời chai, cốc, laptop và sách, cố định vật trong suốt một lượt 360°. "
        "Mỗi phòng dùng vị trí camera riêng đã được xác minh ở batch trước, cao 0,36 m. "
        "Kitchen holdout trước dùng camera cao 1,10 m và vật trên bàn. Vì vậy, bảng giữa "
        "ba world phản ánh cả điều kiện bố trí/camera, chưa cô lập ảnh hưởng riêng của world.", "",
        *table(["Phòng", "Camera base XYZ (m)", "Yaw base", "Hướng khu vực vật", "Cao độ sàn (m)"], [
            ("AWS", "−2,00 / 0,75 / 0,36", "0°", "Bắc, quanh 90°", "0,006"),
            ("Tiffany", "−1,85 / 1,38 / 0,36", "0°", "Đông, quanh 0°", "0,003"),
        ]),
        "Broadcaster production hỗ trợ base song song trục world. Bản sao rig đặt yaw "
        "base 0°, còn các góc quét bao phủ toàn phòng. TF được lấy đúng stamp và kiểm "
        "với yaw joint, pose rig được so với Gazebo. Bốn asset và texture dùng lại từ "
        "Kitchen, đặt trên sàn với AABB không chồng nhau. Tâm mesh tính theo phép biến "
        "đổi pose riêng của từng phòng. Cao độ sàn lấy từ cấu hình scene, không fit theo GT.", "",
        "AWS ban đầu dùng bước physics 5 ms. Lượt đầu ghi được stop 0, sau đó pan dao động "
        "với vận tốc joint đo tới khoảng ±1111 rad/s. Đã dừng lượt này và giữ dữ liệu/log "
        "trong aws_initial_unstable. Bản sao AWS được đổi bước physics thành 1 ms giống "
        "Kitchen. Các ngưỡng nhận diện, ORB, association và camera được giữ như đã khóa. "
        "Tiffany vốn dùng 1 ms. Frozen inputs được ghi lại trước các lượt đánh giá hợp lệ. "
        "Nguồn world và asset gốc giữ nguyên. Chỉ kết quả lượt đủ 18 stop được chấm.", "",
        "ORB-A lấy median XYZ của điểm bề mặt. ORB-B lấy median optical Z rồi chiếu qua "
        "centroid mask RGB đã erode bằng K/TF. Sàn dùng cùng bộ tìm vùng floor RGB và "
        "gate đã thử ở Kitchen. P3 chọn ORB-B → sàn → Metric3D gốc theo các gate đó. "
        "GT panoptic/depth và tâm mesh chỉ dùng để chấm. Oracle sàn được ghi riêng. "
        "Không dùng hệ số hiệu chỉnh được fit ở Kitchen hoặc từng phòng trong P0/P3.", "",
        "[Thiết kế](PLAN.md) · [Frozen inputs](frozen.json) · [QA](verification.json) · "
        "[Pose AWS](aws/layout.json) · [Pose Tiffany](tiffany/layout.json) · "
        "[Nguồn và commit world](../metric3d_crossworld_fullbatch_20261110_222348/world_sources.json)", "",
    ]
    for label, key, scan in scans:
        report.extend(sections.scan_report(label, key, scan))
    report += [
        "### Trường hợp giảm recall ở Tiffany", "",
        "P0 xác nhận chai/cốc/laptop nhưng cả ba đều lệch XY trên 50 cm. P3 xác nhận "
        "cốc và laptop, với XY lần lượt 5,8 và 11,2 cm. Chai có hai observations ORB "
        "gần nhau, còn stop 16 thiếu feature và dùng Metric3D. Quan sát dự phòng nằm "
        "cách vị trí ORB hiện có 1,153 m, vượt radius association 0,35 m. Confidence "
        "của observation này là 0,3668, dưới mức 0,4 để tạo object mới. Vì vậy nó "
        "được lưu với object_id rỗng, bản ghi chai chỉ có hai observations và bị rejected "
        "theo min_obs=3. Đây là giới hạn đã tái hiện khi trộn các nguồn depth có bias "
        "khác nhau trong association hiện tại.", "",
        "Ở AWS, P0 và P3 cùng confirmed chai. ORB cũng tính được vị trí cốc ở hai ảnh, "
        "nhưng chưa đủ ba observations. Laptop và sách không có detection đáp ứng matching "
        "trên lượt này. ORB không khôi phục được vật khi detector chưa cung cấp vùng phù hợp.", "",
        "[Observation và nguồn đo](association_sources.csv) · "
        "[Bằng chứng association chai Tiffany](tiffany_bottle_association.json)", "",
        "Ưu tiên thử tiếp là lấy bổ sung góc nhìn cho các vật đang thiếu observations "
        "ORB, rồi kiểm chứng có giữ được recall cùng mức giảm sai số hay không. "
        "Đây là đề xuất cho lượt sau.", "",

        "## Kết luận kiểm chứng", "",
        *table(["Hạng mục", "Kết quả", "Bằng chứng"], [
            ("Thu mới 18×1 mỗi world", "PASS", "Hai action SUCCEEDED, 36 quartet đồng bộ"),
            ("Không chọn lại ngưỡng ORB", "PASS", "orb.py giống Kitchen, frozen hashes trước/sau khớp"),
            ("K, TF, pan, GT instance và depth", "PASS",
             "capture_audit.csv, pose_check.json, sensor_instance_qa.csv và verification.json"),
            ("P0 khớp SQLite live, confidence và query", "PASS",
             "replay strict, foreign keys, conf_sum/conf_mean, nearest/radius/approach"),
            ("Ngưỡng chất lượng toàn hệ thống ở AWS",
             "PASS" if accepted(scans[0][2]["branches"]["P3_combined"]) else "FAIL",
             "crossworld_methods.csv"),
            ("Ngưỡng chất lượng toàn hệ thống ở Tiffany",
             "PASS" if accepted(scans[1][2]["branches"]["P3_combined"]) else "FAIL",
             "crossworld_methods.csv"),
            ("Regression", "PASS", "59 LOC3D + 79 YOLOE + 4 diagnostic"),
            ("Thời gian ORB end-to-end ROS và camera thật", "NOT TESTED",
             "ORB chỉ chạy offline; camera pose lấy từ Gazebo/TF"),
        ]),
        "Mỗi world hiện có một bố trí và một lượt hợp lệ. Kết quả đủ để kiểm tra phương pháp "
        "ở hai điều kiện mới, chưa xác định độ ổn định qua nhiều lần lặp hoặc robot thật. "
        "Các ảnh ngoài FOV, cắt biên, thiếu detection và thiếu ORB được giữ trong CSV. "
        "Nhiều feature trong một cặp và các góc cùng một vật có tương quan.", "",
        "Giữ riêng lỗi bề mặt, lỗi đại diện và lỗi SQLite. Các điểm bề mặt chỉ được chấm "
        "khi pixel ở cả hai ảnh có GT cùng instance. Nhiều điểm trên một detection "
        "vẫn chỉ tạo tối đa một observation. Vị trí bề mặt chưa phải tâm hình học của vật.", "",
        "Đối với triển khai trực tiếp, đọc thêm nhánh S_on_demand chỉ dùng ảnh quá khứ. "
        "P3 offline có thể dùng ảnh ở các stop chụp sau. Mức tiết kiệm Metric3D trong runtime.csv "
        "là tổng inference time của các frame chọn lại, chưa phải thời gian quét ROS của P3.", "",
        "## Lệnh đã chạy và artifact", "",
        "Các lệnh WSL chạy từ /mnt/d/loc3d_ws. Lần đầu run_batch.sh dừng ở diagnostic adapter "
        "trước khi chụp. Đã sửa phạm vi thay chuỗi floor-height trong adapter và giữ "
        "regression_diagnostic_initial.log. QA panoptic kiểm tra cặp semantic label và instance count. "
        "Instance count có thể trùng giữa các semantic label, như đã đối chiếu header Gazebo rendering. "
        "Lượt AWS physics 5 ms dừng ở stop đầu. "
        "Sau khi lưu log và đổi physics của bản sao, resume.sh chạy hai lượt đánh giá.", "",
        "```bash",
        'b="$PWD/data/eval/orb_crossworld_20261111_091739"',
        'bash "$b/run_batch.sh"',
        'bash "$b/resume.sh"',
        '# Within the runners, once for each room:',
        'bash "$b/capture.sh" aws',
        '.venv/bin/python "$b/experiment.py" aws',
        'bash "$b/capture.sh" tiffany',
        '.venv/bin/python "$b/experiment.py" tiffany',
        '.venv/bin/python "$b/test_diagnostic.py"',
        '.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$b/tmp/pytest" tests',
        '.venv/bin/python "$b/verify.py"',
        '.venv/bin/python "$b/association_trace.py"',
        '.venv/bin/python "$b/write_report.py"',
        "```", "",
        "YOLOE regression chạy trong PowerShell tại D:\\yoloe_test.", "",
        "```powershell",
        r".\.venv\Scripts\python.exe -m unittest discover -s tests",
        "```", "",
        "[LOC3D tests](regression_loc3d.log) · [YOLOE tests](regression_yoloe.log) · "
        "[Diagnostic tests](regression_diagnostic.log) · [Bảng tổng hợp](crossworld_methods.csv) · "
        "[Manifest SHA-256](manifest.sha256) · [Hash frame gốc local](raw_frames.sha256) · "
        "[Phạm vi công bố](PUBLISHED.md)", "",
    ]
    (ROOT / "REPORT.md").write_text("\n".join(report), encoding="utf-8", newline="\n")
    for path in (ROOT / "aws" / "frames", ROOT / "tiffany" / "frames"):
        assert len(list(path.glob("*.npz"))) == 18
    raw = sorted(path for room in ("aws", "tiffany") for path in (ROOT / room / "frames").glob("*.npz"))
    (ROOT / "raw_frames.sha256").write_text(
        "".join(f"{sha(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in raw), encoding="utf-8")
    publish = sorted(published())
    (ROOT / "manifest.sha256").write_text(
        "".join(f"{sha(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in publish), encoding="utf-8")
    print(f"Report, {len(publish)} publication hashes, {len(raw)} raw frame hashes written")


if __name__ == "__main__":
    main()
