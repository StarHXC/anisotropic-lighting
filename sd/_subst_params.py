# -*- coding: utf-8 -*-
"""stages.py 常数→参数解析批量替换工具（一次性）。"""
import re

p = r'E:\AI_Project\Anisotropic Lighting\sd\stages.py'
src = open(p, encoding='utf-8').read()

scalars = ['aniso_amount', 'shift1', 'shift2', 'exponent1', 'exponent2',
           'spec_edge0', 'spec_edge1', 'spec_threshold', 'front_k',
           'diffuse_edge0', 'diffuse_edge1', 'diffuse_threshold',
           'ao_strength', 'ao_direct_light', 'light_intensity',
           'ambient_intensity']
n = 0
for s in scalars:
    old = f"em.c_f1(P['{s}'])"
    new = f"sc('{s}')"
    cnt = src.count(old)
    if cnt:
        n += cnt
        src = src.replace(old, new)
print('scalar replacements:', n)

pat = re.compile(
    r"em\.v3\(em\.c_f1\(P\['(\w+)'\]\[0\]\),\s*"
    r"em\.c_f1\(P\['\1'\]\[1\]\),\s*"
    r"em\.c_f1\(P\['\1'\]\[2\]\)\)")
src, n3 = pat.subn(lambda m: f"v3p('{m.group(1)}')", src)
print('v3 replacements:', n3)

open(p, 'w', encoding='utf-8').write(src)
print('written')
