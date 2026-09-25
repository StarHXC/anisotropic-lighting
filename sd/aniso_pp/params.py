# -*- coding: utf-8 -*-
"""参数 schema 单一来源（SD_MIGRATION_PLAN §7.4/§7.5）。

41 项参数：id / 类型 / 默认 / UI 范围 / 分组 / GLSL uniform-define 映射。
默认值来源：out/bake_report.json 冻结快照（light_dir=(0.4,-0.6,0.7) 等）。
角度参数由完整精度向量推导（显示近似 −56.3°/44.1° 不写回数值基准）。

校验器：跨字段规则在 validate() —— 滑块注解只管 UI，不替代校验。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    pid: str            # SD 参数 id（p_ 前缀）
    ptype: str          # 'float1' | 'int' | 'float3'
    default: object     # float | int | (r,g,b)
    group: str
    ui_min: float | None = None
    ui_max: float | None = None
    clamp: bool = True
    step: float = 0.01
    glsl_map: str = ''  # 对应 uniform/define 名（证据链用）
    note: str = ''


def _angles_from_light_dir(v=(0.4, -0.6, 0.7)):
    """完整精度角度推导（§7.4：显示近似不得写回数值基准）。"""
    x, y, z = v
    az = math.degrees(math.atan2(y, x))
    el = math.degrees(math.atan2(z, math.hypot(x, y)))
    return az, el


_AZ, _EL = _angles_from_light_dir()


GROUPS = {
    '01': '01_光照方向',
    '02': '02_各向异性',
    '03': '03_高光',
    '04': '04_漫反射_曝光',
    '05': '05_观察模式',
    '06': '06_调试与系统',
}

PARAMS: list[Param] = [
    # ---- 01 光照方向
    Param('p_light_azimuth_deg', 'float1', _AZ, GROUPS['01'], -180.0, 180.0,
          glsl_map='u_lightDir(球坐标分量)', note='完整精度默认由 light_dir 推导'),
    Param('p_light_elevation_deg', 'float1', _EL, GROUPS['01'], -89.0, 89.0,
          glsl_map='u_lightDir(球坐标分量)'),
    Param('p_light_intensity', 'float1', 1.0, GROUPS['01'], 0.0, 4.0,
          glsl_map='u_lightIntensity'),
    Param('p_light_color', 'float3', (1.0, 1.0, 1.0), GROUPS['01'],
          glsl_map='u_lightColor'),
    Param('p_ambient_color', 'float3', (0.06, 0.07, 0.09), GROUPS['01'],
          glsl_map='u_ambientColor'),
    Param('p_ambient_intensity', 'float1', 1.0, GROUPS['01'], 0.0, 4.0,
          glsl_map='u_ambientIntensity'),
    # ---- 02 各向异性
    Param('p_aniso_angle_deg', 'float1', 0.0, GROUPS['02'], -180.0, 180.0,
          glsl_map='u_anisoAngle（度→图内转弧度）'),
    Param('p_aniso_axis', 'int', 0, GROUPS['02'], 0, 2,
          step=1.0, glsl_map='ANISO_AXIS define → 运行期选择', note='0=u 1=v'),
    Param('p_aniso_amount', 'float1', 1.0, GROUPS['02'], 0.0, 1.0,
          glsl_map='u_anisoAmount'),
    # ---- 03 高光
    Param('p_shift1', 'float1', 0.0, GROUPS['03'], -4.0, 4.0, glsl_map='u_shift1'),
    Param('p_shift2', 'float1', 0.35, GROUPS['03'], -4.0, 4.0, glsl_map='u_shift2'),
    Param('p_exponent1', 'float1', 48.0, GROUPS['03'], 1.0, 256.0,
          step=1.0, glsl_map='u_exponent1'),
    Param('p_exponent2', 'float1', 8.0, GROUPS['03'], 1.0, 256.0,
          step=1.0, glsl_map='u_exponent2'),
    Param('p_spec1_color', 'float3', (1.0, 1.0, 1.0), GROUPS['03'],
          glsl_map='u_spec1Color'),
    Param('p_spec1_intensity', 'float1', 1.0, GROUPS['03'], 0.0, 4.0,
          glsl_map='u_spec1Intensity'),
    Param('p_spec2_color', 'float3', (1.0, 1.0, 1.0), GROUPS['03'],
          glsl_map='u_spec2Color'),
    Param('p_spec2_intensity', 'float1', 0.6, GROUPS['03'], 0.0, 4.0,
          glsl_map='u_spec2Intensity'),
    Param('p_spec_mode', 'int', 1, GROUPS['03'], 0, 2, step=1.0,
          glsl_map='SPEC_MODE define → 运行期选择', note='0=continuous 1=smooth 2=hard'),
    Param('p_spec_edge0', 'float1', 0.35, GROUPS['03'], 0.0, 1.0,
          glsl_map='u_specEdge0'),
    Param('p_spec_edge1', 'float1', 0.55, GROUPS['03'], 0.0, 1.0,
          glsl_map='u_specEdge1'),
    Param('p_spec_threshold', 'float1', 0.5, GROUPS['03'], 0.0, 1.0,
          glsl_map='u_specThreshold'),
    Param('p_front_k', 'float1', 1.0, GROUPS['03'], 0.01, 4.0,
          glsl_map='u_frontK', note='有限正数'),
    # ---- 04 漫反射/曝光
    Param('p_diffuse_mode', 'int', 1, GROUPS['04'], 0, 2, step=1.0,
          glsl_map='DIFFUSE_MODE define → 运行期选择'),
    Param('p_diffuse_color', 'float3', (1.0, 1.0, 1.0), GROUPS['04'],
          glsl_map='u_diffuseColor'),
    Param('p_diffuse_edge0', 'float1', 0.30, GROUPS['04'], 0.0, 1.0,
          glsl_map='u_diffuseEdge0'),
    Param('p_diffuse_edge1', 'float1', 0.50, GROUPS['04'], 0.0, 1.0,
          glsl_map='u_diffuseEdge1'),
    Param('p_diffuse_threshold', 'float1', 0.5, GROUPS['04'], 0.0, 1.0,
          glsl_map='u_diffuseThreshold'),
    Param('p_ao_strength', 'float1', 1.0, GROUPS['04'], 0.0, 1.0,
          glsl_map='u_aoStrength'),
    Param('p_ao_direct_light', 'float1', 0.0, GROUPS['04'], 0.0, 1.0,
          glsl_map='u_aoDirectLight'),
    Param('p_exposure_ev', 'float1', 0.0, GROUPS['04'], -10.0, 10.0,
          step=0.1, glsl_map='输出级 exposure（与现有校验器一致）'),
    Param('p_validity_fill', 'float1', 1.0, GROUPS['04'], 0.0, 1.0,
          glsl_map='输出级 validityFill', note='属于 PP2'),
    # ---- 05 观察模式
    Param('p_view_mode', 'int', 2, GROUPS['05'], 0, 2, step=1.0,
          glsl_map='VIEW_MODE define → 运行期选择',
          note='0=directional 1=perspective 2=normal_proxy'),
    Param('p_view_direction', 'float3', (0.0, 0.0, 1.0), GROUPS['05'],
          glsl_map='u_viewDirection（宿主归一化语义必须复刻）'),
    Param('p_camera_position', 'float3', (0.0, 0.0, 1.0), GROUPS['05'],
          glsl_map='u_cameraPosition'),
    # ---- 06 调试与系统
    Param('p_debug_mode', 'int', 0, GROUPS['06'], 0, 9, step=1.0,
          glsl_map='DEBUG_MODE define → 运行期级联 i=1→9'),
    Param('p_spec_layer_index', 'int', 0, GROUPS['06'], 0, 1, step=1.0,
          glsl_map='SPEC_LAYER_INDEX（DEBUG 7 层选择）'),
    Param('p_detail_mode', 'int', 0, GROUPS['06'], 0, 1, step=1.0,
          glsl_map='DETAIL_MODE define → 运行期选择',
          note='真实资产未解锁时固定 off'),
    Param('p_detail_strength', 'float1', 0.0, GROUPS['06'], 0.0, 1.0,
          glsl_map='u_detailStrength'),
    Param('p_detail_green_sign', 'int', 1, GROUPS['06'], 0, 1, step=1.0,
          glsl_map='DETAIL_GREEN_SIGN',
          note='UI int 0/1 映射 −1/+1；快照保存规范符号'),
    Param('p_texel_u', 'float1', 1.0 / 2048.0, GROUPS['06'],
          glsl_map='（无；系统参数）',
          note='由输入位置图实际 W 派生，非艺术滑块；替换输入须重验'),
    Param('p_texel_v', 'float1', 1.0 / 2048.0, GROUPS['06'],
          glsl_map='（无；系统参数）',
          note='由输入位置图实际 H 派生'),
]


def param_count() -> int:
    return len(PARAMS)


def get(pid: str) -> Param:
    for p in PARAMS:
        if p.pid == pid:
            return p
    raise KeyError(pid)


def validate(values: dict) -> list[str]:
    """跨字段校验（§7.5：滑块注解不替代校验）。返回错误列表（空=通过）。

    values: pid → 值（缺项用默认值补齐后校验）。
    """
    errs = []
    v = {p.pid: p.default for p in PARAMS}
    v.update(values)

    def f(pid):
        return float(v[pid])

    # 边缘有序
    if not f('p_spec_edge0') < f('p_spec_edge1'):
        errs.append(f'p_spec_edge0 ({f("p_spec_edge0")}) 必须 < p_spec_edge1 ({f("p_spec_edge1")})')
    if not f('p_diffuse_edge0') < f('p_diffuse_edge1'):
        errs.append(f'p_diffuse_edge0 ({f("p_diffuse_edge0")}) 必须 < p_diffuse_edge1 ({f("p_diffuse_edge1")})')
    # 有限正数
    for pid in ('p_front_k', 'p_light_intensity', 'p_ambient_intensity',
                'p_exponent1', 'p_exponent2'):
        val = f(pid)
        if not (math.isfinite(val) and val > 0):
            errs.append(f'{pid} 必须为有限正数, 得到 {val}')
    # 枚举合法域
    for pid, lo, hi in (('p_spec_mode', 0, 2), ('p_diffuse_mode', 0, 2),
                        ('p_view_mode', 0, 2), ('p_debug_mode', 0, 9),
                        ('p_spec_layer_index', 0, 1), ('p_detail_mode', 0, 1),
                        ('p_aniso_axis', 0, 1)):
        iv = int(v[pid])
        if not (lo <= iv <= hi):
            errs.append(f'{pid}={iv} 超出枚举域 [{lo},{hi}]')
    # 方向向量非零（送入宿主归一化前）
    for pid in ('p_view_direction',):
        x, y, z = v[pid]
        if not math.isfinite(x + y + z) or math.hypot(x, y, z) < 1e-8:
            errs.append(f'{pid} 不能是零/非有限向量（宿主归一化语义 render_setup.py:28-33）')
    # light_dir 合成向量非零
    az, el = math.radians(f('p_light_azimuth_deg')), math.radians(f('p_light_elevation_deg'))
    ld = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    if math.hypot(*ld) < 1e-8:
        errs.append('光照方向合成向量退化')
    # detail green sign 二值
    if int(v['p_detail_green_sign']) not in (0, 1):
        errs.append('p_detail_green_sign 仅允许 0/1（映射 −1/+1）')
    # texel 正数且 ≤1
    for pid in ('p_texel_u', 'p_texel_v'):
        tv = f(pid)
        if not (math.isfinite(tv) and 0 < tv <= 1.0):
            errs.append(f'{pid} 必须在 (0,1], 得到 {tv}')
    return errs


def default_values() -> dict:
    return {p.pid: p.default for p in PARAMS}


if __name__ == '__main__':
    # 本地自检：计数 + 默认值校验通过 + bake_report 快照校验通过
    import json
    from pathlib import Path
    print('参数总数:', param_count())
    errs = validate({})
    assert not errs, errs
    print('默认值校验: OK')
    bake = Path(__file__).resolve().parent.parent / 'out_placeholder.json'
    # bake_report 快照对照（若存在）
    report_p = Path(__file__).resolve().parent.parent.parent / 'out' / 'bake_report.json'
    if report_p.exists():
        snap = json.loads(report_p.read_text(encoding='utf-8'))['params']
        errs2 = validate({
            'p_exposure_ev': snap['exposure_ev'],
            'p_spec_edge0': snap['spec_edge0'],
            'p_spec_edge1': snap['spec_edge1'],
            'p_diffuse_edge0': snap['diffuse_edge0'],
            'p_diffuse_edge1': snap['diffuse_edge1'],
        })
        assert not errs2, errs2
        print('bake_report 快照兼容校验: OK')
    # 错误配置必须被拒
    bad = validate({'p_spec_edge0': 0.6, 'p_spec_edge1': 0.4})
    assert any('edge0' in e for e in bad)
    print('非法配置拒收: OK')
