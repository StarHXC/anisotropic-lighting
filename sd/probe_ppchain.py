# -*- coding: utf-8 -*-
r"""架构验证：4 个直通 PP（各接 1 张 bitmap，sample(0) 已验证可靠）
+ 1 个主 PP 接 4 个直通 PP 的输出 → 主 PP 内 sample(0..3) 是否规整。
输出：sd/validation/ppchain.exr + probe_ppchain_report.json
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_ppchain_report.json')
EXR_PATH = os.path.join(VAL_DIR, 'ppchain.exr')


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

        # 4 张 bitmap
        wanted = {}
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
                if f'/{key}' in url and key not in wanted:
                    wanted[key] = node

        with SDAPI.undo_group('aniso_pp ppchain: build'):
            # 4 个直通 PP（2048²，直通 sample(0)）
            pass_pps = {}
            for idx, (name, bmp) in enumerate(wanted.items()):
                pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
                pp.setPosition(float2(3800.0, -2600.0 + idx * 500.0))
                SDAPI.connect_pp_input(bmp, pp)
                fg, _ = SDAPI.get_perpixel_graph(pp)
                pos = SDAPI.get_pos_node(fg)
                smp = fg.newNode('sbs::function::samplecol')
                pos.newPropertyConnectionFromId('unique_filter_output', smp, 'pos')
                smp.setInputPropertyValueFromId('__constant__',
                                                SDValueInt2.sNew(int2(0, 0)))
                fg.setOutputNode(smp, True)
                pass_pps[name] = pp

        # 主 PP：接 4 个直通 PP 输出（顺序 pos/nrm/mask/ao）
        with SDAPI.undo_group('aniso_pp ppchain: main wiring'):
            order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
            main_pp2, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
            main_pp2.setPosition(float2(5600.0, -1800.0))
            for name in order:
                SDAPI.connect_pp_input(pass_pps[name], main_pp2)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(6200.0, -1800.0))
            main_pp2.newPropertyConnectionFromId('unique_filter_output', out_node,
                                                 'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(main_pp2)
        pos = SDAPI.get_pos_node(fg)
        em = Emitter(fg, cache_scope='ppchain')
        samples = [SDAPI.samplecol_node(fg, pos, i) for i in range(4)]
        rs = [em.sw1(NodeRef(s, 'f4'), 0) for s in samples]
        packed = em.v4_from_f3(em.v3(rs[0], rs[1], rs[2]), rs[3])
        fg.setOutputNode(packed.node, True)

        rb = compute_and_save(graph, main_pp2, EXR_PATH)
        res['readback'] = {'ok': rb['ok'], 'size': rb['size'],
                           'err': (rb['error'] or '')[:200]}
        res['order'] = order
        res['ok'] = rb['ok']
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
