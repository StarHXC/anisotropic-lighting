# -*- coding: utf-8 -*-
r"""Step 0 诊断：v5 暗区（平色区）内烘焙法线的有效性统计。

目的（计划 Step 0）：回答"双面翻转是否有收益"——
  - 暗区 = mask=1 且 v5 白环境光输出 ≈ 0.7354（direct≈0 的平色区）
  - 统计该区内：法线长度退化比例 / nz<0（朝下）/ ndl<0（背光）/ ndotv<0（背相机）
判定：背相机比例高且退化比例低 → 翻转有效；退化比例高 → 翻转收益受限。

本地 Python 运行（不经 SD 桥）：python sd/judge_normal_diag.py
输出：sd/validation/normal_diag.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_export import load_image_any  # noqa: E402

BAKE = Path(r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake')
V5_EXR = Path(__file__).resolve().parent / 'validation' / 'ambient_white.exr'
OUT = Path(__file__).resolve().parent / 'validation' / 'normal_diag.json'

V5_GRAY = 0.735357      # sRGB(Reinhard(1.0))——v5 平色区特征值
EPS_BAND = 0.02         # |px-0.7354|<0.02 判平色

# Stage 1 快照冻结的默认光向（stages.py P['light_dir']，未归一化）
L_DEFAULT = (0.4, -0.6, 0.7)
V_DEFAULT = (0.0, 0.0, 1.0)   # view_mode=2 代理 Vn=Ns，翻转参考用世界上向


def _unit(v):
    l = math.sqrt(sum(c * c for c in v))
    return tuple(c / l for c in v)


def main() -> int:
    def _unit_range(img):
        # imageio 对该 16-bit PNG 实际返回 uint8/float 值域 0..255（非 0..1）；
        # 整数 dtype 或 max>1.5 的 float 都按 0..255 → 0..1 缩放
        img = np.asarray(img, dtype=np.float32)
        if img.max() > 1.5:
            return img / 255.0
        return img

    nrm, _ = load_image_any(BAKE / 'bake_normalobj.png')     # [0,1] 编码
    mask, _ = load_image_any(BAKE / 'mask1.png')
    out5, _ = load_image_any(V5_EXR)                         # v5 白环境光渲染
    h = min(nrm.shape[0], out5.shape[0], mask.shape[0])
    w = min(nrm.shape[1], out5.shape[1], mask.shape[1])
    nrm, mask, out5 = nrm[:h, :w], mask[:h, :w], out5[:h, :w]

    nrm = _unit_range(nrm)                                   # [0,1] 编码
    mask = _unit_range(mask)
    n0 = nrm[..., :3] * 2.0 - 1.0                            # 解码 *2-1
    nlen = np.linalg.norm(n0, axis=2)
    mask1 = mask[..., 0] >= 0.5
    gray = np.abs(out5[..., :3] - V5_GRAY).max(axis=2) < EPS_BAND
    dark = mask1 & gray

    n = int(dark.sum())
    if n == 0:
        json.dump({'ok': False, 'err': 'dark region empty', 'dark_px': 0},
                  open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
        print('[ABORT] dark region empty')
        return 1

    L = np.array(_unit(L_DEFAULT), dtype=np.float32)
    V = np.array(V_DEFAULT, dtype=np.float32)
    ndl = (n0 @ L) / np.maximum(nlen, 1e-12)
    ndv = n0[..., 2] / np.maximum(nlen, 1e-12)

    stats = {
        'dark_px': n,
        'dark_ratio_of_mask': float(dark.sum() / max(mask1.sum(), 1)),
        'degenerate_len2_10pct': float(((np.abs(nlen - 1.0) > 0.1) & dark).sum() / n),
        'nz_negative': float(((n0[..., 2] < 0) & dark).sum() / n),
        'backlight_ndl_lt0': float(((ndl < 0) & dark).sum() / n),
        'backcam_ndv_lt0': float(((ndv < 0) & dark).sum() / n),
        'degenerate_or_backcam': float((((np.abs(nlen - 1.0) > 0.1) | (ndv < 0)) & dark).sum() / n),
    }
    flip_effective = (stats['backcam_ndv_lt0'] > 0.5
                      and stats['degenerate_len2_10pct'] < 0.2)
    report = {
        'ok': True,
        'probe': 'normal_diag',
        'inputs': {'normal': str(BAKE / 'bake_normalobj.png'),
                   'mask': str(BAKE / 'mask1.png'),
                   'v5_exr': str(V5_EXR)},
        'v5_gray': V5_GRAY, 'eps_band': EPS_BAND,
        'light_dir': list(_unit(L_DEFAULT)), 'view': list(V_DEFAULT),
        'stats': stats,
        'verdict': ('flip_effective' if flip_effective
                    else 'flip_limited_ao_dominant'),
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print('[VERDICT]', report['verdict'])
    print('[DONE]', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
