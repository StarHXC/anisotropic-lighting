# -*- coding: utf-8 -*-
r"""idxmap 终局：5 连接 PP，sample(0..4) 全枚举。
输出 (s0,s1,s2,s3) 于 PP-A；单独 PP-B 输出 s4.r 到 RGB+A。
uniform r 值 0.1/0.2/0.3/0.4/0.5（线性可辨识）。
输出：sd/validation/idxmap4_*.exr + idxmap4.json
"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'idxmap4.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, ColorRGBA, int2
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    res = {'fail': None}
    try:
        graph = SDAPI.get_current_graph()
        srcs = []
        for i in range(5):
            u = graph.newNode('sbs::compositing::uniform')
            cprop = u.getPropertyFromId('outputcolor', SDPropertyCategory.Input)
            u.setPropertyValue(cprop, SDValueColorRGBA.sNew(
                ColorRGBA(0.1 * (i + 1), 0, 0, 1)))
            u.setPosition(float2(2400.0, -2600.0 + i * 150.0))
            srcs.append(u)

        def build_pp(y, sample_ids):
            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
            pp.setPosition(float2(3000.0, y))
            for src in srcs:
                SDAPI.connect_pp_input(src, pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(3300.0, y))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')
            fg, _ = SDAPI.get_perpixel_graph(pp)
            pos = SDAPI.get_pos_node(fg)
            em = Emitter(fg, cache_scope=f'idxmap4_{y}')
            samples = []
            for idx in sample_ids:
                smp = fg.newNode('sbs::function::samplecol')
                pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
                smp.setInputPropertyValueFromId('__constant__',
                                                SDValueInt2.sNew(int2(idx, 0)))
                samples.append(smp)
            rs = [em.sw1(NodeRef(s, 'f4'), 0) for s in samples]
            packed = em.v4_from_f3(em.v3(rs[0], rs[1], rs[2]), rs[3])
            fg.setOutputNode(packed.node, True)
            return pp

        ppA = build_pp(-2600.0, [0, 1, 2, 3])
        ppB = build_pp(-2000.0, [4, 4, 4, 4])
        rbA = compute_and_save(graph, ppA, os.path.join(VAL_DIR, 'idxmap4_a.exr'))
        rbB = compute_and_save(graph, ppB, os.path.join(VAL_DIR, 'idxmap4_b.exr'))
        res['rb'] = [{'ok': rbA['ok'], 'err': (rbA['error'] or '')[:150]},
                     {'ok': rbB['ok'], 'err': (rbB['error'] or '')[:150]}]
        res['uniform_r'] = [0.1, 0.2, 0.3, 0.4, 0.5]
        res['ok'] = all(x['ok'] for x in res['rb'])
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
