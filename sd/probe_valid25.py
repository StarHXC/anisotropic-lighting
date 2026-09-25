# -*- coding: utf-8 -*-
r"""25 个 validity mismatch 专项：输出 neighborValid 全分量。
打包：R=inside(qPlus) G=cov(qPlus) B=inside(qMinus) A=cov(qMinus)
（dPdqx 方向）；再加第二组竖向的读回文件。
输出：sd/validation/nv_x.exr / nv_y.exr
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


def build(graph, em_tag, dir_x, dir_y, out_name):
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2

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
        for key in ('mask1',):
            if f'/{key}' in url and key not in bmps:
                bmps[key] = node

    pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
    pp.setPosition(float2(25000.0, -2600.0))
    # bitmap 显式 $outputsize（否则 SD 默认缩到父图默认尺寸 → 边缘混叠）
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdvalueint2 import SDValueInt2 as _SI2
    from sd.api.sdvalueint import SDValueInt as _SI
    from sd.api.sdbasetypes import int2 as _i2
    mprop_sz = bmps['mask1'].getPropertyFromId('$outputsize',
                                               SDPropertyCategory.Input)
    bmps['mask1'].setPropertyInheritanceMethod(mprop_sz,
                                               SDPropertyInheritanceMethod.Absolute)
    bmps['mask1'].setPropertyValue(mprop_sz, _SI2.sNew(_i2(11, 11)))
    mprop_fm = bmps['mask1'].getPropertyFromId('$format',
                                               SDPropertyCategory.Input)
    bmps['mask1'].setPropertyInheritanceMethod(mprop_fm,
                                               SDPropertyInheritanceMethod.Absolute)
    bmps['mask1'].setPropertyValue(mprop_fm, _SI.sNew(3))
    SDAPI.connect_pp_input(bmps['mask1'], pp)
    out_node = graph.newNode('sbs::compositing::output')
    out_node.setPosition(float2(25600.0, -2600.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope=em_tag)
    pos = SDAPI.get_pos_node(fg)
    q = NodeRef(pos, 'f2')
    tex = em.c_f1(TEXEL)
    d_x = em.mul(em.c_f1(dir_x), tex)
    d_y = em.mul(em.c_f1(dir_y), tex)
    q_plus = em.add(q, em.v2(d_x, d_y))
    q_minus = em.sub(q, em.v2(d_x, d_y))

    def nv(qn):
        qx, qy = em.sw1(qn, 0), em.sw1(qn, 1)
        low_x = em.step(em.c_f1(0.0), qx)
        low_y = em.step(em.c_f1(0.0), qy)
        omt = em.sub(em.c_f1(1.0), tex)
        high_x = em.step(qx, omt)
        high_y = em.step(qy, omt)
        inside = em.mul(em.mul(low_x, low_y), em.mul(high_x, high_y))
        s_m = fg.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(qn, s_m, 'pos')
        s_m.setInputPropertyValueFromId('__constant__',
                                        SDValueInt2.sNew(int2(0, 0)))
        cov = em.step(em.c_f1(0.5), em.sw1(NodeRef(s_m, 'f4'), 0))
        return inside, cov

    ip, cp = nv(q_plus)
    im, cm = nv(q_minus)
    packed = em.v4_from_f3(em.v3(ip, cp, im), cm)
    fg.setOutputNode(packed.node, True)
    compute_and_save(graph, pp, os.path.join(VAL_DIR, out_name))


def main():
    import sd
    from aniso_pp import api as SDAPI
    graph = SDAPI.get_current_graph()
    build(graph, 'nv_x', 1.0, 0.0, 'nv_x.exr')
    build(graph, 'nv_y', 0.0, 1.0, 'nv_y.exr')
    print('[DONE]')


main()
