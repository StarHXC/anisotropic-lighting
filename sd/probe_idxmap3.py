# -*- coding: utf-8 -*-
r"""idxmap 收官：单连接 PP 上枚举 sample_idx 0..4。
slot0 实验（idxmap2）证明：1 连接时 sample(0)=唯一连接，sample(>0)=0（空口）。
现在测：1 连接时 sample(0..4) 全枚举 + 2 连接时 sample(0..2)。
输出：sd/validation/idxmap3.json
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
REPORT_PATH = os.path.join(VAL_DIR, 'idxmap3.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, ColorRGBA, int2
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    res = {'cases': [], 'fail': None}
    try:
        graph = SDAPI.get_current_graph()

        def make_uniform(v, y):
            u = graph.newNode('sbs::compositing::uniform')
            cprop = u.getPropertyFromId('outputcolor', SDPropertyCategory.Input)
            u.setPropertyValue(cprop, SDValueColorRGBA.sNew(ColorRGBA(v, 0, 0, 1)))
            u.setPosition(float2(600.0, y))
            return u

        def run_case(n_conn, y_base):
            """n_conn 个 uniform 接一个 PP，sample(0..4) 打包 rgb+? 单输出 4 通道 →
            输出 (s0.r, s1.r, s2.r, s3.r)；s4 单独第二个 PP? 简化：分两轮，
            本轮输出 s0..s3，若需要 s4 再来一轮。"""
            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
            pp.setPosition(float2(1800.0, y_base))
            srcs = [make_uniform((i + 1) / 5.0, y_base + i * 150.0)
                    for i in range(n_conn)]
            for src in srcs:
                SDAPI.connect_pp_input(src, pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(2100.0, y_base))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')
            fg, _ = SDAPI.get_perpixel_graph(pp)
            pos = SDAPI.get_pos_node(fg)
            samples = []
            for i in range(4):
                smp = fg.newNode('sbs::function::samplecol')
                pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
                smp.setInputPropertyValueFromId('__constant__',
                                                SDValueInt2.sNew(int2(i, 0)))
                samples.append(smp)
            from aniso_pp.emitter import Emitter, NodeRef
            em = Emitter(fg, cache_scope=f'idxmap3_{n_conn}')
            rs = [em.sw1(NodeRef(s, 'f4'), 0) for s in samples]
            packed = em.v4_from_f3(em.v3(rs[0], rs[1], rs[2]), rs[3])
            fg.setOutputNode(packed.node, True)
            exr = os.path.join(VAL_DIR, f'idxmap3_{n_conn}conn.exr')
            rb = compute_and_save(graph, pp, exr)
            return {'n_conn': n_conn, 'ok': rb['ok'], 'exr': exr,
                    'err': (rb['error'] or '')[:150]}

        res['cases'].append(run_case(1, -2600.0))
        res['cases'].append(run_case(2, -2000.0))
        res['cases'].append(run_case(3, -1400.0))
        res['ok'] = True
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
