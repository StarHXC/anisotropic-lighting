# -*- coding: utf-8 -*-
"""aniso_mask kernel — §3 数学规格的函数图发射（缎面宏观椭圆主瓣）。

复用旧 core 的 frame 出口量（Ns/Us/L/H/validity），在本模块内建立
独立正交反射基底（§3.1）→ 两轴宽度（§3.2）→ 归一化椭圆主瓣与遮罩（§3.3）。
不消费旧 packed（linear RGB），不复用 KK 的 raw/shaped 结果。

所有发射均经 aniso_pp.emitter.Emitter（类型断言）；bool 不进浮点运算
（比较 → bool_to_f1 / ifelse）。
"""
from __future__ import annotations

try:
    from .emitter import Emitter, NodeRef
except ImportError:
    from aniso_pp.emitter import Emitter, NodeRef

import math

# ---------------------------------------------------------------- §3.1 基底

def build_frame_base(em: Emitter, frame: dict) -> dict:
    """由 frame 出口量建立独立正交反射基底 (N, T0, B0) 与 H。

    frame keys: normal/tangent_u/half_vector (f3), geometry_validity,
    tangent_validity, half_validity (f1)。
    返回 dict: N/T0/B0/H (f3), Vg/Vh (f1), 或在退化时各分量有效位独立。

    单位正交条件（§3.1）：
      nN = safeNormalize(frame.normal, (0,0,1))
      T0 = safeNormalize(tangent_u - N·tangent_u, planeFallback(N))
      B0 = safeNormalize(cross(N, T0), planeFallback(N))
      hN = safeNormalize(frame.half_vector, (0,0,1))
      Vg = geometry_validity * tangent_validity * nN.w * tN.w * bN.w
      Vh = half_validity * hN.w
    """
    one = em.c_f1(1.0)
    zero3 = em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(1.0))

    # nN —— Ns（旧 core 已 safeNormalize；出口再走一次规格要求的独立链，
    # 输入本就单位长度，此步不改变方向，仅按规格补全 w 有效位）
    nN = em.safe_normalize(frame['normal'], zero3, 1e-12)
    N = em.swizzle3_from_f4(nN)

    # tN —— tangent_u 去除 N 分量后 safeNormalize，fallback = planeFallback(N)
    tu = frame['tangent_u']
    tu_proj = em.sub(tu, em.mulscalar(N, em.dot3(N, tu)))
    pfN = em.plane_fallback(N)          # finitePlaneFallback(N)
    tN = em.safe_normalize(tu_proj, pfN, 1e-12)
    T0 = em.swizzle3_from_f4(tN)

    # bN —— cross(N, T0)，fallback = planeFallback(N)
    cr = em.cross3(N, T0)
    bN = em.safe_normalize(cr, pfN, 1e-12)
    B0 = em.swizzle3_from_f4(bN)

    # hN —— H（同上再归一化）
    hN = em.safe_normalize(frame['half_vector'], zero3, 1e-12)
    H = em.swizzle3_from_f4(hN)

    Vg = em.mul(em.mul(frame['geometry_validity'], frame['tangent_validity']),
                em.mul(em.sw1(nN, 3), em.mul(em.sw1(tN, 3), em.sw1(bN, 3))))
    Vh = em.mul(frame['half_validity'], em.sw1(hN, 3))

    return {'N': N, 'T0': T0, 'B0': B0, 'H': H, 'Vg': Vg, 'Vh': Vh,
            'nN_w': em.sw1(nN, 3), 'tN_w': em.sw1(tN, 3), 'bN_w': em.sw1(bN, 3),
            'hN_w': em.sw1(hN, 3)}


def rotate_frame(em: Emitter, base: dict, theta: NodeRef) -> dict:
    """§3.1 方向旋转（弧度）：两轴一起旋转。

    T  = cos·T0 + sin·B0
    B  = -sin·T0 + cos·B0
    """
    assert theta.t == 'f1'
    ct, st = em.cos(theta), em.sin(theta)
    T = em.add(em.mulscalar(base['T0'], ct), em.mulscalar(base['B0'], st))
    B = em.sub(em.mulscalar(base['B0'], ct), em.mulscalar(base['T0'], st))
    return {'T': T, 'B': B}


# ---------------------------------------------------------------- §3.2 宽度

