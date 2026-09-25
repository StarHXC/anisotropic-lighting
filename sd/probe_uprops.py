# -*- coding: utf-8 -*-
r"""枚举 sbs::compositing::uniform 节点的属性签名（桥执行）。
输出：sd/validation/uniform_props.json
"""
import json
import os
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'props': [], 'fail': None}

try:
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    u = graph.newNode('sbs::compositing::uniform')
    for cat in (SDPropertyCategory.Input, SDPropertyCategory.Output):
        props = u.getProperties(cat)
        for i in range(props.getSize()):
            p = props.getItem(i)
            try:
                t = p.getType().getId()
            except BaseException:
                t = '?'
            res['props'].append({'cat': str(cat), 'id': p.getId(), 'type': t,
                                 'variadic': p.isVariadic() if hasattr(p, 'isVariadic') else None})
    res['uid'] = u.getIdentifier() if hasattr(u, 'getIdentifier') else '?'
except BaseException:
    res['fail'] = traceback.format_exc()

out_path = os.path.join(SD_DIR, 'validation', 'uniform_props.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE]', len(res['props']), 'props')
