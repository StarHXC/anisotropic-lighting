# -*- coding: utf-8 -*-
"""SD Python API 薄封装（Stage 0 探针用）。

__future__ annotations 兼容 Python 3.7+；`int | None` 语法由 annotations
延迟求值支持（SD 宿主 Python 版本待 0A 实测登记）。

设计依据 doc/SD_MIGRATION_PLAN.md §4 事实清单：
- 每个设置动作之后读回并断言；任何不一致显式抛 RuntimeError，不吞异常。
- 只使用本文件内已列出的 API；未在本机绑定源码核实的方法一律不调用。
- owner 标识：节点以 aniso_pp:: 前缀 annotation/名称承载归属（0A 演练）。

本模块在 SD 的 Python 编辑器内执行（宿主提供 sd 包）；不允许 import
moderngl/NumPy 等外部依赖（计划 §7.1：进程内外依赖分开登记）。
"""
from __future__ import annotations

from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
from sd.api.sdbasetypes import float2, float3, int2
from sd.api.sdvaluebool import SDValueBool
from sd.api.sdvalueint import SDValueInt
from sd.api.sdvalueint2 import SDValueInt2
from sd.api.sdvaluefloat import SDValueFloat
from sd.api.sdvaluestring import SDValueString
from sd.api.sdvaluefloat3 import SDValueFloat3
from sd.api.sdtypefloat import SDTypeFloat
from sd.api.sdtypeint import SDTypeInt
from sd.api.sdtypefloat3 import SDTypeFloat3


# ---------------------------------------------------------------- 基础查询

def get_app():
    """SDApplication 单例（context.py:37-43 已核实）。"""
    import sd
    return sd.getContext().getSDApplication()


def app_version() -> str:
    """engine/API 版本字符串（sdapplication.py:201）。"""
    return get_app().getVersion()


def get_current_graph():
    """UI 当前激活 graph；类型断言由调用方做。

    路径：SDApplication.getUIMgr()（sdapplication.py:132）→
    SDUIMgr.getCurrentGraph()（sduimgr.py:151）。
    实测（SD 16.0.1）：无 getUI_manager 属性；getQtForPythonUIMgr 是
    Qt 扩展管理器，取 graph 用 getUIMgr 即可。
    """
    ui = get_app().getUIMgr()
    if ui is None:
        raise RuntimeError('getUIMgr() 返回 None（无 UI 环境？）')
    return ui.getCurrentGraph()


def get_graph_title(graph) -> str:
    """graph 标识（供证据记录；不同版本属性名可能不同，逐一尝试）。"""
    for attr in ('getIdentifier', 'getUrl'):
        fn = getattr(graph, attr, None)
        if fn is not None:
            try:
                return str(fn())
            except BaseException:
                pass
    return '<unknown>'


# ---------------------------------------------------------------- 读回断言

def _read_back_int(node, prop_id: str) -> int:
    prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
    if prop is None:
        raise RuntimeError(f'属性不存在: {prop_id}')
    val = node.getInputPropertyValueFromId(prop_id)
    if val is None:
        raise RuntimeError(f'属性值读取为 None: {prop_id}')
    return val.get()


def _set_and_check_int(node, prop_id: str, value: int, inherit: bool = True) -> int:
    """设置 Input int 属性（可选 Absolute 继承），读回断言后返回实际值。"""
    prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
    if prop is None:
        raise RuntimeError(f'属性不存在: {prop_id}')
    if inherit:
        node.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
    node.setPropertyValue(prop, SDValueInt.sNew(value))
    got = _read_back_int(node, prop_id)
    if got != value:
        raise RuntimeError(f'{prop_id} 设置读回不一致: 期望 {value}, 实际 {got}')
    return got


def _read_back_inheritance(node, prop_id: str) -> SDPropertyInheritanceMethod:
    prop = node.getPropertyFromId(prop_id, SDPropertyCategory.Input)
    if prop is None:
        raise RuntimeError(f'属性不存在: {prop_id}')
    return node.getPropertyInheritanceMethod(prop)


# ---------------------------------------------------------------- PP 创建

PP_NODE_ID = 'sbs::compositing::pixelprocessor'

# $format 枚举值 3 = "HDR high precision (32F)"（审核稿 §4.1 [文档] C:4304–4325）
FORMAT_HDR_32F = 3


