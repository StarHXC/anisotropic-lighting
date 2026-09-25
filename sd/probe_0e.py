# -*- coding: utf-8 -*-
r"""Stage 0 / 0E 探针 — DAG 可执行性 / 深度 / 扇出 / 成本实测。

前置：0A–0D 通过（发射器配方数值正确、32F 导出可用）。
在 SD Python 编辑器执行：
    exec(open(r'E:\AI_Project\Anisotropic Lighting\sd\probe_0e.py', encoding='utf-8').read())

验证内容（SD_MIGRATION_PLAN §7.2 / 0E、§3.2/§3.5）：
  1. 深度链：~40 层级联算术（模拟最坏依赖深度）
  2. 扇出：单 NodeRef 连接 ~32 个下游（模拟常量/中间量扇出）
  3. 运行期选择：pick3 全候选发射 + 未选中候选参与求值的成本
  4. 实测登记：节点数、最长深度、构建耗时、编译耗时（首次显示）、
     参数热更新耗时（改一个 comp 参数后的重新求值）

  性能数据是 0E 的核心产出——没有这些数字，不得宣称
  "2048² 正常实时负载"（审核稿 §3.2）。

输出：sd/validation/probe_0e_report.json（含耗时实测）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
VAL_DIR = os.path.join(SD_DIR, 'validation')

# SD 会话内重复执行时强制重读磁盘模块（否则拿到首次运行的旧缓存）
for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

REPORT_PATH = os.path.join(VAL_DIR, 'probe_0e_report.json')

report = {'probe': '0E', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0E 探针失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from sd.api.sdbasetypes import float2
    from sd.api.sdproperty import SDPropertyCategory

    step('环境登记', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('当前 graph', 'CompGraph' in type(graph).__name__,
         {'class': type(graph).__name__, 'id': SDAPI.get_graph_title(graph)})

    # ---------------------------------------------------------- PP-E：深度+扇出+选择
    t0 = time.perf_counter()
    with SDAPI.undo_group('aniso_pp 0E: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pp.setPosition(float2(0.0, 0.0))

        # 一个 comp 参数（热更新测量用）
        prop_t, _ = SDAPI.new_param(graph, 'p_probe_0e_scalar', 'float1', 0.5,
                                    group='00_probe', ui_min=0.0, ui_max=1.0)
    t_build_struct = time.perf_counter() - t0
    step('PP-E 创建 + 参数注册', True, {**ev, 'struct_seconds': round(t_build_struct, 4)})

    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='probe_0e')

    t1 = time.perf_counter()

    # ---- 深度链 40 层：x = ((...(c+a1)+a2)...)+a40，a_i 用 $pos.u 的微分项
    # （常数链会被引擎折叠，用 $pos 分量参与避免死码消除）
    pos = SDAPI.get_pos_node(fg)
    p = NodeRef(pos, 'f2')
    u = em.sw1(p, 0)
    x = u
    for i in range(40):
        x = em.add(x, em.mul(u, em.c_f1(0.001)))  # 每层依赖上一层
    step('深度链 40 层发射', True, {'nodes_so_far': em.node_count})

    # ---- 扇出 32：同一 x 引用 32 个下游再加权求和
    acc = em.c_f1(0.0)
    for i in range(32):
        acc = em.add(acc, em.mul(x, em.c_f1(1.0 / 32.0)))
    step('扇出 32 下游发射', True, {'nodes_so_far': em.node_count})

    # ---- 运行期选择：三候选全发射（模拟 pick3/调试级联成本）
    # 候选里故意放一个"未选中也会算"的重分支（40 层链），验证有限性而非短路
    c0 = acc
    c1 = u
    c2 = em.mul(x, x)
    mode = em.c_f1(1.0)  # 固定选 c1，但 c0/c2 仍发射
    picked = em.pick3(c0, c1, c2, mode)
    t_emit = time.perf_counter() - t1
    step('运行期选择发射（全候选）', True,
         {'total_nodes': em.node_count, 'emit_seconds': round(t_emit, 4)})

    out = em.v4_from_f3(em.bc_f3(picked), u)
    SDAPI.fg_set_output(fg, out.node)
    step('输出节点设置', True, {'outputs': 'RGB=picked A=u'})

    # ---------------------------------------------------------- 参数热更新测量
    # 改 comp graph 参数值（若函数图未引用该参数，则此步只测 set 成本；
    # 真实热更新成本 = 用户在面板拖动滑块后的重新求值，需要用户配合秒表级
    # 观测 —— 打印指引）。此处先登记 API 调用耗时。
    t2 = time.perf_counter()
    SDAPI.set_param_value(graph, prop_t, 0.75)
    t_param = time.perf_counter() - t2
    step('参数 set API 调用', True, {'seconds': round(t_param, 6),
         'note': '面板拖动→2D 视图刷新的端到端耗时由用户配合观测（见手动项）'})

    # ---------------------------------------------------------- 汇总
    report['metrics'] = {
        'total_nodes': em.node_count,
        'depth_chain_layers': 40,
        'fanout_downstreams': 32,
        'runtime_candidates': 3,
        'struct_build_seconds': round(t_build_struct, 4),
        'fg_emit_seconds': round(t_emit, 4),
        'param_set_seconds': round(t_param, 6),
        'output_size': '2048²',
    }
    report['manual_checks'] = [
        '① 首次打开 2D 视图（触发编译）：目测/秒表记录从点击到出图的时间，'
        '填入报告 compile_seconds。',
        '② 在面板拖动 p_probe_0e_scalar（虽然未参与计算）：记录视图刷新是否卡顿。',
        '③ 记录 SD 状态栏/历史窗口是否出现求值错误或 NaN 警告。',
        '④ 2048² 下缩放/平移 2D 视图，记录交互帧率主观评价（流畅/卡顿/不可用）。',
    ]
    for m in report['manual_checks']:
        print('[手动] ' + m)

    report['ok'] = True


# ---------------------------------------------------------------- 运行
try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT] ' + repr(e))
    print(traceback.format_exc())

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'[DONE] 报告已写入 {REPORT_PATH}')
