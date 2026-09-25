# -*- coding: utf-8 -*-
r"""DEBUG 全模式矩阵判定：SD 侧逐模式重建（P['debug_mode'] 覆盖 0..9）vs GLSL dump。
每模式一次 dispatch 太慢——用 10 个独立 PP 并行构建（每 PP 一个 debug_mode 常数），
一次 compute 全部读回。
输出：sd/validation/dbg_matrix_report.json + dbg_m{i}.exr
"""
import json
import math
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.') or k == 'stages']:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'dbg_matrix_report.json')

report = {'probe': 'dbg_matrix', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'dbg_matrix 失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdbasetypes import float2, int2
    import stages

    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

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
    step('bitmap 定位', len(bmps) == 4)

    order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
    pps = {}
    with SDAPI.undo_group('aniso_pp dbg_matrix: build 10 PP'):
        for dbg in range(10):
            for name in order:
                node = bmps[name]
                for prop_id, val in (('$outputsize',
                                      SDValueInt2.sNew(int2(11, 11))),
                                     ('$format', SDValueInt.sNew(3))):
                    prop = node.getPropertyFromId(prop_id,
                                                  SDPropertyCategory.Input)
                    node.setPropertyInheritanceMethod(
                        prop, SDPropertyInheritanceMethod.Absolute)
                    node.setPropertyValue(prop, val)

            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
            pp.setPosition(float2(3000.0 + (dbg % 5) * 900.0,
                                  -4000.0 + (dbg // 5) * 900.0))
            for name in order:
                SDAPI.connect_pp_input(bmps[name], pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(3600.0 + (dbg % 5) * 900.0,
                                        -4000.0 + (dbg // 5) * 900.0))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')
            stages.P['debug_mode'] = dbg
            fg, _ = SDAPI.get_perpixel_graph(pp)
            packed, meta = stages.build_core(fg)
            fg.setOutputNode(packed.node, True)
            pps[dbg] = (pp, meta['nodes'])
    step('10 模式 PP 构建', True,
         {f'debug{d}': n for d, (p, n) in pps.items()})

    readbacks = {}
    for dbg, (pp, _) in pps.items():
        exr = os.path.join(VAL_DIR, f'dbg_m{dbg}.exr')
        rb = compute_and_save(graph, pp, exr)
        readbacks[dbg] = {'ok': rb['ok'], 'exr': exr,
                          'err': (rb['error'] or '')[:150]}
        step(f'读回 debug{dbg}', rb['ok'], {'size': rb['size']})

    report['readbacks'] = readbacks
    report['ok'] = all(v['ok'] for v in readbacks.values())


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
