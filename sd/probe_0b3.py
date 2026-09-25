# -*- coding: utf-8 -*-
r"""0B 第三轮 — shuffle 打包架构 + 2 输入采样验证（最终架构定型实验）。

架构（绕开 SD 16.0.1 samplecol 多输入索引缺陷，证据 idxmap5/ppchain）：
    图X = shuffle(pos, ao)   → RGBA=(pos.r, pos.g, pos.b, ao.r)
    图Y = shuffle(nrm, mask) → RGBA=(nrm.r, nrm.g, nrm.b, mask.r)
    主 PP（2 输入）: sample(0)=图X sample(1)=图Y —— 0/1 两索引已被多实验证实可靠
    主 PP 输出打包 (X.r, Y.a, X.a, Y.r) 用于对照判定。

判定：外部相关性分析 sample 各通道 vs 源图 → corr=1.0 全对号即通过。
输出：sd/validation/probe_0b3_report.json + pack_x.exr / pack_y.exr / main.exr
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0b3_report.json')

report = {'probe': '0B3', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0B3 失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp.emitter import Emitter, NodeRef

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

    # 4 张 bitmap
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
        for key in ('bake_position', 'bake_normalobj', 'mask1', 'bake_ao'):
            if f'/{key}' in url and key not in bmps:
                bmps[key] = node
    step('bitmap 定位', len(bmps) == 4, sorted(bmps))

    with SDAPI.undo_group('aniso_pp 0B3: build'):
        # shuffle 节点：channelred/green/blue/alpha 枚举语义待查——先默认
        # （SD shuffle 默认 R←input1.R G←input1.G B←input1.B A←input2.R ? 不确定）
        # 保守：先建节点读回 4 个通道枚举值，再按需设置。
        shuf_x = graph.newNode('sbs::compositing::shuffle')
        shuf_x.setPosition(float2(7600.0, -1800.0))
        # input1=position（3 通道→RGB），input2=ao（→A）
        bmps['bake_position'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_x, 'input1')
        bmps['bake_ao'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_x, 'input2')

        shuf_y = graph.newNode('sbs::compositing::shuffle')
        shuf_y.setPosition(float2(7600.0, -1200.0))
        bmps['bake_normalobj'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_y, 'input1')
        bmps['mask1'].newPropertyConnectionFromId(
            'unique_filter_output', shuf_y, 'input2')

        # 通道枚举值读回（留痕）
        ch = {}
        for node, tag in ((shuf_x, 'X'), (shuf_y, 'Y')):
            for cid in ('channelred', 'channelgreen', 'channelblue',
                        'channelalpha'):
                v = node.getInputPropertyValueFromId(cid)
                ch[f'{tag}.{cid}'] = str(v.get()) if v is not None else None
        report['channel_defaults'] = ch

        # 主 PP：2 输入（X, Y）
        main_pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        main_pp.setPosition(float2(8200.0, -1500.0))
        SDAPI.connect_pp_input(shuf_x, main_pp)
        SDAPI.connect_pp_input(shuf_y, main_pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(8800.0, -1500.0))
        main_pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                            'inputNodeOutput')

    # 函数图：sample(0)=图X sample(1)=图Y；输出 (X.r, Y.r, X.a, Y.a)
    # X.r=pos.r（对照 pos.r），Y.r=nrm.r（对照 nrm.r），X.a=ao.r，Y.a=mask.r
    fg, _ = SDAPI.get_perpixel_graph(main_pp)
    pos = SDAPI.get_pos_node(fg)
    em = Emitter(fg, cache_scope='probe_0b3')
    s0 = SDAPI.samplecol_node(fg, pos, 0)
    s1 = SDAPI.samplecol_node(fg, pos, 1)
    r0 = em.sw1(NodeRef(s0, 'f4'), 0)   # X.r = pos.r
    r1 = em.sw1(NodeRef(s1, 'f4'), 0)   # Y.r = nrm.r
    a0 = em.sw1(NodeRef(s0, 'f4'), 3)   # X.a = ao.r
    a1 = em.sw1(NodeRef(s1, 'f4'), 3)   # Y.a = mask.r
    packed = em.v4_from_f3(em.v3(r0, r1, a0), a1)
    SDAPI.fg_set_output(fg, packed.node)
    step('主 PP 函数图（2 输入采样打包）', True,
         {'mapping': 'R=pos.r G=nrm.r B=ao.r A=mask.r'})

    rb = compute_and_save(graph, main_pp,
                          os.path.join(VAL_DIR, 'probe_0b3_main.exr'))
    step('compute+save', rb['ok'], {'size': rb['size'],
                                    'err': (rb['error'] or '')[:200]})
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