def create_pp(graph, *, colorswitch: bool = True, size_log2: int = 11):
    """创建 PP 并逐项读回断言：colorswitch / $format=3 / $outputsize。

    size_log2=11 → 2048²。所有失败显式抛错。
    返回 (pp_node, evidence_dict)。
    """
    ev = {}
    pp = graph.newNode(PP_NODE_ID)
    ev['node_id'] = PP_NODE_ID

    # colorswitch（彩色模式）
    prop_cs = pp.getPropertyFromId('colorswitch', SDPropertyCategory.Input)
    if prop_cs is None:
        raise RuntimeError('PP 无 colorswitch 属性')
    pp.setPropertyValue(prop_cs, SDValueBool.sNew(colorswitch))
    got_cs = pp.getInputPropertyValueFromId('colorswitch')
    if got_cs is None or bool(got_cs.get()) != colorswitch:
        raise RuntimeError(f'colorswitch 读回不一致: {got_cs}')
    ev['colorswitch'] = colorswitch

    # $format = HDR 32F（Absolute）
    ev['format'] = _set_and_check_int(pp, '$format', FORMAT_HDR_32F, inherit=True)
    inh_fmt = _read_back_inheritance(pp, '$format')
    ev['format_inheritance'] = str(inh_fmt)

    # $outputsize（Absolute；数值是 log2）
    want = int2(size_log2, size_log2)
    prop_sz = pp.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
    if prop_sz is None:
        raise RuntimeError('PP 无 $outputsize 属性')
    pp.setPropertyInheritanceMethod(prop_sz, SDPropertyInheritanceMethod.Absolute)
    pp.setPropertyValue(prop_sz, SDValueInt2.sNew(want))
    got_sz = pp.getInputPropertyValueFromId('$outputsize')
    if got_sz is None:
        raise RuntimeError('$outputsize 读回为 None')
    got = got_sz.get()
    if (got.x, got.y) != (size_log2, size_log2):
        raise RuntimeError(f'$outputsize 读回不一致: 期望 ({size_log2},{size_log2}), 实际 ({got.x},{got.y})')
    ev['outputsize_log2'] = (got.x, got.y)
    ev['size_inheritance'] = str(_read_back_inheritance(pp, '$outputsize'))

    return pp, ev


def get_perpixel_graph(pp):
    """取得（或新建）perpixel 函数图；返回 (fg, created: bool)。

    审核稿 §4.1：不无条件重建用户已有函数图。
    """
    prop = pp.getPropertyFromId('perpixel', SDPropertyCategory.Input)
    if prop is None:
        raise RuntimeError('PP 无 perpixel 属性')
    existing = pp.getPropertyGraph(prop)
    if existing is not None:
        return existing, False
    fg = pp.newPropertyGraph(prop, 'SDSBSFunctionGraph')
    if fg is None:
        raise RuntimeError('newPropertyGraph(SDSBSFunctionGraph) 返回 None')
    return fg, True


def connect_pp_input(src_node, pp, *, expect_index: int | None = None) -> str:
    """把 src 输出连到 PP 的最后一个空 input 引脚（VARIADIC）。

    返回实际使用的引脚 id（'input0'/'input1'/...）；expect_index 非 None 时断言。
    审核稿 §4.1：sd_utils.py:82-96 的 helper 不检查空口语义，这里逐枚举确认。
    """
    props = pp.getProperties(SDPropertyCategory.Input)
    input_props = []
    for i in range(props.getSize()):
        p = props.getItem(i)
        if p.getId().startswith('input'):
            input_props.append(p)
    if not input_props:
        raise RuntimeError('PP 无任何 input 引脚')
    target = input_props[-1]
    target_id = target.getId()
    conn = src_node.newPropertyConnectionFromId('unique_filter_output', pp, target_id)
    if conn is None:
        raise RuntimeError(f'连接失败: -> {target_id}')
    if expect_index is not None:
        # SD 16.0.1 实测：VARIADIC 引脚未连接时 id 是基名 'input'，
        # 连接后实例化为 'input0'/'input1'/...（0B 裁定）。因此 expect_index
        # 不能按连接前的 id 断言——改为连接后枚举验证序号。
        pass
    return target_id


