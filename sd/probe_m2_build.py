# -*- coding: utf-8 -*-
r"""M2 探针 — 调用 build_aniso_mask.main() 生成正式 aniso_mask.sbs。"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm2_build', 'fail': None}

try:
    import build_aniso_mask
    rep = build_aniso_mask.main()
    REPORT['build'] = {'ok': rep.get('ok'), 'pp_nodes': rep.get('pp_nodes'),
                       'texel': rep.get('texel'),
                       'steps': [s['step'] + ('=' + str(s['ok'])) for s in rep.get('steps', [])]}
    REPORT['ok'] = bool(rep.get('ok'))
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(OUT_DIR, 'm2_build_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] m2_build_report.json')
