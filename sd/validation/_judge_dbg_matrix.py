# -*- coding: utf-8 -*-
"""DEBUG 全模式矩阵判定：SD dbg_m{i}.exr vs GLSL debug{i}.npy。
RGB 与 A 分别在各自比较域判定；mismatch 计数（不阻断，登记）。"""
import json
import sys
from pathlib import Path

import imageio.v2 as iio
import numpy as np

VAL = Path(__file__).resolve().parent
TOL = 1e-4

fails_total = []
for dbg in range(10):
    glsl_p = VAL / f'glsl_core_debug{dbg}.npy'
    if not glsl_p.exists():
        print(f'debug{dbg}: GLSL dump 缺失，跳过')
        continue
    glsl = np.load(glsl_p)
    sd = iio.imread(VAL / f'dbg_m{dbg}.exr', format='EXR-FI').astype(np.float32)[:2048, :2048, :4]

    nf = int((~np.isfinite(sd)).sum())
    # RGB 数值域：GLSL A>0.5 ∪ SD A>0.5 的并集（宽容版；mismatch 像素 RGB 应相同）
    dom = (glsl[..., 3] > 0.5) | (sd[..., 3] > 0.5)
    d = np.abs(sd[..., :3] - glsl[..., :3])[dom]
    max_abs = float(d.max()) if d.size else 0.0
    amism = int(((glsl[..., 3] > 0.5) != (sd[..., 3] > 0.5)).sum())
    ok = nf == 0 and max_abs <= TOL
    status = 'PASS' if ok else 'FAIL'
    print(f'debug{dbg}: {status}  non-finite={nf}  max|Δ|={max_abs:.2e}  '
          f'A-mismatch={amism}')
    if not ok:
        fails_total.append(dbg)

print(f'\n总体: {"ALL PASS" if not fails_total else f"FAIL modes={fails_total}"}')
sys.exit(0 if not fails_total else 1)
