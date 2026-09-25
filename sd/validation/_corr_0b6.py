# -*- coding: utf-8 -*-
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()

order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
for idx in range(4):
    img = iio.imread(
        rf'E:\AI_Project\Anisotropic Lighting\sd\validation\bmidx_{idx}.exr',
        format='EXR-FI')
    c = img[:, :, 0].ravel()
    corrs = {n: round(float(np.corrcoef(v, c)[0, 1]), 3) for n, v in src.items()}
    best = max(corrs.items(), key=lambda kv: kv[1])
    expect = order[idx]
    ok = best[0] == expect and best[1] > 0.999
    print(f'sample({idx}): 期望 {expect:<15} 实测 {best[0]:<15} corr={best[1]}  '
          f'{"PASS" if ok else "FAIL"}')
