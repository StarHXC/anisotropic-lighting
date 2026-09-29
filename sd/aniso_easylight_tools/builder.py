# -*- coding: utf-8 -*-
r"""aniso_easylight 正式包构建（build_aniso_easylight.py 的引擎）。

范式模板 = aniso_mask_tools/mask_builder.py（已验证交付）：
  - 新 wrapper identifier=aniso_easylight、11 参数注册（group/slider 注解；
    int 属性注解用 SDValueInt——stage3_pp2.py 模式）
  - 4 bitmap 复制旧 SBS 真实绑定 filename → 独立 aniso_easylight.resources/
  - 灰度 PP（colorswitch=False，2048² Raw 32F）
  - resolver：11 活参数 → get_float1 / get_integer1+tofloat；
    冻结项 → em.c_f1 / em.v3 图内常数；未知 pid 报错
  - stages.build_core 完整复用（KK/翻转/差分/validity 链原文）→ packed(f4)
  - 灰度尾部：gray = dot(rgb, luma) × step(0.5, validity)
  - auto_layout → savePackageAs

不 import stage3_pp2（顶层会重建旧 SBS）；不扩 stages.py（packed 消费者路径）。
"""
from __future__ import annotations

import os
import re
import struct

SD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_SBS = os.path.join(SD_DIR, 'aniso_lightmap.sbs')
OLD_RES = os.path.join(SD_DIR, 'aniso_lightmap.resources')
SBS_OUT = os.path.join(SD_DIR, 'aniso_easylight.sbs')

