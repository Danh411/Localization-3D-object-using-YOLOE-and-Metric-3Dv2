#!/usr/bin/env python3
"""W2-A1/A2: sinh worlds/room.sdf và config/gt_objects.yaml TỪ CÙNG MỘT danh sách vật => không lệch nhau.
Chạy từ gốc repo:  python3 tools/gen_scene.py
Đổi vật sang model thật: thêm khoá  uri: "https://fuel.gazebosim.org/..."  vào OBJECTS (xem W2-B1)."""
import yaml, os, math
ROOM = dict(x=5.0, y=4.0, h=2.8)
CAM = (2.0, 2.0, 1.2)          # = camera.base_xyz trong config/default.yaml
# name, class, shape, (x, y, zc), size (box: sx sy sz | cyl: r len), rgb
OBJECTS = [
 ("chair_1",  "chair",       "box", (3.5, 0.8, 0.45), (0.45, 0.45, 0.9),  (0.5, 0.3, 0.1)),
 ("backpack_1","backpack",   "box", (0.8, 3.2, 0.22), (0.30, 0.20, 0.45), (0.1, 0.2, 0.5)),
 ("plant_1",  "potted_plant","cyl", (4.3, 3.5, 0.25), (0.15, 0.50),       (0.1, 0.5, 0.1)),
 ("tv_1",     "tv",          "box", (2.0, 3.92, 1.0),  (0.90, 0.08, 0.55), (0.05, 0.05, 0.05)),
 ("clock_1",  "clock",       "box", (0.05, 2.0, 1.8),  (0.04, 0.30, 0.30), (0.9, 0.9, 0.9)),
 ("laptop_1", "laptop",      "box", (3.40, 3.05, 0.70), (0.33, 0.23, 0.03), (0.6, 0.6, 0.6)),
 ("keyboard_1","keyboard",   "box", (3.85, 2.70, 0.715), (0.45, 0.15, 0.03), (0.1, 0.1, 0.1)),
 ("mouse_1",  "mouse",       "box", (4.10, 2.95, 0.72),  (0.06, 0.10, 0.04), (0.2, 0.2, 0.2)),
 ("book_1",   "book",        "box", (3.30, 2.70, 0.70), (0.20, 0.15, 0.05), (0.7, 0.1, 0.1)),
 ("cup_1",    "cup",         "cyl", (3.85, 3.10, 0.70),  (0.04, 0.10),       (0.9, 0.9, 0.2)),
 ("bottle_1", "bottle",      "cyl", (3.15, 2.90, 0.83),  (0.04, 0.22),       (0.1, 0.6, 0.8)),
 ("vase_1",   "vase",        "cyl", (4.05, 3.10, 0.80),  (0.05, 0.20),       (0.8, 0.4, 0.2)),
]
FUEL_ASSETS = {
    "laptop_1": {
        "uri": "https://fuel.gazebosim.org/1.0/GoogleResearch/models/Travel_Mate_P_series_Notebook",
        "size": (0.3327, 0.3754, 0.1939),
        "center_z_offset": 0.09695,
        "rpy": (0.0, 0.0, 0.0),
        "label": 3,
    },
    "book_1": {
        "uri": "https://fuel.gazebosim.org/1.0/GoogleResearch/models/Eat_to_Live_The_Amazing_NutrientRich_Program_for_Fast_and_Sustained_Weight_Loss_Revised_Edition_Book",
        "size": (0.1405, 0.0506, 0.2104),
        "center_z_offset": 0.1052,
        "rpy": (0.0, 0.0, 0.0),
        "label": 4,
    },
    "cup_1": {
        "uri": "https://fuel.gazebosim.org/1.0/GoogleResearch/models/ACE_Coffee_Mug_Kristen_16_oz_cup",
        "size": (0.1263, 0.0906, 0.1349),
        "center_z_offset": 0.06745,
        "rpy": (0.0, 0.0, 0.0),
        "label": 1,
    },
    "bottle_1": {
        "uri": "https://fuel.gazebosim.org/1.0/iche033/models/Water%20Bottle",
        "size": (0.1089, 0.1089, 0.2604),
        "center_z_offset": 0.0,
        "rpy": (math.pi / 2.0, 0.0, 0.0),
        "label": 2,
    },
}
TABLE = dict(name="table", pose=(3.65, 2.9, 0.35), size=(1.2, 0.7, 0.70))   # mặt bàn z = 0.70
MARKER = dict(name="yaw_marker", pose=(3.5, 3.5, 0.6), r=0.1, length=1.2)  # W2-A5: magenta, KHÔNG nằm trong GT

