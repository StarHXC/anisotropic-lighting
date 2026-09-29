# -*- coding: utf-8 -*-
r"""M2 — aniso_easylight 构建探针（经 sd-bridge 执行 build_aniso_easylight）。"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

OUT_DIR = os.path.join(SD_DIR, 'validation_easylight', 'out', 'm2')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'easylight_build', 'fail': None}


def main():
    import build_aniso_easylight
    rep = build_aniso_easylight.main()
    REPORT['build'] = rep


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(OUT_DIR, 'probe_build_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] probe_easylight_build')
