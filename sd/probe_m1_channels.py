# -*- coding: utf-8 -*-
r"""M1 通道级诊断：把 mask kernel 的 ht/hb/hn/alphaT/alphaB/denH 打包进
一个 f4 输出（R=ht G=hb B=alphaT A=alphaB），第二 PP 输出 hn/q。
定位 SD 侧与 CPU ref 的 q 差异来源。256² 输出落 EXR。
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
REPORT = {'probe': 'm1_channels', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdtypefloat import SDTypeFloat
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.params import PARAMS as OLD_PARAMS
    import stages
    from aniso_mask_tools import kernel as kmask

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('m1_channels')
    try:
        wrapper.setDefaultParentSize(int2(8, 8))
    except BaseException:
        pass

    for pid, dv in (('p_anisotropy', 0.7), ('p_direction_deg', 0.0),
                    ('p_roughness', 0.5),
                    ('p_light_azimuth_deg', -56.309932474020215),
                    ('p_light_elevation_deg', 44.148948676558244)):
        prop = wrapper.newProperty(pid, SDTypeFloat.sNew(),
                                   SDPropertyCategory.Input)
        wrapper.setPropertyValue(prop, SDValueFloat.sNew(float(dv)))

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

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=8)  # 256² 彩色 PP
    pp.setPosition(float2(300.0, 0.0))
    for n in bmp_nodes:
        SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m1_ch')

    BY_PID = {}
    for _p in OLD_PARAMS:
        BY_PID[_p.pid] = _p

    def resolver(pid):
        full = pid if pid.startswith('p_') else 'p_' + pid
        if full in ('p_light_azimuth_deg', 'p_light_elevation_deg'):
            gf = fg.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full))
            return NodeRef(gf, 'f1')
        p = BY_PID.get(full)
        v = p.default
        if isinstance(v, tuple):
            return em.v3(em.c_f1(float(v[0])), em.c_f1(float(v[1])),
                         em.c_f1(float(v[2])))
        return em.c_f1(float(v))

    frame = {}
    packed, meta = stages.build_core(fg, texel=1.0 / 256.0,
                                     param_resolver=resolver, frame_out=frame)

    # 基底（重复 kernel 内部步骤以取中间量）
    base = kmask.build_frame_base(em, frame)
    theta = em.mul(NodeRef(fg.newNode('sbs::function::get_float1'), 'f1'),
                   em.c_f1(3.141592653589793 / 180.0))
    # get p_direction_deg
    gf = fg.newNode('sbs::function::get_float1')
    gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_direction_deg'))
    theta = em.mul(NodeRef(gf, 'f1'), em.c_f1(3.141592653589793 / 180.0))
    rot = kmask.rotate_frame(em, base, theta)
    gfa = fg.newNode('sbs::function::get_float1')
    gfa.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_anisotropy'))
    gfr = fg.newNode('sbs::function::get_float1')
    gfr.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_roughness'))
    widths = kmask.build_widths(em, NodeRef(gfa, 'f1'), NodeRef(gfr, 'f1'))

    N, H = base['N'], base['H']
    hn = em.clamp_f1(em.dot3(N, H), -1.0, 1.0)
    ht = em.clamp_f1(em.dot3(rot['T'], H), -1.0, 1.0)
    hb = em.clamp_f1(em.dot3(rot['B'], H), -1.0, 1.0)
    denH = em.max_f1(hn, em.c_f1(1e-4))

    # 输出1: R=ht G=hb B=alphaT A=alphaB
    o1 = em.v4_from_f3(em.v3(ht, hb, widths['alphaT']), widths['alphaB'])
    fg.setOutputNode(o1.node, True)

    # 输出2: hn/q —— 第二 PP
    pp2, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=8)
    pp2.setPosition(float2(600.0, 0.0))
    for n in bmp_nodes:
        SDAPI.connect_pp_input(n, pp2)
    fg2, _ = SDAPI.get_perpixel_graph(pp2)
    em2 = Emitter(fg2, cache_scope='m1_ch2')

    def resolver2(pid):
        full = pid if pid.startswith('p_') else 'p_' + pid
        if full in ('p_light_azimuth_deg', 'p_light_elevation_deg'):
            gf2 = fg2.newNode('sbs::function::get_float1')
            gf2.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full))
            return NodeRef(gf2, 'f1')
        p = BY_PID.get(full)
        v = p.default
        if isinstance(v, tuple):
            return em2.v3(em2.c_f1(float(v[0])), em2.c_f1(float(v[1])),
                          em2.c_f1(float(v[2])))
        return em2.c_f1(float(v))

    frame2 = {}
    stages.build_core(fg2, texel=1.0 / 256.0, param_resolver=resolver2,
                      frame_out=frame2)
    base2 = kmask.build_frame_base(em2, frame2)
    gf2 = fg2.newNode('sbs::function::get_float1')
    gf2.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_direction_deg'))
    rot2 = kmask.rotate_frame(em2, base2,
                              em2.mul(NodeRef(gf2, 'f1'), em2.c_f1(3.141592653589793 / 180.0)))
    hn2 = em2.clamp_f1(em2.dot3(base2['N'], base2['H']), -1.0, 1.0)
    denH2 = em2.max_f1(hn2, em2.c_f1(1e-4))
    ht2 = em2.clamp_f1(em2.dot3(rot2['T'], base2['H']), -1.0, 1.0)
    hb2 = em2.clamp_f1(em2.dot3(rot2['B'], base2['H']), -1.0, 1.0)
    gfa2 = fg2.newNode('sbs::function::get_float1')
    gfa2.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_anisotropy'))
    gfr2 = fg2.newNode('sbs::function::get_float1')
    gfr2.setInputPropertyValueFromId('__constant__', SDValueString.sNew('p_roughness'))
    w2 = kmask.build_widths(em2, NodeRef(gfa2, 'f1'), NodeRef(gfr2, 'f1'))
    qt2 = em2.mul(em2.div(ht2, em2.mul(w2['alphaT'], denH2)),
                  em2.div(ht2, em2.mul(w2['alphaT'], denH2)))
    qb2 = em2.mul(em2.div(hb2, em2.mul(w2['alphaB'], denH2)),
                  em2.div(hb2, em2.mul(w2['alphaB'], denH2)))
    q2 = em2.add(qt2, qb2)
    o2 = em2.v4_from_f3(em2.v3(hn2, q2, em2.c_f1(0.0)), em2.c_f1(1.0))
    fg2.setOutputNode(o2.node, True)

    on1 = wrapper.newNode('sbs::compositing::output')
    on1.setPosition(float2(900.0, 300.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on1, 'inputNodeOutput')
    on2 = wrapper.newNode('sbs::compositing::output')
    on2.setPosition(float2(900.0, 700.0))
    pp2.newPropertyConnectionFromId('unique_filter_output', on2, 'inputNodeOutput')

    wrapper.setOutputNode(on1, True)
    rb1 = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm1_ch1.exr'))
    print('[RENDER] ch1', rb1['ok'], rb1['size'])
    wrapper.setOutputNode(on2, True)
    rb2 = compute_and_save(wrapper, pp2, os.path.join(OUT_DIR, 'm1_ch2.exr'))
    print('[RENDER] ch2', rb2['ok'], rb2['size'])
    REPORT['ok'] = bool(rb1['ok'] and rb2['ok'])


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm1_channels_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