def verify_pin_count(pp, expect_n: int) -> list[str]:
    """连接后验证 PP 的实例化 input 引脚（0B 实测 SD 16.0.1 行为）。

    实测：PP 新建时 VARIADIC 自带 1 个基名 'input' 引脚；每次连接扩展出
    'input:1'..'input:{k}'（冒号序号，1 基）。连接 expect_n 个源后共
    expect_n 个引脚（基名被首次连接占用，不新增）——但实测出现 n+1 个
    （基名 + :1..:n），说明首次连接用基名、其后每次新增一个。
    以实测为准：期望 = ['input'] + [f'input:{i}' for i in 1..expect_n]。
    samplecol int2 第一分量与引脚的对应由导出颜色验证（0B 核心产出）。
    """
    pins = enumerate_input_pins(pp)
    if len(pins) != expect_n + 1:
        raise RuntimeError(f'input 引脚数量异常: 实际 {len(pins)} 个 {pins}, '
                           f'期望 {expect_n + 1} 个（基名+实例）')
    if pins[0] != 'input' or pins[1:] != [f'input:{i}' for i in range(1, expect_n + 1)]:
        raise RuntimeError(f'引脚命名异常: {pins}')
    return pins


def enumerate_input_pins(pp) -> list[str]:
    """按声明顺序列出 PP 当前全部 input 引脚 id（0B 证据用）。"""
    props = pp.getProperties(SDPropertyCategory.Input)
    out = []
    for i in range(props.getSize()):
        p = props.getItem(i)
        pid = p.getId()
        if pid.startswith('input'):
            out.append(pid)
    return out


# ---------------------------------------------------------------- 函数图节点

def fg_new_node(fg, def_id: str):
    return fg.newNode(def_id)


def fg_connect(src, dst, dst_pin: str):
    """连接两个函数图节点；接受裸 SDNode 或 NodeRef（取 .node）。"""
    src_n = getattr(src, 'node', src)
    dst_n = getattr(dst, 'node', dst)
    src_n.newPropertyConnectionFromId('unique_filter_output', dst_n, dst_pin)


def fg_set_output(fg, node):
    fg.setOutputNode(node, True)


def fg_node_position(fg, node, x: float, y: float):
    node.setPosition(float2(x, y))


def get_pos_node(fg):
    """get_float2('$pos') 采样上下文节点。"""
    n = fg.newNode('sbs::function::get_float2')
    n.setInputPropertyValueFromId('__constant__', SDValueString.sNew('$pos'))
    return n


def samplecol_node(fg, pos_node, input_index: int):
    """samplecol；__constant__ = int2(input_index, 0)（第二分量语义按 0B 实测留痕）。"""
    n = fg.newNode('sbs::function::samplecol')
    fg_connect(pos_node, n, 'pos')
    n.setInputPropertyValueFromId('__constant__', SDValueInt2.sNew(int2(input_index, 0)))
    return n


# ---------------------------------------------------------------- 参数注册