def mat(c): return f"<material><ambient>{c[0]} {c[1]} {c[2]} 1</ambient><diffuse>{c[0]} {c[1]} {c[2]} 1</diffuse></material>"
def geom(shape, s):
    if shape == "box": return f"<box><size>{s[0]} {s[1]} {s[2]}</size></box>"
    return f"<cylinder><radius>{s[0]}</radius><length>{s[1]}</length></cylinder>"
def static_model(name, pose, shape, size, rgb):
    g = geom(shape, size)
    return f"""    <model name="{name}"><static>true</static><pose>{pose[0]} {pose[1]} {pose[2]} 0 0 0</pose>
      <link name="link"><collision name="c"><geometry>{g}</geometry></collision>
      <visual name="v"><geometry>{g}</geometry>{mat(rgb)}</visual></link></model>"""

def fuel_model(name, pose, asset):
    p = " ".join(f"{value:.6f}" for value in (*pose, *asset["rpy"]))
    return f"""    <include><uri>{asset["uri"]}</uri><name>{name}</name>
      <pose>{p}</pose><static>true</static>
      <plugin filename="gz-sim-label-system" name="gz::sim::systems::Label">
        <label>{asset["label"]}</label>
      </plugin>
    </include>"""

def room_walls():
    X, Y, H, t = ROOM["x"], ROOM["y"], ROOM["h"], 0.1
    walls = [("wall_s", (X/2, -t/2, H/2), (X, t, H)), ("wall_n", (X/2, Y+t/2, H/2), (X, t, H)),
             ("wall_w", (-t/2, Y/2, H/2), (t, Y, H)), ("wall_e", (X+t/2, Y/2, H/2), (t, Y, H))]
    out = [static_model(n, p, "box", s, (0.85, 0.82, 0.75)) for n, p, s in walls]
    out.append(static_model("floor", (X/2, Y/2, -0.05), "box", (X, Y, 0.1), (0.55, 0.45, 0.35)))
    out.append(static_model("ceiling", (X/2, Y/2, H+0.05), "box", (X, Y, 0.1), (0.95, 0.95, 0.95)))
    return out

RIG = f"""    <model name="camera_rig">
      <pose>{CAM[0]} {CAM[1]} {CAM[2]} 0 0 0</pose>
      <link name="base_link"><inertial><mass>5</mass><inertia><ixx>0.1</ixx><iyy>0.1</iyy><izz>0.1</izz></inertia></inertial>
        <visual name="v"><geometry><cylinder><radius>0.04</radius><length>0.1</length></cylinder></geometry></visual></link>
      <link name="pan_link"><inertial><mass>0.5</mass><inertia><ixx>0.001</ixx><iyy>0.001</iyy><izz>0.001</izz></inertia></inertial>
        <visual name="v"><geometry><box><size>0.06 0.10 0.06</size></box></geometry></visual>
        <sensor name="rgbd" type="rgbd_camera">
          <pose>0.05 0 0 0 0 0</pose>
          <topic>camera</topic><gz_frame_id>camera_optical_frame</gz_frame_id>
          <update_rate>10</update_rate><always_on>true</always_on>
          <camera><horizontal_fov>1.2217305</horizontal_fov>
            <image><width>1280</width><height>720</height><format>R8G8B8</format></image>
            <clip><near>0.1</near><far>10.0</far></clip>
            <noise><type>gaussian</type><mean>0.0</mean><stddev>0.007</stddev></noise>
          </camera>
        </sensor>
        <sensor name="segmentation" type="segmentation">
          <pose>0.05 0 0 0 0 0</pose>
          <topic>camera/segmentation</topic>
          <camera>
            <segmentation_type>instance</segmentation_type>
            <horizontal_fov>1.2217305</horizontal_fov>
            <image><width>1280</width><height>720</height></image>
            <clip><near>0.1</near><far>10.0</far></clip>
          </camera>
          <always_on>true</always_on><update_rate>10</update_rate>
        </sensor>
      </link>
      <joint name="fix" type="fixed"><parent>world</parent><child>base_link</child></joint>
      <joint name="pan_joint" type="revolute"><parent>base_link</parent><child>pan_link</child>
        <axis><xyz>0 0 1</xyz><limit><lower>-1e16</lower><upper>1e16</upper></limit><dynamics><damping>0.5</damping></dynamics></axis></joint>
      <plugin filename="gz-sim-joint-position-controller-system" name="gz::sim::systems::JointPositionController">
        <joint_name>pan_joint</joint_name><topic>pan_cmd</topic><p_gain>20</p_gain><i_gain>0.5</i_gain><d_gain>2.0</d_gain></plugin>
      <plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher">
        <topic>joint_states</topic><joint_name>pan_joint</joint_name></plugin>
    </model>"""

