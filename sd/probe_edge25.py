# -*- coding: utf-8 -*-
r"""边界分歧诊断：mask1 直通 PP（2048²，1:1），读回 25 个分歧 texel 的
mask 采样值与 coverage。同时输出 position.r 对照。
输出：sd/validation/edge25.exr
"""
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')


def main():
    import sd
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save

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
        for key in ('bake_position', 'mask1'):
            if f'/{key}' in url and key not in bmps:
                bmps[key] = node

    with SDAPI.undo_group('aniso_pp edge25: build'):
        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pp.setPosition(float2(21000.0, -2600.0))
        SDAPI.connect_pp_input(bmps['mask1'], pp)
        SDAPI.connect_pp_input(bmps['bake_position'], pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(21600.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='edge25')
    pos = SDAPI.get_pos_node(fg)
    s0 = SDAPI.samplecol_node(fg, pos, 0)   # mask1
    s1 = SDAPI.samplecol_node(fg, pos, 1)   # position
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdbasetypes import int2
    r0 = em.sw1(NodeRef(s0, 'f4'), 0)
    g0 = em.sw1(NodeRef(s0, 'f4'), 1)
    r1 = em.sw1(NodeRef(s1, 'f4'), 0)
    a0 = em.sw1(NodeRef(s0, 'f4'), 3)
    packed = em.v4_from_f3(em.v3(r0, g0, r1), a0)
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, 'edge25.exr'))
    print('[DONE]')


main()
