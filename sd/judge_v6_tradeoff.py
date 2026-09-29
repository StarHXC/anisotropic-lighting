# -*- coding: utf-8 -*-
"""v6 ambient_ao 扫描的细节/过曝/黑斑权衡分析（复用已有 EXR，不重渲）。

逐 ao 档 (off/flip/s0/s25/full) 量化：
- 暗区整体亮度均值
- 褶皱细节（局部标准差，越大越有层次）
- 过曝比例（>=0.999）
- 黑斑（相对邻域 <-0.15 的像素绝对亮度 p50/min）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SD = Path(r'E:\AI_Project\Anisotropic Lighting\sd')
sys.path.insert(0, str(SD))
from check_export import load_image_any  # noqa: E402

VAL = SD / 'validation'
BAKE = Path(r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake')
V5_GRAY = 0.735357


def unit(img):
    img = np.asarray(img, dtype=np.float32)
    return img / 255.0 if img.max() > 1.5 else img


def local_std(lum, k=5):
    pad = k // 2
    mean = np.zeros_like(lum)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            mean += np.roll(np.roll(lum, dy, 0), dx, 1) / (k * k)
    var = np.zeros_like(lum)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            d = np.roll(np.roll(lum, dy, 0), dx, 1) - mean
            var += d * d / (k * k)
    return np.sqrt(np.maximum(var, 0.0))


def local_mean(lum, k=11):
    pad = k // 2
    acc = np.zeros_like(lum)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            acc += np.roll(np.roll(lum, dy, 0), dx, 1) / (k * k)
    return acc


def main():
    series = [
        ('v6_off', 'off'),
        ('v6_flip', 'flip (ao=0)'),
        ('spot_s0', 'ao=0.00'),
        ('spot_s25', 'ao=0.25'),
        ('v6_full', 'ao=0.50'),
    ]
    imgs = {}
    for name, _ in series:
        a, _ = load_image_any(VAL / (name + '.exr'))
        imgs[name] = unit(a)[:, :, :3]
    h = min(a.shape[0] for a in imgs.values())
    w = min(a.shape[1] for a in imgs.values())
    for n in imgs:
        imgs[n] = imgs[n][:h, :w]

    mask, _ = load_image_any(BAKE / 'mask1.png')
    m = unit(mask)[:h, :w, 0] >= 0.5

    # v5 平色区（直接光≈0）作为"暗区"几何
    v5, _ = load_image_any(VAL / 'ambient_white.exr')
    v5 = unit(v5)[:h, :w, :3]
    dark = m & (np.abs(v5.mean(axis=2) - V5_GRAY) < 0.03)

    out = {}
    print(f'{"档位":14s} {"mean":>7s} {"p5":>7s} {"Lstd":>7s} {"clip%":>7s} '
          f'{"spot_p50":>9s} {"spot_min":>9s} {"spot_n":>7s}')
    for name, label in series:
        lum = imgs[name].mean(axis=2)
        ls = local_std(lum)
        nb = local_mean(lum, 11)
        rel = lum - nb
        spots = dark & (rel < -0.15)
        ls_sp = lum[spots]
        rec = {
            'mean': float(lum[dark].mean()),
            'p5': float(np.percentile(lum[dark], 5)),
            'local_std': float(ls[dark].mean()),
            'clip_pct': float((lum[dark] >= 0.999).mean() * 100),
            'spot_px': int(spots.sum()),
            'spot_abs_p50': float(np.percentile(ls_sp, 50)) if ls_sp.size else None,
            'spot_abs_min': float(ls_sp.min()) if ls_sp.size else None,
            'spot_rel_p50': float(np.percentile(rel[spots], 50)) if spots.any() else None,
        }
        out[name] = rec
        print(f'{label:14s} {rec["mean"]:7.4f} {rec["p5"]:7.4f} {rec["local_std"]:7.4f} '
              f'{rec["clip_pct"]:7.2f} {rec["spot_abs_p50"]:9.4f} {rec["spot_abs_min"]:9.4f} '
              f'{rec["spot_px"]:7d}')

    # 参考线：v5 平色灰 0.7354
    out['note'] = 'v5 平色 = 0.7354（暗区基线，无细节）'
    with open(VAL / 'v6_ao_tradeoff.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\n[DONE]', VAL / 'v6_ao_tradeoff.json')


if __name__ == '__main__':
    main()