def build_widths(em: Emitter, a: NodeRef, r: NodeRef) -> dict:
    """§3.2 两轴宽度：

    a = clamp(p_anisotropy,0,1); r = clamp(p_roughness,0,1)
    alpha  = 0.03 + 0.47*r*r
    k      = 1 + 7*a
    alphaT = alpha*sqrt(k);  alphaB = alpha/sqrt(k)
    """
    assert a.t == 'f1' and r.t == 'f1'
    a_c = em.clamp_f1(a, 0.0, 1.0)
    r_c = em.clamp_f1(r, 0.0, 1.0)
    rr = em.mul(r_c, r_c)
    alpha = em.add(em.c_f1(0.03), em.mul(em.c_f1(0.47), rr))
    k = em.add(em.c_f1(1.0), em.mul(em.c_f1(7.0), a_c))
    sqrtk = em.sqrt(k)
    alphaT = em.mul(alpha, sqrtk)
    alphaB = em.div(alpha, sqrtk)
    return {'a': a_c, 'r': r_c, 'alpha': alpha, 'k': k,
            'alphaT': alphaT, 'alphaB': alphaB}


# ---------------------------------------------------------------- §3.3 主瓣

def build_lobe(em: Emitter, frame: dict, base: dict, rot: dict,
               widths: dict) -> dict:
    """§3.3 归一化椭圆主瓣与遮罩。

    hn = clamp(dot(N,H),-1,1); ht/hb 同理（T=rot.T, B=rot.B）
    denH = max(hn, 1e-4)
    q = (ht/(alphaT*denH))^2 + (hb/(alphaB*denH))^2
    lobe = pow(2, -min(max(q,0),80))
    frontHalf = bool_to_float(hn > 0)
    facing = clamp(dot(N, light), 0, 1)
    M = clamp(lobe * frontHalf * facing * Vg * Vh, 0, 1)
    """
    N, H = base['N'], base['H']
    T, B = rot['T'], rot['B']
    alphaT, alphaB = widths['alphaT'], widths['alphaB']

    hn = em.clamp_f1(em.dot3(N, H), -1.0, 1.0)
    ht = em.clamp_f1(em.dot3(T, H), -1.0, 1.0)
    hb = em.clamp_f1(em.dot3(B, H), -1.0, 1.0)
    denH = em.max_f1(hn, em.c_f1(1e-4))

    # q = (ht/(alphaT*denH))^2 + (hb/(alphaB*denH))^2
    denT = em.mul(alphaT, denH)
    denB = em.mul(alphaB, denH)
    qt = em.div(ht, denT)
    qb = em.div(hb, denB)
    qt2 = em.mul(qt, qt)
    qb2 = em.mul(qb, qb)
    q = em.add(qt2, qb2)
    # min(max(q,0),80)：q 上限防无意义极端指数（§3.3 不是 NaN 修复）
    q_clamped = em.min_f1(em.max_f1(q, em.c_f1(0.0)), em.c_f1(80.0))
    lobe = em.pow(em.c_f1(2.0), em.mul(em.c_f1(-1.0), q_clamped))

    # frontHalf：bool 显式转 float（§3.3：不把 bool 接进浮点运算）
    front_half = em.bool_to_f1(em.cmp('gt', hn, em.c_f1(0.0)))

    # facing = clamp(dot(N, light), 0, 1)（frame.light 由 builder 注入）
    facing = em.clamp_f1(em.dot3(N, frame['light']), 0.0, 1.0)

    raw = em.mul(lobe, front_half)
    raw = em.mul(raw, facing)
    raw = em.mul(raw, base['Vg'])
    raw = em.mul(raw, base['Vh'])
    M = em.clamp_f1(raw, 0.0, 1.0)

    return {'hn': hn, 'ht': ht, 'hb': hb, 'denH': denH, 'q': q,
            'q_clamped': q_clamped, 'lobe': lobe,
            'front_half': front_half, 'facing': facing, 'M': M}


def build_mask(em: Emitter, frame: dict, a: NodeRef, r: NodeRef,
               theta_deg: NodeRef) -> dict:
    """§3 全链：基底 → 旋转 → 宽度 → 主瓣。返回含最终 M 与中间量。"""
    base = build_frame_base(em, frame)
    theta = em.mul(theta_deg, em.c_f1(math.pi / 180.0))
    rot = rotate_frame(em, base, theta)
    widths = build_widths(em, a, r)
    lobe = build_lobe(em, frame, base, rot, widths)
    out = {'base': base, 'theta': theta, 'rot': rot,
           'widths': widths, 'lobe': lobe}
    out.update(lobe)
    return out
