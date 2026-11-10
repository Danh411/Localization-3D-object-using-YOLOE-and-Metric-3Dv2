# Một vật thấy tại một khung (spec mục 3.3).
builtin_interfaces/Time stamp
int32 class_id
string class_name
float32 confidence
float32[4] bbox_xyxy        # x1 y1 x2 y2 (pixel)
bool truncated              # bbox sát biên ảnh
int32 mask_area_px          # diện tích mask sau khi co (erode)
float32 valid_depth_ratio   # tỉ lệ pixel depth hợp lệ trong mask
float32 depth_m             # độ sâu đại diện (median) theo trục quang học
float32 range_m             # khoảng cách tia = |p_cam|
float64[3] p_cam            # trong camera_optical_frame (X phải, Y xuống, Z trước)
float64[3] p_world          # trong world
float64 yaw_rad             # góc camera khi chụp
int32 stop_index
int32 frame_idx
