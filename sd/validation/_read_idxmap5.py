# -*- coding: utf-8 -*-
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()

for tag in ('a', 'b'):
    img = iio.imread(
        rf'E:\AI_Project\Anisotropic Lighting\sd\validation\idxmap5_{tag}.exr',
        format='EXR-FI')
    rb = img.reshape(-1, 4)
    ids = [0, 1, 2, 3] if tag == 'a' else [4, 1, 2, 3]
    print(f'--- idxmap5_{tag} ---')
    for ch, idx in enumerate(ids):
        c = rb[:, ch]
        corrs = {k: round(float(np.corrcoef(v, c)[0, 1]), 3) for k, v in src.items()}
        best = max(corrs.items(), key=lambda kv: kv[1])
        print(f'  sample({idx}): mean {c.mean():.4f} → {best[0]} corr={best[1]}')
