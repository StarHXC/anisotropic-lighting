# -*- coding: utf-8 -*-
r"""cross3 装填专项：常数 a=(0.3,0.6,0.9) b=(0.2,0.5,0.8)。
真值 cross=(0.03,-0.06,0.03)。同时测 v2 装填（v2(0.1,0.7) 期望 (0.1,0.7)）。
输出：sd/validation/cross3diag.exr
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
    pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
    pp.setPosition(float2(18600.0, -2600.0))
    out_node = graph.newNode('sbs::compositing::output')
    out_node.setPosition(float2(19000.0, -2600.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='cross3diag')

    a = em.v3(em.c_f1(0.3), em.c_f1(0.6), em.c_f1(0.9))
    b = em.v3(em.c_f1(0.2), em.c_f1(0.5), em.c_f1(0.8))
    cr = em.cross3(a, b)
    # 同时直通 a 原样验证 v3 常数装填
    # 输出 (cr.x, cr.y, cr.z, a.y)  —— a.y 应=0.6（v3 的 y 槽）
    packed = em.v4_from_f3(cr, em.sw1(a, 1))
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, 'cross3diag.exr'))
    print('[DONE]')


main()
