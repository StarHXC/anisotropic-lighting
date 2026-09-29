# -*- coding: utf-8 -*-
r"""v6 黑斑归因验证：two_sided=1 固定 + ambient=白，ambient_ao ∈ {0, 0.25}
渲染对照（与已有 v6_full.exr 的 s=0.5 组成梯度），用于定位黑斑来源并给出
ambient_ao 推荐值。结束恢复参数默认。
输出：sd/validation/v6_spot.json + spot_s0.exr / spot_s25.exr
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
report = {'probe': 'v6_spot', 'ok': False}


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
    assert p_ao is not None, 'v6 包缺 p_ambient_ao'

    def render(name):
        test.compute()
        tex = inst.getPropertyValue(outs.getItem(0)).get()
        path = os.path.join(VAL_DIR, name)
        tex.save(path, '')
        report[name] = path
        print('[RENDER]', name)

    # two_sided=1 + ambient=白 固定；扫 ambient_ao 梯度
    wrapper.setPropertyValue(p_amb, SDValueFloat3.sNew(float3(1.0, 1.0, 1.0)))
    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(1))
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.0))
    render('spot_s0.exr')

    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.25))
    render('spot_s25.exr')

    # 恢复默认
    wrapper.setPropertyValue(p_amb, SDValueFloat3.sNew(float3(0.06, 0.07, 0.09)))
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.5))
    test.compute()

    report['ok'] = True


try:
    main()
except BaseException:
    report['fail'] = traceback.format_exc()
    print('[ABORT]', report['fail'][-500:])

with open(os.path.join(VAL_DIR, 'v6_spot.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]')
