# -*- coding: utf-8 -*-
"""v6.2 vs v6.1 黑斑对比（用新 EXR。v6.1 为 validation/v6_full.exr，v6.2 为 v62_full.exr）。"""
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


def unit(img):
    img = np.asarray(img, dtype=np.float32)
    return img / 255.0 if img.max() > 1.5 else img


def local_mean(lum, k=11):
    pad = k // 2
    acc = np.zeros_like(lum)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            acc += np.roll(np.roll(lum, dy, 0), dx, 1) / (k * k)
    return acc


def main():
    def load(name):
        a, _ = load_image_any(VAL / name)
        return unit(a)[:, :, :3]

    old = load('v6_full.exr')   # v6.1 (ndv<=0 AND ndl<=0)
    new = load('v62_full.exr')  # v6.2 (ndl<=0)
    h = min(old.shape[0], new.shape[0]); w = min(old.shape[1], new.shape[1])
    old, new = old[:h, :w], new[:h, :w]

    mask, _ = load_image_any(BAKE / 'mask1.png')
    m = unit(mask)[:h, :w, 0] >= 0.5

    lum_old, lum_new = old.mean(axis=2), new.mean(axis=2)

    def spots(lum):
        rel = lum - local_mean(lum, 11)
        return m & (rel < -0.15)

    so = spots(lum_old)
    sn = spots(lum_new)
    print('黑斑 (rel<-0.15) 像素数：v6.1=%d   v6.2=%d   变化=%+d' % (
        int(so.sum()), int(sn.sum()), int(sn.sum() - so.sum())))
    print('v6.1 黑斑区在 v6.2 的亮度：mean=%.4f  min=%.4f  max=%.4f' % (
        lum_new[so].mean(), lum_new[so].min(), lum_new[so].max()))
    print('整体 mask 区 mean：v6.1=%.4f  v6.2=%.4f' % (lum_old[m].mean(), lum_new[m].mean()))

    # 逐像素差：v6.2 比 v6.1 变化分布
    d = lum_new - lum_old
    changed = (np.abs(new - old).max(axis=2) > 1e-6) & m
    print('v6.2 vs v6.1 变更像素：%d (%.2f%% of mask)' % (
        int(changed.sum()), changed.sum() / m.sum() * 100))
    print('亮度差 d：p5=%.4f p50=%.4f p95=%.4f max=%.4f min=%.4f' % (
        np.percentile(d[changed], 5), np.percentile(d[changed], 50),
        np.percentile(d[changed], 95), d[changed].max(), d[changed].min()))
    # 受光区（ndl>0）应纹丝不动
    n0 = unit(load_image_any(BAKE / 'bake_normalobj.png')[0])[:h, :w, :3] * 2 - 1
    nn = n0 / np.maximum(np.linalg.norm(n0, axis=2, keepdims=True), 1e-12)
    L = np.array((0.4, -0.6, 0.7), np.float32); L /= np.linalg.norm(L)
    ndl = nn @ L
    lit = ndl > 0
    print('受光区 (ndl>0)：max_abs_diff v6.2 vs v6.1 = %.6f' %
          np.abs(new - old)[lit & m].max())

    out = {
        'v61_spot_px': int(so.sum()),
        'v62_spot_px': int(sn.sum()),
        'v62_lum_in_v61_spots_mean': float(lum_new[so].mean()),
        'v62_lum_in_v61_spots_min': float(lum_new[so].min()),
        'changed_px': int(changed.sum()),
        'd_p50': float(np.percentile(d[changed], 50)),
        'd_min': float(d[changed].min()),
        'lit_max_diff': float(np.abs(new - old)[lit & m].max()),
    }
    with open(VAL / 'v62_vs_v61.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('[DONE]', VAL / 'v62_vs_v61.json')


if __name__ == '__main__':
    main()
