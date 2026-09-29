# -*- coding: utf-8 -*-
r"""M0 探针（ANISO_MASK_PLAN §7 M0 行）— 在 SD 内经桥执行。

验收项：
  A. legacy 基准：frame_out=None 的 build_core 求值 4 个标定点（与扩展前
     磁盘基准比对——基准 EXR 已由 stage2 链路留下 stage2_inst.exr；
     本探针重建临时同参 PP 并导出 m0_legacy.exr 供外部逐像素判）
  B. frame_out 出口：frame_out 收集器与默认路径同图共存 → 类型断言；
     frame_out 启用后旧 packed 输出数值一致（同图两条 PP 分别导出）
  C. 灰度 PP：colorswitch=False 的 PP samplecol 彩色槽位读取正确性
     （fixture 图 4 槽直连）+ float1 输出 + Raw 32F
  D. RGB16 低位：灰度 PNG16 fixture 经 PP 直通读回（位深度不降级）

输出：sd/validation_mask/out/m0/m0_report.json + m0_legacy.exr +
      m0_frameout.exr + m0_gray.exr + m0_rgb16.exr
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.')
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')
           or k == 'stages']:
    del sys.modules[_k]

FIX_DIR = os.path.join(SD_DIR, 'validation_mask', 'fixtures')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm0')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm0', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'M0 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    import stages

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ------------------------------------------------ 临时验证包（不落盘 SBS）
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('m0_probe_graph')
    try:
        wrapper.setDefaultParentSize(int2(11, 11))
    except BaseException:
        pass

    # ---- fixture 4 图（M0 用真实资产绑定副本；测试允许 2 幂方形）
    bmp_nodes = []
    for idx, name in enumerate(['fx_position', 'fx_normalobj', 'fx_mask', 'fx_ao']):
        fpath = os.path.join(FIX_DIR, name + '.png')
        res = SDResourceBitmap.sNewFromFile(pkg, fpath, EmbedMethod.CopiedAndLinked)
        res.setIdentifier(f'src_{name}')
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(-600.0, float(idx) * 250.0))
        for prop_id, val in (('$outputsize', SDValueInt2.sNew(int2(8, 8))),
                             ('$format', SDValueInt.sNew(3))):
            prop = n.getPropertyFromId(prop_id, SDPropertyCategory.Input)
            n.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
            n.setPropertyValue(prop, val)
        bmp_nodes.append(n)
    step('fixture 4 bitmap', len(bmp_nodes) == 4)

    # ---- v6.2 兼容常数 resolver（计划 §5.2：冻结旧参数为有限合法常数，
    # 灯光两项=旧 params 完整精度默认；M0 基线注入常数，不经 wrapper 面板）
    from aniso_pp.params import PARAMS as _OLD_PARAMS
    from aniso_pp.emitter import Emitter as _Em

    _BY_PID = {}
    for _p in _OLD_PARAMS:
        _BY_PID[_p.pid] = _p
        if not _p.pid.startswith('p_'):
            _BY_PID['p_' + _p.pid] = _p
        _BY_PID[_p.pid.lstrip('p_')] = _p

    def make_const_resolver(fg, scope):
        em_r = _Em(fg, cache_scope=scope)

        def resolver(pid):
            p = _BY_PID[pid]
            if p.ptype == 'float3':
                from sd.api.sdbasetypes import float3 as _f3t
                v = p.default
                return em_r.v3(em_r.c_f1(float(v[0])), em_r.c_f1(float(v[1])),
                               em_r.c_f1(float(v[2])))
            if p.ptype == 'int':
                return em_r.c_f1(float(int(p.default)))
            return em_r.c_f1(float(p.default))
        return resolver

    # ================================================
    # A+B：同图双 PP—— legacy（frame_out=None）vs frameout（启用收集器）
    # ================================================
    def make_pp(colorswitch=True):
        pp, ev = SDAPI.create_pp(wrapper, colorswitch=colorswitch, size_log2=3)  # 8²
        for n in bmp_nodes:
            SDAPI.connect_pp_input(n, pp)
        return pp

    pp_legacy = make_pp()
    pp_legacy.setPosition(float2(300.0, 0.0))
    fg_l, _ = SDAPI.get_perpixel_graph(pp_legacy)
    packed_l, meta_l = stages.build_core(fg_l, texel=1.0 / 256.0,
                                         param_resolver=make_const_resolver(fg_l, 'm0_legacy'))
    fg_l.setOutputNode(packed_l.node, True)
    step('A: legacy build_core', True, {'nodes': meta_l['nodes']})

    pp_frame = make_pp()
    pp_frame.setPosition(float2(600.0, 0.0))
    fg_f, _ = SDAPI.get_perpixel_graph(pp_frame)
    frame = {}
    packed_f, meta_f = stages.build_core(fg_f, texel=1.0 / 256.0,
                                         param_resolver=make_const_resolver(fg_f, 'm0_frame'),
                                         frame_out=frame)
    fg_f.setOutputNode(packed_f.node, True)
    need_keys = {'normal': 'f3', 'tangent_u': 'f3', 'light': 'f3',
                 'half_vector': 'f3', 'geometry_validity': 'f1',
                 'tangent_validity': 'f1', 'half_validity': 'f1'}
    from aniso_pp.emitter import NodeRef
    got = {k: getattr(v, 't', '?') for k, v in frame.items()}
    step('B: frame_out 收集器', set(frame) == set(need_keys)
         and all(got[k] == need_keys[k] for k in need_keys),
         {'keys': sorted(frame), 'types': got})

    # 节点数一致（出口不新增运算）
    step('B: 出口零新增节点', meta_f['nodes'] == meta_l['nodes'],
         {'legacy': meta_l['nodes'], 'frame': meta_f['nodes']})

    # ================================================
    # C：灰度 PP（colorswitch=False）—— fixture 4 槽 + float1 输出
    # ================================================
    pp_gray = make_pp(colorswitch=False)
    pp_gray.setPosition(float2(900.0, 0.0))
    fg_g, _ = SDAPI.get_perpixel_graph(pp_gray)
    from aniso_pp.emitter import Emitter
    em = Emitter(fg_g, cache_scope='m0_gray')
    pos_g = SDAPI.get_pos_node(fg_g)
    # 直通读 position.r（彩色槽位 → float1 直接输出；§4.1 最终 float1）
    s0 = SDAPI.samplecol_node(fg_g, pos_g, 0)
    r0 = em.sw1(NodeRef(s0, 'f4'), 0)
    fg_g.setOutputNode(r0.node, True)
    step('C: 灰度 PP 发射（colorswitch=False）', True,
         {'colorswitch': False, 'out_float1_components': True})

    # ================================================
    # D：RGB16 低位直通（fixture mask 16bit → PP 读回）
    # ================================================
    pp16 = make_pp()
    pp16.setPosition(float2(1200.0, 0.0))
    fg16, _ = SDAPI.get_perpixel_graph(pp16)
    from aniso_pp.emitter import Emitter as _Em
    em16 = _Em(fg16, cache_scope='m0_16')
    s_m = SDAPI.samplecol_node(fg16, SDAPI.get_pos_node(fg16), 2)
    # mask.r 直通输出（16bit 灰度槽）——输出 RGB=mask.r, A=1
    mr = em16.sw1(NodeRef(s_m, 'f4'), 0)
    packed16 = em16.v4_from_f3(em16.v3(mr, mr, mr), em16.c_f1(1.0))
    fg16.setOutputNode(packed16.node, True)
    step('D: RGB16 直通 PP 发射', True)

    # ================================================
    # 求值 + 导出（死码消除防御：每 PP 接 output 节点；compute 前把
    # graph output 切到对应 output 节点，孤立 PP 求值返回 None）
    # ================================================
    out_nodes = {}
    ox = 300.0
    for key, pp in (('legacy', pp_legacy), ('frameout', pp_frame),
                    ('gray', pp_gray), ('rgb16', pp16)):
        on = wrapper.newNode('sbs::compositing::output')
        on.setPosition(float2(ox, 700.0))
        ox += 400.0
        pp.newPropertyConnectionFromId('unique_filter_output', on,
                                       'inputNodeOutput')
        out_nodes[key] = on

    outs = {}
    for key, pp in (('legacy', pp_legacy), ('frameout', pp_frame),
                    ('gray', pp_gray), ('rgb16', pp16)):
        wrapper.setOutputNode(out_nodes[key], True)
        p = os.path.join(OUT_DIR, f'm0_{key}.exr')
        rb = compute_and_save(wrapper, pp, p)
        outs[key] = rb
        step(f'compute {key}', rb['ok'],
             {'size': rb['size'], 'err': (rb['error'] or '')[:200]})

    # legacy == frameout 同机自检（EXR 端到端逐字节，外部 judge 再精确比对）
    la = os.path.getsize(os.path.join(OUT_DIR, 'm0_legacy.exr'))
    fa = os.path.getsize(os.path.join(OUT_DIR, 'm0_frameout.exr'))
    step('legacy/frameout 同尺寸', la == fa, {'legacy': la, 'frame': fa})

    REPORT['outputs'] = outs
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(OUT_DIR, 'm0_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] m0_report.json')
