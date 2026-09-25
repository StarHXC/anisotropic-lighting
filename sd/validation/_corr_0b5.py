# -*- coding: utf-8 -*-
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()

for k in range(5):
    try:
        img = iio.imread(
            rf'E:\AI_Project\Anisotropic Lighting\sd\validation\s2nd_{k}.exr',
            format='EXR-FI')
        c = img[:, :, 0].ravel()
        corrs = {n: round(float(np.corrcoef(v, c)[0, 1]), 3) for n, v in src.items()}
        best = max(corrs.items(), key=lambda kv: kv[1])
        print(f'sample(0,{k}): mean {c.mean():.4f} → {best[0]} corr={best[1]}')
    except BaseException as e:
        print(f'k={k} read fail: {e}')
