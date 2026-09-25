# -*- coding: utf-8 -*-
r"""0B6：纯 bitmap 4 连接，sample(idx=0..3) 每索引独立探针 PP。
全部 bitmap 直连（无 uniform/PP 源混杂）。
输出：sd/validation/probe_0b6_report.json + bmidx_{i}.exr
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0b6_report.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    res = {'cases': [], 'fail': None}
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

        order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
        # 一个"源 PP"负责 4 连接？不行——每探针独立建 4 连接才隔离。
        # 共享源 PP：若资源索引按 PP 实例隔离，探针 PP 各自建 4 连接最干净。
        for idx in range(4):
            with SDAPI.undo_group(f'aniso_pp 0B6 idx={idx}'):
                pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
                pp.setPosition(float2(11600.0, -2600.0 + idx * 500.0))
                for name in order:
                    SDAPI.connect_pp_input(bmps[name], pp)
                out_node = graph.newNode('sbs::compositing::output')
                out_node.setPosition(float2(12200.0, -2600.0 + idx * 500.0))
                pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                               'inputNodeOutput')
            fg, _ = SDAPI.get_perpixel_graph(pp)
            pos = SDAPI.get_pos_node(fg)
            smp = fg.newNode('sbs::function::samplecol')
            pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
            smp.setInputPropertyValueFromId('__constant__',
                                            SDValueInt2.sNew(int2(idx, 0)))
            fg.setOutputNode(smp, True)
            exr = os.path.join(VAL_DIR, f'bmidx_{idx}.exr')
            rb = compute_and_save(graph, pp, exr)
            res['cases'].append({'idx': idx, 'ok': rb['ok'], 'exr': exr,
                                 'err': (rb['error'] or '')[:120]})
        res['order'] = order
        res['ok'] = all(c['ok'] for c in res['cases'])
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
