# -*- coding: utf-8 -*-
r"""M2 诊断 6 — 连接顺序实验：真实资产 4 图按不同连接顺序连接新 PP，
读 slot0..3 的 R，确定 samplecol 索引的真实映射规律。

实验矩阵：顺序 A(pos,nrm,mask,ao) 与 反序 A'(ao,mask,nrm,pos)。
输出每实验 4 个值（slot0..3 的 R @ (937,493) 附近均值块）。
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
REPORT = {'probe': 'm2_order', 'fail': None}


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

    def run(order, tag):
        pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
        pp.setPosition(float2(2600.0, 2000.0 + 500.0 * (0 if tag == 'fwd' else 1)))
        for res in order:
            n = wrapper.newInstanceNode(res)
            n.setPosition(float2(2600.0, 2000.0))
            SDAPI.connect_pp_input(n, pp)
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope=f'm2_ord_{tag}')
        pos_n = SDAPI.get_pos_node(fg)
        reads = []
        for i in range(4):
            s = SDAPI.samplecol_node(fg, pos_n, i)
            reads.append(em.sw1(NodeRef(s, 'f4'), 0))
        packed = em.v4_from_f3(em.v3(reads[0], reads[1], reads[2]), reads[3])
        fg.setOutputNode(packed.node, True)
        on = wrapper.newNode('sbs::compositing::output')
        on.setPosition(float2(3200.0, 2000.0))
        pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
        wrapper.setOutputNode(on, True)
        p = os.path.join(OUT_DIR, f'm2_ord_{tag}.exr')
        rb = compute_and_save(wrapper, pp, p)
        REPORT[f'{tag}_order'] = [str(r.getUrl()) for r in order]
        REPORT[f'{tag}_path'] = p
        REPORT[f'{tag}_render'] = rb
        wrapper.deleteNode(on)
        wrapper.deleteNode(pp)

    run(bmps, 'fwd')
    run(list(reversed(bmps)), 'rev')
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_order_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
