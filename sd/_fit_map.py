# -*- coding: utf-8 -*-
"""拟合 SD slot 读值与 pos 图坐标的仿射关系（临时诊断）。"""
import sys
sys.path.insert(0, 'validation_mask')
import png16

import numpy as np
import imageio.v3 as iio

sd = np.asarray(iio.imread(r'validation_mask\out\m2\m2_slot1.exr'), np.float32)
pos = png16.read_png16_f(r'aniso_lightmap.resources\bake_position.png'.replace('\\b', '/b'))

pts = [((937, 493), (784, 1594)), ((100, 100), (119, 57)),
       ((500, 1500), (755, 1234)), ((1500, 500), (1441, 479)),
       ((1800, 1800), (1944, 1699))]
src = np.array([p[0] for p in pts], float)
dst = np.array([p[1] for p in pts], float)
A = np.hstack([src, np.ones((len(src), 1))])
coef_y, res_y, _, _ = np.linalg.lstsq(A, dst[:, 0], rcond=None)
coef_x, res_x, _, _ = np.linalg.lstsq(A, dst[:, 1], rcond=None)
print('y2 = a*y + b*x + c:', np.round(coef_y, 4), 'resid', res_y)
print('x2 = d*y + e*x + f:', np.round(coef_x, 4), 'resid', res_x)
