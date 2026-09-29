# -*- coding: utf-8 -*-
"""检查 aniso_mask.sbs XML 中的参数默认值（临时诊断）。"""
import re

xml = open(r'aniso_mask.sbs', encoding='utf-8').read()
for pid in ('p_light_azimuth_deg', 'p_light_elevation_deg', 'p_anisotropy',
            'p_roughness', 'p_direction_deg'):
    m = re.search(r'<paraminput><identifier v="%s"/>(.*?)</paraminput>' % pid,
                  xml, re.S)
    if m:
        seg = m.group(1)
        dv = re.search(r'constantValueFloat1 v="([^"]+)"', seg)
        grp = re.search(r'<group v="([^"]+)"/>', seg)
        print(pid, 'default=', dv.group(1) if dv else '?',
              'group=', grp.group(1) if grp else '?')
    else:
        print(pid, 'NOT FOUND in XML')
