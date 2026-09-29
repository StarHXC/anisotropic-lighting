# -*- coding: utf-8 -*-
r"""M3 诊断 — 枚举当前图可用的 compositing 节点定义（找 uniform/constant）。"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm3')
REPORT = {'probe': 'm3_defs', 'fail': None}


def main():
    import sd
    from aniso_pp import api as SDAPI

    test = SDAPI.get_current_graph()
    defs = test.getNodeDefinitions()
    names = []
    for i in range(defs.getSize()):
        d = defs.getItem(i)
        try:
            nid = str(d.getId())
        except BaseException:
            continue
        names.append(nid)
    hits = [n for n in names if any(k in n.lower() for k in
            ('uniform', 'const', 'color', 'solid'))]
    REPORT['total'] = len(names)
    REPORT['hits'] = hits
    REPORT['sample'] = sorted(names)[:80]
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm3_defs_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
