# -*- coding: utf-8 -*-
r"""0D2 诊断：直通读回参数图 texelA 原样 + v3 组装顺序验证。
PP-A: 参数图直通（sample(0,0) at $pos）→ 看参数图在 SD 内的实际排布
PP-B: v3(sw1(tA,0), sw1(tA,1), sw1(tA,2)) 原样输出 → 验证 vector3 端口语义
输出：sd/validation/diag_param.exr / diag_v3.exr
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0d2diag_report.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save

    res = {'fail': None}
    try:
        graph = SDAPI.get_current_graph()
        pkg = graph.getPackage()
        # 找已导入的参数图资源
        param_node = None
        nodes = graph.getNodes()
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            try:
                url = node.getReferencedResource().getUrl()
                if 'fixture_0d2_params' in url:
                    param_node = node
                    break
            except BaseException:
                continue
        if param_node is None:
            res['fail'] = 'param node not found'
            raise RuntimeError(res['fail'])

        # PP-A: 参数图直通
        pa, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pa.setPosition(float2(14000.0, -2600.0))
        SDAPI.connect_pp_input(param_node, pa)
        oa = graph.newNode('sbs::compositing::output')
        oa.setPosition(float2(14400.0, -2600.0))
        pa.newPropertyConnectionFromId('unique_filter_output', oa, 'inputNodeOutput')
        fga, _ = SDAPI.get_perpixel_graph(pa)
        posa = SDAPI.get_pos_node(fga)
        # 输出：直接采 (u*36/2048? 参数图是 36×1，PP 2048²) —— u 方向映射：
        # sample u = $pos.x（0..1 线性覆盖 36 texel）
        s0 = SDAPI.samplecol_node(fga, posa, 0)
        SDAPI.fg_set_output(fga, s0)
        ra = compute_and_save(graph, pa, os.path.join(VAL_DIR, 'diag_param.exr'))
        res['a'] = {'ok': ra['ok'], 'err': (ra['error'] or '')[:150]}

        # PP-B: v3 组装顺序验证：tA=texel0=(vx,vy,vz,fbz)，输出 (vx,vy,vz,fbz)
        # 但用 v3 组装（模拟 0D2 的路径）+ texel uv 固定第 0 texel 中心
        pb, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pb.setPosition(float2(14000.0, -1800.0))
        SDAPI.connect_pp_input(param_node, pb)
        ob = graph.newNode('sbs::compositing::output')
        ob.setPosition(float2(14400.0, -1800.0))
        pb.newPropertyConnectionFromId('unique_filter_output', ob, 'inputNodeOutput')
        fgb, _ = SDAPI.get_perpixel_graph(pb)
        emb = Emitter(fgb, cache_scope='diag_v3')
        posb = SDAPI.get_pos_node(fgb)
        p2 = NodeRef(posb, 'f2')
        # 固定 uv = texel0 中心 = 0.5/36
        uv = emb.bc_f2(emb.div(emb.c_f1(0.5), emb.c_f1(36.0)))
        s0 = fgb.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(uv, s0, 'pos')
        s0.setInputPropertyValueFromId('__constant__', SDValueInt2.sNew(int2(0, 0)))
        tA = NodeRef(s0, 'f4')
        v = emb.v3(emb.sw1(tA, 0), emb.sw1(tA, 1), emb.sw1(tA, 2))
        packed = emb.v4_from_f3(v, emb.sw1(tA, 3))
        fgb.setOutputNode(packed.node, True)
        rb = compute_and_save(graph, pb, os.path.join(VAL_DIR, 'diag_v3.exr'))
        res['b'] = {'ok': rb['ok'], 'err': (rb['error'] or '')[:150]}
        res['ok'] = True
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
