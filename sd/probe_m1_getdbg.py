# -*- coding: utf-8 -*-
r"""M1 诊断：get_float1 在未保存临时包的 PP FG 中解析行为最小实验。

场景 A: wrapper 注册参数 p_test=0.73 → PP FG get_float1('p_test') → 输出
场景 B: 同上但参数注册在 PP 节点上
输出: validation_mask/out/m1/getdbg_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm1')
REPORT = {'probe': 'm1_getdbg', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdtypefloat import SDTypeFloat
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('m1_getdbg')
    try:
        wrapper.setDefaultParentSize(int2(3, 3))
    except BaseException:
        pass

    # A: wrapper 参数
    prop = wrapper.newProperty('p_test', SDTypeFloat.sNew(), SDPropertyCategory.Input)
    wrapper.setPropertyValue(prop, SDValueFloat.sNew(0.73))

    # 无输入直通 PP：FG = get_float1('p_test')
    pp, _ = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=3)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    gf = fg.newNode('sbs::function::get_float1')
    gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_test'))
    fg.setOutputNode(gf, True)

    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(300.0, 0.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    rb = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'getdbg_A.exr'))
    REPORT['A'] = rb

    # 读回中心值（外部 judge 承担；SD 宿主无 numpy/imageio）
    if rb['ok']:
        REPORT['A_exr'] = os.path.join(OUT_DIR, 'getdbg_A.exr')


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'getdbg_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2, default=str)
print('[DONE] getdbg_report.json')
