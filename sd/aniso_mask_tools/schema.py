# -*- coding: utf-8 -*-
"""aniso_mask schema — 5 参数、固定常量、合法域、版本与源快照（计划 §2/§4.2）。

5 项 float 参数（3 形状 + 2 光照定位）。光照角度默认从旧 params 完整精度
推导值冻结（light_dir=(0.4,-0.6,0.7) → az/el 全精度），不用显示近似回写。
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------- 版本
MASK_VERSION = '1.0.0'
WRAPPER_ID = 'aniso_mask'
PKG_FILENAME = 'aniso_mask.sbs'

# ---------------------------------------------------------------- 5 参数
# (pid, 显示名, 默认, min, max, group, step)
GROUP_SHAPE = '01_高光形状'
GROUP_LIGHT = '02_光照定位'

PARAMS = [
    # pid                  label        default  min    max   group        step
    ('p_anisotropy',       '各向异性度',   0.7,    0.0,   1.0,  GROUP_SHAPE, 0.01),
    ('p_direction_deg',    '方向（织纹参考）', 0.0, 0.0,   180.0, GROUP_SHAPE, 0.1),
    ('p_roughness',        '高光粗糙度／宽度', 0.5, 0.0,   1.0,  GROUP_SHAPE, 0.01),
    ('p_light_azimuth_deg',   '光照方位',   -56.309932474020215, -180.0, 180.0, GROUP_LIGHT, 0.01),
    ('p_light_elevation_deg', '光照仰角',   44.148948676558244, -89.0, 89.0, GROUP_LIGHT, 0.01),
]


def light_angles_full_precision() -> tuple[float, float]:
    """从 light_dir=(0.4,-0.6,0.7) 推导完整精度角度（§2：读旧 params 默认，
    冻结全精度；与 aniso_pp.params._angles_from_light_dir 同公式）。"""
    x, y, z = 0.4, -0.6, 0.7
    az = math.degrees(math.atan2(y, x))
    el = math.degrees(math.atan2(z, math.hypot(x, y)))
    return az, el


def param_defaults() -> dict:
    """pid → 完整精度默认值（光照角用推导值，非表内显示值）。"""
    az, el = light_angles_full_precision()
    d = {pid: default for pid, _l, default, _mn, _mx, _g, _s in PARAMS}
    d['p_light_azimuth_deg'] = az
    d['p_light_elevation_deg'] = el
    return d


# ---------------------------------------------------------------- 固定常量
# 传给旧 core 的 v6.2 兼容常数（计划 §5.2：view_mode=normal_proxy、two_sided=1、
# 其余旧参数为有限合法常数；灯光两项映射为用户输入）
CORE_CONSTANTS = {
    'light_color': (1.0, 1.0, 1.0),
    'light_intensity': 1.0,
    'ambient_color': (0.06, 0.07, 0.09),
    'ambient_intensity': 1.0,
    'view_mode': 2,                # normal_proxy（计划 §2 固定沿用）
    'view_direction': (0.0, 0.0, 1.0),
    'camera_position': (0.0, 0.0, 1.0),
    'aniso_axis': 0,
    'aniso_angle_deg': 0.0,
    'aniso_amount': 1.0,
    'shift1': 0.0,
    'shift2': 0.35,
    'exponent1': 48.0,
    'exponent2': 8.0,
    'spec_mode': 1,
    'spec1_color': (1.0, 1.0, 1.0),
    'spec1_intensity': 1.0,
    'spec2_color': (1.0, 1.0, 1.0),
    'spec2_intensity': 0.6,
    'spec_edge0': 0.35,
    'spec_edge1': 0.55,
    'spec_threshold': 0.5,
    'front_k': 1.0,
    'diffuse_mode': 1,
    'diffuse_color': (1.0, 1.0, 1.0),
    'diffuse_edge0': 0.30,
    'diffuse_edge1': 0.50,
    'diffuse_threshold': 0.5,
    'ao_strength': 1.0,
    'ao_direct_light': 0.0,
    'ambient_ao': 0.5,
    'two_sided': 1,                # 计划 §5.2：two_sided=1
    'debug_mode': 0,
    'spec_layer_index': 0,
    'validity_fill': 1.0,
    'exposure_ev': 0.0,
}

# 旧 core 两项灯光参数 → 用户输入 pid（计划 §5.2：只映射这两项）
LIGHT_PARAM_MAP = {
    'p_light_azimuth_deg': 'p_light_azimuth_deg',
    'p_light_elevation_deg': 'p_light_elevation_deg',
}

# ---------------------------------------------------------------- 合法域
def validate_param_values(vals: dict) -> list[str]:
    errs = []
    for pid, _l, _d, mn, mx, _g, _s in PARAMS:
        if pid in vals:
            v = float(vals[pid])
            if not math.isfinite(v):
                errs.append(f'{pid} 非有限: {v}')
            elif v < mn - 1e-9 or v > mx + 1e-9:
                errs.append(f'{pid}={v} 超出 [{mn},{mx}]')
    return errs
