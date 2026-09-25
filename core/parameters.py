"""参数校验、默认值与快照。

契约来源：PLAN.md §8.1（参数清单）、§8.2（统一参数校验器）、§8.3（快照）。

规则：
- 预览保存和无头读取必须使用同一个参数校验器；无效配置报出字段与原因，
  不静默修正为另一套参数（PLAN §8.2）。
- 所有开关、阈值和版本都进入快照，不能只保存可见滑块（PLAN §8.1）。
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import moderngl

__all__ = ["LightingParams", "validate_params", "params_to_json", "params_from_json"]


@dataclass
class LightingParams:
    """完整艺术参数集（PLAN §8.1 参数清单的落地字段）。

    数值约定：角度统一弧度；颜色为线性 RGB；方向为「从表面指向光源」。
    """

    # --- 光照（PLAN §8.1 光照）---
    light_dir: tuple[float, float, float] = (0.4, -0.6, 0.7)
    light_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    light_intensity: float = 1.0
    ambient_color: tuple[float, float, float] = (0.06, 0.07, 0.09)
    ambient_intensity: float = 1.0

    # --- 观察（PLAN §3.3/§5.1）---
    view_mode: str = "normal_proxy"  # directional / perspective / normal_proxy
    view_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    camera_position: tuple[float, float, float] = (0.0, 0.0, 1.0)

    # --- 方向场（PLAN §8.1）---
    aniso_axis: str = "u"  # 主轴 U/V
    aniso_angle: float = 0.0  # 全局角度（弧度，绕 +Ns 右手）
    # 角度图：两张未知语义 aniso 图默认关闭（PLAN §8.1 默认安全状态）。
    angle_map_mode: str = "off"  # off / anisotropic_map
    angle_map_range: float = 0.0  # 弧度
    angle_map_sign: float = 1.0

    # --- 各向异性程度（PLAN §5.2：0=各向同性对照，1=各向异性模型）---
    aniso_amount: float = 1.0

    # --- 高光（PLAN §5.2/§5.3）---
    shift1: float = 0.0
    shift2: float = 0.35
    exponent1: float = 48.0
    exponent2: float = 8.0
    spec_mode: str = "smooth"  # continuous / smooth / hard
    spec1_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    spec1_intensity: float = 1.0
    spec2_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    spec2_intensity: float = 0.6
    spec_edge0: float = 0.35
    spec_edge1: float = 0.55
    spec_threshold: float = 0.5  # hard 模式阈值
    front_k: float = 1.0  # 局部朝光抑制系数（有限正数）

    # --- 法线（PLAN §8.1）---
    detail_normal_mode: str = "off"  # off / ts_detail（ts 需基底 verified）
    detail_normal_strength: float = 0.0
    detail_normal_green_sign: int = 1

    # --- 漫反射与调制（PLAN §5.4）---
    diffuse_mode: str = "smooth"  # continuous / smooth / hard
    diffuse_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    diffuse_edge0: float = 0.30
    diffuse_edge1: float = 0.50
    diffuse_threshold: float = 0.5
    ao_strength: float = 1.0
    ao_direct_light: float = 0.0  # AO 对直接光影响，默认关闭（PLAN §5.4）

    # --- 输出（PLAN §6.2/§8.1）---
    exposure_ev: float = 0.0
    padding_width: int = 8

    # --- 调试输出选择（PLAN §8.3）---
    debug_outputs: tuple[str, ...] = (
        "coverage",
        "frame_validity",
        "tuv_buv",
        "ns",
        "taniso",
        "spec_raw",
        "ndl",
        "linear_light",
        "final",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_params(p: LightingParams) -> list[str]:
    """统一参数校验器（PLAN §8.2：无效配置报出字段与原因）。

    返回错误列表（空列表=合法）。CPU 入口拒绝 NaN/Inf、非法范围（PLAN §4.1）。
    """
    errors: list[str] = []

    def _finite(v: float, name: str) -> None:
        if v != v or v in (float("inf"), float("-inf")):
            errors.append(f"{name}: 数值必须有限，得到 {v}")

    def _vec3_finite(v: tuple[float, float, float], name: str) -> None:
        for i, c in enumerate(v):
            _finite(c, f"{name}[{i}]")

    # 光照
    _vec3_finite(p.light_dir, "light_dir")
    _vec3_finite(p.light_color, "light_color")
    _finite(p.light_intensity, "light_intensity")
    if p.light_intensity < 0:
        errors.append("light_intensity: 必须 >= 0")
    _vec3_finite(p.ambient_color, "ambient_color")
    _finite(p.ambient_intensity, "ambient_intensity")
    if p.ambient_intensity < 0:
        errors.append("ambient_intensity: 必须 >= 0")
    if max(abs(c) for c in p.light_dir) == 0:
        errors.append("light_dir: 零光向非法（PLAN §4.1）")

    # 观察
    if p.view_mode not in ("directional", "perspective", "normal_proxy"):
        errors.append(f"view_mode: 非法值 {p.view_mode!r}")
    _vec3_finite(p.view_direction, "view_direction")
    _vec3_finite(p.camera_position, "camera_position")
    if p.view_mode == "directional" and max(abs(c) for c in p.view_direction) == 0:
        errors.append("view_direction: 零向量非法")

    # 方向场
    if p.aniso_axis not in ("u", "v"):
        errors.append(f"aniso_axis: 非法值 {p.aniso_axis!r}")
    _finite(p.aniso_angle, "aniso_angle")
    if p.angle_map_mode not in ("off", "anisotropic_map"):
        errors.append(f"angle_map_mode: 非法值 {p.angle_map_mode!r}")
    _finite(p.angle_map_range, "angle_map_range")
    if p.angle_map_range < 0 or p.angle_map_range > 3.14159265:
        errors.append("angle_map_range: 应在 [0, pi] 内")
    if p.angle_map_mode != "off" and p.angle_map_range == 0:
        errors.append("angle_map_range: 启用角度图时必须 > 0")

    # 各向异性程度
    _finite(p.aniso_amount, "aniso_amount")
    if not 0.0 <= p.aniso_amount <= 1.0:
        errors.append("aniso_amount: 应在 [0,1]（PLAN §5.2）")

    # 高光
    for name in ("shift1", "shift2"):
        v = getattr(p, name)
        _finite(v, name)
        if abs(v) > 4:
            errors.append(f"{name}: 超出受控范围 ±4（PLAN §5.2 shift 有限受控）")
    for name in ("exponent1", "exponent2"):
        v = getattr(p, name)
        _finite(v, name)
        if not 1.0 <= v <= 256.0:
            errors.append(f"{name}: 初版范围 1–256（PLAN §5.2 避免 pow(0,0)）")
    if p.spec_mode not in ("continuous", "smooth", "hard"):
        errors.append(f"spec_mode: 非法值 {p.spec_mode!r}")
    if p.spec_mode == "smooth":
        if not (0.0 <= p.spec_edge0 < p.spec_edge1 <= 1.0):
            errors.append(
                "spec_edge0/edge1: 需满足 0 <= edge0 < edge1 <= 1（PLAN §5.3）"
            )
    if p.spec_mode == "hard" and not 0.0 <= p.spec_threshold <= 1.0:
        errors.append("spec_threshold: 应在 [0,1]")
    _vec3_finite(p.spec1_color, "spec1_color")
    _finite(p.spec1_intensity, "spec1_intensity")
    _vec3_finite(p.spec2_color, "spec2_color")
    _finite(p.spec2_intensity, "spec2_intensity")
    if p.spec1_intensity < 0 or p.spec2_intensity < 0:
        errors.append("spec intensities: 必须 >= 0")
    _finite(p.front_k, "front_k")
    if p.front_k <= 0:
        errors.append("front_k: 必须为有限正数（PLAN §5.3）")

    # 法线
    if p.detail_normal_mode not in ("off", "ts_detail"):
        errors.append(f"detail_normal_mode: 非法值 {p.detail_normal_mode!r}")
    if p.detail_normal_mode == "ts_detail" and p.detail_normal_strength <= 0:
        errors.append("detail_normal_strength: 启用细节法线时必须 > 0")
    if p.detail_normal_green_sign not in (1, -1):
        errors.append("detail_normal_green_sign: 必须为 ±1（0 表示未确认）")

    # 漫反射
    if p.diffuse_mode not in ("continuous", "smooth", "hard"):
        errors.append(f"diffuse_mode: 非法值 {p.diffuse_mode!r}")
    if p.diffuse_mode == "smooth" and not (
        0.0 <= p.diffuse_edge0 < p.diffuse_edge1 <= 1.0
    ):
        errors.append("diffuse_edge0/edge1: 需满足 0 <= edge0 < edge1 <= 1（PLAN §5.3）")
    if p.diffuse_mode == "hard" and not 0.0 <= p.diffuse_threshold <= 1.0:
        errors.append("diffuse_threshold: 应在 [0,1]")
    _vec3_finite(p.diffuse_color, "diffuse_color")
    _finite(p.ao_strength, "ao_strength")
    if not 0.0 <= p.ao_strength <= 1.0:
        errors.append("ao_strength: 应在 [0,1]（PLAN §5.4）")
    if not 0.0 <= p.ao_direct_light <= 1.0:
        errors.append("ao_direct_light: 应在 [0,1]，默认 0（PLAN §5.4）")

    # 输出
    _finite(p.exposure_ev, "exposure_ev")
    if not -10.0 <= p.exposure_ev <= 10.0:
        errors.append("exposure_ev: 应在 [-10,10]")
    if not 0 <= p.padding_width <= 64:
        errors.append("padding_width: 应在 [0,64]")

    return errors


def params_to_json(p: LightingParams, path: str | Path) -> None:
    """保存参数快照（config.json，PLAN §8.3）。"""
    Path(path).write_text(
        json.dumps(p.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def params_from_json(path: str | Path) -> LightingParams:
    """读取参数并经同一校验器（PLAN §8.2：预览/无头共用）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    valid_fields = {f.name for f in fields(LightingParams)}
    unknown = set(data) - valid_fields
    if unknown:
        raise ValueError(f"config.json 含未知字段: {sorted(unknown)}；拒绝静默修正")
    # JSON 数组反序列化为 list；声明为 tuple 的字段（vec3 / debug_outputs）
    # 在入口规整回 tuple，保证 config 往返相等性（to_json → from_json 恒等）。
    for f in fields(LightingParams):
        value = data.get(f.name)
        if isinstance(value, list) and isinstance(f.default, tuple):
            data[f.name] = tuple(value)
    return LightingParams(**data)


def engine_versions() -> dict[str, str]:
    """登记依赖/引擎版本（PLAN §8.3 快照要求）。"""
    ctx = moderngl.create_context(standalone=True)
    versions = {
        "python": platform.python_version(),
        "moderngl": moderngl.__version__,
        "gl_renderer": str(ctx.info.get("GL_RENDERER", "")),
        "gl_version": str(ctx.info.get("GL_VERSION", "")),
    }
    ctx.release()
    return versions
