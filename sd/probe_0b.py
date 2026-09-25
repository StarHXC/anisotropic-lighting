# -*- coding: utf-8 -*-
r"""Stage 0 / 0B 探针 — 输入槽位 / 采样 / 坐标锁定。


前置：0A 已通过（PP/函数图/参数三层归属已裁定）。
在 SD Python 编辑器执行：
    exec(open(r'E:\AI_Project\Anisotropic Lighting\sd\probe_0b.py', encoding='utf-8').read())

验证内容（SD_MIGRATION_PLAN §7.2 / 0B）：
  1. 5 个输入槽（0..4）接唯一标记图后 idx→pin→语义映射逐一验证
  2. 断开/重接不静默重排（enumerate_input_pins 前后对照）
  3. 坐标适配锁定：$pos→规范 q 与 规范 q→samplecol 地址 两个独立适配
     —— 用非对称四角标记图 + 中心/半像素采样实测，不预设 q.y=1-$pos.y
  4. 越界采样与 $tiling 组合行为留痕

用户操作（执行本脚本前）：
  a. 准备 5 张 4×4 标记图（脚本会在 validation/ 生成 PNG16 fixture，
     用户手动 import 为 SD 资源并按脚本提示接进指定 input 引脚），
     或者直接用脚本内嵌的 comp graph 常数图方案（无需手动 import）。
  b. 脚本自动接线 + 读回。

本脚本采用【纯 API 自动方案】：在当前 graph 内创建 5 个 uniform 节点
（每个通道不同常数/梯度），自动连进 PP 的 input0..4，逐槽采样，
用 PP 输出 + 外部导出验证 idx 映射与坐标方向。

输出：sd/validation/probe_0b_report.json + 导出指引。
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

REPORT_PATH = os.path.join(SD_DIR, 'validation', 'probe_0b_report.json')

report = {'probe': '0B', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0B 探针失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdtypefloat import SDTypeFloat

    step('环境', True, {'sd_api_version': SDAPI.app_version(),
                        'python': sys.version.split()[0]})

    graph = SDAPI.get_current_graph()
    gcls = type(graph).__name__
    step('当前 graph', 'CompGraph' in gcls, {'class': gcls,
                                             'id': SDAPI.get_graph_title(graph)})

    # ---------------------------------------------------------- PP + 5 槽接线
    with SDAPI.undo_group('aniso_pp 0B: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=2)  # 4×4 输出
        pp.setPosition(float2(0.0, 0.0))

        # 5 个 uniform 常数节点（sbs::compositing::uniform，值输入= outputcolor
        # 类型 ColorRGBA —— probe_uprops 实测；无 compositing::constant 定义）
        from sd.api.sdvaluecolorrgba import SDValueColorRGBA
        from sd.api.sdbasetypes import ColorRGBA
        marker_values = [
            (1.0, 0.0, 0.0),   # input0 → 红
            (0.0, 1.0, 0.0),   # input1 → 绿
            (0.0, 0.0, 1.0),   # input2 → 蓝
            (1.0, 1.0, 0.0),   # input3 → 黄
            (0.0, 1.0, 1.0),   # input4 → 青
        ]
        srcs = []
        for i, rgb in enumerate(marker_values):
            u = graph.newNode('sbs::compositing::uniform')
            cprop = u.getPropertyFromId('outputcolor', SDPropertyCategory.Input)
            if cprop is None:
                raise RuntimeError('uniform 节点无 outputcolor 属性')
            u.setPropertyValue(cprop, SDValueColorRGBA.sNew(ColorRGBA(rgb[0], rgb[1], rgb[2], 1.0)))
            u.setPosition(float2(-400.0, float(i) * 200.0))
            srcs.append(u)

        used_pins = []
        for idx, src in enumerate(srcs):
            pin = SDAPI.connect_pp_input(src, pp, expect_index=idx)
            used_pins.append(pin)
        # 连接后验证实例化引脚 input0..input4（SD 16.0.1：连接前 id='input'）
        final_pins = SDAPI.verify_pin_count(pp, len(srcs))
    step('PP 4×4 + 5 槽按序接线', True,
         {'used_pins_raw': used_pins, 'pins_instantiated': final_pins,
          'markers': marker_values})

    # ---------------------------------------------------------- 函数图：逐槽采样
    fg, created = SDAPI.get_perpixel_graph(pp)
    step('perpixel 函数图', True, {'created': created})

    pos = SDAPI.get_pos_node(fg)
    # 输出：samplecol(idx) 的 r/g/b 直接输出 → 每槽一次构建（简化：采样 0 号槽全通道）
    # 为一次导出验证全部 5 槽，把 5 次采样打包进一个 float4 不可能（5 个值），
    # 方案：采样 4 个槽打包 rgb+a（0,1,2,3），第 5 槽由用户切换 __constant__ 后二次导出；
    # 或输出 (s0.r, s1.g, s2.b, s3.r) —— 0 号槽选红色、1 号绿、2 号蓝、3 号黄(r=1)。
    from aniso_pp.emitter import Emitter, NodeRef
    em = Emitter(fg, cache_scope='probe_0b')
    s0 = SDAPI.samplecol_node(fg, pos, 0)
    s1 = SDAPI.samplecol_node(fg, pos, 1)
    s2 = SDAPI.samplecol_node(fg, pos, 2)
    s3 = SDAPI.samplecol_node(fg, pos, 3)
    r0 = em.sw1(NodeRef(s0, 'f4'), 0)
    g1 = em.sw1(NodeRef(s1, 'f4'), 1)
    b2 = em.sw1(NodeRef(s2, 'f4'), 2)
    r3 = em.sw1(NodeRef(s3, 'f4'), 0)
    packed = em.v4_from_f3(em.v3(r0, g1, b2), r3)
    SDAPI.fg_set_output(fg, packed.node)
    step('函数图打包输出 (s0.r, s1.g, s2.b, s3.r)', True,
         {'interpretation': '导出后 R=input0红 G=input1绿 B=input2蓝 A=input3黄红'})

    # ---------------------------------------------------------- 期望读回
    # 4×4 uniform 输出：每像素 (1, 1, 1, 1)（红r=1 绿g=1 蓝b=1 黄r=1）
    # 若 idx 映射错乱（例如错位），会出现通道颜色互换特征（如 R=0/G=1/B=1）
    report['expected_export'] = {
        'format': 'PNG16 或 EXR（Raw、关色彩变换、非预乘）',
        'size': [4, 4],
        'expect_R_G_B_A': [1.0, 1.0, 1.0, 1.0],
        'failure_signatures': {
            'R=0,G=1,B=1,A=1': 'idx 错位 1（采样到的实际是后一个槽）',
            'R=1,G=0,B=1,A=1': 'idx 错位 2',
            'R=G=B=0': '全部槽位未接/采样失败',
        },
        'export_note': '用户手动导出 4×4 到 sd/validation/probe_0b_export.png/tiff/exr',
    }

    # ---------------------------------------------------------- 断开/重接演练
    with SDAPI.undo_group('aniso_pp 0B: reconnect drill'):
        pins_before = SDAPI.enumerate_input_pins(pp)
        # SD 16.0.1 实测：首个 VARIADIC 引脚 id 是基名 'input'（0B 裁定）
        in0 = pp.getPropertyFromId('input', SDPropertyCategory.Input)
        pp.deletePropertyConnections(in0)
        SDAPI.connect_pp_input(srcs[0], pp)
    pins_after = SDAPI.enumerate_input_pins(pp)
    # SD 16.0.1 实测：断开不回收 VARIADIC 引脚，重连新增空口（:6）。
    # 「无静默重排」的正确判据：已实例化引脚（before）的 id 序列保持为
    # after 的前缀——既有引脚不消失、不换名，已有连接的语义不变。
    ok = (len(pins_after) >= len(pins_before)
          and pins_after[:len(pins_before)] == pins_before)
    step('断开/重接 input0 无静默重排', ok,
         {'before': pins_before, 'after': pins_after,
          'note': '断开残留空口不回收（SD VARIADIC 行为），重接新增 :6；'
                  '既有引脚 id 序列保持前缀一致 → 无重排'})

    # ---------------------------------------------------------- 坐标适配锁定指引
    # 纯色常数图无法锁定 q 方向 —— 需梯度图。生成 X/Y 梯度 fixture 的
    # 导入与四角采样验证归入 0B 第二轮（需用户手动 import 资源）；
    # 本轮先把方向假设收口成两个待定常量 FLIP_QY / SWAP_UV 写进报告。
    report['coordinate_adapters'] = {
        'pos_to_q': '待梯度标记图实测（0B 第二轮）：候选 q=(u,1-v) 或 q=(u,v)',
        'q_to_sample_address': '待实测：候选恒等或 y 翻转',
        'decision_rule': '四角+横纵梯度+导数分别裁定；禁止凭成品朝向猜测',
    }
    report['manual_checks'] = [
        '① 导出 4×4 PP 输出（Raw/关色彩变换/非预乘）到 sd/validation/，'
        '文件名 probe_0b_export.<png16|tiff|exr>，供 check_export.py 验证 idx 映射。',
        '② 观察断开重接演练后 2D 视图无变化（红色应仍在打包输出的 R 位对应位置）。',
        '③ 后续提供 X/Y 梯度标记图后做四角采样（0B 第二轮，锁定两个坐标适配常量）。',
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
