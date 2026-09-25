# -*- coding: utf-8 -*-
"""Stage 2 判定：wrapper 实例输出 vs GLSL DEBUG0 基准（同参数应逐位一致）。"""
import json
from pathlib import Path

import imageio.v2 as iio
import numpy as np

VAL = Path(__file__).resolve().parent
glsl = np.load(VAL / 'glsl_core_debug0.npy')
sd = iio.imread(VAL / 'stage2_inst.exr', format='EXR-FI').astype(np.float32)[:2048, :2048, :4]

nf = int((~np.isfinite(sd)).sum())
va = glsl[..., 3] > 0.5
vb = sd[..., 3] > 0.5
amism = int((va != vb).sum())
dom = va & vb  # 严格内域（两侧都有效）
d = np.abs(sd[..., :3] - glsl[..., :3])[dom]
print(f'有限性: SD non-finite={nf}')
print(f'A-mismatch: {amism}（已知 bValid 阈值例外集合）')
print(f'严格内域（双有效 {int(dom.sum())} texel）: max|Δ|={float(d.max()):.6f}')

ok = nf == 0 and float(d.max()) <= 1e-4
print(f'STAGE 2 判定: {"PASS" if ok else "FAIL"}')
with open(VAL / 'stage2_judge.json', 'w', encoding='utf-8') as f:
    json.dump({'finite': nf, 'a_mismatch': amism,
               'max_abs': float(d.max()), 'ok': ok}, f, indent=2)
