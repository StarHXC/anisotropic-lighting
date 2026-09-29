# -*- coding: utf-8 -*-
r"""M2 诊断 3 — 真实资产上的 frame 诊断（临时 PP 完整复刻 kernel 前半段）。

输出 R=facing G=Vg B=Vh A=lobe（2048² EXR float32）。
定位 SD 与 CPU ref 在真实资产上的分歧环节。
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

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
REPORT = {'probe': 'm2_frame', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from sd.api.sdvaluestring import SDValueString
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.params import PARAMS as OLD_PARAMS
    import struct as _struct
    import stages
    from aniso_mask_tools import kernel as kmask

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')

    # 包内 bitmap 资源
    bmps = []
    for rid in ('src_bake_position', 'src_bake_normalobj', 'src_mask1', 'src_bake_ao'):
        r = pkg.findResourceFromUrl(f'pkg:///{rid}')
        assert r is not None, rid
        bmps.append(r)

    # texel
    with open(os.path.join(SD_DIR, 'aniso_lightmap.resources', 'bake_position.png'), 'rb') as fh:
        hdr = fh.read(24)
    pw, _ph = _struct.unpack('>II', hdr[16:24])

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp.setPosition(float2(1600.0, 2400.0))
    for res in bmps:
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(1600.0, 2400.0))
        SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_frame')

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
    stages.build_core(fg, texel=1.0 / pw, param_resolver=resolver,
                      frame_out=frame)
    base = kmask.build_frame_base(em, frame)

    def getf(pid):
        gf = fg.newNode('sbs::function::get_float1')
        gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(pid))
        return NodeRef(gf, 'f1')

    theta = em.mul(getf('p_direction_deg'), em.c_f1(3.141592653589793 / 180.0))
    rot = kmask.rotate_frame(em, base, theta)
    widths = kmask.build_widths(em, getf('p_anisotropy'), getf('p_roughness'))

    N, H = base['N'], base['H']
    hn = em.clamp_f1(em.dot3(N, H), -1.0, 1.0)
    ht = em.clamp_f1(em.dot3(rot['T'], H), -1.0, 1.0)
    hb = em.clamp_f1(em.dot3(rot['B'], H), -1.0, 1.0)
    denH = em.max_f1(hn, em.c_f1(1e-4))
    qt2 = em.mul(em.div(ht, em.mul(widths['alphaT'], denH)),
                 em.div(ht, em.mul(widths['alphaT'], denH)))
    qb2 = em.mul(em.div(hb, em.mul(widths['alphaB'], denH)),
                 em.div(hb, em.mul(widths['alphaB'], denH)))
    q = em.add(qt2, qb2)
    q_cl = em.min_f1(em.max_f1(q, em.c_f1(0.0)), em.c_f1(80.0))
    lobe = em.pow(em.c_f1(2.0), em.mul(em.c_f1(-1.0), q_cl))
    front_half = em.bool_to_f1(em.cmp('gt', hn, em.c_f1(0.0)))
    facing = em.clamp_f1(em.dot3(N, frame['light']), 0.0, 1.0)

    # N 方向图（诊断: 'T0' 是否实际是 N）
    N = base['N']
    half = em.bc_f3(em.c_f1(0.5))
    n_vis = em.add(em.mulscalar(N, em.c_f1(0.5)), half)
    packed = em.v4_from_f3(n_vis, base['nN_w'])
    fg.setOutputNode(packed.node, True)

    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(2200.0, 2400.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    rb = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm2_frame.exr'))
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']
    REPORT['channels'] = 'R/G/B=N*0.5+0.5 A=nN.w'

    wrapper.deleteNode(on)
    wrapper.deleteNode(pp)


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_frame_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
