# -*- coding: utf-8 -*-
r"""aniso_mask — 新包构建（ANISO_MASK_PLAN §5.2 / §4）。

职责：
  - 新 package/wrapper（aniso_mask）、5 个 float 参数、4 张独立 bitmap
  - 调用现有 core（build_core）传冻结的 v6.2 兼容常数 resolver + frame_out
  - 同一 FG 中用 frame_out + Emitter 构建 §3 基底与主瓣（kernel.build_mask）
  - M 设为最终输出（float1；colorswitch=False 的 PP）
  - 不创建 PP2、不注册颜色控件

蓝图（builder 蓝图被 build_aniso_mask.py 与验证探针共用）：
  build_mask_graph(wrapper, pkg, bmp_nodes, texel, params_ui=True) →
  dict(pp_mask, packed…, meta)
"""
from __future__ import annotations

import os

try:
    from . import kernel
    from .schema import CORE_CONSTANTS, LIGHT_PARAM_MAP
except ImportError:
    from aniso_mask_tools import kernel
    from aniso_mask_tools.schema import CORE_CONSTANTS, LIGHT_PARAM_MAP


def make_mask_resolver(fg, em, param_source):
    """v6.2 兼容常数 resolver：灯光两项 → get_float1(用户 pid)，
    其余旧参数 → 图内常数。param_source: 'ui'（get 节点）。

    未知源 pid 报错（§5.2）。
    """
    from sd.api.sdvaluestring import SDValueString

    def resolver(pid):
        full = pid if pid.startswith('p_') else 'p_' + pid
        if full in LIGHT_PARAM_MAP.values() or full in (
                'p_light_azimuth_deg', 'p_light_elevation_deg'):
            gf = fg.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__',
                                           SDValueString.sNew(full))
            return em.NodeRefWrap(gf) if hasattr(em, 'NodeRefWrap') else _nr(gf)
        v = CORE_CONSTANTS.get(full)
        if v is None:
            raise RuntimeError(f'未知旧参数 pid: {full}')
        if isinstance(v, (tuple, list)):
            return em.v3(em.c_f1(float(v[0])), em.c_f1(float(v[1])),
                         em.c_f1(float(v[2])))
        return em.c_f1(float(v))
    return resolver


def _nr(node):
    from aniso_pp.emitter import NodeRef
    return NodeRef(node, 'f1')


def mask_param_resolver_ui(em, fg):
    """新 5 参数 → 图内 get_float1（实例面板驱动）。"""
    from sd.api.sdvaluestring import SDValueString

    def getf(pid):
        gf = fg.newNode('sbs::function::get_float1')
        gf.setInputPropertyValueFromId('__constant__',
                                       SDValueString.sNew(pid))
        from aniso_pp.emitter import NodeRef
        return NodeRef(gf, 'f1')
    return getf
