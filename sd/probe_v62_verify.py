# -*- coding: utf-8 -*-
r"""v6.2 翻转门控修正验证（ndl<0 门控，根除 T_Render_03 黑斑）。

默认参数 + 白 ambient 四态 + 默认参数成品（给用户直接回贴 Unity）：
1. v62_off.exr      two_sided=0, ambient_ao=0
2. v62_flip.exr     two_sided=1, ambient_ao=0   → 纯翻转（新门控）
3. v62_ao25.exr     two_sided=1, ambient_ao=0.25
4. v62_full.exr     two_sided=1, ambient_ao=0.5
5. v62_default.exr  默认参数（ambient_color 默认深色，ao=0.5）
结束恢复默认（不改用户面板）。

输出：sd/validation/v62_verify.json + 5 个 EXR
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')
report = {'probe': 'v62_verify', 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, float3
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
    from aniso_pp import api as SDAPI

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.getUserPackageFromFilePath(SBS_OUT)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_lightmap')

    test = SDAPI.get_current_graph()
    nodes = test.getNodes()
    inst = None
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            rr = node.getReferencedResource()
            if rr is not None and 'aniso_lightmap' in rr.getUrl():
                inst = node
                break
        except BaseException:
            continue
    assert inst is not None, 'test graph 中无 aniso_lightmap 实例'
    out_node = test.newNode('sbs::compositing::output')
    out_node.setPosition(float2(5600.0, 2800.0))
    outs = inst.getProperties(SDPropertyCategory.Output)
    inst.newPropertyConnectionFromId(str(outs.getItem(0).getId()),
                                     out_node, 'inputNodeOutput')

    p_amb = wrapper.getPropertyFromId('p_ambient_color', SDPropertyCategory.Input)
    p_ts = wrapper.getPropertyFromId('p_two_sided', SDPropertyCategory.Input)
    p_ao = wrapper.getPropertyFromId('p_ambient_ao', SDPropertyCategory.Input)
    assert p_ts is not None and p_ao is not None, 'v6.2 包缺 two_sided/ambient_ao'

    def render(name):
        test.compute()
        tex = inst.getPropertyValue(outs.getItem(0)).get()
        path = os.path.join(VAL_DIR, name)
        tex.save(path, '')
        report[name] = path
        print('[RENDER]', name)

    # 四态：白 ambient 隔离 flip 与 ao 作用
    wrapper.setPropertyValue(p_amb, SDValueFloat3.sNew(float3(1.0, 1.0, 1.0)))
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.0))
    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(0))
    render('v62_off.exr')
    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(1))
    render('v62_flip.exr')
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.25))
    render('v62_ao25.exr')
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.5))
    render('v62_full.exr')

    # 默认参数成品（用户直接回贴 Unity 的状态）
    wrapper.setPropertyValue(p_amb, SDValueFloat3.sNew(float3(0.06, 0.07, 0.09)))
    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(1))
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.5))
    render('v62_default.exr')

    report['ok'] = True


try:
    main()
except BaseException:
    report['fail'] = traceback.format_exc()
    print('[ABORT]', report['fail'][-800:])

with open(os.path.join(VAL_DIR, 'v62_verify.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]')