def main():
    parts = ['<?xml version="1.0"?>', '<sdf version="1.9">', '  <world name="room">',
      '    <physics name="1ms" type="ignored"><max_step_size>0.001</max_step_size><real_time_factor>1.0</real_time_factor></physics>',
      '    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>',
      '    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>',
      '    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>',
      '    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>',
      '    <scene><ambient>0.35 0.35 0.35 1</ambient></scene>']
    for i, (x, y) in enumerate([(1.5, 1.0), (3.5, 1.0), (2.5, 3.0)]):
        parts.append(f'    <light type="point" name="lamp{i}"><pose>{x} {y} 2.5 0 0 0</pose><diffuse>0.8 0.8 0.75 1</diffuse>'
                     f'<specular>0.1 0.1 0.1 1</specular><attenuation><range>8</range><constant>0.5</constant><linear>0.05</linear><quadratic>0.01</quadratic></attenuation></light>')
    parts += room_walls()
    parts.append(static_model(TABLE["name"], TABLE["pose"], "box", TABLE["size"], (0.6, 0.45, 0.3)))
    parts.append(static_model(MARKER["name"], MARKER["pose"], "cyl", (MARKER["r"], MARKER["length"]), (1.0, 0.0, 1.0)))
    for n, c, shp, pose, size, rgb in OBJECTS:
        asset = FUEL_ASSETS.get(n)
        parts.append(
            fuel_model(n, pose, asset) if asset else static_model(n, pose, shp, size, rgb)
        )
    parts += [RIG, "  </world>", "</sdf>"]
    os.makedirs("src/room_sim/worlds", exist_ok=True); os.makedirs("config", exist_ok=True)
    open("src/room_sim/worlds/room.sdf", "w").write("\n".join(parts) + "\n")
    gt = []
    for n, c, shape, pose, size, _ in OBJECTS:
        asset = FUEL_ASSETS.get(n)
        dimensions = asset["size"] if asset else (
            (size[0], size[1], size[2]) if shape == "box"
            else (2 * size[0], 2 * size[0], size[1])
        )
        item = dict(
            model_name=n,
            class_name=c,
            shape="mesh" if asset else shape,
            x=pose[0],
            y=pose[1],
            z=pose[2] + (asset["center_z_offset"] if asset else 0.0),
            size_x=dimensions[0],
            size_y=dimensions[1],
            size_z=dimensions[2],
        )
        if asset:
            item["asset_uri"] = asset["uri"]
            item["semantic_label"] = asset["label"]
        gt.append(item)
    yaml.safe_dump({"frame": "world", "objects": gt}, open("config/gt_objects.yaml", "w"), sort_keys=False)
    # kiểm tra khoảng cách cùng lớp >= 0.6 m
    for i, a in enumerate(OBJECTS):
        for b in OBJECTS[i+1:]:
            if a[1] == b[1] and math.dist(a[3][:2], b[3][:2]) < 0.6: raise SystemExit(f"cùng lớp quá gần: {a[0]} {b[0]}")
    for n, c, sh, p, s, _ in OBJECTS:
        print(f"{n:12s} d_cam={math.dist(p[:2], CAM[:2]):.2f} m  bearing={math.degrees(math.atan2(p[1]-CAM[1], p[0]-CAM[0])):6.1f} deg")
if __name__ == "__main__": main()
