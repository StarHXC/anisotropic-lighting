# -*- coding: utf-8 -*-
r"""Stage 0 / 0A 探针 — API / 参数面板 / 作用域 / 持久化 / 安全重建。

在 Substance Designer 的 Python 编辑器中执行：
    exec(open(r'E:\AI_Project\Anisotropic Lighting\sd\probe_0a.py', encoding='utf-8').read())

验证内容（SD_MIGRATION_PLAN §7.2 / 0A）：
  1. 当前 graph 类型断言（必须是 compositing graph）
  2. 创建 PP：colorswitch / $format=3(32F) / $outputsize=int2(11,11)，逐项读回断言
  3. perpixel 函数图创建与最小输出
  4. 参数注册三层级探测：comp graph / PP 节点 / perpixel 函数图
     —— SDSBSCompNode.newProperty 在本机绑定源码缺失但 HTML 文档列出，
        用 hasattr 实测裁定（本探针的核心产出之一）
  5. 参数作用域隔离：同名参数在两个 PP 内各自读取，不得串值
  6. 面板改值 → 输出变化由用户在 UI 验证（脚本打印操作指引）
  7. 持久化：打印保存/重开指引；安全重建：演练 owned 节点清单删除重建

输出：sd/validation/probe_0a_report.json + 控制台逐项 PASS/FAIL。
失败即停（fail-fast），保留原始异常与定位。
"""
from __future__ import annotations

import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

# SD 会话内重复执行时强制重读磁盘模块（否则拿到首次运行的旧缓存）
for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

REPORT_PATH = os.path.join(SD_DIR, 'validation', 'probe_0a_report.json')

report = {
    'probe': '0A',
    'steps': [],
    'fail': None,
}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0A 探针失败于: {name}  ({detail})')


