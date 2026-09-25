# -*- coding: utf-8 -*-
r"""0B4：主 PP 2 输入（X=shuffle(pos,ao), Y=shuffle(nrm,mask)），
两个探针 PP 分别原样输出 sample(0) / sample(1) 的 float4，读回全通道统计。
输出：sd/validation/s0_raw.exr / s1_raw.exr
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0b4_report.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    res = {'fail': None}
    try:
        graph = SDAPI.get_current_graph()
        bmps = {}
        nodes = graph.getNodes()
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            try:
                if node.getDefinition().getId() != 'sbs::compositing::bitmap':
                    continue
                url = node.getReferencedResource().getUrl()
            except BaseException:
                continue
            for key in ('bake_position', 'bake_normalobj', 'mask1', 'bake_ao'):
                if f'/{key}' in url and key not in bmps:
                    bmps[key] = node

        shuf_x = graph.newNode('sbs::compositing::shuffle')
        shuf_x.setPosition(float2(9200.0, -1800.0))
        bmps['bake_position'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_x, 'input1')
        bmps['bake_ao'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_x, 'input2')
        shuf_y = graph.newNode('sbs::compositing::shuffle')
        shuf_y.setPosition(float2(9200.0, -1200.0))
        bmps['bake_normalobj'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_y, 'input1')
        bmps['mask1'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_y, 'input2')

        with SDAPI.undo_group('aniso_pp 0B4: probes'):
            # 探针 A：只接 X → sample(0) 原样
            pa, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
            pa.setPosition(float2(9600.0, -1800.0))
            SDAPI.connect_pp_input(shuf_x, pa)
            oa = graph.newNode('sbs::compositing::output')
            oa.setPosition(float2(10000.0, -1800.0))
            pa.newPropertyConnectionFromId('unique_filter_output', oa,
                                           'inputNodeOutput')
            fga, _ = SDAPI.get_perpixel_graph(pa)
            posa = SDAPI.get_pos_node(fga)
            s0 = SDAPI.samplecol_node(fga, posa, 0)
            SDAPI.fg_set_output(fga, s0)

            # 探针 B：接 X+Y → sample(0) 与 sample(1) 打包（r/r/a/a）
            pb, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
            pb.setPosition(float2(9600.0, -600.0))
            SDAPI.connect_pp_input(shuf_x, pb)
            SDAPI.connect_pp_input(shuf_y, pb)
            ob = graph.newNode('sbs::compositing::output')
            ob.setPosition(float2(10000.0, -600.0))
            pb.newPropertyConnectionFromId('unique_filter_output', ob,
                                           'inputNodeOutput')
            fgb, _ = SDAPI.get_perpixel_graph(pb)
            posb = SDAPI.get_pos_node(fgb)
            from aniso_pp.emitter import Emitter, NodeRef
            em = Emitter(fgb, cache_scope='probe_0b4')
            s0b = SDAPI.samplecol_node(fgb, posb, 0)
            s1b = SDAPI.samplecol_node(fgb, posb, 1)
            r0 = em.sw1(NodeRef(s0b, 'f4'), 0)
            r1 = em.sw1(NodeRef(s1b, 'f4'), 0)
            a0 = em.sw1(NodeRef(s0b, 'f4'), 3)
            a1 = em.sw1(NodeRef(s1b, 'f4'), 3)
            packed = em.v4_from_f3(em.v3(r0, r1, a0), a1)
            SDAPI.fg_set_output(fgb, packed.node)

        ra = compute_and_save(graph, pa, os.path.join(VAL_DIR, 's0_raw.exr'))
        rb = compute_and_save(graph, pb, os.path.join(VAL_DIR, 's1_pack.exr'))
        res = {'a': {'ok': ra['ok'], 'err': (ra['error'] or '')[:150]},
               'b': {'ok': rb['ok'], 'err': (rb['error'] or '')[:150]},
               'ok': ra['ok'] and rb['ok']}
    except BaseException:
        import traceback as tb
        res = {'fail': tb.format_exc()}

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
