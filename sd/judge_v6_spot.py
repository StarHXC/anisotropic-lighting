# -*- coding: utf-8 -*-
"""v6 黑斑定位：跨 s=0/0.25/0.5 + flip + off + T_Render_03 的像素级统计。

定义"斑"= 褶皱内壁暗区：局部比邻域显著变暗的像素。逐档量化其绝对亮度、
覆盖比例，以及 flip 是否引入硬边界（splotchy）。
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
RENDER03 = Path(r'C:\Users\xingcan.huang\Pictures\Tex test\T_Render_03.png')


def unit(img):
    img = np.asarray(img, dtype=np.float32)
    return img / 255.0 if img.max() > 1.5 else img


def load_exr(name):
    a, _ = load_image_any(VAL / name)
    return unit(a)[:, :, :3]


def local_mean(lum, k=5):
    pad = k // 2
    acc = np.zeros_like(lum)
    cnt = np.zeros_like(lum)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            s = np.roll(np.roll(lum, dy, 0), dx, 1)
            acc += s
            cnt += 1.0
    return acc / np.maximum(cnt, 1.0)


def main():
    names = ['v6_off', 'v6_flip', 'spot_s0', 'spot_s25', 'v6_full']
    imgs = {n: load_exr(n + '.exr') for n in names}
    h = min(a.shape[0] for a in imgs.values())
    w = min(a.shape[1] for a in imgs.values())
    for n in imgs:
        imgs[n] = imgs[n][:h, :w]

    mask, _ = load_image_any(BAKE / 'mask1.png')
    m = unit(mask)[:h, :w, 0] >= 0.5
    nrm, _ = load_image_any(BAKE / 'bake_normalobj.png')
    n0 = unit(nrm)[:h, :w, :3] * 2.0 - 1.0
    nn = n0 / np.maximum(np.linalg.norm(n0, axis=2, keepdims=True), 1e-12)
    L = np.array((0.4, -0.6, 0.7), np.float32); L /= np.linalg.norm(L)
    ndl = nn @ L
    ndv = nn[..., 2]
    gate = (ndv <= 0) & (ndl <= 0)

    # 褶皱暗区定义：v6_full 相对局部邻域显著变暗（rel < -0.15），且在 mask 内
    lum = {n: a.mean(axis=2) for n, a in imgs.items()}
    base = lum['v6_full']
    nb = local_mean(base, 11)
    rel = base - nb
    spots = m & (rel < -0.15)
    # 黑斑候选（T_Render_03 同口径）
    out = {}

    print(f'{"name":10s} {"mean":>7s} {"p1":>7s} {"p5":>7s} {"spot_n":>9s} '
          f'{"spot_abs_p50":>13s} {"spot_rel_p50":>13s} {"spot_rel_min":>12s}')
    for n in names:
        a = imgs[n]
        l = lum[n]
        sp = spots
        ls = l[sp]
        rs = rel[sp]
        rec = {
            'mean': float(l[m].mean()),
            'p1': float(np.percentile(l[m], 1)),
            'p5': float(np.percentile(l[m], 5)),
            'spot_px': int(sp.sum()),
            'spot_cov_pct': float(sp.sum() / m.sum() * 100),
            'spot_abs_p50': float(np.percentile(ls, 50)) if ls.size else None,
            'spot_abs_min': float(ls.min()) if ls.size else None,
            'spot_rel_p50': float(np.percentile(rs, 50)) if rs.size else None,
            'spot_rel_min': float(rs.min()) if rs.size else None,
        }
        out[n] = rec
        print(f'{n:10s} {rec["mean"]:7.4f} {rec["p1"]:7.4f} {rec["p5"]:7.4f} '
              f'{rec["spot_px"]:9d} {rec["spot_abs_p50"]:13.4f} {rec["spot_rel_p50"]:13.4f} '
              f'{rec["spot_rel_min"]:12.4f}')

    # flip 硬边界 / splotchy：翻转作用域的连通性与边界密度
    changed = (np.abs(imgs['v6_flip'] - imgs['v6_off']).max(axis=2) > 1e-6) & m
    fg = changed & gate
    # gate 内被翻转比例
    out['flip_stats'] = {
        'gate_px': int(gate.sum()),
        'flipped_px': int(fg.sum()),
        'flipped_in_gate_pct': float(fg.sum() / max(gate.sum(), 1) * 100),
        'mean_ndl_in_flipped': float(ndl[fg & (ndl <= 0)].mean()) if (fg & (ndl <= 0)).any() else None,
    }
    print('\nflip:', out['flip_stats'])

    # T_Render_03 口径（绝对暗 + 相对暗）
    if RENDER03.exists():
        r3, _ = load_image_any(RENDER03)
        r3 = unit(r3)[:h, :w, :3]
        lr = r3.mean(axis=2)
        nb_r = local_mean(lr, 11)
        rel_r = lr - nb_r
        abs_dark = m & (lr < 0.2)
        rel_dark = m & (rel_r < -0.15)
        clipped = float((lr >= 0.999).sum() / m.sum() * 100)
        out['T_Render_03'] = {
            'mean': float(lr[m].mean()),
            'clipped_pct': clipped,
            'abs_dark_px': int(abs_dark.sum()),
            'rel_dark_px': int(rel_dark.sum()),
            'rel_dark_abs_p50': float(np.percentile(lr[rel_dark], 50)) if rel_dark.any() else None,
            'rel_dark_abs_min': float(lr[rel_dark].min()) if rel_dark.any() else None,
            'rel_dark_rel_min': float(rel_r[rel_dark].min()) if rel_dark.any() else None,
        }
        print('\nT_Render_03:', out['T_Render_03'])

    # 与 SD v6_full 对位比较（确认 SD 链复现用户的斑）
    if RENDER03.exists():
        d = np.abs(r3 - imgs['v6_full']).max(axis=2)
        out['sd_vs_render03'] = {
            'max_abs_diff': float(d[m].max()),
            'p50_abs_diff': float(np.percentile(d[m], 50)),
            'p95_abs_diff': float(np.percentile(d[m], 95)),
        }
        print('sd_vs_render03:', out['sd_vs_render03'])

    with open(VAL / 'v6_spot_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\n[DONE]', VAL / 'v6_spot_analysis.json')


if __name__ == '__main__':
    main()
