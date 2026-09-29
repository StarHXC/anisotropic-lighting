# -*- coding: utf-8 -*-
r"""aniso_mask 生成入口（独立；main guard；ANISO_MASK_PLAN §6 文件分工）。

在 SD 内经桥执行（probe 包装见 probe_m2_build.py）或 SD Python 编辑器直接跑。

用法（SD 内）:
    import build_aniso_mask; build_aniso_mask.main()
"""
from __future__ import annotations

import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)


def main():
    for _k in [k for k in sys.modules
               if k == 'aniso_pp' or k.startswith('aniso_pp.')
               or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')
               or k == 'stages']:
        del sys.modules[_k]
    from aniso_mask_tools.mask_builder import build, REPORT
    build()
    import json
    out = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'build_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    return REPORT


if __name__ == '__main__':
    main()
