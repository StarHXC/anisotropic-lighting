# -*- coding: utf-8 -*-
r"""M2 诊断 2 — 正式包 4 槽直通渲染（RGB=槽位原样）确认求值链数据流。

新临时 PP：同 4 bitmap 直连，FG = samplecol(i) 直通 RGB。
不修改正式包。
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
REPORT = {'probe': 'm2_passthru', 'fail': None}


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

    # 找包内 4 个 bitmap 资源
    bmps = []
    for rid in ('src_bake_position', 'src_bake_normalobj', 'src_mask1', 'src_bake_ao'):
        r = pkg.findResourceFromUrl(f'pkg:///{rid}')
        assert r is not None, rid
        bmps.append(r)

    # 临时 PP 直通
    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp.setPosition(float2(1600.0, 1200.0))
    for res in bmps:
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(1600.0, 1200.0))
        SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_pt')
    pos = SDAPI.get_pos_node(fg)
    s2 = SDAPI.samplecol_node(fg, pos, 2)  # mask 槽
    cov = em.step(em.c_f1(0.5), em.sw1(NodeRef(s2, 'f4'), 0))
    packed = em.v4_from_f3(em.v3(cov, cov, cov), em.c_f1(1.0))
    fg.setOutputNode(packed.node, True)

    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(2200.0, 1200.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    rb = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm2_cov_pt.exr'))
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']

    # 清理：删临时 PP/output（不保存包 — 内存对象随会话丢弃）
    wrapper.deleteNode(on)
    wrapper.deleteNode(pp)


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm2_passthru_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
