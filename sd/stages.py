# -*- coding: utf-8 -*-
"""Stage 1 — aniso.frag 主链 SD 函数图发射（aniso_pp.stages）。

架构（Stage 0 裁定落地）：
- 4 张 bitmap 直连主 PP 的 4 个 VARIADIC 槽（sample(i,0) 0 基精确对应，0B6 模型）：
    input0=bake_position  input1=bake_normalobj  input2=mask1  input3=bake_ao
- $pos 恒等即 q（0B 裁定：无翻转）
- 全部标量参数以常数注入（= out/bake_report.json 冻结快照）；参数面板经 wrapper
  于后续阶段接入
- DEBUG 选择：v4 起级联移除（验收证据由 Stage 1 判定链承担）

配方逐条对应 shaders/aniso.frag:219-355 与 common.glsl，不修复任何边界行为。

v4：DEBUG 1-9 级联移除（验收证据由 Stage 1 判定链承担，成品路径数值恒等）。
v6（用户裁定，差异 #8）：
- 双面翻转：N·V<0 的 texel 法线翻向观察侧（p_two_sided，默认开）——
  背光暗区重新吃到直射光（提亮+恢复各向异性高光），正面亮区逐像素不动
- ambient 有界 AO 调制：amb = ambient_color × lerp(1, AO, p_ambient_ao)
  （默认 0.5）——恢复褶皱暗部层次但有界（不回近黑）；v5 平面化 = s=0
"""
from __future__ import annotations

import math

try:
    from .emitter import Emitter, NodeRef
    from . import api as SDAPI
except ImportError:
    # 桥以顶层脚本 exec 探针时 stages 无包上下文 —— 回退绝对导入
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp import api as SDAPI


# ---------------------------------------------------------------- 快照参数
# 来源 out/bake_report.json（accepted_unverified 快照；0D/0C 校验过的默认值）
P = {
    'light_dir': (0.4, -0.6, 0.7),
    'light_color': (1.0, 1.0, 1.0),
    'light_intensity': 1.0,
    'ambient_color': (0.06, 0.07, 0.09),
    'ambient_intensity': 1.0,
    'view_mode': 2,              # normal_proxy
    'view_direction': (0.0, 0.0, 1.0),
    'camera_position': (0.0, 0.0, 1.0),
    'aniso_axis': 0,             # u
    'aniso_angle_deg': 0.0,
    'aniso_amount': 1.0,
    'shift1': 0.0,
    'shift2': 0.35,
    'exponent1': 48.0,
    'exponent2': 8.0,
    'spec_mode': 1,              # smooth
    'spec1_color': (1.0, 1.0, 1.0),
    'spec1_intensity': 1.0,
    'spec2_color': (1.0, 1.0, 1.0),
    'spec2_intensity': 0.6,
    'spec_edge0': 0.35,
    'spec_edge1': 0.55,
    'spec_threshold': 0.5,
    'front_k': 1.0,
    'diffuse_mode': 1,           # smooth
    'diffuse_color': (1.0, 1.0, 1.0),
    'diffuse_edge0': 0.30,
    'diffuse_edge1': 0.50,
    'diffuse_threshold': 0.5,
    'ao_strength': 1.0,
    'ao_direct_light': 0.0,
    'debug_mode': 0,
    'spec_layer_index': 0,
    'texel': 1.0 / 2048.0,
}


def _norm3(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / l, v[1] / l, v[2] / l)


