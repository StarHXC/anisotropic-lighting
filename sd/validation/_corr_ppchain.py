# -*- coding: utf-8 -*-
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

img = iio.imread(
    r'E:\AI_Project\Anisotropic Lighting\sd\validation\ppchain.exr',
    format='EXR-FI')
print('EXR', img.shape)
base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()

rb = img.reshape(-1, 4)
for ch, cname in enumerate(['R(sample0)', 'G(sample1)', 'B(sample2)', 'A(sample3)']):
    stats = f"min {rb[:,ch].min():.4f} max {rb[:,ch].max():.4f} mean {rb[:,ch].mean():.4f}"
    corrs = {k: round(float(np.corrcoef(v, rb[:, ch])[0, 1]), 4) for k, v in src.items()}
    best = max(corrs.items(), key=lambda kv: kv[1])
    print(f'{cname:<14} {stats}')
    print('   →', best, ' all:', corrs)
