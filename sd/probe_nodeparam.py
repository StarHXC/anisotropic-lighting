# -*- coding: utf-8 -*-
import json, os, traceback
SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'steps': [], 'fail': None}
try:
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdtypefloat import SDTypeFloat
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdvaluebool import SDValueBool
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    pp = graph.newNode('sbs::compositing::pixelprocessor')
    # 1) 节点级 newProperty
    prop = pp.newProperty('p_node_param', SDTypeFloat.sNew(), SDPropertyCategory.Input)
    res['steps'].append(['newProperty', prop is not None])
    # 2) setPropertyValue（此前 DataIsReadOnly）
    set_err = None
    try:
        pp.setPropertyValue(prop, SDValueFloat.sNew(0.25))
        res['steps'].append(['setPropertyValue', True])
    except BaseException as e:
        set_err = repr(e)
        res['steps'].append(['setPropertyValue', False, set_err])
    # 3) 节点注解 API（SDNode.setAnnotationPropertyValueFromId —— 不是属性注解）
    #    但注意：group/slider 是「属性注解」不是「节点注解」。先测属性注解的替代路径：
    #    SDNode.setAnnotationPropertyValueFromId 作用于节点自身注解（如 UI 位置），
    #    属性注解只能走 SDResource（comp graph）。
    has_node_annot = hasattr(pp, 'setAnnotationPropertyValueFromId')
    res['steps'].append(['node-level setAnnotationPropertyValueFromId exists', has_node_annot])
    # 4) 节点函数图内 get_float1 读 p_node_param 可行性——先读回属性
    got = None
    try:
        got = pp.getPropertyValue(prop)
    except BaseException as e:
        got = f'ERR {e!r}'
    res['steps'].append(['getPropertyValue', str(got)])
    # 清理
    pp.deleteProperty(prop) if prop is not None else None
    graph.deleteNode(pp)
except BaseException:
    import traceback as tb
    res['fail'] = tb.format_exc()
with open(os.path.join(SD_DIR, 'validation', 'node_param_probe.json'), 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE]')