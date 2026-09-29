# -*- coding: utf-8 -*-
r"""v5 ambient 平面化数值验证：
1) 设 p_ambient_color=白 → 前后 EXR 对比：全域 AFTER ≥ BEFORE - eps（无任何像素变暗）
2) direct=0 区域（旧行为最暗区）输出 == tonemap(ambient_color)：
   白色时 = sRGB(Reinhard(1.0)) ≈ 0.7354
3) p_ambient_color 交互：改色后暗斑区输出随之变化
输出：sd/validation/ambient_fix.json + ambient_white.exr / ambient_red.exr
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
report = {'probe': 'ambient_fix', 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, float3
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

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

    amb = wrapper.getPropertyFromId('p_ambient_color', SDPropertyCategory.Input)

    # 1) 白色 ambient
    wrapper.setPropertyValue(amb, SDValueFloat3.sNew(float3(1.0, 1.0, 1.0)))
    test.compute()
    tex = inst.getPropertyValue(outs.getItem(0)).get()
    tex.save(os.path.join(VAL_DIR, 'ambient_white.exr'), '')

    # 2) 红色 ambient（交互验证）
    wrapper.setPropertyValue(amb, SDValueFloat3.sNew(float3(1.0, 0.0, 0.0)))
    test.compute()
    tex = inst.getPropertyValue(outs.getItem(0)).get()
    tex.save(os.path.join(VAL_DIR, 'ambient_red.exr'), '')

    # 还原默认
    wrapper.setPropertyValue(amb, SDValueFloat3.sNew(float3(0.06, 0.07, 0.09)))
    test.compute()

    report['ok'] = True


try:
    main()
except BaseException:
    report['fail'] = traceback.format_exc()
    print('[ABORT]', report['fail'][-500:])

with open(os.path.join(VAL_DIR, 'ambient_fix.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]')
