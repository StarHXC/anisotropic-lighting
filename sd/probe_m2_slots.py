# -*- coding: utf-8 -*-
r"""M2 诊断 4 — 正式包内新建 PP 直读 4 槽原始值（同一包内资源连接验证）。

输出 RGB = samplecol(1).rgb（normalobj 槽原值）A=1 → 检查包内槽读取。
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
REPORT = {'probe': 'm2_slots', 'fail': None}


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

    bmps = []
    for rid in ('src_bake_position', 'src_bake_normalobj', 'src_mask1', 'src_bake_ao'):
        r = pkg.findResourceFromUrl(f'pkg:///{rid}')
        assert r is not None, rid
        bmps.append(r)

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp.setPosition(float2(1600.0, 3000.0))
    for res in bmps:
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(1600.0, 3000.0))
        SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_slots')
    pos_n = SDAPI.get_pos_node(fg)
    s0 = SDAPI.samplecol_node(fg, pos_n, 0)
    s1 = SDAPI.samplecol_node(fg, pos_n, 1)
    s2 = SDAPI.samplecol_node(fg, pos_n, 2)
    s3 = SDAPI.samplecol_node(fg, pos_n, 3)
    r0 = em.sw1(NodeRef(s0, 'f4'), 0)
    r1 = em.sw1(NodeRef(s1, 'f4'), 0)
    r2 = em.sw1(NodeRef(s2, 'f4'), 0)
    r3 = em.sw1(NodeRef(s3, 'f4'), 0)
    packed = em.v4_from_f3(em.v3(r0, r1, r2), r3)
    fg.setOutputNode(packed.node, True)
    REPORT['slots'] = 'R=slot0.R G=slot1.R B=slot2.R A=slot3.R'

    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(2200.0, 3000.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    rb = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm2_slot1.exr'))
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']
    wrapper.deleteNode(on)
    wrapper.deleteNode(pp)


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_slots_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
