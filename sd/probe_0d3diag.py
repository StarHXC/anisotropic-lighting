# -*- coding: utf-8 -*-
r"""0D3 诊断：主 PP 3 参数图连接，输出 (s0.r, s1.r, s2.r, s0.a) 原样。
判定 sample 0/1/2 是否分别对应 P1/P2/P3。
输出：sd/validation/diag3.exr
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


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save

    graph = SDAPI.get_current_graph()
    param_nodes = []
    nodes = graph.getNodes()
    order = ['p1', 'p2', 'p3']
    found = {}
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            url = node.getReferencedResource().getUrl()
        except BaseException:
            continue
        for tag in order:
            if f'fixture_0d3_{tag}' in url and tag not in found:
                found[tag] = node
    param_nodes = [found[t] for t in order]

    pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=4)
    pp.setPosition(float2(17000.0, -2600.0))
    for pn in param_nodes:
        SDAPI.connect_pp_input(pn, pp)
    out_node = graph.newNode('sbs::compositing::output')
    out_node.setPosition(float2(17400.0, -2600.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    pos = SDAPI.get_pos_node(fg)
    em = Emitter(fg, cache_scope='diag3')
    s0 = SDAPI.samplecol_node(fg, pos, 0)
    s1 = SDAPI.samplecol_node(fg, pos, 1)
    s2 = SDAPI.samplecol_node(fg, pos, 2)
    r0 = em.sw1(NodeRef(s0, 'f4'), 0)
    r1 = em.sw1(NodeRef(s1, 'f4'), 0)
    r2 = em.sw1(NodeRef(s2, 'f4'), 0)
    a0 = em.sw1(NodeRef(s0, 'f4'), 3)
    packed = em.v4_from_f3(em.v3(r0, r1, r2), a0)
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, 'diag3.exr'))
    print('[DONE]')


main()
