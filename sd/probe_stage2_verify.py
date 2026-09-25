# -*- coding: utf-8 -*-
r"""Stage 2 持久化验证：unload aniso_lightmap 包 → 重新 load → 枚举参数与节点 →
在 test graph 实例化该 wrapper → compute。
输出：sd/validation/stage2_verify_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'stage2_verify_report.json')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')

report = {'probe': 'stage2_verify', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'stage2_verify 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- unload（若已加载）
    existing = pkg_mgr.getUserPackageFromFilePath(SBS_OUT)
    if existing is not None:
        pkg_mgr.unloadUserPackage(existing)
        step('unload 旧包', True)

    # ---- reload
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    step('重新加载 .sbs', pkg is not None)

    # ---- 枚举 wrapper：参数与节点
    graph = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
    step('wrapper graph 找回', graph is not None)

    params = graph.getProperties(SDPropertyCategory.Input)
    n_params = 0
    param_ids = []
    for i in range(params.getSize()):
        pid = str(params.getItem(i).getId())
        if pid.startswith('p_'):
            n_params += 1
            param_ids.append(pid)
    step('参数持久化', n_params == 41, {'count': n_params})

    nodes = graph.getNodes()
    kinds = {}
    for i in range(nodes.getSize()):
        d = str(nodes.getItem(i).getDefinition().getId())
        kinds[d] = kinds.get(d, 0) + 1
    step('节点持久化', kinds.get('sbs::compositing::pixelprocessor') == 1
         and kinds.get('sbs::compositing::bitmap') == 4,
         kinds)

    # ---- 在 test graph 实例化
    test = SDAPI.get_current_graph()
    step('test graph', 'CompGraph' in type(test).__name__)
    res = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
    inst = test.newInstanceNode(res)
    inst.setPosition(float2(5000.0, 2000.0))
    step('实例化到 test graph', inst is not None)

    # ---- compute（含 wrapper 内 4 bitmap 相对路径解析）
    exr = os.path.join(VAL_DIR, 'stage2_inst.exr')
    # 实例节点输出属性 = 第一个 Output
    rb = compute_and_save(test, inst, exr)
    step('实例 compute+save', rb['ok'],
         {'size': rb['size'], 'err': (rb['error'] or '')[:200]})

    report['param_ids'] = param_ids
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
