# -*- coding: utf-8 -*-
r"""0B5：samplecol __constant__ 第二分量语义探测。
主 PP 5 连接（dummy+4 图），固定第一分量=0，第二分量 k=0..4 → 每槽独立 PP 读回。
若某 k 让 sample(0,k) 变图 → 找到真正的图选择维度。
输出：sd/validation/probe_0b5_report.json + s2nd_k.exr 系列
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0b5_report.json')


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

        # 连接序：pos, nrm, mask, ao（4 连接，无 dummy——先验证无 dummy 时 idx0=谁）
        order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
        for k in range(5):
            with SDAPI.undo_group(f'aniso_pp 0B5 k={k}'):
                pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
                pp.setPosition(float2(10400.0, -2600.0 + k * 500.0))
                for name in order:
                    SDAPI.connect_pp_input(bmps[name], pp)
                out_node = graph.newNode('sbs::compositing::output')
                out_node.setPosition(float2(11000.0, -2600.0 + k * 500.0))
                pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                               'inputNodeOutput')
            fg, _ = SDAPI.get_perpixel_graph(pp)
            pos = SDAPI.get_pos_node(fg)
            smp = fg.newNode('sbs::function::samplecol')
            pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
            smp.setInputPropertyValueFromId('__constant__',
                                            SDValueInt2.sNew(int2(0, k)))
            fg.setOutputNode(smp, True)
            exr = os.path.join(VAL_DIR, f's2nd_{k}.exr')
            rb = compute_and_save(graph, pp, exr)
            res['cases'].append({'k': k, 'ok': rb['ok'], 'exr': exr,
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
