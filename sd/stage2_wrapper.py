# -*- coding: utf-8 -*-
r"""Stage 2 wrapper（方案 C）— 生成 aniso_lightmap.sbs：
  wrapper comp graph 内含 [4 bitmap(CopiedAndLinked) → 主链 PP(参数读取版)] → output
  41 参数注册在 wrapper 图层（实例面板可调）。

图输入 API 缺口（0D3 系列实验）：Python API 无法创建 image 类型图输入
（SDTypeTexture/Usage 均 InvalidType；paraminput type 1/2 无法经 API 生成）。
故 wrapper 的贴图输入用 bitmap 资源直连（CopiedAndLinked），换资产=重跑本脚本。

输出：sd/aniso_lightmap.sbs + sd/validation/stage2_wrapper_report.json
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
REPORT_PATH = os.path.join(VAL_DIR, 'stage2_wrapper_report.json')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')
BAKE_ROOT = r'D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake'

report = {'probe': 'stage2_wrapper', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'stage2 失败于: {name}  ({detail})')


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

    step('环境', True, {'sd_api_version': SDAPI.app_version()})

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- 1. wrapper graph
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('aniso_lightmap')
    # wrapper 默认父尺寸设为 2048（避免 bitmap 默认 256 缩水）
    try:
        wrapper.setDefaultParentSize(int2(11, 11))
    except BaseException:
        pass
    step('wrapper graph', wrapper is not None)

    # ---- 2. 41 参数
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
            if prop is None:
                raise RuntimeError('newProperty None')
            wrapper.setPropertyValue(prop, sd_value)
            if hasattr(wrapper, 'setPropertyAnnotationValueFromId'):
                wrapper.setPropertyAnnotationValueFromId(
                    prop, 'group', SDValueString.sNew(p.group))
                if p.ui_min is not None and p.ui_max is not None:
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
            report['steps'].append({'step': f'参数 {p.pid}', 'ok': False,
                                    'detail': repr(e)[:120]})
            print(f'[WARN] 参数 {p.pid}: {e!r}')
    step('41 参数注册', reg_ok == len(PARAMS), {'registered': reg_ok})

    # ---- 3. 4 bitmap 资源导入（CopiedAndLinked → 相对路径可移植）
    bmp_names = ['bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
    bmp_nodes = []
    for idx, name in enumerate(bmp_names):
        fpath = os.path.join(BAKE_ROOT, f'{name}.png')
        resource = SDResourceBitmap.sNewFromFile(folder=None, filepath=fpath,
                                                 embed=EmbedMethod.CopiedAndLinked,
                                                 parent=pkg) if False else \
            SDResourceBitmap.sNewFromFile(pkg, fpath,
                                          EmbedMethod.CopiedAndLinked)
        resource.setIdentifier(f'src_{name}')
        node = wrapper.newInstanceNode(resource)
        node.setPosition(float2(-600.0, float(idx) * 250.0))
        # 显式 2048²/32F（0B/Stage1 关键修复）
        for prop_id, val in (('$outputsize', SDValueInt2.sNew(int2(11, 11))),
                             ('$format', SDValueInt.sNew(3))):
            prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
            node.setPropertyInheritanceMethod(
                prop, SDPropertyInheritanceMethod.Absolute)
            node.setPropertyValue(prop, val)
        bmp_nodes.append(node)
    step('4 bitmap 导入（CopiedAndLinked + 2048²/32F）', len(bmp_nodes) == 4)

    # ---- 4. 主链 PP（核心链发射；函数图内参数读取留待 A2——先常数快照版）
    pp, ev = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=11)
    pp.setPosition(float2(300.0, 0.0))
    step('主链 PP 创建', True, ev)

    for idx, node in enumerate(bmp_nodes):
        SDAPI.connect_pp_input(node, pp)

    # ---- 5. 核心链发射（参数读取版：函数图内 get_float1/get_integer1/get_float3
    #      读 wrapper 图层参数 —— 0A 裁定的参数载体 + 0D 验证的读取链）
    from aniso_pp.emitter import Emitter, NodeRef
    from sd.api.sdvaluestring import SDValueString as _SVS
    import stages

    fg, created = SDAPI.get_perpixel_graph(pp)

    _scalar_map = {p.pid: p for p in PARAMS if p.ptype != 'float3'}
    _f3_map = {p.pid: p for p in PARAMS if p.ptype == 'float3'}

    def resolve_scalar(pid: str) -> NodeRef:
        """标量参数 → get 节点。int 参数走 get_integer1→tofloat。
        stages 传短名（'aniso_axis'）→ 补 p_ 前缀。"""
        full = pid if pid.startswith('p_') else f'p_{pid}'
        p = _scalar_map[full]
        if p.ptype == 'int':
            gi = fg.newNode('sbs::function::get_integer1')
            gi.setInputPropertyValueFromId('__constant__',
                                           _SVS.sNew(full))
            tf = fg.newNode('sbs::function::tofloat')
            SDAPI.fg_connect(NodeRef(gi, 'f1'), tf, 'value')
            return NodeRef(tf, 'f1')
        gf = fg.newNode('sbs::function::get_float1')
        gf.setInputPropertyValueFromId('__constant__', _SVS.sNew(full))
        return NodeRef(gf, 'f1')

    def resolve_f3(pid: str) -> NodeRef:
        full = pid if pid.startswith('p_') else f'p_{pid}'
        gf3 = fg.newNode('sbs::function::get_float3')
        gf3.setInputPropertyValueFromId('__constant__', _SVS.sNew(full))
        return NodeRef(gf3, 'f3')

    def resolver(pid: str) -> NodeRef:
        full = pid if pid.startswith('p_') else f'p_{pid}'
        if full in _f3_map:
            return resolve_f3(pid)
        return resolve_scalar(pid)

    # debug_mode 的 get_integer1→tofloat 是 f1，但 stages 级联用 cmp('gteq',
    # dbg_f, …) 比较 —— f1 兼容 ✓。spec_layer_index/aniso_axis 同理。
    packed, meta = stages.build_core(fg, param_resolver=resolver)
    fg.setOutputNode(packed.node, True)
    step('核心链发射（参数读取版）', True, {'fg_nodes': meta['nodes']})

    # ---- 6. wrapper output（必须 setOutputNode 标记为图输出，否则实例求值 None）
    out_node = wrapper.newNode('sbs::compositing::output')
    out_node.setPosition(float2(900.0, 0.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                   'inputNodeOutput')
    wrapper.setOutputNode(out_node, True)
    step('wrapper output（setOutputNode 标记）', True)

    # ---- 7. 保存
    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    step('保存 aniso_lightmap.sbs', os.path.getsize(SBS_OUT) > 0,
         {'path': SBS_OUT, 'size': os.path.getsize(SBS_OUT)})

    report['sbs_path'] = SBS_OUT
    report['fg_nodes'] = meta['nodes']
    report['manual_checks'] = [
        f'① 删除 test graph 里旧的 aniso_lightmap 实例，重新导入 {SBS_OUT}'
        '（File → Import 覆盖）并拖入新实例。',
        '② 拖动 01_光照方向 组的 p_light_azimuth_deg 滑块：高光方位应实时变化。',
        '③ 拖动 06_调试与系统 组的 p_debug_mode（0-9）：切换调试视图。',
        '④ 全部调参实时生效（函数图内 get 节点直读参数）。',
    ]
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
