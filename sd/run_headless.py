# -*- coding: utf-8 -*-
r"""Headless SD runner —— 用 SD 命令行自动执行探针并读回结果。

用法（外部 PowerShell，由执行者/Claude 调用）：
    python "E:\AI_Project\Anisotropic Lighting\sd\run_headless.py" 0a

机制：
    SD 启动参数 --startup-script <runner> --quit：
    启动 → 执行 runner → runner exec 对应 probe → SD 自动退出。
    探针自身把每步结果写进 sd/validation/probe_0x_report.json，
    runner 退出码 = 探针是否 ok。

限制：headless 下 getUIMgr() 可能为 None / getCurrentGraph 为空，
    因此 runner 不依赖 UI：在内存中新建 package + comp graph 作为
    探针目标（这正是"明确选定的新副本"，符合红线）。
"""
from __future__ import annotations

import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SD_DIR)

PROBE = sys.argv[1] if len(sys.argv) > 1 else '0a'
MARKER = os.path.join(SD_DIR, 'validation', f'probe_{PROBE}_headless_done.json')


def main():
    import sd
    from aniso_pp import api as SDAPI

    ctx = sd.getContext()
    app = ctx.getSDApplication()
    pkg_mgr = app.getPackageMgr()

    # 新建内存 package + comp graph（不触碰用户已加载的包）
    pkg = pkg_mgr.newUserPackage()
    if pkg is None:
        raise RuntimeError('newUserPackage 返回 None')
    graph = SDAPI_SNEW(pkg)
    # graph 标识
    try:
        graph.setIdentifier(f'aniso_pp_headless_{PROBE}')
    except BaseException:
        pass

    # 把目标 graph 注入探针环境：monkeypatch get_current_graph
    SDAPI.get_current_graph = lambda: graph
    # 探针模块同样 monkeypatch（它们 from aniso_pp import api 后调用属性）
    report_path = os.path.join(SD_DIR, 'validation', f'probe_{PROBE}_report.json')

    src = open(os.path.join(SD_DIR, f'probe_{PROBE}.py'), encoding='utf-8').read()
    g = {'__name__': '__headless__', '__file__': os.path.join(SD_DIR, f'probe_{PROBE}.py')}
    try:
        exec(compile(src, f'probe_{PROBE}.py', 'exec'), g)
        ok = bool(g.get('report', {}).get('ok'))
    except BaseException as e:
        ok = False
        print('[RUNNER-FAIL]', repr(e))
        print(traceback.format_exc())

    with open(MARKER, 'w', encoding='utf-8') as f:
        json.dump({'probe': PROBE, 'ok': ok,
                   'report_path': report_path,
                   'headless': True}, f, ensure_ascii=False, indent=2)
    print(f'[RUNNER] probe {PROBE} ok={ok} → {MARKER}')


def SDAPI_SNEW(pkg):
    """SDSBSCompGraph.sNew(pkg)（sdsbscompgraph.py:46，parent=SDPackage）。"""
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    g = SDSBSCompGraph.sNew(pkg)
    if g is None:
        raise RuntimeError('SDSBSCompGraph.sNew 返回 None')
    return g


main()
