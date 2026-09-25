# -*- coding: utf-8 -*-
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

img = iio.imread(
    r'E:\AI_Project\Anisotropic Lighting\sd\validation\probe_0b2_readback.exr',
    format='EXR-FI')
print('EXR', img.shape)
base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()  # r 通道 2048² 原尺寸

rb = img.reshape(-1, 4)
for ch, cname in enumerate(['R(sample0)', 'G(sample1)', 'B(sample3)', 'A(sample4)']):
    corrs = {k: float(np.corrcoef(v, rb[:, ch])[0, 1]) for k, v in src.items()}
    best = max(corrs.items(), key=lambda kv: kv[1])
    stats = f"min {rb[:,ch].min():.4f} max {rb[:,ch].max():.4f} mean {rb[:,ch].mean():.4f}"
    print(f'{cname:<14} {stats}  → {best[0]}  corr={best[1]:.4f}')
    print('   all:', {k: round(v, 3) for k, v in corrs.items()})
