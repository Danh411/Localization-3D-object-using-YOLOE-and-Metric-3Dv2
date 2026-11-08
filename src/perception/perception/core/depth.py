"""Metric3D v2 (ViT-Small). Toán chuẩn hóa tiêu cự theo mục 5.1 (giữ nguyên logic của webcam.py đã chạy đúng).
Đầu vào RGB uint8 (HxWx3) — KHÔNG phải BGR. Trả về độ sâu mét float32 (H, W) ở kích thước ảnh gốc."""
import numpy as np
import torch
import torch.nn.functional as F


class Metric3DDepth:
    def __init__(self, device="cuda:0", input_hw=(616, 1064), fp16=False, canonical_f=1000.0, max_m=10.0,
                 hub_repo="yvanyin/metric3d", hub_name="metric3d_vit_small"):
        self.device, self.input_hw, self.canonical_f, self.max_m = device, tuple(input_hw), canonical_f, max_m
        self.use_cuda = device.startswith("cuda")
        self.fp16 = fp16 and self.use_cuda
        model = torch.hub.load(hub_repo, hub_name, pretrain=True, trust_repo=True)
        self.model = model.to(device).eval()
        self.mean = torch.tensor([123.675, 116.28, 103.53], device=device).view(1, 3, 1, 1)
        self.std = torch.tensor([58.395, 57.12, 57.375], device=device).view(1, 3, 1, 1)
        self.last = {}   # thông tin gỡ lỗi của lần chạy gần nhất

    @torch.inference_mode()
    def estimate(self, rgb, fx):
        h, w = rgb.shape[:2]
        th, tw = self.input_hw
        scale = min(th / h, tw / w)
        nh, nw = int(h * scale), int(w * scale)
        pad_h, pad_w = th - nh, tw - nw
        pt, pl = pad_h // 2, pad_w // 2
        x = torch.from_numpy(np.ascontiguousarray(rgb)).to(self.device).permute(2, 0, 1).unsqueeze(0).float()
        x = F.interpolate(x, size=(nh, nw), mode="bilinear", align_corners=False, antialias=True)
        x = (x - self.mean) / self.std
        x = F.pad(x, (pl, pad_w - pl, pt, pad_h - pt), value=0.0)
        with torch.autocast(device_type="cuda" if self.use_cuda else "cpu", dtype=torch.float16, enabled=self.fp16):
            out = self.model.inference({"input": x})
        pred = (out[0] if isinstance(out, (tuple, list)) else out).float().squeeze()
        if tuple(pred.shape) != (th, tw):
            pred = F.interpolate(pred[None, None], size=(th, tw), mode="bilinear", align_corners=False)[0, 0]
        pred = pred[pt:th - (pad_h - pt), pl:tw - (pad_w - pl)]
        pred = F.interpolate(pred[None, None], size=(h, w), mode="bilinear", align_corners=False)[0, 0]
        factor = fx * scale / self.canonical_f                 # fx_r / 1000 (mục 5.1, bước 5)
        self.last = {"scale": scale, "fx_r": fx * scale, "factor": factor, "input_hw": self.input_hw}
        return torch.clamp(pred * factor, 0, self.max_m).cpu().numpy().astype(np.float32)
