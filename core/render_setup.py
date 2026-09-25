"""uniform 打包与编译期 define 映射（预览/烘焙共用）。

契约来源：PLAN.md §8.2——预览与无头必须走同一计算与编码链路。
本模块是参数 → GPU 状态的唯一映射点：aniso_bake.py（--bake）与
preview.py（--preview）都从这里取 uniforms/defines，
任一侧改动必须同步另一侧（事实上不允许单侧改动）。

向量以 numpy float32 打包（moderngl 接受）；方向在 CPU 侧归一化，
shader 内不再重复归一化（与 PLAN §4.1 安全运算语义一致）。
"""

from __future__ import annotations

import numpy as np

from core.parameters import LightingParams

__all__ = ["build_uniforms", "build_defines"]


def _vec3(values, name: str) -> np.ndarray:
    v = np.asarray(values, dtype=np.float32)
    if v.shape != (3,):
        raise ValueError(f"{name}: 期望 3 分量，实际 {v.shape}")
    return v


def _unit_vec3(values, name: str) -> np.ndarray:
    v = _vec3(values, name)
    length = float(np.linalg.norm(v))
    if length < 1e-8:
        raise ValueError(f"{name}: 零向量不能归一化")
    return (v / length).astype(np.float32)


def build_uniforms(p: LightingParams) -> dict:
    """LightingParams → aniso.frag uniform 字典（与 bake/preview 共用）。"""
    return {
        # 光照（u_lightDir CPU 侧已归一化，PLAN §4.1）
        "u_lightDir": _unit_vec3(p.light_dir, "light_dir"),
        "u_lightColor": _vec3(p.light_color, "light_color"),
        "u_lightIntensity": float(p.light_intensity),
        "u_ambientColor": _vec3(p.ambient_color, "ambient_color"),
        "u_ambientIntensity": float(p.ambient_intensity),
        # 观察
        "u_viewDirection": _unit_vec3(p.view_direction, "view_direction"),
        "u_cameraPosition": _vec3(p.camera_position, "camera_position"),
        # 各向异性方向
        "u_anisoAngle": float(p.aniso_angle),
        "u_anisoAmount": float(p.aniso_amount),
        # 高光
        "u_shift1": float(p.shift1),
        "u_shift2": float(p.shift2),
        "u_exponent1": float(p.exponent1),
        "u_exponent2": float(p.exponent2),
        "u_spec1Color": _vec3(p.spec1_color, "spec1_color"),
        "u_spec1Intensity": float(p.spec1_intensity),
        "u_spec2Color": _vec3(p.spec2_color, "spec2_color"),
        "u_spec2Intensity": float(p.spec2_intensity),
        "u_specEdge0": float(p.spec_edge0),
        "u_specEdge1": float(p.spec_edge1),
        "u_specThreshold": float(p.spec_threshold),
        "u_frontK": float(p.front_k),
        # 漫反射与调制
        "u_diffuseColor": _vec3(p.diffuse_color, "diffuse_color"),
        "u_diffuseEdge0": float(p.diffuse_edge0),
        "u_diffuseEdge1": float(p.diffuse_edge1),
        "u_diffuseThreshold": float(p.diffuse_threshold),
        "u_aoStrength": float(p.ao_strength),
        "u_aoDirectLight": float(p.ao_direct_light),
        # 细节法线
        "u_detailStrength": float(p.detail_normal_strength),
    }


def build_defines(p: LightingParams) -> dict:
    """LightingParams → 编译期 define 字典（PLAN §7 C4：离散模式为编译期变体）。"""
    return {
        "DEBUG_MODE": "0",
        "VIEW_MODE": {"directional": "0", "perspective": "1", "normal_proxy": "2"}[p.view_mode],
        "DETAIL_MODE": "1" if p.detail_normal_mode == "ts_detail" else "0",
        "DETAIL_GREEN_SIGN": str(p.detail_normal_green_sign),
        "SPEC_MODE": {"continuous": "0", "smooth": "1", "hard": "2"}[p.spec_mode],
        "DIFFUSE_MODE": {"continuous": "0", "smooth": "1", "hard": "2"}[p.diffuse_mode],
        "ANISO_AXIS": {"u": "0", "v": "1"}[p.aniso_axis],
    }
