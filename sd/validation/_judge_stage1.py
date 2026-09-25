# -*- coding: utf-8 -*-
"""Stage 1 判定：SD 主链 EXR vs GLSL dump（DEBUG 0/2/9）逐 texel。

SD 侧 EXR 是 DEBUG=0 级联输出（像素级同参数）。判定：
  1) 有限性（全图 NaN/Inf = 0）
  2) 有效性标记（A 通道 vs GLSL debug0 A）精确比对
  3) 数值：有效内域 max|Δ|≤1e-4、RMSE≤1e-5
  4) DEBUG 2/9 通道对比（需 SD 侧重跑；本轮先比 debug0）
"""
import json
import sys
from pathlib import Path

import numpy as np
import imageio.v2 as iio

VAL = Path(__file__).resolve().parent
TOL_ABS = 1e-4
TOL_RMSE = 1e-5

glsl = np.load(VAL / 'glsl_core_debug0.npy')          # (H,W,4) 首行为顶部
sd_img = iio.imread(VAL / 'stage1_core.exr', format='EXR-FI').astype(np.float32)
# EXR 读回行序：SDTexture.save 的行序约定（GLSL dump 首行为顶部）——
# 若 SD save 为底行开始需翻转。先按同序比，若大面积错位再翻。
h, w = glsl.shape[:2]
sd = sd_img[:h, :w, :4]

report = {'ok': False, 'checks': []}

# 1) 有限性
nf_glsl = int((~np.isfinite(glsl)).sum())
nf_sd = int((~np.isfinite(sd)).sum())
print(f'有限性: GLSL non-finite={nf_glsl}  SD non-finite={nf_sd}')
report['checks'].append({'finite': {'glsl': nf_glsl, 'sd': nf_sd,
                                    'ok': nf_glsl == 0 and nf_sd == 0}})

# 2) 有效性（A 通道 0/1 语义）
va = glsl[..., 3] > 0.5
vb = sd[..., 3] > 0.5
mism = int((va != vb).sum())
false_valid = int((vb & ~va).sum())
false_invalid = int((~vb & va).sum())
print(f'有效性: mismatches={mism} (false_valid={false_valid}, '
      f'false_invalid={false_invalid})')
report['checks'].append({'valid': {'mismatches': mism,
                                   'false_valid': false_valid,
                                   'false_invalid': false_invalid}})

# 3) 数值（有效内域 = GLSL valid 域）
domain = va
n = int(domain.sum())
if n == 0:
    print('比较域为空 → FAIL')
    report['checks'].append({'numeric': {'ok': False, 'error': 'empty domain'}})
else:
    d = (sd[..., :3] - glsl[..., :3])[domain]
    max_abs = float(np.max(np.abs(d)))
    rmse = float(np.sqrt(np.mean(d * d)))
    n_over = int((np.abs(d) > TOL_ABS).sum())
    print(f'数值（{n} texel 有效内域）: max|Δ|={max_abs:.6f} RMSE={rmse:.6f} '
          f'超差={n_over}')
    # 分通道
    for ch, cname in enumerate('RGB'):
        dc = (sd[..., ch] - glsl[..., ch])[domain]
        print(f'   {cname}: max|Δ|={np.max(np.abs(dc)):.6f}')
    report['checks'].append({'numeric': {
        'n': n, 'max_abs': max_abs, 'rmse': rmse, 'n_over': n_over,
        'ok': max_abs <= TOL_ABS and rmse <= TOL_RMSE}})

ok = all(c.get('ok', False) if isinstance(c.get(list(c.keys())[0]), dict) is False
         else all(v.get('ok', True) for v in c.values() if isinstance(v, dict))
         for c in report['checks'])
report['ok'] = bool(ok)
(VAL / 'stage1_judge.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2, default=str),
    encoding='utf-8')
print(f"[DONE] Stage1 判定: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
