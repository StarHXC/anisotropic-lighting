# -*- coding: utf-8 -*-
import re
src = open(r'E:\AI_Project\Anisotropic Lighting\sd\stages.py',
           encoding='utf-8').read()
refs = sorted(set(m.group(1) for m in re.finditer(r"P\['(\w+)'\]", src)))
print('剩余 P 引用:', refs)
