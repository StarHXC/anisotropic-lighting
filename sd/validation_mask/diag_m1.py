# -*- coding: utf-8 -*-
"""M1 差异定位诊断（临时）。"""
import sys
sys.path.insert(0, 'validation_mask')
import png16
import reference

import numpy as np
import imageio.v3 as iio

FIX = 'validation_mask/fixtures'
fx = {k: png16.read_png16_f(f'{FIX}/fx_{n}.png')
      for k, n in (('position', 'position'), ('normalobj', 'normalobj'),
                   ('mask', 'mask'), ('ao', 'ao'))}
PD = {'a': 0.7, 'r': 0.5, 'theta_deg': 0.0,
      'az_deg': -56.309932474020215, 'el_deg': 44.148948676558244}
ref = reference.reference_mask(fx, PD)
m_sd = np.asarray(iio.imread('validation_mask/out/m1/m1_mask.exr'), np.float32)
q_sd = np.asarray(iio.imread('validation_mask/out/m1/m1_q.exr'), np.float32)
if m_sd.ndim == 2:
    m_sd = m_sd[..., None]
if q_sd.ndim == 2:
    q_sd = q_sd[..., None]
M_sd = m_sd[:, :, 0]
Q_sd = q_sd[:, :, 0]
cov = fx['mask'][..., 0] >= 0.5
Vg = ref['Vg']
valid = cov & (Vg > 0.5)
diff = np.abs(M_sd - ref['M'])
print('差异>1e-4 像素数:', int((diff > 1e-4).sum()), '/', int(valid.sum()))
probe = np.zeros_like(diff, bool)
probe[64 - 24:64 + 25, 64 - 24:64 + 25] = True
print('探针区 max diff: %.6f' % diff[probe & valid].max())
print('非探针 valid 区 max diff: %.6f' % diff[(~probe) & valid].max())
for (y, x) in [(64, 64), (64, 80), (30, 30), (100, 100), (64, 45)]:
    print((y, x), 'sd=%.5f ref=%.5f q_sd=%.3f q_ref=%.3f hn=%.4f' %
          (M_sd[y, x], ref['M'][y, x], Q_sd[y, x], ref['q'][y, x], ref['hn'][y, x]))
