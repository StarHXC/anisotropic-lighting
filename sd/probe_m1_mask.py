# -*- coding: utf-8 -*-
r"""M1 — 新主瓣 kernel 的 SD 求值探针（fixture 256²）。

1. 临时验证包（不落盘）：fixture 4 图直连灰度 PP（colorswitch=False, 256²）
2. build_core（frame_out 收集 + v6.2 常数 resolver，灯光=旧默认角）
3. 同 FG 构建 §3 mask kernel（a/r/theta 用 get_float1 → wrapper 参数）
4. 导出 M（float1 → EXR float32）+ 中间量 lobe/hn/q 三张诊断 EXR
5. 输出 sd/validation_mask/out/m1/m1_report.json + m1_mask.exr 等

外部 judge_m1.py 与 CPU reference 逐像素对照 + §8.2 不变量。
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
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm1')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm1_mask', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'M1 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.params import PARAMS as OLD_PARAMS
    import stages
    from aniso_mask_tools import kernel as kmask

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('m1_probe_graph')
    try:
        wrapper.setDefaultParentSize(int2(8, 8))
    except BaseException:
        pass

    # ---- 新 5 参数（与 M2 正式包一致：灯光两项也注册到 wrapper，
    # get_float1 才能解析；缺注册 → 解析 0 → L=(1,0,0)（m1_channels 定位））
    from aniso_mask_tools.schema import param_defaults
    PD = param_defaults()
    from sd.api.sdtypefloat import SDTypeFloat
    for pid in ('p_anisotropy', 'p_direction_deg', 'p_roughness',
                'p_light_azimuth_deg', 'p_light_elevation_deg'):
        prop = wrapper.newProperty(pid, SDTypeFloat.sNew(),
                                   SDPropertyCategory.Input)
        wrapper.setPropertyValue(prop, SDValueFloat.sNew(float(PD[pid])))
    step('wrapper 5 参数注册', True)

    # ---- fixture 4 bitmap（256²）
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
    step('fixture 4 bitmap 256²', len(bmp_nodes) == 4)

    # ---- 灰度 PP（colorswitch=False）
    pp, _ev = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=8)  # 256²
    pp.setPosition(float2(300.0, 0.0))
    for n in bmp_nodes:
        SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)

    # ---- v6.2 常数 resolver（灯光两项=旧默认全精度）
    BY_PID = {}
    for _p in OLD_PARAMS:
        BY_PID[_p.pid] = _p
        BY_PID[_p.pid.lstrip('p_')] = _p

    em = Emitter(fg, cache_scope='m1_core')

    def resolver(pid):
        full = pid if pid.startswith('p_') else 'p_' + pid
        if full in ('p_light_azimuth_deg', 'p_light_elevation_deg'):
            gf = fg.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full))
            return NodeRef(gf, 'f1')
        p = BY_PID.get(full)
        if p is None:
            raise RuntimeError(f'未知旧参数 pid: {full}')
        v = p.default
        if isinstance(v, tuple):
            return em.v3(em.c_f1(float(v[0])), em.c_f1(float(v[1])),
                         em.c_f1(float(v[2])))
        return em.c_f1(float(v))

    # ---- core + frame 收集
    frame = {}
    packed, meta = stages.build_core(fg, texel=1.0 / 256.0,
                                     param_resolver=resolver, frame_out=frame)
    step('core 发射（frame 收集）', len(frame) == 7, {'nodes': meta['nodes']})

    # ---- §3 mask kernel（a/r/theta ← wrapper get_float1）
    def make_getf(fg_):
        def getf(pid):
            gf = fg_.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(pid))
            return NodeRef(gf, 'f1')
        return getf

    getf = make_getf(fg)
    a = getf('p_anisotropy')
    r = getf('p_roughness')
    theta_deg = getf('p_direction_deg')
    kout = kmask.build_mask(em, frame, a, r, theta_deg)
    M = kout['M']
    fg.setOutputNode(M.node, True)
    step('mask kernel 发射', True, {'total_nodes': meta['nodes'] + em.node_count})

    # ---- 中间量诊断输出（第二 PP：复用主 PP 输出？不——死码消除与单图约束，
    # 用同 FG 的三个额外 swizzle 直接输出不可行（单输出）。改为第二/三 PP
    # 重建同链取 lobe/hn/q。M1 先只导 M + q（两个 PP）。
    pp2, _ = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=8)
    pp2.setPosition(float2(600.0, 0.0))
    for n in bmp_nodes:
        SDAPI.connect_pp_input(n, pp2)
    fg2, _ = SDAPI.get_perpixel_graph(pp2)
    em2 = Emitter(fg2, cache_scope='m1_core2')

    def resolver2(pid):
        full = pid if pid.startswith('p_') else 'p_' + pid
        if full in ('p_light_azimuth_deg', 'p_light_elevation_deg'):
            gf = fg2.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full))
            return NodeRef(gf, 'f1')
        p = BY_PID.get(full)
        v = p.default
        if isinstance(v, tuple):
            return em2.v3(em2.c_f1(float(v[0])), em2.c_f1(float(v[1])),
                          em2.c_f1(float(v[2])))
        return em2.c_f1(float(v))

    frame2 = {}
    packed2, _m2 = stages.build_core(fg2, texel=1.0 / 256.0,
                                     param_resolver=resolver2, frame_out=frame2)
    getf2 = make_getf(fg2)
    kout2 = kmask.build_mask(em2, frame2, getf2('p_anisotropy'),
                             getf2('p_roughness'), getf2('p_direction_deg'))
    fg2.setOutputNode(kout2['q'].node, True)
    step('诊断 q 链发射', True)

    # ---- 求值导出（output 节点防死码消除）
    on1 = wrapper.newNode('sbs::compositing::output')
    on1.setPosition(float2(900.0, 300.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on1, 'inputNodeOutput')
    on2 = wrapper.newNode('sbs::compositing::output')
    on2.setPosition(float2(900.0, 700.0))
    pp2.newPropertyConnectionFromId('unique_filter_output', on2, 'inputNodeOutput')

    wrapper.setOutputNode(on1, True)
    rb1 = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm1_mask.exr'))
    step('compute M', rb1['ok'], {'size': rb1['size'], 'err': (rb1['error'] or '')[:150]})
    wrapper.setOutputNode(on2, True)
    rb2 = compute_and_save(wrapper, pp2, os.path.join(OUT_DIR, 'm1_q.exr'))
    step('compute q', rb2['ok'], {'size': rb2['size'], 'err': (rb2['error'] or '')[:150]})

    REPORT['nodes'] = {'core': meta['nodes'], 'mask_extra': em.node_count}
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(OUT_DIR, 'm1_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] m1_report.json')
