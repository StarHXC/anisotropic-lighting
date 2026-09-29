# -*- coding: utf-8 -*-
"""aniso_easylight schema — 11 参数、冻结常数表、合法域（ANISO_EASYLIGHT 计划）。

参考 aniso_mask 范式：分组滑块、无颜色控件。相对旧 aniso_lightmap（35 参数）
的删减与冻结机制逐项注释（「冻结≠结构删除」——公式在常数下构造性退化）。

光照角默认从 light_dir=(0.4,-0.6,0.7) 完整精度推导冻结
（与 aniso_pp.params._angles_from_light_dir 同式），不用显示近似回写。
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------- 版本
EASYLIGHT_VERSION = '1.0.0'
WRAPPER_ID = 'aniso_easylight'
PKG_FILENAME = 'aniso_easylight.sbs'

# ---------------------------------------------------------------- 分组
GROUP_LIGHT = '01_光照定位'
GROUP_ANISO = '02_各向异性'
GROUP_SPEC = '03_高光形状'
GROUP_MASKING = '04_遮蔽与双面'

# ---------------------------------------------------------------- 11 参数
# (pid, label, default, min, max, group, step)
PARAMS = [
    # pid                      label        default  mn      mx     group          step
    ('p_light_azimuth_deg',    '光照方位',   None,    -180.0, 180.0, GROUP_LIGHT,   0.01),
    ('p_light_elevation_deg',  '光照仰角',   None,    -89.0,  89.0,  GROUP_LIGHT,   0.01),
    ('p_aniso_axis',           '主轴（u/v）', 0,       0,      1,     GROUP_ANISO,   1.0),
    ('p_aniso_angle_deg',      '条纹旋转角', 0.0,     -180.0, 180.0, GROUP_ANISO,   0.1),
    ('p_aniso_amount',         '各向异性度', 1.0,     0.0,    1.0,   GROUP_ANISO,   0.01),
    ('p_shift1',               '层1偏移',    0.0,     -4.0,   4.0,   GROUP_SPEC,    0.01),
    ('p_exponent1',            '层1锐度',    48.0,    1.0,    256.0, GROUP_SPEC,    1.0),
    ('p_shift2',               '层2偏移',    0.35,    -4.0,   4.0,   GROUP_SPEC,    0.01),
    ('p_exponent2',            '层2锐度',    8.0,     1.0,    256.0, GROUP_SPEC,    1.0),
    ('p_two_sided',            '双面光照',   1,       0,      1,     GROUP_MASKING, 1.0),
    ('p_ao_direct',            '直射光 AO',  0.0,     0.0,    1.0,   GROUP_MASKING, 0.01),
]

EXPOSED_PIDS = frozenset(p[0] for p in PARAMS)
INT_PIDS = frozenset(pid for pid, _l, _d, _mn, _mx, _g, _s in PARAMS
                     if pid in ('p_aniso_axis', 'p_two_sided'))


def light_angles_full_precision() -> tuple[float, float]:
    """从 light_dir=(0.4,-0.6,0.7) 推导完整精度角度（与
    aniso_pp.params._angles_from_light_dir 同公式）。"""
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


# ---------------------------------------------------------------- 冻结常数表
# 旧 build_core 面板参数中不暴露的部分 → 图内常数（机制注释逐项写明）。
# 机制三类：
#   [恒等] 白色/intensity=1 乘子——乘法恒等，删控件不改数值
#   [配比] spec2_intensity=0.6——旧烘焙快照双层配比，冻 1.0 会改变默认外观
#   [外观] spec 分段旧默认 smooth(0.35/0.55/0.5)——签名观感保留
#   [简化] diffuse_mode=0（连续 half-lambert，旧默认 mode=1 smooth）——
#          声明式简化（用户裁定「分段全部冻结」；mode=0 分支=clamp，
#          diff_x∈[0,1] 定义域内无数值畸变，仅换掉卡通台阶观感）
#   [置零] ambient_color=(0,0,0)——amb 项精确为零（用户裁定：纯直射响应，
#          0=无光；引擎侧自行加 ambient）
#   [死常数] ambient_ao——只服务 amb 项，随置零退场
#   [基准] view 三件套 normal_proxy 烘焙语义（mode=2 下另两项不进求值）
FREEZE_CONSTANTS = {
    'light_color': (1.0, 1.0, 1.0),        # [恒等]
    'light_intensity': 1.0,                # [恒等]
    'ambient_color': (0.0, 0.0, 0.0),      # [置零]（计划裁定 #2）
    'ambient_intensity': 1.0,              # [恒等]（历史项，build_core 不读）
    'view_mode': 2,                        # [基准] normal_proxy
    'view_direction': (0.0, 0.0, 1.0),     # [基准]
    'camera_position': (0.0, 0.0, 1.0),    # [基准]
    'spec1_color': (1.0, 1.0, 1.0),        # [恒等]
    'spec2_color': (1.0, 1.0, 1.0),        # [恒等]
    'spec1_intensity': 1.0,                # [恒等]
    'spec2_intensity': 0.6,                # [配比] 旧默认衬光层弱 40%
    'spec_mode': 1,                        # [外观] smooth（旧默认）
    'spec_edge0': 0.35,                    # [外观]
    'spec_edge1': 0.55,                    # [外观]
    'spec_threshold': 0.5,                 # [外观]
    'front_k': 1.0,                        # [恒等]（旧默认）
    'diffuse_color': (1.0, 1.0, 1.0),      # [恒等]
    'diffuse_mode': 0,                     # [简化] 连续 half-lambert（裁定 #3）
    'diffuse_edge0': 0.30,                 # [死常数] mode=0 不进求值
    'diffuse_edge1': 0.50,                 # [死常数]
    'diffuse_threshold': 0.5,              # [死常数]
    'ao_strength': 1.0,                    # [合并] 语义并入 p_ao_direct（恒等合并：
    #        ao_direct = lerp(1, lerp(1, ao_r, 1.0), p_ao_direct)
    #                   = lerp(1, ao_r, p_ao_direct)，默认输出不变）
    'ambient_ao': 0.5,                     # [死常数] amb 置零后不进有效数值
    'validity_fill': 0.0,                  # [契约] 无效区精确 0（PP2 已删，留档）
    'exposure_ev': 0.0,                    # [契约] Raw 线性输出（PP2 已删，留档）
}

# 旧 build_core 参数名 → 新面板 pid 映射（只列非同名项）
EXPOSED_MAP = {
    'ao_direct_light': 'p_ao_direct',      # 合并 ao_strength（冻结 1.0）
}

# ---------------------------------------------------------------- 合法域
def validate_param_values(vals: dict) -> list[str]:
    errs = []
    defaults = param_defaults()
    for pid, _l, _d, mn, mx, _g, _s in PARAMS:
        v = vals.get(pid, defaults[pid])
        v = float(v)
        if not math.isfinite(v):
            errs.append(f'{pid} 非有限: {v}')
        elif v < mn - 1e-9 or v > mx + 1e-9:
            errs.append(f'{pid}={v} 超出 [{mn},{mx}]')
    # 跨字段：光照方向合成向量非零（与 aniso_pp.params.validate 同语义）
    az = math.radians(float(vals.get('p_light_azimuth_deg',
                                     defaults['p_light_azimuth_deg'])))
    el = math.radians(float(vals.get('p_light_elevation_deg',
                                     defaults['p_light_elevation_deg'])))
    ld = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    if math.hypot(*ld) < 1e-8:
        errs.append('光照方向合成向量退化')
    return errs
