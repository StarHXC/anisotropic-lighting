# -*- coding: utf-8 -*-
r"""vector3 端口语义裁定实验：常数 (0.1, 0.2, 0.3) 用三种组装方式，
读回确定真实装填顺序。
  方式1（当前 emitter.v3）：x→componentsin, y→componentsin, z→componentslast
  方式2（node_builder.vec3 同构）：vec2(x,y)→componentsin, z→componentslast
  方式3：const_float3 单节点
输出：sd/validation/v3order.exr / v3order.json
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
REPORT_PATH = os.path.join(VAL_DIR, 'v3order.json')


def main():
    import sd
    from sd.api.sdbasetypes import float2, float3, float4, int2
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdvaluefloat4 import SDValueFloat4
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save

    res = {'fail': None}
    try:
        graph = SDAPI.get_current_graph()
        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)  # 4×4
        pp.setPosition(float2(16000.0, -2600.0))
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(16400.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope='v3order')

        x, y, z = em.c_f1(0.1), em.c_f1(0.2), em.c_f1(0.3)

        # 方式1
        n1 = em._new('sbs::function::vector3')
        SDAPI.fg_connect(x, n1, 'componentsin')
        SDAPI.fg_connect(y, n1, 'componentsin')
        SDAPI.fg_connect(z, n1, 'componentslast')
        n1.t = 'f3'
        # 方式2：vec2(x,y)→componentsin
        v2 = em._new('sbs::function::vector2')
        SDAPI.fg_connect(x, v2, 'componentsin')
        SDAPI.fg_connect(y, v2, 'componentsin')
        v2.t = 'f2'
        n2 = em._new('sbs::function::vector3')
        SDAPI.fg_connect(v2, n2, 'componentsin')
        SDAPI.fg_connect(z, n2, 'componentslast')
        n2.t = 'f3'
        # 方式3：const_float3
        n3 = em._new('sbs::function::const_float3')
        em._cst(n3, SDValueFloat3.sNew(float3(0.1, 0.2, 0.3)))
        n3.t = 'f3'

        # 打包 3 行 → 用像素行区分：输出 = (m1.r, m1.g, m1.b) 在 R 通道按 v 坐标切换？
        # 单输出限制：三次读回。简单做法：3 个探针输出各 set (v3, w=标记行号)
        results = {}
        for idx, (tag, nref) in enumerate(
                [('m1_componentsin_x2', n1),
                 ('m2_vec2_sin', n2),
                 ('m3_const_f3', n3)]):
            wmark = em.c_f1(float(idx + 1))
            packed = em.v4_from_f3(nref, wmark)
            fg.setOutputNode(packed.node, True)
            exr = os.path.join(VAL_DIR, f'v3order_{idx}.exr')
            rb = compute_and_save(graph, pp, exr)
            results[tag] = {'ok': rb['ok'], 'exr': exr,
                            'err': (rb['error'] or '')[:150]}
        res['results'] = results
        res['ok'] = all(v['ok'] for v in results.values())
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
