# -*- coding: utf-8 -*-
import json
import imageio.v2 as iio
import numpy as np

VAL = r'E:\AI_Project\Anisotropic Lighting\sd\validation'
r = json.load(open(VAL + r'\probe_0c2_report.json', encoding='utf-8'))
png_ref = np.array(r['expect']['png16_vals_u16'], dtype=np.float32).reshape(8, 8, 3) / 65535.0
f32_ref = np.array(r['expect']['f32_vals'], dtype=np.float32).reshape(8, 8, 4)

for tag in ('png16_default', 'png16_32f', 'f32_default', 'f32_32f'):
    try:
        img = iio.imread(VAL + f'\\probe_0c2_{tag}.exr', format='EXR-FI')
    except BaseException as e:
        print(tag, 'READ FAIL', e)
        continue
    h, w = img.shape[:2]
    img = img[:8, :8, :]
    if tag.startswith('png16'):
        # PNG16 源经 SD 加载的值域待定：读回可能是 u16/65535 或 sRGB 解码后
        ref = png_ref
        d = np.abs(img[:, :, :3] - ref)
        note = 'vs u16/65535'
    else:
        ref = f32_ref
        d = np.abs(img - ref)
        note = 'vs float32 exact'
    print(f'{tag:<14} max|d|={d.max():.6f} mean={d.mean():.6f}  ({note})')
    # 分通道统计读回
    for ch, cname in enumerate('RGBA' if img.shape[2] == 4 else 'RGB'):
        c = img[:, :, ch]
        print(f'   {cname}: min {c.min():.4f} max {c.max():.4f} mean {c.mean():.4f}')
