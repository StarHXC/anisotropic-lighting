# -*- coding: utf-8 -*-
r"""Stage 1 探针 — 主 PP 完整核心链（DEBUG 0/2/9 级联）。

用户 test graph 中已接好 4 张 bitmap（bake_position/normalobj/mask1/ao）。
本探针：创建主 PP → 4 槽按序接线 → stages.build_core 发射 → compute → EXR 读回。
外部与 GLSL dump（dump_glsl_ref.py --core）逐 texel 对比。

输出：sd/validation/stage1_report.json + stage1_core.exr
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.') or k == 'stages']:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'stage1_report.json')
EXR_PATH = os.path.join(VAL_DIR, 'stage1_core.exr')

report = {'probe': 'stage1', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'stage1 失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from sd.api.sdbasetypes import float2
    import stages

    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

    # 4 张 bitmap 定位（语义名匹配）
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
    step('4 bitmap 定位', len(bmps) == 4, sorted(bmps))

    order = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdbasetypes import int2 as _int2
    with SDAPI.undo_group('aniso_pp stage1: build'):
        # bitmap 节点显式 $outputsize=2048² + $format=32F
        # （SD 默认把 bitmap 输出缩到父图默认尺寸——Stage 1 边缘偏差根因；
        #   renderer_sbsar create_data_bitmap:187-194 同款做法）
        for name in order:
            node = bmps[name]
            for prop_id, val in (('$outputsize', SDValueInt2.sNew(_int2(11, 11))),
                                 ('$format', SDValueInt.sNew(3))):
                prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
                if prop is not None:
                    node.setPropertyInheritanceMethod(
                        prop, SDPropertyInheritanceMethod.Absolute)
                    node.setPropertyValue(prop, val)

        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pp.setPosition(float2(3000.0, -2600.0))
        for name in order:
            SDAPI.connect_pp_input(bmps[name], pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(3600.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
    step('主 PP + 4 槽接线（bitmap 2048²/32F）', True,
         {'format': ev['format'], 'size': ev['outputsize_log2']})

    fg, created = SDAPI.get_perpixel_graph(pp)
    packed, meta = stages.build_core(fg)
    SDAPI.fg_set_output(fg, packed.node)
    step('核心链发射', True, {'fg_nodes': meta['nodes']})

    rb = compute_and_save(graph, pp, EXR_PATH)
    step('compute+save', rb['ok'],
         {'size': rb['size'], 'err': (rb['error'] or '')[:200]})

    report['fg_nodes'] = meta['nodes']
    report['readback'] = {'path': EXR_PATH, 'size': rb['size']}
    report['manual_checks'] = []
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
