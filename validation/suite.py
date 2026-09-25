#!/usr/bin/env python3
"""validation/suite.py — 步骤 2 合成数据验证套件（G1 门禁）。

契约来源：PLAN.md §10 步骤 2：
- 解析平面 z=slope·(x+y) + 常量法线，验证 N0/Tuv/Buv 的解析一致性。
- CPU 参考实现与 GPU aniso.frag 调试 pass 输出逐 texel 比较。
- 验证 Tu/Bu/N 的长度、正交性与手性；验证 q→网格 UV 的导数符号。
- 全部调试路径 NaN/Inf 必须为 0（PLAN §10 统一数值验收）。

CPU 参考的对齐要点（与 aniso.frag 逐条对应，任一侧改动需同步另一侧）：
- derivativeQ 差分不除以步长（以「1 texel」为单位）。
- 邻居有效（shader inside 是 vec2 step，作用于 qNeighbor 两个分量，texel 中心基准）：
  不变轴分量 = 中心坐标，需 ≤ 1-texel ⟺ 不变轴索引 ≤ N-2；
  移动轴分量 plus 需中心索引 ≤ N-3、minus 需中心索引 ≥ 1；
  再与邻居 coverage>=0.5 相与。禁止 np.roll（环绕语义与 clamp 不符）。
- weighted = (dPlus*vPlus + dMinus*vMinus) / max(vPlus+vMinus, 1)；
  valid = step(0.5, vPlus+vMinus)，即「至少一侧有效」。
- dPdu=dPdqx、dPdv=-dPdqy（烘焙映射 q=(u,1-v)，PLAN §3.4/§4.2.5）。
- buildBasis/safeNormalize/pickSign 的阈值常量（1e-12/1e-16/1e-6）逐一复刻。

量化噪声说明：CPU 与 GPU 读取同一份量化数据，量化误差同源抵消；
GPU(float32) 与 CPU(float64) 的残差仅为舍入级（~1e-6），
逐 texel 比较取 PLAN §10 默认阈值 1e-4/1e-5 即可，无需放宽到 1 LSB。

用法：python validation/suite.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gl.context import RenderContext  # noqa: E402
from gl.textures import upload_rgba32f  # noqa: E402
from validation.compare_reference import (  # noqa: E402
    MAX_ABS_ERR,
    RMSE_THRESHOLD,
    CompareResult,
    check_finite,
    compare_arrays,
    compare_unit_vectors,
    save_report,
)

SIZE = 64  # 小型测试图使用各自尺寸，不写死 2048（PLAN §3.4）


# ---------------------------------------------------------------------------
# 合成数据
# ---------------------------------------------------------------------------

def float_to_u16(pos01: np.ndarray) -> np.ndarray:
    """[0,1] float → uint16，四舍五入到最近样本。

    不能截断（astype 直接向下取整会引入系统性 -0.5 LSB 偏差）。
    """
    return np.clip(np.round(pos01 * 65535.0), 0, 65535).astype(np.uint16)


def make_plane_position(size: int, slope: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """解析平面 z=slope·(x+y)：世界即 UV [0,1]²，逐轴 0..1 → uint16。

    行 index 对应 y、列 index 对应 x（meshgrid 'xy'）；首行为顶部上传后
    q.y 直接落在行 index 上（PLAN §3.4 行序约定）。
    限制：uint16 编码非负且当前链路 scale=1/bias=0 → slope 必须 >= 0
    （负斜率的 z 会被 clip 成 0，夹具失真）。
    """
    xs = np.linspace(0.0, 1.0, size, dtype=np.float64)
    ys = np.linspace(0.0, 1.0, size, dtype=np.float64)
    gx, gy = np.meshgrid(xs, ys)  # indexing='xy' → 行随 gy、列随 gx
    pz = slope * (gx + gy)
    pos = np.stack([gx, gy, pz], axis=-1)
    mask = np.full((size, size), 255, dtype=np.uint8)
    return float_to_u16(pos), mask


def make_plane_normal(size: int, normal: tuple[float, float, float]) -> np.ndarray:
    """常量法线 → uint8 编码 (n*0.5+0.5)*255，np.round 量化（理由同 float_to_u16）。

    注意：量化后解码值偏离理想法线至多 0.5 LSB（如 (0,0,1) 解码为
    (0.0039, 0.0039, 1.0)）。解析一致性检查必须基于解码值而非理想值。
    """
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    enc = (n * 0.5 + 0.5) * 255.0
    img = np.clip(np.round(enc), 0, 255).astype(np.uint8)
    return np.broadcast_to(img, (size, size, 3)).copy()


# ---------------------------------------------------------------------------
# CPU 参考实现（与 aniso.frag 语义逐条对应）
# ---------------------------------------------------------------------------

def _plane_fallback_vec(n: np.ndarray) -> np.ndarray:
    """复刻 aniso.frag planeFallback：避开与 n 近平行的固定轴。"""
    len2 = np.sum(n * n, axis=-1, keepdims=True)
    use_y = (n[..., 0:1] ** 2 >= len2 * 0.5).astype(np.float64)  # step 语义
    ex = np.array([1.0, 0.0, 0.0])
    ey = np.array([0.0, 1.0, 0.0])
    ref = (1.0 - use_y) * ex + use_y * ey
    cross_nv = np.cross(n, ref) + np.array([0.0, 0.0, 1e-6])
    return cross_nv / np.linalg.norm(cross_nv, axis=-1, keepdims=True)


def _safe_normalize(v: np.ndarray, fallback: np.ndarray, min_len: float) -> tuple[np.ndarray, np.ndarray]:
    """复刻 common.glsl safeNormalize：返回（归一化向量, 有效标记）。"""
    len2 = np.sum(v * v, axis=-1, keepdims=True)
    valid = (len2 >= min_len * min_len).astype(np.float64)
    candidate = v / np.sqrt(np.maximum(len2, min_len * min_len))
    out = np.where(valid > 0.5, candidate, fallback)
    return out, valid[..., 0]


def _derivative_axis(pos01: np.ndarray, mask: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    """复刻 aniso.frag derivativeQ（无分支语义的 numpy 等价）。

    axis=1 为列方向（q.x），axis=0 为行方向（q.y）。
    shader inside 检查是 vec2 step，作用于邻居采样坐标 qNeighbor 的两个分量
    （texel 中心基准，q(i)=(i+0.5)/N，q <= 1-texel ⟺ 索引 ≤ N-2）：
    - 不变轴分量等于中心坐标 → 不变轴索引 ≤ N-2（对 plus/minus 同时生效）；
    - 移动轴分量：plus 需中心索引 ≤ N-3，minus 需中心索引 ≥ 1。
    因此最后一行/列 texel 的导数整体失效（GPU 实测与此前 64/4096 差异率吻合）。
    返回 (weighted*valid, valid)；weighted 不除以步长（1 texel 单位）。
    """
    n_along = pos01.shape[axis]
    n_cross = pos01.shape[1 - axis]
    idx = np.arange(n_along)
    moving_plus = idx + 1 <= n_along - 2
    moving_minus = idx - 1 >= 0
    cross_upper = np.arange(n_cross) <= n_cross - 2

    if axis == 1:  # q.x 差分：移动=列，不变=行
        plus_ok = cross_upper[:, None] & moving_plus[None, :]
        minus_ok = cross_upper[:, None] & moving_minus[None, :]
    else:          # q.y 差分：移动=行，不变=列
        plus_ok = moving_plus[:, None] & cross_upper[None, :]
        minus_ok = moving_minus[:, None] & cross_upper[None, :]

    # 邻居索引（越界处 clip 取自身，由有效标记屏蔽，与 shader 采样 clamp 后加权 0 等价）
    nb_plus = np.clip(idx + 1, 0, n_along - 1)
    nb_minus = np.clip(idx - 1, 0, n_along - 1)
    cov = mask >= 0.5
    cov_plus = np.take(cov, nb_plus, axis=axis)
    cov_minus = np.take(cov, nb_minus, axis=axis)
    v_plus = plus_ok & cov_plus
    v_minus = minus_ok & cov_minus

    p_center = pos01
    p_plus = np.take(pos01, nb_plus, axis=axis)
    p_minus = np.take(pos01, nb_minus, axis=axis)
    d_plus = p_plus - p_center   # 正向差分 (Pplus-P)
    d_minus = p_center - p_minus  # 反向差分 (P-Pminus)

    denom = np.maximum(v_plus.astype(np.float64) + v_minus.astype(np.float64), 1.0)
    weighted = (d_plus * v_plus[..., None] + d_minus * v_minus[..., None]) / denom[..., None]
    valid = (v_plus | v_minus).astype(np.float64)  # step(0.5, vPlus+vMinus)
    return weighted * valid[..., None], valid


def _build_basis(n0: np.ndarray, pu: np.ndarray, pv: np.ndarray,
                 pu_valid: np.ndarray, pv_valid: np.ndarray) -> tuple:
    """复刻 aniso.frag buildBasis：返回 (Tuv, tValid, Buv, bValid)。"""
    tuc = pu - n0 * np.sum(n0 * pu, axis=-1, keepdims=True)
    tuv, tu_valid = _safe_normalize(tuc, _plane_fallback_vec(n0), 1e-12)
    proj_len2 = np.sum(tuc * tuc, axis=-1)
    t_valid = tu_valid * pu_valid * (proj_len2 >= 1e-16).astype(np.float64)

    handed = np.sum(np.cross(n0, tuv) * pv, axis=-1)
    handed_valid = (np.abs(handed) >= 1e-12).astype(np.float64) * pv_valid * t_valid
    # pickSign：|x| >= 1e-6 取 sign(x)，否则 1（0 手性归 1）
    h_sign = np.where(np.abs(handed) >= 1e-6, np.sign(handed), 1.0)
    buv = h_sign[..., None] * np.cross(n0, tuv)
    return tuv, t_valid, buv, handed_valid


def cpu_reference(pos01, mask01, normal_enc01) -> dict:
    """CPU 参考实现（float64）：逐条复刻 aniso.frag 的语义。

    pos01: (H,W,3) 归一化位置（当前链路假设 scale=1/bias=0，见 aniso.frag 输入注释）
    mask01: (H,W)/(H,W,1) coverage（0..1）
    normal_enc01: (H,W,3) 法线编码值（0..1，调用方按位深归一化）

    返回 dict：n0/n_valid、dpdqx/dqx_valid、dpdqy/dqy_valid、tuv/t_valid、buv/b_valid。
    """
    pos01 = np.asarray(pos01, dtype=np.float64)
    mask = np.asarray(mask01, dtype=np.float64)
    if mask.ndim == 3:
        mask = mask[..., 0]
    enc = np.asarray(normal_enc01, dtype=np.float64)

    # --- N0：解码 + safeNormalize（common.glsl 语义）---
    n0raw = enc * 2.0 - 1.0
    n0, n0_valid = _safe_normalize(n0raw, _plane_fallback_vec(n0raw), 1e-12)
    coverage = (mask >= 0.5).astype(np.float64)
    n_valid = n0_valid * coverage

    # --- 位置差分：q.x=列方向（np axis 1）、q.y=行方向（np axis 0）---
    dpdqx, dqx_valid = _derivative_axis(pos01, mask, axis=1)
    dpdqy, dqy_valid = _derivative_axis(pos01, mask, axis=0)

    # --- q → 网格 UV 导数（烘焙映射 q=(u,1-v)：dPdu=dPdqx，dPdv=-dPdqy）---
    d_pdu = dpdqx
    d_pdv = -dpdqy

    # --- 原始 UV 基底（buildBasis 语义）---
    tuv, t_valid, buv, b_valid = _build_basis(n0, d_pdu, d_pdv, dqx_valid, dqy_valid)

    return {
        "n0": n0, "n_valid": n_valid,
        "dpdqx": dpdqx, "dqx_valid": dqx_valid,
        "dpdqy": dpdqy, "dqy_valid": dqy_valid,
        "tuv": tuv, "t_valid": t_valid,
        "buv": buv, "b_valid": b_valid,
    }


# ---------------------------------------------------------------------------
# GPU 执行
# ---------------------------------------------------------------------------

def run_gpu_case(rc: RenderContext, pos_u16: np.ndarray, mask_u8: np.ndarray,
                 normal_u8: np.ndarray, debug_mode: int) -> np.ndarray:
    """上传合成数据并执行 aniso.frag 指定 DEBUG_MODE pass，返回 (H,W,4) 首行为顶部。"""
    h, w = mask_u8.shape
    tex_pos = upload_rgba32f(rc.ctx, pos_u16, 16)
    tex_n = upload_rgba32f(rc.ctx, normal_u8, 8)
    tex_mask = upload_rgba32f(rc.ctx, mask_u8[..., None], 8)
    for tex in (tex_pos, tex_n, tex_mask):
        tex.repeat_x = tex.repeat_y = False  # Clamp（PLAN §3.4）
    try:
        fbo = rc.run_pass(
            "aniso.frag",
            w, h,
            uniforms={"u_texel": (1.0 / w, 1.0 / h)},
            textures={"u_position": tex_pos, "u_normalobj": tex_n, "u_mask": tex_mask},
            defines={"DEBUG_MODE": str(debug_mode)},
        )
        return rc.readback_top_first(fbo)
    finally:
        for tex in (tex_pos, tex_n, tex_mask):
            tex.release()


# ---------------------------------------------------------------------------
# 用例执行与比较
# ---------------------------------------------------------------------------

def _finite_result(name: str, got: np.ndarray) -> CompareResult:
    nan_count, inf_count = check_finite(got)
    return CompareResult(
        name=name, passed=(nan_count == 0 and inf_count == 0),
        max_abs_err=0.0, rmse=0.0, nan_count=nan_count, inf_count=inf_count,
        details={},
    )


def _invariant_result(name: str, value: float, tol: float,
                      details: dict | None = None) -> CompareResult:
    return CompareResult(
        name=name, passed=value <= tol,
        max_abs_err=value, rmse=0.0, nan_count=0, inf_count=0,
        details=details or {"tolerance": tol},
    )


def _run_case(rc: RenderContext, name: str, pos_u16: np.ndarray, mask_u8: np.ndarray,
              normal_u8: np.ndarray, slope: float, results: list[CompareResult]) -> None:
    """单用例：GPU 四个调试 pass vs CPU 参考 vs 解析值 + 几何不变量。"""
    print(f"-- 用例 {name} --")
    pos01 = pos_u16.astype(np.float64) / 65535.0
    normal_enc01 = normal_u8.astype(np.float64) / 255.0
    ref = cpu_reference(pos01, mask_u8.astype(np.float64) / 255.0, normal_enc01)

    got = {
        "deriv_x": run_gpu_case(rc, pos_u16, mask_u8, normal_u8, debug_mode=2),
        "deriv_y": run_gpu_case(rc, pos_u16, mask_u8, normal_u8, debug_mode=9),
        "tuv": run_gpu_case(rc, pos_u16, mask_u8, normal_u8, debug_mode=3),
        "buv": run_gpu_case(rc, pos_u16, mask_u8, normal_u8, debug_mode=4),
        "ns": run_gpu_case(rc, pos_u16, mask_u8, normal_u8, debug_mode=5),
    }

    # --- NaN/Inf（PLAN §10：正常计算必须为 0）---
    for gname, g in got.items():
        results.append(_finite_result(f"{name}/{gname}/finite", g))

    # --- 逐 texel 比较（调试输出为 rgb*0.5+0.5 编码，解码后比较；
    #     量化两侧同源抵消，残差仅为 float32/float64 舍入，用 PLAN §10 默认阈值）---

    results.append(compare_arrays(f"{name}/dpdqx", got["deriv_x"][..., :3] * 2.0 - 1.0, ref["dpdqx"]))
    results.append(compare_arrays(f"{name}/dqx_valid", got["deriv_x"][..., 3], ref["dqx_valid"]))
    results.append(compare_arrays(f"{name}/dpdqy", got["deriv_y"][..., :3] * 2.0 - 1.0, ref["dpdqy"]))
    results.append(compare_arrays(f"{name}/dqy_valid", got["deriv_y"][..., 3], ref["dqy_valid"]))
    results.append(compare_arrays(f"{name}/tuv", got["tuv"][..., :3] * 2.0 - 1.0, ref["tuv"]))
    results.append(compare_arrays(f"{name}/t_valid", got["tuv"][..., 3], ref["t_valid"]))
    results.append(compare_arrays(f"{name}/buv", got["buv"][..., :3] * 2.0 - 1.0, ref["buv"]))
    results.append(compare_arrays(f"{name}/b_valid", got["buv"][..., 3], ref["b_valid"]))
    results.append(compare_arrays(f"{name}/n0", got["ns"][..., :3] * 2.0 - 1.0, ref["n0"]))
    results.append(compare_arrays(f"{name}/n_valid", got["ns"][..., 3], ref["n_valid"]))

    # --- 解析一致性（PLAN 步骤 2）：平面逐 texel 线性 → 导数 = (系数)/(N-1)。
    #     该检查同时锁死导数符号约定：dPdqy 沿行方向 +y（行 index 增大即 y 增大），
    #     与「dPdv=-dPdqy」共同构成 q→网格 UV 的符号契约。 ---
    size = pos_u16.shape[1]
    # 列方向 gy 不变 → dPdqx.y = 0；行方向 gx 不变 → dPdqy.x = 0。
    expected_x = np.array([1.0, 0.0, slope]) / (size - 1)
    expected_y = np.array([0.0, 1.0, slope]) / (size - 1)
    for dname, expected, valid in (
        ("dpdqx", expected_x, ref["dqx_valid"]),
        ("dpdqy", expected_y, ref["dqy_valid"]),
    ):
        sel = valid > 0.5
        err = float(np.abs(ref[dname][sel] - expected).max()) if sel.any() else 0.0
        results.append(_invariant_result(
            f"{name}/analytic_{dname}", err, MAX_ABS_ERR,
            {"expected": expected.tolist(), "tolerance": MAX_ABS_ERR,
             "valid_texels": int(sel.sum())},
        ))

    # --- 几何不变量（PLAN 步骤 2：长度/正交性/手性，基于 GPU 解码值）---
    tuv_g = got["tuv"][..., :3] * 2.0 - 1.0
    buv_g = got["buv"][..., :3] * 2.0 - 1.0
    n0_g = got["ns"][..., :3] * 2.0 - 1.0
    basis_valid = ref["t_valid"] * ref["b_valid"] > 0.5
    results.append(compare_unit_vectors(f"{name}/tuv_unit", tuv_g, basis_valid))
    results.append(compare_unit_vectors(f"{name}/buv_unit", buv_g, basis_valid))
    results.append(compare_unit_vectors(f"{name}/n0_unit", n0_g, ref["n_valid"] > 0.5))

    if basis_valid.any():
        dots = {
            "t·b": np.sum(tuv_g * buv_g, axis=-1),
            "t·n": np.sum(tuv_g * n0_g, axis=-1),
            "b·n": np.sum(buv_g * n0_g, axis=-1),
        }
        for dname, dvals in dots.items():
            max_dot = float(np.abs(dvals[basis_valid]).max())
            results.append(_invariant_result(f"{name}/orthogonality_{dname}", max_dot, MAX_ABS_ERR))
        # 手性：|dot(cross(N0,Tuv), Buv)| = 1（Buv = h·cross(N0,Tuv)，h=±1）
        chirality = np.abs(np.sum(np.cross(n0_g, tuv_g) * buv_g, axis=-1))
        max_chir = float(np.abs(chirality[basis_valid] - 1.0).max())
        results.append(_invariant_result(f"{name}/handedness", max_chir, MAX_ABS_ERR))


def main() -> int:
    print("== 步骤 2：合成数据验证（G1）==")
    results: list[CompareResult] = []

    rc = RenderContext.standalone(SIZE, SIZE)
    try:
        # 用例 1：基本平面，法线 (0,0,1)
        pos, mask = make_plane_position(SIZE, slope=0.1)
        nrm = make_plane_normal(SIZE, (0.0, 0.0, 1.0))
        _run_case(rc, "plane_n001", pos, mask, nrm, 0.1, results)

        # 用例 2：倾斜法线 + 缓正斜率 + 不同尺寸（跨尺寸 texel 步长 / 法线投影非平凡；
        # 法线与平面真实几何法线刻意不一致——N0 是输入数据，基底一致性不依赖两者相符）
        size2 = 48
        pos2, mask2 = make_plane_position(size2, slope=0.05)
        nrm2 = make_plane_normal(size2, (0.3, -0.4, 0.85))
        _run_case(rc, "plane_tilted", pos2, mask2, nrm2, 0.05, results)

        # 用例 3：coverage 空洞（邻居有效性门控 / 失效传播；同时复核行序：
        # 空洞必须出现在读回数组的同一行列位置）
        pos3, mask3 = make_plane_position(SIZE, slope=0.1)
        mask3[28:36, 28:36] = 0
        nrm3 = make_plane_normal(SIZE, (0.0, 0.0, 1.0))
        _run_case(rc, "plane_hole", pos3, mask3, nrm3, 0.1, results)
    finally:
        rc.release()

    out_dir = PROJECT_ROOT / "validation" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_report(results, out_dir / "suite_report.json")

    print()
    all_passed = True
    for r in results:
        all_passed &= r.passed
        status = "ok  " if r.passed else "FAIL"
        print(f"  [{status}] {r.name}: max_abs={r.max_abs_err:.3e} rmse={r.rmse:.3e} "
              f"nan={r.nan_count} inf={r.inf_count}")
    print()
    print(f"== G1 结果：{'全部通过' if all_passed else '存在失败'} "
          f"({sum(r.passed for r in results)}/{len(results)})==")
    print(f"报告：{out_dir / 'suite_report.json'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
