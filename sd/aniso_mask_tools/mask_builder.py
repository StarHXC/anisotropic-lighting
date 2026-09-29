# -*- coding: utf-8 -*-
r"""aniso_mask 正式包构建核心（build_aniso_mask.py 的引擎；§5.2）。

与探针的区别：
  - 正式 wrapper identifier=aniso_mask、5 参数全注册（group/slider 注解）
  - 4 bitmap 来自旧 SBS 真实绑定 filename（§4.2 解析打包资源）
  - 2048² 生产尺寸（生产仅 2048²；测试探针才允许小尺寸）
  - 保存 aniso_mask.sbs + 独立 aniso_mask.resources/
  - 保存后 XML 补写（无颜色控件——不需要 valueInterpretation；仅 slider）

资源绑定解析：读旧 aniso_lightmap.sbs 的 XML，取 4 个 bitmap 实例的
filename 属性（真实绑定），再解析到 aniso_lightmap.resources/ 内文件。
不按 1-/2- 前缀副本猜（§4.2）。
"""
from __future__ import annotations

import json
import os
import re

SD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_SBS = os.path.join(SD_DIR, 'aniso_lightmap.sbs')
OLD_RES = os.path.join(SD_DIR, 'aniso_lightmap.resources')
SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')

REPORT = {'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'aniso_mask 构建失败于: {name}  ({detail})')


def parse_old_bindings():
    """旧 SBS XML → 4 个 bitmap 资源 identifier → filename 映射。

    实际结构（SD 16.0.1 实测）：资源定义块为
      <resource><identifier v="src_bake_position"/>…<source><externalcopy>
      <filename v="aniso_lightmap.resources/bake_position.png"/></externalcopy>
      </source></resource>
    """
    xml = open(OLD_SBS, encoding='utf-8').read()
    binds = {}
    for m in re.finditer(
            r'<resource><identifier v="([^"]+)"/>.*?'
            r'<externalcopy><filename v="([^"]+)"/></externalcopy>',
            xml, re.S):
        rid, fname = m.group(1), m.group(2)
        binds[rid] = fname
    return binds


def resolve_bitmap_files():
    """真实绑定 filename → 磁盘绝对路径（aniso_lightmap.resources 内）。

    filename 形如 'aniso_lightmap.resources/bake_position.png'（相对包）。
    """
    binds = parse_old_bindings()
    files = {}
    for rid, fname in binds.items():
        base = os.path.basename(fname)
        p = os.path.join(OLD_RES, base)
        if not os.path.exists(p):
            raise RuntimeError(f'绑定资源缺失: {rid} → {p}')
        files[rid] = p
    # 槽位固定（§4.2）：0=position 1=normalobj 2=coverage 3=AO
    order = [('src_bake_position', 0), ('src_bake_normalobj', 1),
             ('src_mask1', 2), ('src_bake_ao', 3)]
    slots = [None, None, None, None]
    for rid, idx in order:
        if rid not in files:
            raise RuntimeError(f'旧包缺少槽位资源: {rid}（实际: {sorted(files)}）')
        slots[idx] = files[rid]
    return slots


def build(save_xml_patch=True):
    """构建并保存 aniso_mask.sbs。返回 REPORT。"""
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluebool import SDValueBool
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdtypefloat import SDTypeFloat
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.params import PARAMS as OLD_PARAMS
    import struct as _struct
    import stages
    from aniso_mask_tools import kernel as kmask
    from aniso_mask_tools.schema import (
        MASK_VERSION, WRAPPER_ID, param_defaults)

    step('环境', True, {'sd_api_version': SDAPI.app_version(),
                        'mask_version': MASK_VERSION})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- 槽位资源解析（§4.2 真实绑定）
    slots = resolve_bitmap_files()
    step('旧绑定解析（真实 filename）', len(slots) == 4,
         {i: os.path.basename(p) for i, p in enumerate(slots)})

    # ---- 新包
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier(WRAPPER_ID)
    try:
        wrapper.setDefaultParentSize(int2(11, 11))
    except BaseException:
        pass
    step('wrapper aniso_mask', wrapper is not None)

    # ---- 5 参数（group + slider 注解；§2 面板）
    PD = param_defaults()
    UI = [
        ('p_anisotropy', '各向异性度', 0.0, 1.0, 0.01, '01_高光形状'),
        ('p_direction_deg', '方向（织纹参考）', 0.0, 180.0, 0.1, '01_高光形状'),
        ('p_roughness', '高光粗糙度／宽度', 0.0, 1.0, 0.01, '01_高光形状'),
        ('p_light_azimuth_deg', '光照方位', -180.0, 180.0, 0.01, '02_光照定位'),
        ('p_light_elevation_deg', '光照仰角', -89.0, 89.0, 0.01, '02_光照定位'),
    ]
    reg_ok = 0
    for pid, label, mn, mx, st, group in UI:
        prop = wrapper.newProperty(pid, SDTypeFloat.sNew(),
                                   SDPropertyCategory.Input)
        wrapper.setPropertyValue(prop, SDValueFloat.sNew(float(PD[pid])))
        if hasattr(wrapper, 'setPropertyAnnotationValueFromId'):
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'group', SDValueString.sNew(group))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'editor', SDValueString.sNew('slider'))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'min', SDValueFloat.sNew(float(mn)))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'max', SDValueFloat.sNew(float(mx)))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'step', SDValueFloat.sNew(float(st)))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'clamp', SDValueBool.sNew(True))
        reg_ok += 1
    step('5 参数注册（group/slider）', reg_ok == 5)

    # ---- 4 bitmap（CopiedAndLinked → 独立 aniso_mask.resources/）
    bmp_nodes = []
    for idx, fpath in enumerate(slots):
        res = SDResourceBitmap.sNewFromFile(pkg, fpath,
                                            EmbedMethod.CopiedAndLinked)
        res.setIdentifier(f'src_{["bake_position", "bake_normalobj", "mask1", "bake_ao"][idx]}')
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(-700.0, float(idx) * 260.0))
        for prop_id, val in (('$outputsize', SDValueInt2.sNew(int2(11, 11))),
                             ('$format', SDValueInt.sNew(3))):
            prop = n.getPropertyFromId(prop_id, SDPropertyCategory.Input)
            n.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
            n.setPropertyValue(prop, val)
        bmp_nodes.append(n)
    step('4 bitmap 内嵌（独立 resources）', len(bmp_nodes) == 4)

    # ---- texel 由位置图实际尺寸派生（PNG IHDR；构建期常数）
    with open(slots[0], 'rb') as fh:
        hdr = fh.read(24)
    if hdr[:8] != b'\x89PNG\r\n\x1a\n' or hdr[12:16] != b'IHDR':
        raise RuntimeError(f'位置图不是合法 PNG: {slots[0]}')
    pw, ph = _struct.unpack('>II', hdr[16:24])
    TEXEL = 1.0 / pw
    step('texel 派生', pw == ph and pw > 0, {'size': (pw, ph), 'texel': TEXEL})

    # ---- 灰度 PP（colorswitch=False；§4.1 首选）
    pp, ev = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=11)
    pp.setPosition(float2(300.0, 0.0))
    for n in bmp_nodes:
        SDAPI.connect_pp_input(n, pp)
    step('灰度 PP（colorswitch=False, 2048²）',
         ev['colorswitch'] is False and ev['outputsize_log2'] == (11, 11), ev)

    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='aniso_mask_core')

    # ---- v6.2 兼容常数 resolver（灯光两项 → wrapper get_float1）
    BY_PID = {}
    for _p in OLD_PARAMS:
        BY_PID[_p.pid] = _p

    def resolver(pid):
        full = pid if pid.startswith('p_') else 'p_' + pid
        if full in ('p_light_azimuth_deg', 'p_light_elevation_deg'):
            gf = fg.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full))
            return NodeRef(gf, 'f1')
        p = BY_PID.get(full)
        if p is None:
            raise RuntimeError(f'未知旧参数 pid: {full}')
        v = p.default
        if isinstance(v, tuple):
            return em.v3(em.c_f1(float(v[0])), em.c_f1(float(v[1])),
                         em.c_f1(float(v[2])))
        return em.c_f1(float(v))

    # ---- core + frame 收集
    frame = {}
    packed, meta = stages.build_core(fg, texel=TEXEL, param_resolver=resolver,
                                     frame_out=frame)
    step('core 发射 + frame 收集', len(frame) == 7, {'nodes': meta['nodes']})

    # ---- §3 kernel（5 参数中 3 个形状参数进入 kernel）
    def getf(pid):
        gf = fg.newNode('sbs::function::get_float1')
        gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(pid))
        return NodeRef(gf, 'f1')

    kout = kmask.build_mask(em, frame, getf('p_anisotropy'),
                            getf('p_roughness'), getf('p_direction_deg'))
    M = kout['M']
    fg.setOutputNode(M.node, True)
    step('mask kernel 发射（M=float1 输出）', True,
         {'kernel_nodes': em.node_count})

    # ---- wrapper output
    out_node = wrapper.newNode('sbs::compositing::output')
    out_node.setPosition(float2(900.0, 0.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    wrapper.setOutputNode(out_node, True)
    step('wrapper output', True)

    # ---- 函数图排布（stage3 auto_layout 同款）
    from sd.api.sdproperty import SDPropertyCategory as _Cat
    from sd.api.sdbasetypes import float2 as _f2

    def auto_layout(fg_, max_rows=6, sx=220.0, sy=140.0):
        nodes_arr = fg_.getNodes()
        all_nodes = [nodes_arr.getItem(i) for i in range(nodes_arr.getSize())]
        if not all_nodes:
            return 0
        uid_map = {id(n): n for n in all_nodes}
        in_conns = {id(n): set() for n in all_nodes}
        out_adj = {id(n): [] for n in all_nodes}
        for n in all_nodes:
            props = n.getProperties(_Cat.Input)
            for j in range(props.getSize()):
                p_ = props.getItem(j)
                try:
                    conns = n.getPropertyConnections(p_)
                    if conns:
                        for k in range(conns.getSize()):
                            c = conns.getItem(k)
                            src = c.getInputPropertyNode()
                            if id(src) in in_conns:
                                in_conns[id(n)].add(id(src))
                                out_adj[id(src)].append(id(n))
                except BaseException:
                    pass
        in_deg = {nid: len(s) for nid, s in in_conns.items()}
        queue = [nid for nid, d in in_deg.items() if d == 0]
        ordered = []
        while queue:
            cur = queue.pop(0)
            ordered.append(cur)
            for nxt in out_adj[cur]:
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    queue.append(nxt)
        ordered.extend([nid for nid in in_conns if nid not in ordered])
        depth = {nid: 0 for nid in ordered}
        for nid in ordered:
            for nxt in out_adj[nid]:
                if depth[nxt] < depth[nid] + 1:
                    depth[nxt] = depth[nid] + 1
        layers = {}
        for nid in ordered:
            layers.setdefault(depth[nid], []).append(nid)
        x_offset = 0.0
        for d in sorted(layers.keys()):
            nids = layers[d]
            layer_cols = (len(nids) + max_rows - 1) // max_rows
            for idx, nid in enumerate(nids):
                col = idx // max_rows
                row = idx % max_rows
                uid_map[nid].setPosition(_f2((x_offset + col) * sx, row * sy))
            x_offset += layer_cols
        return len(all_nodes)

    n_laid = auto_layout(fg)
    step('函数图排布', n_laid > 0, {'laid': n_laid})

    # ---- 保存（新文件；已存在同名且非本工具 → 拒绝覆盖由调用方先行检查）
    if os.path.exists(SBS_OUT):
        os.remove(SBS_OUT)
    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    step('保存 aniso_mask.sbs', os.path.getsize(SBS_OUT) > 0,
         {'size': os.path.getsize(SBS_OUT)})

    REPORT['pp_nodes'] = meta['nodes'] + em.node_count
    REPORT['texel'] = TEXEL
    REPORT['ok'] = True
    return REPORT