REPORT = {'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'aniso_easylight 构建失败于: {name}  ({detail})')


def parse_old_bindings():
    """旧 SBS XML → bitmap 资源 identifier → filename 映射（mask_builder 同款）。"""
    xml = open(OLD_SBS, encoding='utf-8').read()
    binds = {}
    for m in re.finditer(
            r'<resource><identifier v="([^"]+)"/>.*?'
            r'<externalcopy><filename v="([^"]+)"/></externalcopy>',
            xml, re.S):
        binds[m.group(1)] = m.group(2)
    return binds


def resolve_bitmap_files():
    """真实绑定 filename → 磁盘绝对路径。槽位固定（§4.2）：
    0=position 1=normalobj 2=coverage 3=AO。"""
    binds = parse_old_bindings()
    files = {}
    for rid, fname in binds.items():
        p = os.path.join(OLD_RES, os.path.basename(fname))
        if not os.path.exists(p):
            raise RuntimeError(f'绑定资源缺失: {rid} → {p}')
        files[rid] = p
    order = [('src_bake_position', 0), ('src_bake_normalobj', 1),
             ('src_mask1', 2), ('src_bake_ao', 3)]
    slots = [None, None, None, None]
    for rid, idx in order:
        if rid not in files:
            raise RuntimeError(f'旧包缺少槽位资源: {rid}（实际: {sorted(files)}）')
        slots[idx] = files[rid]
    return slots


def build():
    """构建并保存 aniso_easylight.sbs。返回 REPORT。"""
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluebool import SDValueBool
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdtypefloat import SDTypeFloat
    from sd.api.sdtypeint import SDTypeInt
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    import stages
    from aniso_easylight_tools import schema as sch

    step('环境', True, {'sd_api_version': SDAPI.app_version(),
                        'easylight_version': sch.EASYLIGHT_VERSION})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- 槽位资源解析
    slots = resolve_bitmap_files()
    step('旧绑定解析（真实 filename）', len(slots) == 4,
         {i: os.path.basename(p) for i, p in enumerate(slots)})

    # ---- 新包
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier(sch.WRAPPER_ID)
    try:
        wrapper.setDefaultParentSize(int2(11, 11))
    except BaseException:
        pass
    step(f'wrapper {sch.WRAPPER_ID}', wrapper is not None)

    # ---- 11 参数注册（group/slider 注解；int 属性注解用 SDValueInt）
    PD = sch.param_defaults()
    reg_ok = 0
    for pid, label, default, mn, mx, group, st in sch.PARAMS:
        is_int = pid in sch.INT_PIDS
        if is_int:
            prop = wrapper.newProperty(pid, SDTypeInt.sNew(),
                                       SDPropertyCategory.Input)
            wrapper.setPropertyValue(prop, SDValueInt.sNew(int(PD[pid])))
        else:
            prop = wrapper.newProperty(pid, SDTypeFloat.sNew(),
                                       SDPropertyCategory.Input)
            wrapper.setPropertyValue(prop, SDValueFloat.sNew(float(PD[pid])))
        if hasattr(wrapper, 'setPropertyAnnotationValueFromId'):
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'group', SDValueString.sNew(group))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'editor', SDValueString.sNew('slider'))
            if is_int:
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'min', SDValueInt.sNew(int(mn)))
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'max', SDValueInt.sNew(int(mx)))
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'step', SDValueInt.sNew(max(1, int(round(st)))))
            else:
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'min', SDValueFloat.sNew(float(mn)))
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'max', SDValueFloat.sNew(float(mx)))
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'step', SDValueFloat.sNew(float(st)))
            wrapper.setPropertyAnnotationValueFromId(
                prop, 'clamp', SDValueBool.sNew(True))
        reg_ok += 1
    step('11 参数注册（group/slider）', reg_ok == len(sch.PARAMS),
         {'count': reg_ok})

    # ---- 4 bitmap（CopiedAndLinked → 独立 resources；Absolute 尺寸）
    bmp_names = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
    bmp_nodes = []
    for idx, fpath in enumerate(slots):
        res = SDResourceBitmap.sNewFromFile(pkg, fpath,
                                            EmbedMethod.CopiedAndLinked)
        res.setIdentifier(f'src_{bmp_names[idx]}')
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(-700.0, float(idx) * 260.0))
        for prop_id, val in (('$outputsize', SDValueInt2.sNew(int2(11, 11))),
                             ('$format', SDValueInt.sNew(3))):
            prop = n.getPropertyFromId(prop_id, SDPropertyCategory.Input)
            n.setPropertyInheritanceMethod(prop,
                                           SDPropertyInheritanceMethod.Absolute)
            n.setPropertyValue(prop, val)
        bmp_nodes.append(n)
    step('4 bitmap 内嵌（独立 resources）', len(bmp_nodes) == 4)

    # ---- texel 由位置图实际尺寸派生（PNG IHDR；构建期常数）
    with open(slots[0], 'rb') as fh:
        hdr = fh.read(24)
    if hdr[:8] != b'\x89PNG\r\n\x1a\n' or hdr[12:16] != b'IHDR':
        raise RuntimeError(f'位置图不是合法 PNG: {slots[0]}')
    pw, ph = struct.unpack('>II', hdr[16:24])
    TEXEL = 1.0 / pw
    step('texel 派生', pw == ph and pw > 0, {'size': (pw, ph), 'texel': TEXEL})

    # ---- 灰度 PP（colorswitch=False；mask 同款契约）
    pp, ev = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=11)
    pp.setPosition(float2(300.0, 0.0))
    for n in bmp_nodes:
        SDAPI.connect_pp_input(n, pp)
    step('灰度 PP（colorswitch=False, 2048²）',
         ev['colorswitch'] is False and ev['outputsize_log2'] == (11, 11), ev)

    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='aniso_easylight_core')

    # ---- resolver：11 活参数 → get 节点；冻结项 → 图内常数
    def _get_f1(full_pid):
        gf = fg.newNode('sbs::function::get_float1')
        gf.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full_pid))
        return NodeRef(gf, 'f1')

    def _get_int_as_f1(full_pid):
        gi = fg.newNode('sbs::function::get_integer1')
        gi.setInputPropertyValueFromId('__constant__', SDValueString.sNew(full_pid))
        tf = fg.newNode('sbs::function::tofloat')
        SDAPI.fg_connect(NodeRef(gi, 'f1'), tf, 'value')
        return NodeRef(tf, 'f1')

    # 面板 pid 集合的无前缀形式（build_core 用短名调 resolver）
    EXPOSED_BASE = {pid[2:] for pid in sch.EXPOSED_PIDS}

    def resolver(pid):
        base = pid[2:] if pid.startswith('p_') else pid
        # 活参数：新面板直接读（ao_direct_light → 面板 p_ao_direct）
        panel_pid = ('p_' + sch.EXPOSED_MAP[base]) if base in sch.EXPOSED_MAP \
            else ('p_' + base if base in EXPOSED_BASE else None)
        if panel_pid is not None:
            return (_get_int_as_f1(panel_pid) if panel_pid in sch.INT_PIDS
                    else _get_f1(panel_pid))
        # 冻结常数（FREEZE_CONSTANTS 键为无前缀旧名）
        if base in sch.FREEZE_CONSTANTS:
            v = sch.FREEZE_CONSTANTS[base]
            if isinstance(v, (tuple, list)):
                return em.v3(em.c_f1(float(v[0])), em.c_f1(float(v[1])),
                             em.c_f1(float(v[2])))
            return em.c_f1(float(v))
        raise RuntimeError(f'未知旧参数 pid: {pid}')

    # ---- core 完整复用（packed = linear.rgb + validity.a）
    packed, meta = stages.build_core(fg, texel=TEXEL, param_resolver=resolver)
    step('core 发射（KK 链原文复用）', True, {'nodes': meta['nodes']})

    # ---- 灰度尾部：gray = dot(rgb, luma)；out = gray × step(0.5, validity)
    lin_rgb = em.swizzle3_from_f4(packed)
    luma = em.mul(em.sw1(lin_rgb, 0), em.c_f1(0.2126))
    luma = em.add(luma, em.mul(em.sw1(lin_rgb, 1), em.c_f1(0.7152)))
    luma = em.add(luma, em.mul(em.sw1(lin_rgb, 2), em.c_f1(0.0722)))
    valid = em.step(em.c_f1(0.5), em.sw1(packed, 3))
    out = em.mul(luma, valid)
    fg.setOutputNode(out.node, True)
    step('灰度尾部（luma × validity 门控）', True)

    # ---- wrapper output
    out_node = wrapper.newNode('sbs::compositing::output')
    out_node.setPosition(float2(900.0, 0.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    wrapper.setOutputNode(out_node, True)
    step('wrapper output', True)

    # ---- 函数图排布（stage3/mask 同款 auto_layout）
    def auto_layout(fg_, max_rows=6, sx=220.0, sy=140.0):
        nodes_arr = fg_.getNodes()
        all_nodes = [nodes_arr.getItem(i) for i in range(nodes_arr.getSize())]
        if not all_nodes:
            return 0
        uid_map = {id(n): n for n in all_nodes}
        in_conns = {id(n): set() for n in all_nodes}
        out_adj = {id(n): [] for n in all_nodes}
        for n in all_nodes:
            props = n.getProperties(SDPropertyCategory.Input)
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
                uid_map[nid].setPosition(float2((x_offset + col) * sx,
                                                row * sy))
            x_offset += layer_cols
        return len(all_nodes)

    n_laid = auto_layout(fg)
    step('函数图排布', n_laid > 0, {'laid': n_laid})

    # ---- 保存（重跑前删旧文件）
    if os.path.exists(SBS_OUT):
        os.remove(SBS_OUT)
    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    step('保存 aniso_easylight.sbs', os.path.getsize(SBS_OUT) > 0,
         {'size': os.path.getsize(SBS_OUT)})

    REPORT['pp_nodes'] = meta['nodes']
    REPORT['texel'] = TEXEL
    REPORT['params'] = len(sch.PARAMS)
    REPORT['ok'] = True
    return REPORT
