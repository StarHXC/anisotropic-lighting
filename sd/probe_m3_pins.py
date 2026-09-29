# -*- coding: utf-8 -*-
r"""M3 诊断 3 — uniform/blend 节点的完整输入/输出属性枚举。"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm3')
REPORT = {'probe': 'm3_pins', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI

    test = SDAPI.get_current_graph()

    def dump(nid):
        n = test.newNode(nid)
        out = {'inputs': [], 'outputs': []}
        for cat, key in ((SDPropertyCategory.Input, 'inputs'),
                         (SDPropertyCategory.Output, 'outputs')):
            props = n.getProperties(cat)
            for i in range(props.getSize()):
                p = props.getItem(i)
                out[key].append(str(p.getId()))
        test.deleteNode(n)
        return out

    REPORT['uniform'] = dump('sbs::compositing::uniform')
    REPORT['blend'] = dump('sbs::compositing::blend')
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm3_pins_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
