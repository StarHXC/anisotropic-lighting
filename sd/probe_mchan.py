# -*- coding: utf-8 -*-
r"""裁定实验：单图全通道采样。
PP 只接 mask1（idx0），输出原样 float4 → EXR。读回看 4 通道真实值。
同时接 position（idx1）输出也放进 A 通道？不行——单输出。
只测 mask1 全通道。
输出：sd/validation/mask1_channels.exr
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_mchan_report.json')
EXR_PATH = os.path.join(VAL_DIR, 'mask1_channels.exr')

report = {'probe': 'mchan', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'mchan 失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2

    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__, type(graph).__name__)

    # 找 mask1 bitmap
    mask1 = None
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            if node.getDefinition().getId() != 'sbs::compositing::bitmap':
                continue
            if '/mask1' in node.getReferencedResource().getUrl():
                mask1 = node
                break
        except BaseException:
            continue
    step('mask1 定位', mask1 is not None)

    with SDAPI.undo_group('aniso_pp mchan: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)
        pp.setPosition(float2(1200.0, 400.0))
        SDAPI.connect_pp_input(mask1, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(1500.0, 400.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node, 'inputNodeOutput')

    fg, _ = SDAPI.get_perpixel_graph(pp)
    pos = SDAPI.get_pos_node(fg)
    smp = SDAPI.samplecol_node(fg, pos, 0)   # mask1 → idx0
    SDAPI.fg_set_output(fg, smp)

    rb = compute_and_save(graph, pp, EXR_PATH)
    step('compute+save EXR', rb['ok'], {'size': rb['size'],
                                        'error': (rb['error'] or '')[:200]})
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
