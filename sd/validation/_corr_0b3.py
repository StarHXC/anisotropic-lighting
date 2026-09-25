# -*- coding: utf-8 -*-
import json
import imageio.v2 as iio
import imageio.v3 as iio3
import numpy as np

base = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'
src = {}
for name in ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']:
    a = iio3.imread(base + '\\' + name + '.png').astype(np.float32) / 255.0
    src[name] = a[:, :, 0].ravel()

img = iio.imread(
    r'E:\AI_Project\Anisotropic Lighting\sd\validation\probe_0b3_main.exr',
    format='EXR-FI')
rb = img.reshape(-1, 4)

r = json.load(open(
    r'E:\AI_Project\Anisotropic Lighting\sd\validation\probe_0b3_report.json',
    encoding='utf-8'))
print('channel defaults:', json.dumps(r.get('channel_defaults'), ensure_ascii=False))

expect = ['bake_position', 'bake_normalobj', 'bake_ao', 'mask1']
names = ['R(pos.r)', 'G(nrm.r)', 'B(ao.r)', 'A(mask.r)']
all_ok = True
for ch, (cname, want) in enumerate(zip(names, expect)):
    c = rb[:, ch]
    corrs = {k: round(float(np.corrcoef(v, c)[0, 1]), 4) for k, v in src.items()}
    ok = corrs.get(want, 0) > 0.999
    all_ok = all_ok and ok
    print(f'{cname:<12} mean {c.mean():.4f} corr({want})={corrs[want]}  {"PASS" if ok else "FAIL"}')
print('ALL:', 'PASS' if all_ok else 'FAIL')
