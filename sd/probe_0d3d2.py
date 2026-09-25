# -*- coding: utf-8 -*-
r"""safeNormalize 拆解诊断：PP 输出 (len2, valid, inv, out3.x)。
用 P1 参数图 case6 near_zero v=(1e-8,0,0) fb=(0,0,1)。
输出：sd/validation/sn_diag.exr
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
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save

    graph = SDAPI.get_current_graph()
    found = {}
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            url = node.getReferencedResource().getUrl()
        except BaseException:
            continue
        for tag in ('p1', 'p2', 'p3'):
            if f'fixture_0d3_{tag}' in url and tag not in found:
                found[tag] = node
    p1 = found['p1']

    pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=4)
    pp.setPosition(float2(17800.0, -2600.0))
    SDAPI.connect_pp_input(p1, pp)
    out_node = graph.newNode('sbs::compositing::output')
    out_node.setPosition(float2(18200.0, -2600.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='sndiag')
    pos = SDAPI.get_pos_node(fg)
    tA = SDAPI.samplecol_node(fg, pos, 0)
    tA = NodeRef(tA, 'f4')
    v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
    fb = em.v3(em.c_f1(0.0), em.c_f1(0.0), em.sw1(tA, 3))

    min_len = 1e-12
    eps2 = em.c_f1(min_len * min_len)
    len2 = em.dot3(v, v)
    valid = em.step(eps2, len2)
    prot = em.max_f1(len2, eps2)
    inv = em.div(em.c_f1(1.0), em.sqrt(prot))
    cand = em.mulscalar(v, inv)
    out3 = em.lerp(fb, cand, valid)
    # 输出 (len2, valid, inv, out3.x)
    packed = em.v4_from_f3(em.v3(len2, valid, inv), em.sw1(out3, 0))
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, 'sn_diag.exr'))
    print('[DONE]')


main()
