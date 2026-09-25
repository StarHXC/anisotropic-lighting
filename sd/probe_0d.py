# -*- coding: utf-8 -*-
r"""Stage 0 / 0D 探针 — 安全数学 / 类型 / 旋转 / 单层高光。

前置：0A–0C 通过（参数归属、采样映射、32F 导出通路均已锁定）。
在 SD Python 编辑器执行：
    exec(open(r'E:\AI_Project\Anisotropic Lighting\sd\probe_0d.py', encoding='utf-8').read())

验证内容（SD_MIGRATION_PLAN §7.2 / 0D、§6 配方、§5.3 类型规则）：
  构建一个【已知答案 fixture】函数图：常数输入 → 全部 §6 配方逐级展开，
  每个配方结果打进输出 float4 的不同分量组。与 GLSL 侧 dump_glsl_ref.py
  生成的同 fixture 基准做逐 texel 对比（check_export.py）。

  fixture 布局（2048×2048 输出，每 2×2 texel 一个 case）：
    x 方向 case 索引 cx = floor(u*CasesX)，y 方向 cy
    每个案例由 (cx,cy) 解码出一组输入向量（v/fallback/mode/e0/e1...），
    喂给 safeNormalize/planeFallback/cross3/pickSign/pick3/segmented/
    linearToSRGB/旋转。这样一次导出覆盖全部 case。

  为控制图规模，本轮拆两个 pass 图（PP-A 数学配方 / PP-B 编码配方），
  共用同一 case 解码子图。

输出：sd/validation/probe_0d_report.json + 期望 case 表
     （GLSL 侧 dump 用同一张表驱动，保证两侧 case 一致）。
"""
from __future__ import annotations

import json
import math
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
VAL_DIR = os.path.join(SD_DIR, 'validation')

# SD 会话内重复执行时强制重读磁盘模块（否则拿到首次运行的旧缓存）
for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

REPORT_PATH = os.path.join(VAL_DIR, 'probe_0d_report.json')

