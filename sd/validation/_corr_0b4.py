# -*- coding: utf-8 -*-
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()

print('=== A: 单输入(X) sample(0) 原样 ===')
a = iio.imread(r'E:\AI_Project\Anisotropic Lighting\sd\validation\s0_raw.exr',
               format='EXR-FI')
for ch, cname in enumerate('RGBA'):
    c = a[:, :, ch].ravel()
    corrs = {k: round(float(np.corrcoef(v, c)[0, 1]), 3) for k, v in src.items()}
    best = max(corrs.items(), key=lambda kv: kv[1])
    print(f'  A.{cname}: mean {c.mean():.4f} → {best[0]} corr={best[1]}')

print('=== B: 双输入 sample(0).r / sample(1).r / sample(0).a / sample(1).a ===')
b = iio.imread(r'E:\AI_Project\Anisotropic Lighting\sd\validation\s1_pack.exr',
               format='EXR-FI')
rb = b.reshape(-1, 4)
for ch, cname in enumerate(['sample(0).r', 'sample(1).r', 'sample(0).a', 'sample(1).a']):
    c = rb[:, ch]
    corrs = {k: round(float(np.corrcoef(v, c)[0, 1]), 3) for k, v in src.items()}
    best = max(corrs.items(), key=lambda kv: kv[1])
    print(f'  {cname}: mean {c.mean():.4f} → {best[0]} corr={best[1]}')
