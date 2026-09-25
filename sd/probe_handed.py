# -*- coding: utf-8 -*-
r"""handed 值放大输出（×1e6）—— 量化两侧距阈值的距离。
输出：sd/validation/handed.exr
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
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdbasetypes import float2, int2
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
        for key in ('bake_position', 'bake_normalobj', 'mask1'):
            if f'/{key}' in url and key not in bmps:
                bmps[key] = node

    with SDAPI.undo_group('aniso_pp handed: build'):
        for name, node in bmps.items():
            for prop_id, val in (('$outputsize',
                                  SDValueInt2.sNew(int2(11, 11))),
                                 ('$format', SDValueInt.sNew(3))):
                prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
                node.setPropertyInheritanceMethod(
                    prop, SDPropertyInheritanceMethod.Absolute)
                node.setPropertyValue(prop, val)

        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pp.setPosition(float2(28000.0, -2600.0))
        for name in ('bake_position', 'bake_normalobj', 'mask1'):
            SDAPI.connect_pp_input(bmps[name], pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(28600.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')

    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='handed')
    pos = SDAPI.get_pos_node(fg)
    q = NodeRef(pos, 'f2')

    def sample(i):
        s = fg.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(q, s, 'pos')
        s.setInputPropertyValueFromId(
            '__constant__',
            __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
            .SDValueInt2.sNew(
                __import__('sd.api.sdbasetypes', fromlist=['int2']).int2(i, 0)))
        return NodeRef(s, 'f4')

    s_pos, s_nrm = sample(0), sample(1)
    texel = 1.0 / 2048.0

    Pw = em.v3(em.sw1(s_pos, 0), em.sw1(s_pos, 1), em.sw1(s_pos, 2))
    N0raw = em.sub(em.mul(em.v3(em.sw1(s_nrm, 0), em.sw1(s_nrm, 1),
                                em.sw1(s_nrm, 2)),
                          em.c_f1(2.0)), em.bc_f3(em.c_f1(1.0)))
    nx = em.sw1(N0raw, 0)
    len2_n = em.dot3(N0raw, N0raw)
    use_y = em.step(em.mul(len2_n, em.c_f1(0.5)), em.mul(nx, nx))
    ref = em.v3(em.sub(em.c_f1(1.0), use_y), use_y, em.c_f1(0.0))
    pf_c = em.add(em.cross3(N0raw, ref), em.v3(em.c_f1(0.0), em.c_f1(0.0),
                                               em.c_f1(1e-6)))
    pf = em.swizzle3_from_f4(em.safe_normalize(pf_c, em.v3(em.c_f1(0.0),
                                                           em.c_f1(0.0),
                                                           em.c_f1(1.0)),
                                              1e-12))
    n0N = em.safe_normalize(N0raw, pf, 1e-12)
    N0 = em.swizzle3_from_f4(n0N)

    tex = em.c_f1(texel)

    def sample_pos(qv):
        s = fg.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(qv, s, 'pos')
        s.setInputPropertyValueFromId(
            '__constant__',
            __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
            .SDValueInt2.sNew(
                __import__('sd.api.sdbasetypes', fromlist=['int2']).int2(0, 0)))
        return em.swizzle3_from_f4(NodeRef(s, 'f4'))

    def derivative(dir_x, dir_y):
        d_x = em.mul(em.c_f1(dir_x), tex)
        d_y = em.mul(em.c_f1(dir_y), tex)
        q_plus = em.add(q, em.v2(d_x, d_y))
        q_minus = em.sub(q, em.v2(d_x, d_y))
        Pp, Pm = sample_pos(q_plus), sample_pos(q_minus)
        d_plus = em.sub(Pp, Pw)
        d_minus = em.sub(Pw, Pm)
        # 无 valid 加权——直接取正向差分（边缘处 max(0+1,1) 分母=1 时一致）
        weighted = d_minus
        return em.swizzle3_from_f4(em.v4_from_f3(weighted, em.c_f1(1.0)))

    dPdu = derivative(1.0, 0.0)
    dPdv = em.mulscalar(derivative(0.0, 1.0), em.c_f1(-1.0))
    dotN0Pu = em.dot3(N0, dPdu)
    TuCand = em.sub(dPdu, em.mulscalar(N0, dotN0Pu))
    tuN = em.safe_normalize(TuCand, pf, 1e-12)
    Tuv = em.swizzle3_from_f4(tuN)
    handed = em.dot3(em.cross3(N0, Tuv), dPdv)
    # 输出 handed*1e6 + 0.5 偏置（可分辨正负与量级）
    packed = em.v4_from_f3(
        em.add(em.mulscalar(em.bc_f3(handed), em.c_f1(1e6)),
               em.bc_f3(em.c_f1(0.5))), em.c_f1(0.0))
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, 'handed.exr'))
    print('[DONE]')


main()