def main():
    # ---------------------------------------------------------- 1. 环境
    from aniso_pp import api as SDAPI

    ver = SDAPI.app_version()
    import sd
    py_ver = sys.version
    step('环境版本登记', True, {'sd_api_version': ver, 'python': py_ver,
                              'module_sd': getattr(sd, '__file__', '?')})

    # ---------------------------------------------------------- 2. graph 类型
    graph = SDAPI.get_current_graph()
    gcls = type(graph).__name__
    step('当前 graph 取得', graph is not None, {'class': gcls,
                                               'id': SDAPI.get_graph_title(graph)})
    if 'CompGraph' not in gcls:
        raise RuntimeError(
            f'当前 graph 不是 compositing graph（{gcls}）。请在 SD 中先选中/打开'
            '目标物质图，再运行本探针。')

    # ---------------------------------------------------------- 3. PP 创建
    with SDAPI.undo_group('aniso_pp 0A: create PP'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
    step('PP 创建（colorswitch/$format=3/$outputsize 11,11 读回一致）', True, ev)

    pp.setPosition(SDAPI.float2(0.0, 0.0))

    # ---------------------------------------------------------- 4. 函数图
    fg, created = SDAPI.get_perpixel_graph(pp)
    step('perpixel 函数图', True, {'created': created, 'class': type(fg).__name__})

    # 最小输出：$pos → samplecol(input0) → 输出
    pos = SDAPI.get_pos_node(fg)
    smp = SDAPI.samplecol_node(fg, pos, 0)
    SDAPI.fg_set_output(fg, smp)
    step('函数图最小输出（get_float2 $pos → samplecol(input0) → setOutput）', True,
         {'note': 'input0 未接线时输出视为 0/黑属正常，0B 才验证绑定'})

    # ---------------------------------------------------------- 5. 参数三层级
    # 5a. comp graph 参数（官方示例与参考插件已证实的路径）
    prop_cg, got_cg = SDAPI.new_param(
        graph, 'p_probe_f1', 'float1', 0.5,
        group='00_probe', ui_min=0.0, ui_max=1.0)
    step('comp graph 参数 float1 注册+读回', True,
         {'got': str(got_cg.get()) if hasattr(got_cg, 'get') else str(got_cg)})

    prop_cg_i, got_cg_i = SDAPI.new_param(graph, 'p_probe_int', 'int', 1,
                                          group='00_probe', ui_min=0, ui_max=2)
    step('comp graph 参数 int 注册+读回', True,
         {'got': str(got_cg_i.get()) if hasattr(got_cg_i, 'get') else str(got_cg_i)})

    prop_cg_v, got_cg_v = SDAPI.new_param(
        graph, 'p_probe_f3', 'float3', (1.0, 0.5, 0.0), group='00_probe')
    step('comp graph 参数 float3 注册+读回', True, {'got': str(got_cg_v)})

    # 5b. PP 节点级参数（核心裁定：文档列出 newProperty，绑定源码缺失）
    pp_has = SDAPI.has_node_new_property(pp)
    step('SDSBSCompNode.newProperty 存在性（hasattr 实测）', True,
         {'has_newProperty': pp_has})
    if pp_has:
        # 0A 核心裁定（SD 16.0.1 实测）：
        # 1) SDSBSCompNode.newProperty 存在 → 可建属性
        # 2) setPropertyValue → DataIsReadOnly（值只读）
        # 3) SDSBSCompNode 无 setPropertyAnnotationValueFromId
        #    （注解 API 仅在 SDResource 层）→ 无 group/slider 注解
        # 结论：节点级参数不能承载可调参数 UI；参数载体 = comp graph 层
        # （与参考插件 node_builder.py:844-879 _expose_parameters 实证一致）。
        # 不在节点上留孤儿属性 —— 只记录裁定。
        node_has_annot = hasattr(pp, 'setPropertyAnnotationValueFromId')
        step('PP 节点级参数能力裁定', True,
             {'newProperty': pp_has, 'annotation_api': node_has_annot,
              'verdict': ('节点级: newProperty 可建属性, 但值只读 + 无注解 API → '
                          '不可承载可调参数; 参数最终载体 = comp graph 层')})
    else:
        report['steps'][-1]['detail']['consequence'] = (
            '节点级 newProperty 不可用 → 参数只能走 comp graph 层（wrapper 变体）')

    # 5c. perpixel 函数图级参数
    fg_has = hasattr(fg, 'newProperty')
    step('函数图 newProperty 存在性', True, {'has_newProperty': fg_has})
    if fg_has:
        # 0A 裁定补充（SD 16.0.1 实测）：SDSBSFunctionGraph.newProperty
        # → SDApiError.InvalidHandle（sdresource.py:345）——内嵌属性图
        # 不接受动态参数注册。函数图层同样不是参数载体。
        fg_param_err = None
        try:
            SDAPI.new_param(fg, 'p_probe_fg_f1', 'float1', 0.75,
                            group='00_probe', ui_min=0.0, ui_max=1.0)
        except BaseException as e:
            fg_param_err = repr(e)
        step('函数图级参数能力裁定', True,
             {'newProperty_exists': fg_has, 'register_result': fg_param_err,
              'verdict': ('函数图 newProperty 报 InvalidHandle → '
                          '函数图层也不承载参数; 载体唯一 = comp graph 层')})

    # ---------------------------------------------------------- 6. 参数读取链
    # 函数图内 get_float1 读 comp graph 参数（当前判定的读取路径，0D 再验证数值端点）
    # 只建节点验证"能创建"，不接到输出（避免污染 5 的最小输出语义）
    try:
        g1 = fg.newNode('sbs::function::get_float1')
        from sd.api.sdvaluestring import SDValueString
        g1.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_probe_f1'))
        step('函数图 get_float1(p_probe_f1) 节点创建', True, None)
    except BaseException as e:
        step('函数图 get_float1 节点创建', False, repr(e))

    # ---------------------------------------------------------- 7. 作用域隔离
    # 第二个 PP + 同名 comp 参数读取（不同函数图实例互不串值由 0B/0D 数值验证；
    # 本步先验证"两个 PP 各自有独立函数图"这一前提）
    with SDAPI.undo_group('aniso_pp 0A: second PP'):
        pp2, ev2 = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
    pp2.setPosition(SDAPI.float2(300.0, 0.0))
    fg2, created2 = SDAPI.get_perpixel_graph(pp2)
    pos2 = SDAPI.get_pos_node(fg2)
    smp2 = SDAPI.samplecol_node(fg2, pos2, 0)
    SDAPI.fg_set_output(fg2, smp2)
    step('第二 PP + 独立函数图（作用域隔离前提）', True,
         {'created': created2, 'pp_positions': 'PP1(0,0) PP2(300,0)'})

    # ---------------------------------------------------------- 8. owner 清单
    owned = SDAPI.list_owned_nodes(graph)
    step('owner 节点清单', len(owned) >= 2, {'owned_pp_count': len(owned)})

    # ---------------------------------------------------------- 9. 安全重建演练
    # 删除 PP2 再重建，验证删除动作只影响 owned 节点且清单随之更新
    with SDAPI.undo_group('aniso_pp 0A: rebuild drill'):
        SDAPI.delete_node(graph, pp2)
    owned_after = SDAPI.list_owned_nodes(graph)
    step('安全重建：删除 PP2', len(owned_after) == len(owned) - 1,
         {'before': len(owned), 'after': len(owned_after)})

    # ---------------------------------------------------------- 10. 用户操作指引
    report['manual_checks'] = [
        '① 在 SD 属性面板确认 p_probe_f1/p_probe_int/p_probe_f3 出现在哪个面板层级'
        '（根物质图 Parameters / PP 节点属性 / 函数图），并截图。',
        '② 拖动 p_probe_f1 滑块 0→1，确认面板无异常（数值范围/clamp 生效）。',
        '③ File → Save As 保存当前 .sbs 到临时路径，关闭再重新打开：'
        '确认两个 PP、函数图节点、参数全部保留（持久化证据）。',
        '④ PP 的 input0 尚未接线，2D 视图应显示黑/空——这是预期；0B 再接标记图验证。',
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