def build_core(fg, texel: float = P['texel'], param_resolver=None):
    """发射 aniso.frag 主链到函数图 fg。返回 (packed_output_node, meta)。

    param_resolver: None → 标量/颜色参数用常数（Stage 1 快照版）；
                    callable(pid) → NodeRef（wrapper 参数读取版，A2）。
                    f3 参数返回单个 NodeRef(f3)；标量返回 NodeRef(f1)。
    """
    em = Emitter(fg, cache_scope='stage1_core')
    meta = {'nodes': 0}

    # ---- 参数解析（常数 vs wrapper get 节点）
    def sc(pid):
        """标量参数 → f1 NodeRef。"""
        if param_resolver is not None:
            return param_resolver(pid)
        return em.c_f1(float(P[pid]))

    def v3p(pid):
        """float3 参数 → f3 NodeRef。"""
        if param_resolver is not None:
            return param_resolver(pid)
        c = P[pid]
        return em.v3(em.c_f1(c[0]), em.c_f1(c[1]), em.c_f1(c[2]))

    pos = SDAPI.get_pos_node(fg)
    q = NodeRef(pos, 'f2')  # $pos 恒等 = 规范 q（0B 裁定）

    # ---- 数据采样（0B6 模型：i 直接对应槽）
    def sample(i: int) -> NodeRef:
        s = fg.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(q, s, 'pos')
        s.setInputPropertyValueFromId(
            '__constant__',
            __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
            .SDValueInt2.sNew(
                __import__('sd.api.sdbasetypes', fromlist=['int2'])
                .int2(i, 0)))
        return NodeRef(s, 'f4')

    s_pos = sample(0)
    s_nrm = sample(1)
    s_mask = sample(2)
    s_ao = sample(3)

    # ---- 解码（aniso.frag:223-229）
    coverage = em.step(em.c_f1(0.5), em.sw1(s_mask, 0))          # step(0.5, mask.r)
    Pw = em.v3(em.sw1(s_pos, 0), em.sw1(s_pos, 1), em.sw1(s_pos, 2))

    # ---- 观察向量（v6 上移：供双面翻转的 V 参考；与下方 Vn 级联同源）
    # directional: 归一化由图内 sqrt(1/dot) 实现（render_setup 语义）——
    # 归一化 view_direction 参数（graph 内完成，不依赖 CPU）
    vd_raw = v3p('view_direction')
    vd_len = em.sqrt(em.dot3(vd_raw, vd_raw))
    vd_len_prot = em.max_f1(vd_len, em.c_f1(1e-8))  # render_setup: 拒绝 <1e-8
    Vn_dir = em.div(vd_raw, vd_len_prot)
    vp = em.safe_normalize(em.sub(v3p('camera_position'), Pw),
                           em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(1.0)),
                           1e-12)
    Vn_persp = em.swizzle3_from_f4(vp)
    # 翻转参考 V（v6）：mode2 代理 Vn=Ns 对翻转是循环引用 → 第三支用世界上向常数
    Vref = em.pick3(Vn_dir, Vn_persp,
                    em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(1.0)),
                    sc('view_mode'))
    # 翻转参考 L（v6.1 门控）：与下方 H 块同一角度公式（az/el 参数驱动）
    az_f = em.mul(sc('p_light_azimuth_deg'), em.c_f1(math.pi / 180.0))
    el_f = em.mul(sc('p_light_elevation_deg'), em.c_f1(math.pi / 180.0))
    L_ref = em.v3(em.mul(em.cos(el_f), em.cos(az_f)),
                  em.mul(em.cos(el_f), em.sin(az_f)),
                  em.sin(el_f))

    N0raw = em.sub(em.mul(em.v3(em.sw1(s_nrm, 0), em.sw1(s_nrm, 1),
                                em.sw1(s_nrm, 2)),
                          em.c_f1(2.0)), em.bc_f3(em.c_f1(1.0)))
    # planeFallback(N0raw)（common/aniso:154-160；GLSL 语义 nx²>=len2/2 → useY）
    nx = em.sw1(N0raw, 0)
    len2_n = em.dot3(N0raw, N0raw)
    use_y = em.step(em.mul(len2_n, em.c_f1(0.5)), em.mul(nx, nx))  # nx²>=len2/2
    ref = em.v3(em.sub(em.c_f1(1.0), use_y), use_y, em.c_f1(0.0))
    pf_c = em.add(em.cross3(N0raw, ref), em.v3(em.c_f1(0.0), em.c_f1(0.0),
                                               em.c_f1(1e-6)))
    pf = em.swizzle3_from_f4(em.safe_normalize(pf_c, em.v3(em.c_f1(0.0),
                                                           em.c_f1(0.0),
                                                           em.c_f1(1.0)),
                                              1e-12))
    n0N = em.safe_normalize(N0raw, pf, 1e-12)
    N0 = em.swizzle3_from_f4(n0N)
    # v6 双面翻转（用户裁定，差异 #8）：仅翻转既背向相机、又背向光源的 texel
    #（ndv<0 AND ndl<0）。v6.0 单条件 ndv<0 实测把亮区里朝下但被光照到的
    # 垂边 texel 也翻转（亮区最大变化 0.147，违反"其他位置不变"）；加 ndl<0
    # 门控后亮区（ndl>0）逐像素不动，翻转只发生在本来要提亮的暗区。
    # 翻转不改长度 → nValid（safe_normalize w 分量）与 validity 链完全不变。
    ndv_pre = em.dot3(N0, Vref)
    ndl_pre = em.dot3(N0, L_ref)
    # step(edge,x)=1 当 x>=edge → 反向用：step(ndv,0)=1 当 ndv<=0（背面）
    flip_gate = em.mul(em.step(ndv_pre, em.c_f1(0.0)),
                       em.step(ndl_pre, em.c_f1(0.0)))  # 1=翻转，0=保持
    flip_sign = em.lerp(em.c_f1(1.0), em.c_f1(-1.0), flip_gate)
    flip_mult = em.lerp(em.c_f1(1.0), flip_sign, sc('two_sided'))
    N0 = em.mulscalar(N0, flip_mult)
    nValid = em.mul(em.sw1(n0N, 3), coverage)

    # ---- 位置差分（aniso.frag:131-150；neighborValid :120-126）
    tex = em.c_f1(texel)

    def neighbor_valid(qn: NodeRef) -> NodeRef:
        qx, qy = em.sw1(qn, 0), em.sw1(qn, 1)
        low_x = em.step(em.c_f1(0.0), qx)             # step(0, q.x) → qx>=0
        low_y = em.step(em.c_f1(0.0), qy)
        one_minus_t = em.sub(em.c_f1(1.0), tex)
        high_x = em.step(qx, one_minus_t)             # step(q.x, 1-t) → qx<=1-t
        high_y = em.step(qy, one_minus_t)
        inside = em.mul(em.mul(low_x, low_y), em.mul(high_x, high_y))
        cov = em.step(em.c_f1(0.5), em.sw1(s_mask, 0))  # 采样用同 mask（见下）
        # 注意：GLSL 采样 mask 于 qNeighbor —— 需按 qn 采样 mask 槽
        s_m = fg.newNode('sbs::function::samplecol')
        SDAPI.fg_connect(qn, s_m, 'pos')
        s_m.setInputPropertyValueFromId(
            '__constant__',
            __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
            .SDValueInt2.sNew(
                __import__('sd.api.sdbasetypes', fromlist=['int2'])
                .int2(2, 0)))
        cov = em.step(em.c_f1(0.5), em.sw1(NodeRef(s_m, 'f4'), 0))
        return em.mul(inside, cov)

    def derivative_q(dir_x: float, dir_y: float) -> NodeRef:
        d_x = em.mul(em.c_f1(dir_x), tex)
        d_y = em.mul(em.c_f1(dir_y), tex)
        q_plus = em.add(q, em.v2(d_x, d_y))
        q_minus = em.sub(q, em.v2(d_x, d_y))
        Pc = Pw
        # 位置图按 qPlus/qMinus 采样（bitmap 直连槽 0）
        def sample_pos(qv: NodeRef) -> NodeRef:
            s = fg.newNode('sbs::function::samplecol')
            SDAPI.fg_connect(qv, s, 'pos')
            s.setInputPropertyValueFromId(
                '__constant__',
                __import__('sd.api.sdvalueint2', fromlist=['SDValueInt2'])
                .SDValueInt2.sNew(
                    __import__('sd.api.sdbasetypes', fromlist=['int2'])
                    .int2(0, 0)))
            return em.swizzle3_from_f4(NodeRef(s, 'f4'))
        Pp = sample_pos(q_plus)
        Pm = sample_pos(q_minus)
        v_plus = neighbor_valid(q_plus)
        v_minus = neighbor_valid(q_minus)
        d_plus = em.sub(Pp, Pc)
        d_minus = em.sub(Pc, Pm)
        denom = em.max_f1(em.add(v_plus, v_minus), em.c_f1(1.0))
        wsum = em.add(em.mulscalar(d_plus, v_plus),
                      em.mulscalar(d_minus, v_minus))
        weighted = em.div(wsum, denom)
        valid = em.step(em.c_f1(0.5), em.add(v_plus, v_minus))
        return em.v4_from_f3(em.mulscalar(weighted, valid), valid)

    dPdqx = derivative_q(1.0, 0.0)
    dPdqy = derivative_q(0.0, 1.0)
    dPdu = em.swizzle3_from_f4(dPdqx)
    dPdv = em.mulscalar(em.swizzle3_from_f4(dPdqy), em.c_f1(-1.0))

    # ---- buildBasis（aniso.frag:164-179）
    def build_basis():
        dotN0Pu = em.dot3(N0, dPdu)
        TuCand = em.sub(dPdu, em.mulscalar(N0, dotN0Pu))
        tuN = em.safe_normalize(TuCand, pf, 1e-12)
        Tuv = em.swizzle3_from_f4(tuN)
        projLen2 = em.dot3(TuCand, TuCand)
        tValid = em.mul(em.mul(em.sw1(tuN, 3),
                               em.sw1(dPdqx, 3)),
                        em.step(em.c_f1(1e-16), projLen2))
        handed = em.dot3(em.cross3(N0, Tuv), dPdv)
        handed_valid = em.mul(em.mul(em.step(em.c_f1(1e-12),
                                             em.abs_f1(handed)),
                                     em.sw1(dPdqy, 3)), tValid)
        h = em.pick_sign(handed)
        Buv = em.mulscalar(em.cross3(N0, Tuv), h)
        bValid = handed_valid
        return Tuv, tValid, Buv, bValid, h

    Tuv, tValid, Buv, bValid, handed_h = build_basis()

    # ---- Ns（DETAIL off：Ns=N0）
    Ns = N0

    # ---- Us / Vs / A / TAniso（aniso.frag:253-274）
    us_dot = em.dot3(Ns, Tuv)
    UsCand = em.sub(Tuv, em.mulscalar(Ns, us_dot))
    usN = em.safe_normalize(UsCand, Tuv, 1e-12)
    Us = em.swizzle3_from_f4(usN)
    # uValid 未进最终 validity（源语义），仅 TAniso 链内使用
    handed2 = em.dot3(em.cross3(N0, Tuv), dPdv)
    h = em.pick_sign(handed2)
    Vs = em.mulscalar(em.cross3(Ns, Us), h)
    # A = 两选一（axis∈{0,1}）
    axis_sel = em.step(em.c_f1(0.5), sc('aniso_axis'))
    A = em.lerp(Us, Vs, axis_sel)          # axis=0→Us, 1→Vs
    ang = em.mul(sc('aniso_angle_deg'), em.c_f1(math.pi / 180.0))
    ct, st = em.cos(ang), em.sin(ang)
    TAniso = em.add(em.mulscalar(A, ct), em.mulscalar(em.cross3(Ns, A), st))

    # ---- Vn（VIEW_MODE 三模式运行期级联；§7.5：宿主归一化语义必须复刻）
    # Vn_dir / Vn_persp 已上移到解码前（v6：双面翻转需要 V 参考），此处复用
    Vn = em.pick3(Vn_dir, Vn_persp, Ns, sc('view_mode'))

    # ---- H（aniso.frag:287-289；light_dir 由图内角度公式生成并归一化校验）
    az = em.mul(sc('p_light_azimuth_deg'), em.c_f1(math.pi / 180.0))
    el = em.mul(sc('p_light_elevation_deg'), em.c_f1(math.pi / 180.0))
    L = em.v3(em.mul(em.cos(el), em.cos(az)),
              em.mul(em.cos(el), em.sin(az)),
              em.sin(el))
    hN = em.safe_normalize(em.add(L, Vn),
                           em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(1.0)),
                           1e-12)
    H = em.swizzle3_from_f4(hN)
    hValid = em.sw1(hN, 3)

    # ---- specLayer ×2（aniso.frag:197-216；参数读取版）
    def spec_layer(shift_pid: str, exponent_pid: str, color_pid: str,
                   intensity_pid: str):
        tiN = em.safe_normalize(
            em.add(TAniso, em.mulscalar(Ns, sc(shift_pid))),
            TAniso, 1e-12)
        Ti = em.swizzle3_from_f4(tiN)
        c_raw = em.dot3(Ti, H)
        c = em.min_f1(em.max_f1(c_raw, em.c_f1(-1.0)), em.c_f1(1.0))
        sin_th = em.sqrt(em.max_f1(em.sub(em.c_f1(1.0), em.mul(c, c)),
                                   em.c_f1(0.0)))
        aniso = em.pow(sin_th, sc(exponent_pid))
        iso_in = em.min_f1(em.max_f1(em.dot3(Ns, H), em.c_f1(0.0)),
                           em.c_f1(1.0))
        iso = em.pow(iso_in, sc(exponent_pid))
        raw = em.lerp(iso, aniso, sc('aniso_amount'))
        shaped = em.segmented(raw, sc('spec_mode'),
                              sc('spec_edge0'), sc('spec_edge1'),
                              sc('spec_threshold'))
        col = em.mulscalar(v3p(color_pid),
                           em.mul(shaped, sc(intensity_pid)))
        return em.v4_from_f3(col, hValid)

    s1 = spec_layer('shift1', 'exponent1', 'spec1_color', 'spec1_intensity')
    s2 = spec_layer('shift2', 'exponent2', 'spec2_color', 'spec2_intensity')

    # ---- facing / specTotal（aniso.frag:300-305）
    ndl = em.dot3(Ns, L)
    facing = em.min_f1(em.max_f1(em.mul(ndl, sc('front_k')),
                                 em.c_f1(0.0)), em.c_f1(1.0))
    spec_valid = em.mul(hValid, nValid)
    spec_total = em.mulscalar(em.add(em.swizzle3_from_f4(s1),
                                     em.swizzle3_from_f4(s2)),
                              em.mul(facing, spec_valid))

    # ---- 漫反射 / AO / linear（aniso.frag:308-321）
    diff_x = em.add(em.mul(ndl, em.c_f1(0.5)), em.c_f1(0.5))
    diff = em.segmented(diff_x, sc('diffuse_mode'),
                        sc('diffuse_edge0'), sc('diffuse_edge1'),
                        sc('diffuse_threshold'))
    ao_r = em.min_f1(em.max_f1(em.sw1(s_ao, 0), em.c_f1(0.0)), em.c_f1(1.0))
    ao_factor = em.lerp(em.c_f1(1.0), ao_r, sc('ao_strength'))
    ao_direct = em.lerp(em.c_f1(1.0), ao_factor, sc('ao_direct_light'))

    # ---- ambient（v5 平面化 → v6 有界 AO 调制）----
    # v5 裁定 amb = ambient_color 精确常量（差异 #7）。用户实测（T_Render_02）
    # 反馈：暗区提亮后褶皱暗部细节消失——该区域的明暗层次恰来自 AO 调制。
    # v6 裁定（差异 #8）：amb = ambient_color × lerp(1, AO, s)，s=p_ambient_ao
    # ∈[0,1]（0=v5 平面、1=v4 全量、默认 0.5）。有界：白环境光下最暗
    # ≈ sRGB(Reinhard(0.5))≈0.61，不会回到 v4 的近黑。direct 项不动。
    amb_ao = em.lerp(em.c_f1(1.0), ao_r, sc('ambient_ao'))
    amb = em.mulscalar(v3p('ambient_color'), amb_ao)
    diff_term = em.mulscalar(v3p('diffuse_color'), diff)
    light_rgb = em.mulscalar(v3p('light_color'),
                             sc('light_intensity'))
    light_rgb = em.mulscalar(light_rgb, ao_direct)
    direct = em.mul(em.add(diff_term, spec_total), light_rgb)
    linear = em.add(amb, direct)

    # ---- validity（aniso.frag:324）
    validity = em.mul(em.mul(coverage, nValid), em.mul(tValid, bValid))
    uValid = em.mul(em.sw1(usN, 3), tValid)
    tAnisoValid = em.mul(uValid, nValid)   # aniso.frag:274

    # ---- DEBUG 级联（aniso.frag:327-354）
    # v4：仅验收工具需要 → 级联移除，输出直连 cand0（final linear + validity）。
    # debug=0 常数下级联恒选 cand0，数值恒等；DEBUG 1-9 对照证据由 Stage 1
    # 判定链（glsl_core_debug{0..9}.npy + dbg_m*.exr）永久承担。
    packed = em.v4_from_f3(linear, validity)

    meta['nodes'] = em.node_count
    meta['cache'] = dict(em._expr_cache)
    return packed, meta
