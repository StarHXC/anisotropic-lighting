# -*- coding: utf-8 -*-
import imageio.v2 as iio

for n in (1, 2, 3):
    img = iio.imread(
        rf'E:\AI_Project\Anisotropic Lighting\sd\validation\idxmap3_{n}conn.exr',
        format='EXR-FI')
    vals = [round(float(img[2, 2, ch]), 3) for ch in range(4)]
    print(f'{n} conn: sample(0..3).r = {vals}')
