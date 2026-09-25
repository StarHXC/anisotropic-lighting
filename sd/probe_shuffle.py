# -*- coding: utf-8 -*-
r"""shuffle 节点属性签名 + 双图合成能力探测。
输出：sd/validation/shuffle_props.json
"""
import json
import os

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'props': [], 'fail': None}

try:
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    u = graph.newNode('sbs::compositing::shuffle')
    for cat in (SDPropertyCategory.Input, SDPropertyCategory.Output):
        props = u.getProperties(cat)
        for i in range(props.getSize()):
            p = props.getItem(i)
            try:
                t = p.getType().getId()
            except BaseException:
                t = '?'
            res['props'].append({'cat': str(cat).split('.')[-1], 'id': p.getId(),
                                 'type': t, 'variadic': p.isVariadic()})
except BaseException as e:
    import traceback
    res['fail'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'shuffle_props.json'), 'w',
          encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE]', len(res['props']))
