# -*- coding: utf-8 -*-
r"""aniso_easylight 生成入口（独立；main guard）。

在 SD 内经桥执行（probe 包装）或 SD Python 编辑器直接跑。

用法（SD 内）:
    import build_aniso_easylight; build_aniso_easylight.main()
"""
from __future__ import annotations

import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)


def main():
    for _k in [k for k in list(sys.modules)
               if k == 'aniso_pp' or k.startswith('aniso_pp.')
               or k == 'aniso_easylight_tools'
               or k.startswith('aniso_easylight_tools.')
               or k == 'stages']:
        del sys.modules[_k]
    from aniso_easylight_tools.builder import build, REPORT
    build()
    import json
    out = os.path.join(SD_DIR, 'validation_easylight', 'out', 'm2')
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'build_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    return REPORT


if __name__ == '__main__':
    main()
