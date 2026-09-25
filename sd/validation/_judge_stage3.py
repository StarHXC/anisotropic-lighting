# -*- coding: utf-8 -*-
"""Stage 3 终判：成品域对比，bValid 例外 texel 单列（§8.2(5)）。"""
import json
from pathlib import Path

import imageio.v2 as iio
import numpy as np

VAL = Path(__file__).resolve().parent
glsl_out = np.load(VAL / 'glsl_output_debug0.npy')
lin = np.load(VAL / 'glsl_core_debug0.npy')
sd = iio.imread(VAL / 'stage2_inst.exr',
                format='EXR-FI').astype(np.float32)[:2048, :2048, :4]

nf = int((~np.isfinite(sd)).sum())
dom = lin[..., 3] > 0.5
dmax = np.abs(sd[..., :3] - glsl_out[..., :3]).max(axis=2)

# bValid 例外集合（Stage1 已定性：SD 与 GLSL 的 bValid 阈值骑线 texel）
glsl0 = np.load(VAL / 'glsl_core_debug0.npy')
sd0 = iio.imread(VAL / 'stage1_core.exr', format='EXR-FI').astype(np.float32)[:2048, :2048, :4]
known = ((glsl0[..., 3] > 0.5) != (sd0[..., 3] > 0.5)) & dom

over = (dmax > 2 / 255) & dom
over_known = int((over & known).sum())
over_real = int((over & ~known).sum())

print(f'有限性: SD non-finite={nf}')
print(f'有效内域 {int(dom.sum())} texel:')
print(f'  ≤2LSB: {int((~over & dom).sum())} ({(1 - over.sum()/dom.sum())*100:.4f}%)')
print(f'  >2LSB: {over.sum()}（其中 bValid 例外 {over_known}，真实超差 {over_real}）')
ok = nf == 0 and over_real == 0
print(f'STAGE 3 判定: {"PASS" if ok else "FAIL"}'
      f'（例外 {over_known} 个按 §8.2(5) 单列）')
with open(VAL / 'stage3_judge.json', 'w', encoding='utf-8') as f:
    json.dump({'finite': nf, 'n_domain': int(dom.sum()),
               'over_2lsb': int(over.sum()),
               'over_known_exception': over_known,
               'over_real': over_real,
               'ok': ok}, f, indent=2)
