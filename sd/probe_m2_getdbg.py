# -*- coding: utf-8 -*-
r"""M2 诊断 3 — 正式包 PP FG 内 get_float1 参数解析直通。

在 aniso_mask 包内新建临时 PP，FG = get_float1('p_light_azimuth_deg') 等
5 参数直通（R=az G=el B=a A=r），渲染落盘后删除临时节点（不保存包）。
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.')
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')
           or k == 'stages']:
    del sys.modules[_k]

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
REPORT = {'probe': 'm2_getdbg', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from sd.api.sdvaluestring import SDValueString
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=3)
    pp.setPosition(float2(1600.0, 1800.0))
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_gd')

    def getf(pid):
        gf = fg.newNode('sbs::function::get_float1')
        gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(pid))
        return NodeRef(gf, 'f1')

    az, el = getf('p_light_azimuth_deg'), getf('p_light_elevation_deg')
    a, r = getf('p_anisotropy'), getf('p_roughness')
    # colorswitch=False 的 PP 输出 float4 会合并灰度 → 逐通道分不清。
    # 改为标量输出：单个 get_float1 直接作为 float1 输出（R=该参数值）
    packed = az  # float1 直通：p_light_azimuth_deg
    fg.setOutputNode(packed.node, True)

    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(2200.0, 1800.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    rb = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm2_getdbg.exr'))
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']

    wrapper.deleteNode(on)
    wrapper.deleteNode(pp)


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm2_getdbg_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
