# Khả thi triangulation

Baseline quang học lớn nhất 10,0 cm trong 630 cặp TF. 25/36 cặp chồng quan sát có độ nhạy dưới 10 cm ở nhiễu 1 px. Chọn cặp chẩn đoán theo association cùng lớp và baseline. Correspondence ORB dùng RGB và mask YOLOE, rồi kiểm cheirality và reprojection ≤1 px. Nhãn GT và depth GT chỉ chấm sau đó. Độ nhạy nhiễu dùng cùng một điểm giả định chiếu vào hai camera, tránh giả định hai tâm mask là cùng điểm.

| Vật | Stop A/B | Baseline cm | ΔZ 0,5 / 1 / 2 px cm | ORB match / qua hình học | n GT / median cm |
| --- | --- | --- | --- | --- | --- |
| laptop_1 | 3/34 | 4,2 | 1,6 / 3,3 / 6,8 | 77/71 | 65 / 2,9 |
| laptop_1 | 3/35 | 3,4 | 2,3 / 4,7 / 9,9 | 92/85 | 76 / 3,6 |
| laptop_1 | 2/34 | 3,4 | 2,0 / 4,2 / 8,6 | 100/91 | 84 / 4,1 |
| laptop_1 | 0/3 | 2,6 | 2,4 / 4,9 / 10,2 | 107/90 | 87 / 4,6 |
| cup_1 | 0/3 | 2,6 | 2,0 / 4,0 / 8,3 | 130/121 | 117 / 3,7 |
| cup_1 | 0/2 | 1,7 | 3,2 / 6,7 / 14,4 | 223/218 | 215 / 2,5 |
| cup_1 | 1/3 | 1,7 | 3,0 / 6,1 / 13,1 | 134/125 | 125 / 5,0 |
| cup_1 | 1/2 | 0,9 | 6,7 / 14,4 / 33,6 | 239/230 | 229 / 9,9 |
| bottle_1 | 1/32 | 4,2 | 1,0 / 1,9 / 4,0 | 109/102 | 101 / 2,3 |
| bottle_1 | 1/33 | 3,4 | 1,4 / 2,8 / 5,7 | 81/72 | 71 / 2,6 |
| bottle_1 | 0/32 | 3,4 | 1,2 / 2,5 / 5,2 | 76/68 | 67 / 2,7 |
| bottle_1 | 32/35 | 2,6 | 1,2 / 2,4 / 5,0 | 102/97 | 96 / 3,2 |
