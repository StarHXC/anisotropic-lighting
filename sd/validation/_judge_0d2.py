# -*- coding: utf-8 -*-
"""0D2 判定：5 个 PP 读回 EXR 的 case 中心采样 vs NumPy 基准。
布局：2048²，case c 占 x∈[c*512/3?] —— 参数图 36 texel 线性，
但 PP 输出按 $pos 采样参数图：cx=floor(u*12)。case c 的区域中心
u=(c+0.5)/12, v=0.5 → 像素 (px, py)。
"""
import json
import math
import imageio.v2 as iio
import numpy as np

VAL = r'E:\AI_Project\Anisotropic Lighting\sd\validation'

ref_doc = json.load(open(VAL + r'\probe_0d_glsl_ref.json', encoding='utf-8'))
cases = ref_doc['cases']
man = json.load(open(VAL + r'\probe_0d_manifest.json', encoding='utf-8'))
angles = {c['name']: c['angle'] for c in man['cases']}

imgs = {}
for tag in ('pp1_sn', 'pp2_pf', 'pp3_cr', 'pp4_rot', 'pp5_p3'):
    imgs[tag] = iio.imread(VAL + f'\\probe_0d2_{tag}.exr', format='EXR-FI')

H, W = imgs['pp1_sn'].shape[:2]
print('PP size:', W, 'x', H)

TOL = 1e-4
fails = []
rows = []
for i, case in enumerate(cases):
    # 64×1 布局：case c 占像素 c*3..c*3+2；采样组内中间像素（配方在该像素全组参数有效）
    px = min(i * 3 + 1, W - 1)
    py = 0
    name = case['name']

    sn = imgs['pp1_sn'][py, px]
    pf = imgs['pp2_pf'][py, px]
    cr = imgs['pp3_cr'][py, px]
    rot = imgs['pp4_rot'][py, px]
    p3 = imgs['pp5_p3'][py, px]

    checks = [
        ('sn.x', sn[0], case['sn_xyz'][0]),
        ('sn.y', sn[1], case['sn_xyz'][1]),
        ('sn.z', sn[2], case['sn_xyz'][2]),
        ('sn.valid', sn[3], case['sn_valid']),
        ('pf.x', pf[0], case['plane_fallback'][0]),
        ('pf.y', pf[1], case['plane_fallback'][1]),
        ('pf.z', pf[2], case['plane_fallback'][2]),
        ('pf.trig', pf[3], case['pf_trigger']),
        ('cr.x', cr[0], case['cross3'][0]),
        ('cr.y', cr[1], case['cross3'][1]),
        ('cr.z', cr[2], case['cross3'][2]),
        ('pickSign', cr[3], case['pick_sign']),
        ('rot.x', rot[0], case['rot_x']),
        ('rot.y', rot[1], math.sin(math.radians(angles[name]))),
        ('segmented', rot[2], case['segmented_at_half']),
        ('srgb', rot[3], case['srgb']),
        ('pick3.x', p3[0], case['pick3_center'][0]),
        ('pick3.y', p3[1], case['pick3_center'][1]),
        ('pick3.z', p3[2], case['pick3_center'][2]),
    ]
    for q, got, want in checks:
        d = abs(float(got) - float(want))
        rows.append((name, q, float(got), float(want), d, d <= TOL))
        if d > TOL:
            fails.append((name, q, got, want, d))

print(f'total checks: {len(rows)}  FAIL: {len(fails)}  (tol {TOL})')
for (n, q, got, want, d, ok) in rows:
    if not ok:
        print(f'  FAIL {n}.{q}: got {got:.6f} want {want:.6f} |d|={d:.2e}')
if not fails:
    print('ALL PASS')

# 有限性全图检查
for tag, img in imgs.items():
    nf = int((~np.isfinite(img)).sum())
    print(f'finiteness {tag}: non-finite={nf}')
