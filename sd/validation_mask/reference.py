# -*- coding: utf-8 -*-
r"""CPU 解析参考（ANISO_MASK_PLAN §3 数学规格独立实现）。

独立计算 §3.1–§3.3（不读 SD 输出当真值）；kernel 输入 fixture 与参数 →
逐 texel M 及中间量。与 aniso_mask_tools.kernel 的图内发射互为对照。
"""
from __future__ import annotations

import math

import numpy as np


def safe_normalize(v, fallback, min_len=1e-12):
    """v: (...,3) → (dir, valid)；与 emitter.safe_normalize 同语义。"""
    len2 = np.sum(v * v, axis=-1)
    eps2 = min_len * min_len
    valid = (len2 >= eps2).astype(np.float32)
    prot = np.maximum(len2, eps2)
    inv = 1.0 / np.sqrt(prot)
    cand = v * inv[..., None]
    out = np.where(valid[..., None] > 0.5, cand, fallback)
    return out, valid


def plane_fallback(n):
    len2 = np.sum(n * n, axis=-1)
    use_y = np.step = (len2 * 0.5 <= n[..., 0] * n[..., 0]).astype(np.float32)
    ref = np.stack([1.0 - use_y, use_y, np.zeros_like(use_y)], axis=-1)
    c = np.cross(n, ref) + np.array([0.0, 0.0, 1e-6], np.float32)
    out, _ = safe_normalize(c, np.array([0.0, 0.0, 1.0], np.float32), 1e-12)
    return out


