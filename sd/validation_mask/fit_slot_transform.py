# -*- coding: utf-8 -*-
"""收集多点精确对应，拟合 SD slot0 → pos 图的坐标变换（临时诊断）。"""
import sys
sys.path.insert(0, 'validation_mask')
import png16

import numpy as np
import imageio.v3 as iio

sd = np.asarray(iio.imread(r'validation_mask\out\m2\m2_ord_fwd.exr'), np.float32)
pos = png16.read_png16_f(r'aniso_lightmap.resources/bake_position.png')

pairs = []
for (y, x) in [(100, 100), (937, 493), (500, 1500), (1500, 500), (1800, 1800),
               (300, 300), (1000, 1000), (200, 1800)]:
    tv = sd[y, x, 0]
    d = np.abs(pos[:, :, 0] - tv)
    ys, xs = np.where(d < 0.0008)
    if len(ys):
        k = np.argmin((ys - y) ** 2 + (xs - x) ** 2)
        pairs.append(((y, x), (int(ys[k]), int(xs[k]))))
for p in pairs:
    dy = p[1][0] - p[0][0]
    dx = p[1][1] - p[0][1]
    print(p, f'd=({dy:+d},{dx:+d})')
