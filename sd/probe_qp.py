# -*- coding: utf-8 -*-
r"""q±texel 坐标直读验证：输出 (qp.x, qp.y, qm.x, qm.y) X 方向。
输出：sd/validation/qp_x.exr
"""
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
TEXEL = 1.0 / 2048.0


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
        if '/bake_position' in url:
            bmps['pos'] = node
            break

    pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
    pp.setPosition(float2(26000.0, -2600.0))
    SDAPI.connect_pp_input(bmps['pos'], pp)
    out_node = graph.newNode('sbs::compositing::output')
    out_node.setPosition(float2(26600.0, -2600.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='qpx')
    pos = SDAPI.get_pos_node(fg)
    q = NodeRef(pos, 'f2')
    tex = em.c_f1(TEXEL)
    q_plus = em.add(q, em.v2(tex, em.c_f1(0.0)))
    q_minus = em.sub(q, em.v2(tex, em.c_f1(0.0)))
    # 采 position 于 qPlus/qMinus 的 r 通道（差分验证）
    def sample_r(qv):
        s = fg.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(qv, s, 'pos')
        s.setInputPropertyValueFromId(
            '__constant__',
            __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
            .SDValueInt2.sNew(
                __import__('sd.api.sdbasetypes', fromlist=['int2']).int2(0, 0)))
        return em.sw1(NodeRef(s, 'f4'), 0)
    qp_r = sample_r(q_plus)
    qm_r = sample_r(q_minus)
    pc = em.sw1(NodeRef(SDAPI.samplecol_node(fg, pos, 0), 'f4'), 0)
    packed = em.v4_from_f3(em.v3(qp_r, qm_r, pc), em.c_f1(0.0))
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, 'qp_x.exr'))
    print('[DONE]')


main()