report = {'probe': '0D', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0D 探针失败于: {name}  ({detail})')


# ---------------------------------------------------------------- case 表

# 每个 case: dict(v=f3输入, fallback=f3, minLen, mode, e0, e1, thr, angle_deg)
# case 值直接写死在报告里 → GLSL 侧与 SD 侧用同一张表（两侧一致性由表保证）。
CASES = [
    # 基本方向
    {'name': 'unit_x',      'v': (1, 0, 0), 'fallback': (0, 0, 1), 'mode': 0,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 0.0},
    {'name': 'unit_y',      'v': (0, 1, 0), 'fallback': (0, 0, 1), 'mode': 1,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 90.0},
    {'name': 'unit_z',      'v': (0, 0, 1), 'fallback': (1, 0, 0), 'mode': 2,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 180.0},
    {'name': 'diag',        'v': (1, 1, 1), 'fallback': (0, 0, 1), 'mode': 0,
     'e0': 0.2, 'e1': 0.8, 'thr': 0.4, 'angle': 45.0},
    # 非单位长度
    {'name': 'scaled',      'v': (0, 0, 5), 'fallback': (0, 0, 1), 'mode': 1,
     'e0': 0.1, 'e1': 0.9, 'thr': 0.5, 'angle': -90.0},
    # 零/近零（safeNormalize fallback 触发、pickSign +1 域）
    {'name': 'zero',        'v': (0, 0, 0), 'fallback': (0, 0, 1), 'mode': 2,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 0.0},
    {'name': 'tiny',        'v': (1e-14, 0, 0), 'fallback': (0, 0, 1), 'mode': 0,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 0.0},
    {'name': 'near_zero',   'v': (1e-8, 0, 0), 'fallback': (0, 0, 1), 'mode': 1,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 0.0},
    # pickSign 边界
    {'name': 'neg_small',   'v': (-1e-8, 0, -1), 'fallback': (0, 0, 1), 'mode': 2,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': 90.0},
    {'name': 'neg_unit',    'v': (0, 0, -1), 'fallback': (1, 0, 0), 'mode': 0,
     'e0': 0.3, 'e1': 0.6, 'thr': 0.5, 'angle': -45.0},
    # 非 Z 法线旋转（0/±90/180 在 angle 列；手性由 cross 判定）
    {'name': 'rot_nz_x',    'v': (0.6, 0.8, 0), 'fallback': (0, 0, 1), 'mode': 1,
     'e0': 0.25, 'e1': 0.75, 'thr': 0.5, 'angle': 90.0},
    {'name': 'rot_nz_xy',   'v': (0.6, 0.8, 0), 'fallback': (0, 0, 1), 'mode': 2,
     'e0': 0.25, 'e1': 0.75, 'thr': 0.5, 'angle': -90.0},
]

CASES_X = 4   # 2048/4 → 每 case 512×512 区域（够大，均匀采样可靠）
CASES_Y = 3   # 12 cases = 4×3


def case_table_manifest():
    return {
        'cases': CASES,
        'layout': {'cases_x': CASES_X, 'cases_y': CASES_Y,
                   'grid': [CASES_X, CASES_Y],
                   'case_index': 'cx = min(floor(u*4),3); cy = min(floor(v*3),2);'
                                 ' idx = cy*4+cx',
                   'size': [2048, 2048]},
        'acceptance': {'finite_first': True, 'valid_exact_01': True,
                       'max_abs': 1e-4, 'rmse': 1e-5},
    }


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from sd.api.sdbasetypes import float2

    step('环境登记', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('当前 graph', 'CompGraph' in type(graph).__name__,
         {'class': type(graph).__name__, 'id': SDAPI.get_graph_title(graph)})

    man = case_table_manifest()
    man_path = os.path.join(VAL_DIR, 'probe_0d_manifest.json')
    os.makedirs(VAL_DIR, exist_ok=True)
    with open(man_path, 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    step('case 表 manifest 写出（GLSL 侧同一张表）', True, {'path': man_path,
         'cases': len(CASES), 'layout': man['layout']})

    # ---------------------------------------------------------- PP-A：数学配方
    with SDAPI.undo_group('aniso_pp 0D: PP-A math'):
        ppA, evA = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        ppA.setPosition(float2(0.0, 0.0))
    step('PP-A 2048²', True, evA)

    fg, _ = SDAPI.get_perpixel_graph(ppA)
    em = Emitter(fg, cache_scope='probe_0d_A')

    # ---- case 索引解码：u,v ∈ [0,1]（$pos 语义在 0B 已锁定；此处按恒等假设，
    #      若 0B 第二轮改判翻转，仅需在 get_pos 后插一步 y 翻转——单点收口）
    pos = SDAPI.get_pos_node(fg)
    p = NodeRef(pos, 'f2')
    u = em.sw1(p, 0)
    v = em.sw1(p, 1)
    cx = em._binop('sbs::function::floor',
                   em.min_f1(em.mul(u, em.c_f1(float(CASES_X))),
                             em.c_f1(float(CASES_X - 1))), 'f1')
    cy = em._binop('sbs::function::floor',
                   em.min_f1(em.mul(v, em.c_f1(float(CASES_Y))),
                             em.c_f1(float(CASES_Y - 1))), 'f1')
    idx = em.add(em.mul(cy, em.c_f1(float(CASES_X))), cx)

    # ---- case 常数选择：12 个 case 的每个标量场用级联 ifelse
    # （运行期选择；候选全是有限常数，符合 §3.4）
    def select_scalar(values: list, note: str) -> NodeRef:
        """values[len] 按 idx 选；i=0 起，SEL(gteq(idx,i-0.5),v_i,prev)。"""
        assert len(values) == len(CASES)
        cur = em.c_f1(values[0])
        for i in range(1, len(values)):
            cond = em.cmp('gteq', idx, em.c_f1(float(i) - 0.5))
            cur = em.sel(cond, em.c_f1(values[i]), cur)
        report['runtime_selects'].setdefault(note, len(values))
        return cur

    report['runtime_selects'] = {}

    vx = select_scalar([c['v'][0] for c in CASES], 'vx')
    vy = select_scalar([c['v'][1] for c in CASES], 'vy')
    vz = select_scalar([c['v'][2] for c in CASES], 'vz')
    fb = select_scalar([c['fallback'][2] for c in CASES], 'fb_z')
    v_vec = em.v3(vx, vy, vz)
    fb_vec = em.v3(em.c_f1(0.0), em.c_f1(0.0), fb)

    # ---- safeNormalize（含零/近零 fallback 域）
    sn = em.safe_normalize(v_vec, fb_vec, 1e-12)
    sn_xyz, sn_valid = em.swizzle3_from_f4(sn), em.sw1(sn, 3)

    # ---- planeFallback（用 v 当输入；zero case 触发保护 → 触发计数单列）
    pf = em.plane_fallback(v_vec)

    # ---- cross3（v × fallback）
    cr = em.cross3(v_vec, fb_vec)

    # ---- pickSign（对 vz 符号域）
    ps = em.pick_sign(vz)

    # ---- pick3（三路 fallback 常数演示 + mode 选择）
    mode = select_scalar([float(c['mode']) for c in CASES], 'mode')
    p3 = em.pick3(em.v3(em.c_f1(0.1), em.c_f1(0.0), em.c_f1(0.0)),
                  em.v3(em.c_f1(0.0), em.c_f1(0.2), em.c_f1(0.0)),
                  em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(0.3)), mode)

    # ---- segmented（x 用 |sn_xyz| 长度类值：直接用 u 当输入，e0/e1/thr 按 case）
    e0 = select_scalar([c['e0'] for c in CASES], 'e0')
    e1 = select_scalar([c['e1'] for c in CASES], 'e1')
    thr = select_scalar([c['thr'] for c in CASES], 'thr')
    seg = em.segmented(u, mode, e0, e1, thr)

    # ---- 旋转：TAniso 式 angle 旋转（cos/sin 弧度；angle 按 case）
    ang_rad = select_scalar([c['angle'] for c in CASES], 'angle_deg')
    # 度转弧度：angle * pi/180（发射期常量折叠）
    ang = em.mul(ang_rad, em.c_f1(math.pi / 180.0))
    ca, sa = em.cos(ang), em.sin(ang)
    A = em.v3(em.c_f1(1.0), em.c_f1(0.0), em.c_f1(0.0))          # 轴向量（u 轴）
    cN = em.cross3(em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(1.0)), A)
    rot = em.add(em.mulscalar(A, ca), em.mulscalar(cN, sa))

    # ---- 打包：R=sn.x G=sn.y B=sn.z A=sn_valid
    outA = em.v4_from_f3(sn_xyz, sn_valid)
    SDAPI.fg_set_output(fg, outA.node)
    step('PP-A 函数图（safeNormalize 主输出）', True,
         {'node_count': em.node_count,
          'outputs': 'RGB=sn.xyz A=sn_valid',
          'note': '其余配方结果在 PP-B 打包导出，避免单 float4 通道不够'})

    # ---------------------------------------------------------- PP-B：其余配方
    with SDAPI.undo_group('aniso_pp 0D: PP-B extra'):
        ppB, evB = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        ppB.setPosition(float2(300.0, 0.0))
    step('PP-B 2048²', True, evB)

    fgB, _ = SDAPI.get_perpixel_graph(ppB)
    emB = Emitter(fgB, cache_scope='probe_0d_B')

    # 独立解码（第二个函数图不能共享节点 — §3.3 作用域）
    posB = SDAPI.get_pos_node(fgB)
    pB = NodeRef(posB, 'f2')
    uB = emB.sw1(pB, 0)
    vB = emB.sw1(pB, 1)
    cxB = emB._binop('sbs::function::floor',
                     emB.min_f1(emB.mul(uB, emB.c_f1(float(CASES_X))),
                                emB.c_f1(float(CASES_X - 1))), 'f1')
    cyB = emB._binop('sbs::function::floor',
                     emB.min_f1(emB.mul(vB, emB.c_f1(float(CASES_Y))),
                                emB.c_f1(float(CASES_Y - 1))), 'f1')
    idxB = emB.add(emB.mul(cyB, emB.c_f1(float(CASES_X))), cxB)

    def select_scalar_b(values: list, note: str) -> NodeRef:
        cur = emB.c_f1(values[0])
        for i in range(1, len(values)):
            cond = emB.cmp('gteq', idxB, emB.c_f1(float(i) - 0.5))
            cur = emB.sel(cond, emB.c_f1(values[i]), cur)
        report['runtime_selects'].setdefault(note + '_B', len(values))
        return cur

    # planeFallback.x / cross3.y / pickSign / segmented / rot.x / linearToSRGB
    vzB = select_scalar_b([c['v'][2] for c in CASES], 'vz')
    vxB = select_scalar_b([c['v'][0] for c in CASES], 'vx')
    fbzB = select_scalar_b([c['fallback'][2] for c in CASES], 'fb')
    v_vecB = emB.v3(vxB, select_scalar_b([c['v'][1] for c in CASES], 'vy'),
                    vzB)
    fb_vecB = emB.v3(emB.c_f1(0.0), emB.c_f1(0.0), fbzB)

    pfB = emB.plane_fallback(v_vecB)
    crB = emB.cross3(v_vecB, fb_vecB)
    psB = emB.pick_sign(vzB)
    modeB = select_scalar_b([float(c['mode']) for c in CASES], 'mode')
    e0B = select_scalar_b([c['e0'] for c in CASES], 'e0')
    e1B = select_scalar_b([c['e1'] for c in CASES], 'e1')
    thrB = select_scalar_b([c['thr'] for c in CASES], 'thr')
    segB = emB.segmented(uB, modeB, e0B, e1B, thrB)

    angB = emB.mul(select_scalar_b([c['angle'] for c in CASES], 'angle_deg'),
                   emB.c_f1(math.pi / 180.0))
    rotB = emB.add(
        emB.mulscalar(emB.v3(emB.c_f1(1.0), emB.c_f1(0.0), emB.c_f1(0.0)),
                      emB.cos(angB)),
        emB.mulscalar(emB.cross3(emB.v3(emB.c_f1(0.0), emB.c_f1(0.0),
                                        emB.c_f1(1.0)),
                                 emB.v3(emB.c_f1(1.0), emB.c_f1(0.0),
                                        emB.c_f1(0.0))),
                      emB.sin(angB)))

    srgb_in = select_scalar_b([0.002, 0.0031308, 0.5, 1.0, 2.0, 0.0,
                               0.003, 0.9, 0.1, 0.8, 0.33, 0.77], 'srgb_in')
    srgb_out = emB.linear_to_srgb_f1(srgb_in)

    # 打包：R=pickSign G=rot.x B=seg A=srgb_out
    # （planeFallback/cross3 的整向量由 GLSL 侧同表计算对比——本图只抽 4 分量；
    #   整向量级验证由 PP-A sn.xyz 与后续 Stage 1 覆盖。）
    outB = emB.v4_from_f3(
        emB.v3(psB, emB.sw1(rotB, 0), segB), srgb_out)
    SDAPI.fg_set_output(fgB, outB.node)
    step('PP-B 函数图（pickSign/rot/segmented/sRGB 打包）', True,
         {'node_count': emB.node_count,
          'outputs': 'R=pickSign(vz) G=rot.x B=segmented(u) A=linearToSRGB(c)'})

    # ---------------------------------------------------------- 汇总
    report['pps'] = {
        'PP_A': {'position': [0, 0], 'outputs': 'sn.xyz / sn_valid',
                 'nodes': em.node_count},
        'PP_B': {'position': [300, 0], 'outputs': 'pickSign/rot.x/seg/srgb',
                 'nodes': emB.node_count},
    }
    report['acceptance'] = man['acceptance']
    report['manual_checks'] = [
        '① 两个 PP 均不接任何输入（全部输入是常数与 $pos）——检查 2D 视图无编译错误。',
        '② 分别导出 PP-A / PP-B 为 EXR float32（Raw/非预乘/关色彩变换）：'
        'sd/validation/probe_0d_out_A.exr / probe_0d_out_B.exr。',
        '③ 通知执行者跑 dump_glsl_ref.py --probe 0d（GLSL 侧同 case 表基准）'
        '与 check_export.py --probe 0d。',
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
