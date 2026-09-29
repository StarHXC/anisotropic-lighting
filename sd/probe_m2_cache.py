# -*- coding: utf-8 -*-
r"""M2 诊断 8 — 缓存击破重渲染：pos 单连直通，尺寸往返触发重编译后再导出。

若仍错 → SD 求值缓存/资源解析问题，需重启 SD。
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
REPORT = {'probe': 'm2_cache', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')
    res = pkg.findResourceFromUrl('pkg:///src_bake_position')

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp.setPosition(float2(2600.0, 4800.0))
    n = wrapper.newInstanceNode(res)
    n.setPosition(float2(2600.0, 4800.0))
    SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_cache')
    pos_n = SDAPI.get_pos_node(fg)
    s0 = SDAPI.samplecol_node(fg, pos_n, 0)
    packed = em.v4_from_f3(em.swizzle3_from_f4(NodeRef(s0, 'f4')), em.c_f1(1.0))
    fg.setOutputNode(packed.node, True)
    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(3200.0, 4800.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)

    # 缓存击破: $outputsize 往返
    prop = pp.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
    pp.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
    pp.setPropertyValue(prop, SDValueInt2.sNew(int2(10, 10)))
    wrapper.compute()
    pp.setPropertyValue(prop, SDValueInt2.sNew(int2(11, 11)))
    wrapper.compute()

    p = os.path.join(OUT_DIR, 'm2_pos_cache.exr')
    rb = compute_and_save(wrapper, pp, p)
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']
    wrapper.deleteNode(on)
    wrapper.deleteNode(pp)


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_cache_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
