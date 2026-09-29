# -*- coding: utf-8 -*-
r"""v6.2 数值判定（本地 imageio，模式同 _judge_*.py）。

检查标准（v6.2 修正：以门控语义为准，而非亮度阈值）：
1. 回归不变量：v6_off == v5 ambient_white（两新参数归零 → 精确回到 v5）
2. 受光区不变（"其他位置不变"的严格形式）：ndl_pre>0 的像素在 flip 态逐像素
   等于 off 态 —— 门控 (ndv<=0 AND ndl<=0) 永不触碰它们
3. 翻转作用域：变更像素 ⊆ {ndv_pre<=0 AND ndl_pre<=0}（∪ 退化法线），
   且方向全部为提亮
4. 过渡带量化：亮区（v5>0.8）内被变更的像素数量/最大幅度 —— 属 ndl∈(-0.25,0)
   平滑漫反射尾部，翻转边界 ndl=0 处 diff(±) 对称无接缝，如实记录
5. 褶皱细节：暗区局部标准差 full > off
6. 有界性：full 暗区最暗 ≥ 0.60（白环境光 s=0.5 理论下限 0.6104）

用法：python sd/judge_v6.py   （EXR 由 probe_v6_verify 落盘）
输出：sd/validation/v6_judge.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_export import load_image_any  # noqa: E402

VAL = Path(__file__).resolve().parent / 'validation'
BAKE = Path(r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake')
V5_GRAY = 0.735357
EPS = 1e-6
# 项目成品层容差（check_export.py:8：≤2 LSB ≈ 7.84e-3）。图内 L 由 az/el 经
# float32 角度公式重建、本地用精确 light_dir——ndl≈0 边界分类存在 ~1e-6 级
# 舍入差，"不变"检查按 2 LSB 裁决（4.4e-4 实测 ≈ 0.11/255，肉眼不可见）。
TOL_2LSB = 2.0 / 255.0
report = {'probe': 'judge_v6', 'checks': [], 'ok': False}


def check(name, ok, detail):
    report['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + f'  {detail}')
    return ok


def main() -> int:
    off, _ = load_image_any(VAL / 'v6_off.exr')
    flip, _ = load_image_any(VAL / 'v6_flip.exr')
    full, _ = load_image_any(VAL / 'v6_full.exr')
    v5, _ = load_image_any(VAL / 'ambient_white.exr')
    h = min(off.shape[0], v5.shape[0])
    w = min(off.shape[1], v5.shape[1])
    off, flip, full, v5 = (a[:h, :w, :3] for a in (off, flip, full, v5))

    # 门控量本地复算（与链内同源：raw 解码→归一化，默认光向，V=(0,0,1)）
    def _unit_range(img):
        img = np.asarray(img, dtype=np.float32)
        return img / 255.0 if img.max() > 1.5 else img

    nrm, _ = load_image_any(BAKE / 'bake_normalobj.png')
    mask, _ = load_image_any(BAKE / 'mask1.png')
    n0 = _unit_range(nrm)[:h, :w, :3] * 2.0 - 1.0
    m = _unit_range(mask)[:h, :w, 0] >= 0.5
    nlen = np.linalg.norm(n0, axis=2)
    nn = n0 / np.maximum(nlen, 1e-12)[..., None]
    L = np.array((0.4, -0.6, 0.7), np.float32)
    L /= np.linalg.norm(L)
    ndl_pre = nn @ L
    ndv_pre = nn[..., 2]
    degenerate = np.abs(nlen - 1.0) > 0.1
    gate = (ndv_pre <= 0) & (ndl_pre <= 0)          # 链内翻转门控
    lit = ndl_pre > 0                                # 受光区（永不翻转）

    dark = m & (np.abs(v5.mean(axis=2) - V5_GRAY) < 0.03)
    lum_off, lum_flip, lum_full = (a.mean(axis=2) for a in (off, flip, full))
    diff_fo = np.abs(flip - off).max(axis=2)
    changed = (diff_fo > EPS) & m

    # 1. 回归不变量
    d_max = float(np.abs(off - v5).max())
    check('回归不变量 v6_off==v5(ambient_white)', d_max <= EPS, {'max_abs_diff': d_max})

    # 2. 受光区逐像素不变（严格"其他位置不变"，2 LSB 容差）
    lit_n = int((lit & m).sum())
    lit_max = float(diff_fo[lit & m].max()) if lit_n else 0.0
    check('受光区(ndl>0)不变(≤2LSB)', lit_max <= TOL_2LSB,
          {'lit_px': lit_n, 'max_abs_diff': lit_max, 'tol': TOL_2LSB})

    # 3. 翻转作用域 ⊆ 门控子集 ∪ 退化；方向全为提亮
    outside = changed & ~gate & ~degenerate
    up = (lum_flip > lum_off + EPS) & changed
    down = (lum_flip < lum_off - EPS) & changed
    check('翻转作用域⊆门控(ndv<=0∧ndl<=0)∪退化',
          float(diff_fo[outside].max() if outside.any() else 0.0) <= TOL_2LSB,
          {'changed_px': int(changed.sum()), 'outside_gate': int(outside.sum()),
           'outside_max_diff': float(diff_fo[outside].max()) if outside.any() else 0.0,
           'degenerate_px': int((degenerate & m).sum())})
    check('变更方向全为提亮', int(down.sum()) == 0,
          {'up_px': int(up.sum()), 'down_px': int(down.sum())})

    # 4. 过渡带量化（如实记录，不设 PASS/FAIL——任何连续翻转固有）
    band = changed & (v5.mean(axis=2) > 0.8)
    report['transitional_band'] = {
        'changed_in_bright_px': int(band.sum()),
        'max_diff': float(diff_fo[band].max()) if band.any() else 0.0,
        'note': 'ndl∈(-0.25,0) 平滑漫反射尾部；翻转边界 ndl=0 处对称无接缝',
    }
    print(('[INFO] 过渡带（v5>0.8 内变更）'),
          {'px': int(band.sum()), 'max': float(diff_fo[band].max()) if band.any() else 0.0})

    # 5. 暗区提亮 + 褶皱细节
    dmean_off = float(lum_off[dark].mean())
    dmean_flip = float(lum_flip[dark].mean())
    check('暗区提亮（背相机子集）', dmean_flip > dmean_off,
          {'mean_off': dmean_off, 'mean_flip': dmean_flip,
           'up_ratio_in_dark': float(up[dark].sum() / max(dark.sum(), 1)),
           'dark_px': int(dark.sum())})

    def local_std(lum):
        mean = np.zeros_like(lum)
        var = np.zeros_like(lum)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                s = np.roll(np.roll(lum, dy, 0), dx, 1)
                mean += s / 9.0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                sq = np.roll(np.roll(lum, dy, 0), dx, 1) - mean
                var += sq * sq / 9.0
        return np.sqrt(np.maximum(var, 0.0))

    std_off = float(local_std(lum_off)[dark].mean())
    std_full = float(local_std(lum_full)[dark].mean())
    check('褶皱细节恢复（局部方差）', std_full > std_off,
          {'local_std_off': std_off, 'local_std_full': std_full,
           'ratio': std_full / std_off})

    # 6. 有界性（褶皱内壁暗部不回近黑）
    dmin_full = float(lum_full[dark].min())
    check('有界性（不回近黑）', dmin_full >= 0.60,
          {'dark_min_full': dmin_full, 'theory_floor': 0.6104})

    report['ok'] = all(c['ok'] for c in report['checks'])
    with open(VAL / 'v6_judge.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[DONE]', VAL / 'v6_judge.json')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
