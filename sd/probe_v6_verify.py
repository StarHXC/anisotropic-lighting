# -*- coding: utf-8 -*-
r"""v6 双面翻转 + 有界 AO 调制验证（三态渲染落盘）：

前置：SD 已重载 v6 包（stage3_pp2 生成 + stage2_verify 通过），
test graph 中已有 aniso_lightmap 实例（stage2_verify 会创建）。

渲染序列（ambient 全程 = 白）：
1. v6_off.exr   two_sided=0, ambient_ao=0   → 应与 v5 ambient_white.exr 逐像素一致
2. v6_flip.exr  two_sided=1, ambient_ao=0   → 翻转单独作用
3. v6_full.exr  two_sided=1, ambient_ao=0.5 → 完整 v6 默认态
结束恢复参数默认（ambient_color=(0.06,0.07,0.09)）。

输出：sd/validation/v6_verify.json + 3 个 EXR
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
report = {'probe': 'v6_verify', 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, float3
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
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

    p_amb = wrapper.getPropertyFromId('p_ambient_color', SDPropertyCategory.Input)
    p_ts = wrapper.getPropertyFromId('p_two_sided', SDPropertyCategory.Input)
    p_ao = wrapper.getPropertyFromId('p_ambient_ao', SDPropertyCategory.Input)
    assert p_ts is not None, 'v6 包缺 p_two_sided —— 需先重跑 stage3_pp2 + 重载'
    assert p_ao is not None, 'v6 包缺 p_ambient_ao —— 需先重跑 stage3_pp2 + 重载'

    def render(name):
        test.compute()
        tex = inst.getPropertyValue(outs.getItem(0)).get()
        path = os.path.join(VAL_DIR, name)
        tex.save(path, '')
        report[name] = path
        print('[RENDER]', name)

    # 三态（ambient 全程白，隔离两个新参数的作用）
    wrapper.setPropertyValue(p_amb, SDValueFloat3.sNew(float3(1.0, 1.0, 1.0)))
    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(0))
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.0))
    render('v6_off.exr')

    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(1))
    render('v6_flip.exr')

    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.5))
    render('v6_full.exr')

    # 还原默认
    wrapper.setPropertyValue(p_amb, SDValueFloat3.sNew(float3(0.06, 0.07, 0.09)))
    wrapper.setPropertyValue(p_ts, SDValueInt.sNew(1))
    wrapper.setPropertyValue(p_ao, SDValueFloat.sNew(0.5))
    test.compute()

    report['ok'] = True


try:
    main()
except BaseException:
    report['fail'] = traceback.format_exc()
    print('[ABORT]', report['fail'][-500:])

with open(os.path.join(VAL_DIR, 'v6_verify.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]')
