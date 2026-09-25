# -*- coding: utf-8 -*-
r"""idx 映射决定性实验：5 个纯色 uniform → PP 5 连接 → 打包采样 → EXR 读回。
uniform 颜色各通道编码槽位号（槽 i 的 r=g=b=i/5），读回后按数值直接对号。
输出：sd/validation/idxmap.exr + probe_idxmap_report.json
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_idxmap_report.json')
EXR_PATH = os.path.join(VAL_DIR, 'idxmap.exr')

report = {'probe': 'idxmap', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'idxmap 失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, ColorRGBA
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA

    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__, type(graph).__name__)

    with SDAPI.undo_group('aniso_pp idxmap: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
        pp.setPosition(float2(1200.0, -400.0))
        # 5 个 uniform：槽 i 颜色 = ((i+1)/5, 0, 0, 1) —— r 值编码槽位
        srcs = []
        for i in range(5):
            u = graph.newNode('sbs::compositing::uniform')
            cprop = u.getPropertyFromId('outputcolor', SDPropertyCategory.Input)
            u.setPropertyValue(cprop, SDValueColorRGBA.sNew(
                ColorRGBA((i + 1) / 5.0, 0.0, 0.0, 1.0)))
            u.setPosition(float2(600.0, -400.0 + i * 150.0))
            srcs.append(u)
        for src in srcs:
            SDAPI.connect_pp_input(src, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(1500.0, -400.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node, 'inputNodeOutput')

    fg, _ = SDAPI.get_perpixel_graph(pp)
    pos = SDAPI.get_pos_node(fg)
    em = Emitter(fg, cache_scope='probe_idxmap')
    # 采样 idx 0..4，全部取 r，打包 rgb + a=idx4
    samples = [SDAPI.samplecol_node(fg, pos, i) for i in range(5)]
    r = [em.sw1(NodeRef(s, 'f4'), 0) for s in samples]
    packed = em.v4_from_f3(em.v3(r[0], r[1], r[2]), r[4])
    # idx3 丢失（单输出只有 4 通道）——补：B 通道放 idx2，idx3 另存报告字段？
    # 改为 2 张输出做不全；本轮先验 0..3（rgb）+ 4（a），idx3 用 g 通道? g=r[1]。
    # 更直接：rgb = idx0/idx1/idx2, a = idx4。idx3 由 EXR 第二轮（swap idx3/idx4 常量）验证。
    # 简化：直接再打包一次 (idx3, 0,0,0) 输出到另一个 PP。控制规模：本轮先做 0-2+4。
    SDAPI.fg_set_output(fg, packed.node)

    rb = compute_and_save(graph, pp, EXR_PATH)
    step('compute+save EXR', rb['ok'], {'size': rb['size'],
                                        'error': (rb['error'] or '')[:200]})

    # 第二个 PP：验证 idx3
    with SDAPI.undo_group('aniso_pp idxmap: second'):
        pp2, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
        pp2.setPosition(float2(1200.0, 400.0))
        for src in srcs:
            SDAPI.connect_pp_input(src, pp2)
        out2 = graph.newNode('sbs::compositing::output')
        out2.setPosition(float2(1500.0, 400.0))
        pp2.newPropertyConnectionFromId('unique_filter_output', out2, 'inputNodeOutput')
    fg2, _ = SDAPI.get_perpixel_graph(pp2)
    pos2 = SDAPI.get_pos_node(fg2)
    em2 = Emitter(fg2, cache_scope='probe_idxmap2')
    s3 = SDAPI.samplecol_node(fg2, pos2, 3)
    r3 = em2.sw1(NodeRef(s3, 'f4'), 0)
    packed2 = em2.v4_from_f3(em2.v3(r3, r3, r3), r3)
    SDAPI.fg_set_output(fg2, packed2.node)
    EXR2 = os.path.join(VAL_DIR, 'idxmap_idx3.exr')
    rb2 = compute_and_save(graph, pp2, EXR2)
    step('compute+save EXR (idx3)', rb2['ok'], {'size': rb2['size'],
                                                'error': (rb2['error'] or '')[:200]})

    report['expect'] = {
        'idx0_r': 0.2, 'idx1_r': 0.4, 'idx2_r': 0.6,
        'idx3_r': 0.8, 'idx4_r': 1.0,
        'note': '槽 i uniform r=(i+1)/5；读回 R=sample(0) G=sample(1) '
                'B=sample(2) A=sample(4)；idx3 见 idxmap_idx3.exr',
    }
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