def reference_mask(fx, params):
    """fx: dict(position/normalobj/mask/ao float32 [0,1] [H,W,·]，经 png16 读取)；
    params: dict(a, r, theta_deg, az_deg, el_deg)。
    返回 dict(M, lobe, hn, q, Vg, Vh, facing, front_half, N/T/B/H 有效性)。"""
    pos = fx['position'][..., :3]
    n0raw = fx['normalobj'][..., :3] * 2.0 - 1.0
    coverage = (fx['mask'][..., 0] >= 0.5).astype(np.float32)

    pf = plane_fallback(n0raw)
    n0N, n_w = safe_normalize(n0raw, pf)
    N0 = n0N

    # v6.2 双面翻转门控（与 stages.py 相同）：ndl<0 翻转（two_sided=1）
    az = math.radians(params['az_deg'])
    el = math.radians(params['el_deg'])
    L = np.array([math.cos(el) * math.cos(az),
                  math.cos(el) * math.sin(az),
                  math.sin(el)], np.float32)
    ndl_pre = np.sum(N0 * L, axis=-1)
    flip = np.where(ndl_pre <= 0.0, -1.0, 1.0).astype(np.float32)
    N0 = N0 * flip[..., None]

    # 位置差分（H, W 首行顶部；dPdu=dPdqx, dPdv=-dPdqy）
    H_, W_ = coverage.shape
    tex = 1.0 / W_

    def sample_pos(qy, qx):
        yi = np.clip(np.round(qy * H_ - 0.5).astype(int), 0, H_ - 1)
        xi = np.clip(np.round(qx * W_ - 0.5).astype(int), 0, W_ - 1)
        return pos[yi, xi]

    def neighbor_valid(qy, qx):
        inside = ((qx >= 0.0) & (qx <= 1.0 - tex) &
                  (qy >= 0.0) & (qy <= 1.0 - tex)).astype(np.float32)
        yi = np.clip(np.round(qy * H_ - 0.5).astype(int), 0, H_ - 1)
        xi = np.clip(np.round(qx * W_ - 0.5).astype(int), 0, W_ - 1)
        cov = (fx['mask'][yi, xi, 0] >= 0.5).astype(np.float32)
        return inside * cov

    yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32)
    qy = (yy + 0.5) / H_
    qx = (xx + 0.5) / W_
    P = sample_pos(qy, qx)

    def derivative(dir_y, dir_x):
        qp_y, qp_x = qy + dir_y * tex, qx + dir_x * tex
        qm_y, qm_x = qy - dir_y * tex, qx - dir_x * tex
        vp = neighbor_valid(qp_y, qp_x)
        vm = neighbor_valid(qm_y, qm_x)
        dp = sample_pos(qp_y, qp_x) - P
        dm = P - sample_pos(qm_y, qm_x)
        denom = np.maximum(vp + vm, 1.0)
        weighted = (dp * vp[..., None] + dm * vm[..., None]) / denom[..., None]
        valid = ((vp + vm) >= 0.5).astype(np.float32)
        return weighted * valid[..., None], valid

    dPdu, x_valid = derivative(0.0, 1.0)
    dPdv, y_valid = derivative(1.0, 0.0)
    dPdv = -dPdv
    y_valid_eff = y_valid  # dPdv.w = dPdqy.w（翻转在 xyz，不在 w）

    # buildBasis
    TuCand = dPdu - N0 * np.sum(N0 * dPdu, axis=-1)[..., None]
    tuN, t_w = safe_normalize(TuCand, pf)
    Tuv = tuN
    projLen2 = np.sum(TuCand * TuCand, axis=-1)
    tValid = t_w * x_valid * (projLen2 >= 1e-16).astype(np.float32)
    handed = np.sum(np.cross(N0, Tuv) * dPdv, axis=-1)
    handedValid = ((np.abs(handed) >= 1e-12).astype(np.float32)
                   * y_valid_eff * tValid)
    h_sign = np.where(np.abs(handed) >= 1e-6,
                      np.where(handed >= 0.0, 1.0, -1.0), 1.0).astype(np.float32)
    Buv = h_sign[..., None] * np.cross(N0, Tuv)
    bValid = handedValid

    # Us（frame.tangent_u 出口）
    UsCand = Tuv - N0 * np.sum(N0 * Tuv, axis=-1)[..., None]
    usN, u_w = safe_normalize(UsCand, Tuv)
    Us = usN

    # H（normal_proxy: V=Ns=N0）
    hN, h_w = safe_normalize(L + N0, np.array([0.0, 0.0, 1.0], np.float32))
    Hv = hN

    # ---------- §3.1 mask 基底 ----------
    nN, nN_w = safe_normalize(N0, np.array([0.0, 0.0, 1.0], np.float32))
    Nm = nN
    tu_proj = Us - Nm * np.sum(Nm * Us, axis=-1)[..., None]
    pfN = plane_fallback(Nm)
    tN, tN_w = safe_normalize(tu_proj, pfN)
    T0 = tN
    bN, bN_w = safe_normalize(np.cross(Nm, T0), pfN)
    B0 = bN
    hN2, _ = safe_normalize(Hv, np.array([0.0, 0.0, 1.0], np.float32))
    Hm = hN2

    geometry_validity = coverage * (
        n_w * x_valid * y_valid * tValid * bValid)  # 旧 validity 链
    # Vg = geometry_validity × nN.w × tN.w × bN.w（§3.1 mask 基底链）
    Vg = geometry_validity * nN_w * tN_w * bN_w
    Vh = h_w  # half_validity(frame) × hN2.w；hN2 输入已归一 → w 由 h_w 承载

    # ---------- §3.1 旋转 ----------
    a = min(max(params['a'], 0.0), 1.0)
    r = min(max(params['r'], 0.0), 1.0)
    theta = math.radians(params['theta_deg'])
    ct, st = math.cos(theta), math.sin(theta)
    T = ct * T0 + st * B0
    B = ct * B0 - st * T0

    # ---------- §3.2 宽度 ----------
    alpha = 0.03 + 0.47 * r * r
    k = 1.0 + 7.0 * a
    alphaT = alpha * math.sqrt(k)
    alphaB = alpha / math.sqrt(k)

    # ---------- §3.3 主瓣 ----------
    hn = np.clip(np.sum(Nm * Hm, axis=-1), -1.0, 1.0)
    ht = np.clip(np.sum(T * Hm, axis=-1), -1.0, 1.0)
    hb = np.clip(np.sum(B * Hm, axis=-1), -1.0, 1.0)
    denH = np.maximum(hn, 1e-4)
    q = (ht / (alphaT * denH)) ** 2 + (hb / (alphaB * denH)) ** 2
    lobe = np.power(2.0, -np.minimum(np.maximum(q, 0.0), 80.0))
    front_half = (hn > 0.0).astype(np.float32)
    ndl = np.sum(Nm * L, axis=-1)
    facing = np.clip(ndl, 0.0, 1.0)
    raw = lobe * front_half * facing * Vg * Vh
    M = np.clip(raw, 0.0, 1.0)
    # coverage 外（neighborValid 无关）→ 精确 0
    M = M * coverage

    return {'M': M.astype(np.float32), 'lobe': lobe.astype(np.float32),
            'hn': hn.astype(np.float32), 'q': q.astype(np.float32),
            'Vg': Vg.astype(np.float32), 'Vh': Vh.astype(np.float32),
            'facing': facing.astype(np.float32),
            'front_half': front_half.astype(np.float32),
            'N': Nm, 'T': T, 'B': B, 'H': Hm,
            'alphaT': alphaT, 'alphaB': alphaB,
            'tValid': tValid, 'bValid': bValid * 1.0, 'nValid': n_w,
            'handed': handed}
