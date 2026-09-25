# -*- coding: utf-8 -*-
r"""idxmap 修正实验：uniform 颜色读回验证 + 每槽独立 PP 采样。

- 先读回 5 个 uniform 的 outputcolor 确认设置成功
- 再建 5 个独立 PP（各只接 1 个 uniform，sample(0)）→ 排除 VARIADIC 交互
输出：sd/validation/idxmap2.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'idxmap2.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, ColorRGBA
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    res = {'uniform_readback': [], 'single_pp': [], 'fail': None}
    try:
        graph = SDAPI.get_current_graph()

        # 5 个 uniform + 颜色读回
        srcs = []
        for i in range(5):
            u = graph.newNode('sbs::compositing::uniform')
            cprop = u.getPropertyFromId('outputcolor', SDPropertyCategory.Input)
            want = (i + 1) / 5.0
            u.setPropertyValue(cprop, SDValueColorRGBA.sNew(
                ColorRGBA(want, 0.0, 0.0, 1.0)))
            got = u.getInputPropertyValueFromId('outputcolor').get()
            res['uniform_readback'].append(
                {'want': want, 'got_r': round(float(got.r), 4),
                 'ok': abs(float(got.r) - want) < 1e-3})
            u.setPosition(float2(600.0, -1400.0 + i * 150.0))
            srcs.append(u)

        # 每槽独立 PP：只接 1 个 uniform → sample(0) 应读到该 uniform
        for i, src in enumerate(srcs):
            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
            pp.setPosition(float2(1200.0, -1400.0 + i * 150.0))
            SDAPI.connect_pp_input(src, pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(1500.0, -1400.0 + i * 150.0))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')
            fg, _ = SDAPI.get_perpixel_graph(pp)
            pos = SDAPI.get_pos_node(fg)
            smp = fg.newNode('sbs::function::samplecol')
            pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
            smp.setInputPropertyValueFromId(
                '__constant__',
                __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
                .SDValueInt2.sNew(__import__('sd.api.sdbasetypes',
                                             fromlist=['int2']).int2(i, 0)))
            fg.setOutputNode(smp, True)
            exr = os.path.join(VAL_DIR, f'idxmap2_slot{i}.exr')
            rb = compute_and_save(graph, pp, exr)
            res['single_pp'].append({'slot': i, 'sample_idx': i,
                                     'ok': rb['ok'], 'exr': exr,
                                     'err': (rb['error'] or '')[:150]})
        res['ok'] = True
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
