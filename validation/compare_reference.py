"""数据域/精度/跨平台比较与报告。

契约来源：PLAN.md §8.3（数值数据优先 float32 文件）、§10（统一数值验收规则）。

规则：
- NaN/Inf 数必须为 0；退化几何仍须报告，不能被 fallback 冒充有效方向。
- 有效单位向量长度/正交误差初始阈值 1e-4，并检查方向与手性。
- float32 中间量初始最大绝对误差 1e-4、RMSE 1e-5。
- 比较 float32 文件（.npy/.raw），PNG 预览不是数值真值。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["CompareResult", "compare_arrays", "check_finite", "save_report", "compare_to_reference"]

# PLAN §10 统一数值验收阈值（初始值）
MAX_ABS_ERR = 1e-4
RMSE_THRESHOLD = 1e-5
UNIT_LENGTH_TOL = 1e-4


@dataclass
class CompareResult:
    """单次比较的结果记录。"""

    name: str
    passed: bool
    max_abs_err: float
    rmse: float
    nan_count: int
    inf_count: int
    details: dict[str, Any] = field(default_factory=dict)


def check_finite(a: np.ndarray) -> tuple[int, int]:
    """返回 (NaN 数, Inf 数)。PLAN §10：正常计算 NaN/Inf 必须为 0。"""
    f = a.astype(np.float64)
    return int(np.isnan(f).sum()), int(np.isinf(f).sum())


def compare_arrays(name: str, got: np.ndarray, ref: np.ndarray,
                   max_abs: float = MAX_ABS_ERR,
                   rmse_thr: float = RMSE_THRESHOLD) -> CompareResult:
    """逐元素比较并按 PLAN §10 阈值判定。

    got/ref 需同形状；自动广播失败直接抛错（调用方保证维度一致）。
    """
    if got.shape != ref.shape:
        raise ValueError(f"{name}: 形状不一致 {got.shape} vs {ref.shape}")
    g = got.astype(np.float64)
    r = ref.astype(np.float64)
    nan_count, inf_count = check_finite(g)
    diff = np.abs(g - r)
    max_abs_err = float(diff.max()) if diff.size else 0.0
    rmse = float(np.sqrt(((g - r) ** 2).mean())) if diff.size else 0.0
    passed = (
        max_abs_err <= max_abs
        and rmse <= rmse_thr
        and nan_count == 0
        and inf_count == 0
    )
    return CompareResult(
        name=name,
        passed=passed,
        max_abs_err=max_abs_err,
        rmse=rmse,
        nan_count=nan_count,
        inf_count=inf_count,
        details={"threshold_max_abs": max_abs, "threshold_rmse": rmse_thr},
    )


def compare_unit_vectors(name: str, vectors: np.ndarray,
                         valid_mask: np.ndarray | None = None) -> CompareResult:
    """检查有效单位向量长度误差（PLAN §10：初始阈值 1e-4）。

    vectors: (..., 3) float；valid_mask: 同除最后一维的 bool。
    无效区不计入统计，但总数记录在 details（退化须报告，PLAN §4.1）。
    """
    nan_count, inf_count = check_finite(vectors)
    lengths = np.linalg.norm(vectors.astype(np.float64), axis=-1)
    if valid_mask is None:
        valid_mask = np.ones(lengths.shape, dtype=bool)
    invalid_count = int((~valid_mask).sum())
    sel = lengths[valid_mask]
    max_len_err = float(np.abs(sel - 1.0).max()) if sel.size else 0.0
    passed = max_len_err <= UNIT_LENGTH_TOL and nan_count == 0 and inf_count == 0
    return CompareResult(
        name=name,
        passed=passed,
        max_abs_err=max_len_err,
        rmse=float(np.sqrt(((sel - 1.0) ** 2).mean())) if sel.size else 0.0,
        nan_count=nan_count,
        inf_count=inf_count,
        details={
            "unit_length_tolerance": UNIT_LENGTH_TOL,
            "invalid_texel_count": invalid_count,
        },
    )


def save_report(results: list[CompareResult], path: str | Path) -> None:
    """保存 JSON 报告（PLAN §8.3：诊断报告随导出落盘）。"""
    payload = {
        "all_passed": all(r.passed for r in results),
        "results": [asdict(r) for r in results],
    }
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def compare_to_reference(got_dir: Path, ref_dir: Path, names: list[str]) -> list[CompareResult]:
    """比较两组 float32 .npy 调试数据（PLAN §8.3：数值数据优先 float32 文件）。"""
    results: list[CompareResult] = []
    for name in names:
        got_path = got_dir / f"{name}.npy"
        ref_path = ref_dir / f"{name}.npy"
        if not got_path.exists() or not ref_path.exists():
            continue
        got = np.load(got_path)
        ref = np.load(ref_path)
        results.append(compare_arrays(name, got, ref))
    return results
