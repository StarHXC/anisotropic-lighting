# -*- coding: utf-8 -*-
r"""决定性实验：wrapper 图 new input_color/input_grayscale 节点 → 保存 .sbs →
读 XML 看是否生成 <input type="image"> 图输入定义。
输出：sd/validation/ginput4.json + gi4.sbs
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'ginput4.json')
SBS_OUT = os.path.join(VAL_DIR, 'gi4.sbs')

report = {'fail': None}


def main():
    import sd
    from sd.api.sdbasetypes import float2
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph

    ctx = sd.getContext()
    pkg_mgr = ctx.getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    g = SDSBSCompGraph.sNew(pkg)
    g.setIdentifier('gi4')

    # input_color ×1（彩色图像输入）
    ic = g.newNode('sbs::compositing::input_color')
    ic.setPosition(float2(0.0, 0.0))
    out_node = g.newNode('sbs::compositing::output')
    out_node.setPosition(float2(300.0, 0.0))
    ic.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')

    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    xml = open(SBS_OUT, encoding='utf-8', errors='replace').read()
    # 找 input 定义
    segs = [s[:200] for s in xml.split('<input')[1:5]]
    report = {
        'input_segments': segs,
        'has_input_def': '<input' in xml,
        'ok': True,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[DONE]')


try:
    main()
except BaseException:
    import traceback
    report = {'fail': traceback.format_exc()}
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[ABORT]')
