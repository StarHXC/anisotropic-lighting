# -*- coding: utf-8 -*-
r"""M2 诊断 7 — 单张 pos 图直通渲染（2048² 1:1），导出 EXR 与磁盘 PNG 逐像素对照。

直接判定 SD 的 bitmap 解码是否保真（高字节/低字节/插值）。
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
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')]:
    del sys.modules[_k]

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
REPORT = {'probe': 'm2_single', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')

    res = pkg.findResourceFromUrl('pkg:///src_bake_position')
    assert res is not None

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp.setPosition(float2(2600.0, 4200.0))
    n = wrapper.newInstanceNode(res)
    n.setPosition(float2(2600.0, 4200.0))
    SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_single')
    pos_n = SDAPI.get_pos_node(fg)
    s0 = SDAPI.samplecol_node(fg, pos_n, 0)
    packed = em.v4_from_f3(em.swizzle3_from_f4(NodeRef(s0, 'f4')), em.c_f1(1.0))
    fg.setOutputNode(packed.node, True)
    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(3200.0, 4200.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    p = os.path.join(OUT_DIR, 'm2_pos_single.exr')
    rb = compute_and_save(wrapper, pp, p)
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']
    wrapper.deleteNode(on)
    wrapper.deleteNode(pp)


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_single_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