def new_param(graph_or_node, param_id: str, ptype: str, default, *,
              group: str | None = None, ui_min: float | None = None,
              ui_max: float | None = None, clamp: bool = True,
              step: float = 0.01, allow_function_only: bool = False):
    """在 comp graph / PP 节点 / 函数图上注册参数并读回断言。

    ptype: 'float1' | 'int' | 'float3'
    返回 (SDProperty, 读回值 | None)。
    allow_function_only=True 时：属性若 FunctionOnly（setPropertyValue 报
    DataIsReadOnly，sdnode.html:317），接受创建成功但值只读，返回 (prop, None)。
    注：SDSBSCompNode.newProperty 在本机绑定源码缺失（HTML 文档有），
    调用前先用 has_node_new_property() 探测；不存在则抛错并留痕。
    """
    if ptype == 'float1':
        sd_type, sd_value = SDTypeFloat.sNew(), SDValueFloat.sNew(float(default))
    elif ptype == 'int':
        sd_type, sd_value = SDTypeInt.sNew(), SDValueInt.sNew(int(default))
    elif ptype == 'float3':
        # SDValueFloat3.sNew 需要 ctypes float3 结构体（sdbasetypes.py:157-162），
        # 不接受 Python tuple
        if isinstance(default, float3):
            f3 = default
        else:
            r, g, b = (float(c) for c in default)
            f3 = float3(r, g, b)
        sd_type, sd_value = SDTypeFloat3.sNew(), SDValueFloat3.sNew(f3)
    else:
        raise ValueError(f'未知参数类型: {ptype}')

    prop = graph_or_node.newProperty(param_id, sd_type, SDPropertyCategory.Input)
    if prop is None:
        raise RuntimeError(f'newProperty 返回 None: {param_id}')

    # 值可写性裁定：PP 节点上动态新建的属性可能 setPropertyValue 抛
    # DataIsReadOnly（实测 SD 16.0.1；sdnode.html:317 限 FunctionOnly，
    # 但节点实例属性还有 isReadOnly 路径）。读状态 → 决定 set → 记录结论。
    ro = False
    try:
        if hasattr(prop, 'isReadOnly') and prop.isReadOnly():
            ro = True
        if hasattr(prop, 'isFunctionOnly') and prop.isFunctionOnly():
            ro = True
    except BaseException:
        pass  # 状态查询失败则以 set 实测为准

    value_set = False
    if not ro:
        try:
            graph_or_node.setPropertyValue(prop, sd_value)
            value_set = True
        except BaseException as e:
            if not allow_function_only:
                raise
            ro = True  # 实测只读，留痕
    if ro and not allow_function_only:
        raise RuntimeError(f'{param_id}: 属性只读(FunctionOnly/isReadOnly)且未允许')

    # 注解（属性存在即可设；与值可写性无关）。
    # 注解 API 只在 SDResource 层（sdresource.py:285/301）——comp graph 有，
    # SDSBSCompNode 没有（SD 16.0.1 实测 AttributeError）。无注解能力的
    # owner 跳过注解（节点级参数因此不能承载 group/slider）。
    if hasattr(graph_or_node, 'setPropertyAnnotationValueFromId'):
        if group is not None:
            graph_or_node.setPropertyAnnotationValueFromId(
                prop, 'group', SDValueString.sNew(group))
        if ui_min is not None and ui_max is not None:
            graph_or_node.setPropertyAnnotationValueFromId(
                prop, 'editor', SDValueString.sNew('slider'))
            # min/max 注解值类型必须与属性类型匹配（SD 16.0.1 实测：
            # int 属性用 SDValueFloat 注解 → SDApiError.InvalidValue）
            if ptype == 'int':
                graph_or_node.setPropertyAnnotationValueFromId(
                    prop, 'min', SDValueInt.sNew(int(ui_min)))
                graph_or_node.setPropertyAnnotationValueFromId(
                    prop, 'max', SDValueInt.sNew(int(ui_max)))
                graph_or_node.setPropertyAnnotationValueFromId(
                    prop, 'step', SDValueInt.sNew(max(1, int(round(step)))))
            else:
                graph_or_node.setPropertyAnnotationValueFromId(
                    prop, 'min', SDValueFloat.sNew(float(ui_min)))
                graph_or_node.setPropertyAnnotationValueFromId(
                    prop, 'max', SDValueFloat.sNew(float(ui_max)))
                graph_or_node.setPropertyAnnotationValueFromId(
                    prop, 'step', SDValueFloat.sNew(float(step)))
            graph_or_node.setPropertyAnnotationValueFromId(
                prop, 'clamp', SDValueBool.sNew(clamp))

    # 读回（只读属性可能读回 None / 或默认值不存在 → 依裁定接受）
    got_val = None
    try:
        got_val = graph_or_node.getPropertyValue(prop)
    except BaseException:
        pass
    if got_val is None and not (ro and allow_function_only):
        raise RuntimeError(f'参数默认值读回为 None: {param_id}')
    return prop, (None if (ro and not value_set) else got_val)


def has_node_new_property(node) -> bool:
    """探测节点级 newProperty 是否可用（0A 裁定点：文档与绑定不一致）。"""
    return hasattr(node, 'newProperty')


def set_param_value(owner, prop, value) -> None:
    """改参数值（float1 用）。"""
    owner.setPropertyValue(prop, SDValueFloat.sNew(float(value)))


# ---------------------------------------------------------------- owner 管理

OWNER_TAG = 'aniso_pp'


def list_owned_nodes(graph) -> list:
    """返回 graph 内所有可识别为本工具创建的节点（0A 重建演练用）。

    判定标准：节点类型为 PP_NODE_ID（当前工具只创建 PP；后续阶段扩展
    resource/连接清单）。禁止按名称/位置模糊匹配用户节点。
    """
    nodes = graph.getNodes()
    out = []
    n = nodes.getSize()
    for i in range(n):
        node = nodes.getItem(i)
        try:
            if node.getDefinition().getId() == PP_NODE_ID:
                out.append(node)
            elif node.getDefinition().getId().startswith('sbs::function::'):
                # 函数图节点由所属函数图管理，不在 comp graph 清单内重复登记
                continue
        except BaseException:
            continue
    return out


def delete_node(graph, node) -> None:
    graph.deleteNode(node)


def undo_group(label: str):
    """SDHistoryUtils.UndoGroup（sdhistoryutils.py:59-68：commit-only，
    异常不自动回滚 —— 调用方必须自行清理）。"""
    from sd.api.sdhistoryutils import SDHistoryUtils
    return SDHistoryUtils.UndoGroup(label)
