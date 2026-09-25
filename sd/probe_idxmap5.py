# -*- coding: utf-8 -*-
r"""决定性实验（无空口）：5 个连接全 bitmap（mask1 用两次），无 EMPTY 引脚。
sample(0..4) 全枚举 → 锁定索引模型。
输出：sd/validation/idxmap5.json + idxmap5.exr
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
REPORT_PATH = os.path.join(VAL_DIR, 'idxmap5.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

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

        with SDAPI.undo_group('aniso_pp idxmap5: build'):
            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
            pp.setPosition(float2(6800.0, -1800.0))
            # 5 连接全 bitmap：pos, nrm, mask, ao, mask(重复)
            order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao',
                     'mask1']
            for name in order:
                SDAPI.connect_pp_input(bmps[name], pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(7400.0, -1800.0))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')

        # sample(0..4)：PP 单输出 4 通道 → 分 2 个函数图输出做不全。
        # 直接 5 个值打包：R=s0 G=s1 B=s2 A=s3；s4 用第二轮输出? 简化：
        # 用两个 PP（同接线）分别打包 s0-s3 / s4+s1+s2+s3。
        def build_pp(y, ids):
            pp2, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
            pp2.setPosition(float2(6800.0, y))
            for name in order:
                SDAPI.connect_pp_input(bmps[name], pp2)
            out2 = graph.newNode('sbs::compositing::output')
            out2.setPosition(float2(7400.0, y))
            pp2.newPropertyConnectionFromId('unique_filter_output', out2,
                                            'inputNodeOutput')
            fg, _ = SDAPI.get_perpixel_graph(pp2)
            pos = SDAPI.get_pos_node(fg)
            em = Emitter(fg, cache_scope=f'idxmap5_{y}')
            rs = []
            for idx in ids:
                smp = fg.newNode('sbs::function::samplecol')
                pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
                smp.setInputPropertyValueFromId('__constant__',
                                                SDValueInt2.sNew(int2(idx, 0)))
                rs.append(em.sw1(NodeRef(smp, 'f4'), 0))
            packed = em.v4_from_f3(em.v3(rs[0], rs[1], rs[2]), rs[3])
            fg.setOutputNode(packed.node, True)
            return pp2

        ppA = build_pp(-2600.0, [0, 1, 2, 3])
        ppB = build_pp(-2000.0, [4, 1, 2, 3])
        rbA = compute_and_save(graph, ppA, os.path.join(VAL_DIR, 'idxmap5_a.exr'))
        rbB = compute_and_save(graph, ppB, os.path.join(VAL_DIR, 'idxmap5_b.exr'))
        res['rb'] = [{'ok': rbA['ok'], 'err': (rbA['error'] or '')[:150]},
                     {'ok': rbB['ok'], 'err': (rbB['error'] or '')[:150]}]
        res['order'] = order
        res['ok'] = all(x['ok'] for x in res['rb'])
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
