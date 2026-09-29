# -*- coding: utf-8 -*-
"""检查旧 SBS 中 bitmap 资源的 XML 结构（临时诊断）。"""
import re

xml = open('aniso_lightmap.sbs', encoding='utf-8').read()
for tag in ('SBSBitmap', 'Bitmap', 'filename', 'src_'):
    idxs = [m.start() for m in re.finditer(tag, xml)][:5]
    print(tag, '→', len([m for m in re.finditer(tag, xml)]), 'hits')
    for i in idxs[:2]:
        print('   …', xml[max(0, i - 120):i + 160].replace('\n', ' ')[:260])
