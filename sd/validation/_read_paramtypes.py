# -*- coding: utf-8 -*-
import re
data = open(r'C:\Program Files\Adobe\Adobe Substance 3D Designer\resources'
            r'\packages\slope_blur.sbs', 'rb').read().decode('utf-8',
                                                             errors='replace')
for m in re.finditer(r'<paraminput><identifier v="([^"]+)"/>.*?<type v="(\d+)"/>',
                     data):
    print(f'{m.group(1):<18} type={m.group(2)}')
