# -*- coding: utf-8 -*-
"""0C2b 判定：四条转换曲线对比，锁定 8bit PNG 加载行为。"""
import json
from pathlib import Path

import imageio.v2 as iio
import numpy as np

VAL = Path(__file__).resolve().parent


def srgb_decode(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def load_curve(tag):
    img = iio.imread(VAL / f'curve_{tag}.exr', format='EXR-FI')
    return img[0, :, 0].astype(np.float32)  # 256 值


c8 = load_curve('gray8')
c16 = load_curve('gray16')
c16f = load_curve('gray16_32f')
cf = load_curve('grayf')

ref8 = np.arange(256, dtype=np.float32) / 255.0
ref16 = np.arange(256, dtype=np.float32) * 257 / 65535.0
reff = ref8.copy()

for tag, curve, ref in (('gray8', c8, ref8), ('gray16', c16, ref16),
                        ('gray16_32f', c16f, ref16), ('grayf', cf, reff)):
    d = curve - ref
    print(f'{tag:<10} max|d|={np.abs(d).max():.6f} mean={d.mean():+.6f} '
          f'非零={int((np.abs(d) > 1e-6).sum())}/256')

# gray8 的转换函数形状：抽样打印
print('\ngray8 曲线抽样 (v, v/255, sd读数, 差):')
for v in (0, 6, 32, 64, 128, 202, 250, 255):
    print(f'  {v:3d}  {v/255:.6f}  {c8[v]:.6f}  {c8[v]-v/255:+.6f}')
# 与 sRGB 解码对比
print('\ngray8 vs sRGB解码:')
for v in (32, 128, 202):
    print(f'  {v:3d}: sd={c8[v]:.6f} srgb_dec={srgb_decode(v/255):.6f}')
