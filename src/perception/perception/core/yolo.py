"""YOLOE (phát hiện + phân đoạn) với text prompt cố định theo config/classes.yaml.
LƯU Ý: ultralytics coi ndarray là BGR (kiểu OpenCV) nên ở đây phải đổi RGB -> BGR trước khi đưa vào."""
import cv2
import numpy as np


class YoloeDetector:
    def __init__(self, classes, weights="yoloe-11s-seg.pt", conf=0.35, iou=0.5, imgsz=640, device="cuda:0", half=False):
        from ultralytics import YOLOE
        self.classes, self.conf, self.iou, self.imgsz, self.device, self.half = list(classes), conf, iou, imgsz, device, half
        self.model = YOLOE(weights).to(device)
        self.model.set_classes(self.classes, self.model.get_text_pe(self.classes))

    def detect(self, rgb):
        h, w = rgb.shape[:2]
        r = self.model.predict(source=np.ascontiguousarray(rgb[..., ::-1]), device=self.device, conf=self.conf,
                               iou=self.iou, imgsz=self.imgsz, retina_masks=True, verbose=False)[0]
        out = []
        if r.boxes is None or len(r.boxes) == 0 or r.masks is None:
            return out
        boxes = r.boxes.xyxy.cpu().numpy()
        ids = r.boxes.cls.cpu().numpy().astype(int)
        confs = r.boxes.conf.cpu().numpy()
        masks = (r.masks.data > 0.5).cpu().numpy()
        for i in range(len(boxes)):
            m = masks[i]
            if m.shape != (h, w):                              # mask: luôn nội suy NEAREST (mục 2.5)
                m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
            out.append({"class_id": int(ids[i]), "class_name": self.classes[int(ids[i])], "confidence": float(confs[i]),
                        "bbox_xyxy": [float(v) for v in boxes[i]], "mask": m})
        return out
