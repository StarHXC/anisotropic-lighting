# -*- coding: utf-8 -*-
r"""Stage 3 — PP2 输出级：曝光/Reinhard/sRGB/validityFill（output.frag 对应）。

wrapper 重建 v4：PP1（主链参数读取版）→ PP2（输出级）→ wrapper output。
v4：34 参数（06 调试组移除）；float3 颜色参数用 Color(RGB) 编辑器
（editor='color' + valueInterpretation='color'，取自官方 3d_texture_render.sbs
资源注解）；texel 由 bake_position.png 实际尺寸派生（构建期常数）。
输出：sd/aniso_lightmap.sbs（v4）+ sd/validation/stage3_report.json
"""
import json
import math
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.') or k == 'stages']:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'stage3_report.json')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')
BAKE_ROOT = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'

report = {'probe': 'stage3', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'stage3 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import (SDPropertyCategory,
                                   SDPropertyInheritanceMethod)
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdtypefloat import SDTypeFloat
    from sd.api.sdtypeint import SDTypeInt
    from sd.api.sdtypefloat3 import SDTypeFloat3
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluebool import SDValueBool
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdbasetypes import float3
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.params import PARAMS
    from aniso_pp.emitter import Emitter, NodeRef
    import stages

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('aniso_lightmap')
    try:
        wrapper.setDefaultParentSize(int2(11, 11))
    except BaseException:
        pass
    step('wrapper graph v3', wrapper is not None)

    # 颜色参数集合（Color(RGB) 编辑器；方向/位置 float3 不算颜色）
    COLOR_IDS = {'p_light_color', 'p_ambient_color', 'p_spec1_color',
                 'p_spec2_color', 'p_diffuse_color'}

    reg_ok = 0
    for p in PARAMS:
        try:
            if p.ptype == 'float1':
                sd_type = SDTypeFloat.sNew()
                sd_value = SDValueFloat.sNew(float(p.default))
            elif p.ptype == 'int':
                sd_type = SDTypeInt.sNew()
                sd_value = SDValueInt.sNew(int(p.default))
            elif p.ptype == 'float3':
                sd_type = SDTypeFloat3.sNew()
                sd_value = SDValueFloat3.sNew(float3(*[float(c)
                                                       for c in p.default]))
            else:
                continue
            prop = wrapper.newProperty(p.pid, sd_type, SDPropertyCategory.Input)
            wrapper.setPropertyValue(prop, sd_value)
            if hasattr(wrapper, 'setPropertyAnnotationValueFromId'):
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'group', SDValueString.sNew(p.group))
                if p.ptype == 'float3' and p.pid in COLOR_IDS:
                    # Color(RGB) 编辑器：API 层只设 editor（valueInterpretation/
                    # min/max 注解 API 拒设——colortest 实测 ItemNotFound/
                    # InvalidValue），保存后 XML 后处理补齐（见文末）
                    wrapper.setPropertyAnnotationValueFromId(
                        prop, 'editor', SDValueString.sNew('color'))
                elif p.ui_min is not None and p.ui_max is not None:
                    wrapper.setPropertyAnnotationValueFromId(
                        prop, 'editor', SDValueString.sNew('slider'))
                    if p.ptype == 'int':
                        wrapper.setPropertyAnnotationValueFromId(
                            prop, 'min', SDValueInt.sNew(int(p.ui_min)))
                        wrapper.setPropertyAnnotationValueFromId(
                            prop, 'max', SDValueInt.sNew(int(p.ui_max)))
                        wrapper.setPropertyAnnotationValueFromId(
                            prop, 'step',
                            SDValueInt.sNew(max(1, int(round(p.step)))))
                    else:
                        wrapper.setPropertyAnnotationValueFromId(
                            prop, 'min', SDValueFloat.sNew(float(p.ui_min)))
                        wrapper.setPropertyAnnotationValueFromId(
                            prop, 'max', SDValueFloat.sNew(float(p.ui_max)))
                        wrapper.setPropertyAnnotationValueFromId(
                            prop, 'step', SDValueFloat.sNew(float(p.step)))
                    wrapper.setPropertyAnnotationValueFromId(
                        prop, 'clamp', SDValueBool.sNew(bool(p.clamp)))
            reg_ok += 1
        except BaseException as e:
            print(f'[WARN] {p.pid}: {e!r}')
    step('34 参数注册', reg_ok == len(PARAMS), {'registered': reg_ok})

    bmp_names = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
    bmp_nodes = []
    for idx, name in enumerate(bmp_names):
        fpath = os.path.join(BAKE_ROOT, f'{name}.png')
        resource = SDResourceBitmap.sNewFromFile(pkg, fpath,
                                                 EmbedMethod.CopiedAndLinked)
        resource.setIdentifier(f'src_{name}')
        node = wrapper.newInstanceNode(resource)
        node.setPosition(float2(-600.0, float(idx) * 250.0))
        for prop_id, val in (('$outputsize', SDValueInt2.sNew(int2(11, 11))),
                             ('$format', SDValueInt.sNew(3))):
            prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
            node.setPropertyInheritanceMethod(
                prop, SDPropertyInheritanceMethod.Absolute)
            node.setPropertyValue(prop, val)
        bmp_nodes.append(node)
    step('4 bitmap 导入', len(bmp_nodes) == 4)

    # texel 由位置图实际尺寸派生（构建期常数；迁移稿：非艺术滑块）
    # PNG 尺寸直接读 IHDR（SD 宿主 Python 无 imageio/PIL）
    import struct as _struct
    _pos_png = os.path.join(BAKE_ROOT, 'bake_position.png')
    with open(_pos_png, 'rb') as _fh:
        _hdr = _fh.read(24)
    if _hdr[:8] != b'\x89PNG\r\n\x1a\n' or _hdr[12:16] != b'IHDR':
        raise RuntimeError(f'不是合法 PNG: {_pos_png}')
    pos_w, pos_h = _struct.unpack('>II', _hdr[16:24])
    TEXEL_U, TEXEL_V = 1.0 / pos_w, 1.0 / pos_h
    step('texel 派生', pos_w > 0 and pos_h > 0,
         {'size': (pos_w, pos_h), 'texel': (TEXEL_U, TEXEL_V)})

    _scalar_map = {p.pid: p for p in PARAMS if p.ptype != 'float3'}
    _f3_map = {p.pid: p for p in PARAMS if p.ptype == 'float3'}

    def make_resolver(fg):
        def resolve_scalar(pid):
            full = pid if pid.startswith('p_') else f'p_{pid}'
            p = _scalar_map[full]
            if p.ptype == 'int':
                gi = fg.newNode('sbs::function::get_integer1')
                gi.setInputPropertyValueFromId('__constant__',
                                               SDValueString.sNew(full))
                tf = fg.newNode('sbs::function::tofloat')
                SDAPI.fg_connect(NodeRef(gi, 'f1'), tf, 'value')
                return NodeRef(tf, 'f1')
            gf = fg.newNode('sbs::function::get_float1')
            gf.setInputPropertyValueFromId('__constant__',
                                           SDValueString.sNew(full))
            return NodeRef(gf, 'f1')

        def resolve_f3(pid):
            full = pid if pid.startswith('p_') else f'p_{pid}'
            gf3 = fg.newNode('sbs::function::get_float3')
            gf3.setInputPropertyValueFromId('__constant__',
                                            SDValueString.sNew(full))
            return NodeRef(gf3, 'f3')

        def resolver(pid):
            full = pid if pid.startswith('p_') else f'p_{pid}'
            if full in _f3_map:
                return resolve_f3(pid)
            return resolve_scalar(pid)
        return resolver

    pp1, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp1.setPosition(float2(300.0, 0.0))
    for node in bmp_nodes:
        SDAPI.connect_pp_input(node, pp1)
    fg1, _ = SDAPI.get_perpixel_graph(pp1)
    packed1, meta1 = stages.build_core(fg1, texel=TEXEL_U,
                                       param_resolver=make_resolver(fg1))
    fg1.setOutputNode(packed1.node, True)
    step('PP1 主链发射', True, {'fg_nodes': meta1['nodes']})

    # ---- PP2（output.frag 对应；§6 配方）
    pp2, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp2.setPosition(float2(900.0, 0.0))
    SDAPI.connect_pp_input(pp1, pp2)

    fg2, _ = SDAPI.get_perpixel_graph(pp2)
    em2 = Emitter(fg2, cache_scope='stage3_pp2')
    pos2 = SDAPI.get_pos_node(fg2)
    lin = NodeRef(SDAPI.samplecol_node(fg2, pos2, 0), 'f4')

    resolver2 = make_resolver(fg2)
    ev = resolver2('exposure_ev')
    vfill = resolver2('validity_fill')

    # max(linear.rgb, 0)：f3 逐分量（用 mulscalar+cmp 展开或 max 同型 f3）
    lin_rgb = em2.swizzle3_from_f4(lin)
    zero3 = em2.bc_f3(em2.c_f1(0.0))
    c_pos = em2.max_f3(lin_rgb, zero3)
    c = em2.mul(c_pos, em2.pow(em2.c_f1(2.0), ev))
    ldr = em2.div(c, em2.add(c, em2.bc_f3(em2.c_f1(1.0))))
    srgb = em2.v3(em2.linear_to_srgb_f1(em2.sw1(ldr, 0)),
                 em2.linear_to_srgb_f1(em2.sw1(ldr, 1)),
                 em2.linear_to_srgb_f1(em2.sw1(ldr, 2)))
    valid = em2.step(em2.c_f1(0.5), em2.sw1(lin, 3))
    out_rgb = em2.lerp(em2.bc_f3(vfill), srgb, valid)
    packed2 = em2.v4_from_f3(out_rgb, em2.c_f1(1.0))  # output.frag:39 A=1.0
    fg2.setOutputNode(packed2.node, True)
    step('PP2 输出级发射', True, {'fg_nodes': em2.node_count})

    out_node = wrapper.newNode('sbs::compositing::output')
    out_node.setPosition(float2(1500.0, 0.0))
    pp2.newPropertyConnectionFromId('unique_filter_output', out_node,
                                    'inputNodeOutput')
    wrapper.setOutputNode(out_node, True)
    step('wrapper output → PP2', True)

    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    step('保存 aniso_lightmap.sbs v4', os.path.getsize(SBS_OUT) > 0,
         {'size': os.path.getsize(SBS_OUT)})

    # ---- XML 后处理：为颜色参数补 valueInterpretation/min/max 注解 ----
    # （API 拒设，colortest 实测；格式对照官方 3d_texture_render.sbs defaultWidget）
    _xml = open(SBS_OUT, encoding='utf-8').read()
    _patched = 0
    for _cid in sorted(COLOR_IDS):
        _old = (f'<identifier v="{_cid}"/>')
        _i = _xml.find(_old)
        if _i < 0:
            continue
        # 该 paraminput 的 defaultWidget 已含 editor=color（API 写入）；
        # 在其 </defaultWidget> 前补 option（仅首个命中 = 参数定义处）
        _j = _xml.find('</defaultWidget>', _i)
        if _j < 0 or _j - _i > 2000:
            continue
        _ins = ('<option><name v="valueInterpretation"/><value v="color"/>'
                '</option>'
                '<option><name v="max"/><value v="1000;1000;1000"/></option>'
                '<option><name v="min"/><value v="0;0;0"/></option>')
        _xml = _xml[:_j] + _ins + _xml[_j:]
        _patched += 1
    if _patched:
        open(SBS_OUT, 'w', encoding='utf-8').write(_xml)
    step('颜色注解 XML 补写', _patched == len(COLOR_IDS),
         {'patched': _patched, 'of': len(COLOR_IDS)})

    report['pp1_nodes'] = meta1['nodes']
    report['pp2_nodes'] = em2.node_count
    report['color_patch'] = _patched
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
