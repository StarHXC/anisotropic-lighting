# -*- coding: utf-8 -*-
r"""导出 v6.2 渲染为 PNG 供肉眼对比（sRGB tonemap 后的 EXR 已经是 sRGB 域）。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

SD = Path(r'E:\AI_Project\Anisotropic Lighting\sd')
sys.path.insert(0, str(SD))
from check_export import load_image_any  # noqa: E402

VAL = SD / 'validation'
OUT = Path(r'E:\AI_Project\Anisotropic Lighting\out')
OUT.mkdir(parents=True, exist_ok=True)


def unit(a):
    a = np.asarray(a, dtype=np.float32)
    return a / 255.0 if a.max() > 1.5 else a


def main():
    for name in ['v62_off', 'v62_flip', 'v62_ao25', 'v62_full', 'v62_default', 'v6_full']:
        a, _ = load_image_any(VAL / (name + '.exr'))
        rgb = unit(a)[:, :, :3]
        rgb = np.clip(rgb, 0.0, 1.0)
        img = Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), 'RGB')
        p = OUT / (name + '.png')
        img.save(p)
        print('[PNG]', p, 'mean=%.4f' % rgb.mean())


if __name__ == '__main__':
    main()
