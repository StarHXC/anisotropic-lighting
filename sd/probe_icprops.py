# -*- coding: utf-8 -*-
r"""枚举 sbs::compositing::input_color 的属性签名（找图输入绑定方式）。
输出：sd/validation/ic_props.json
"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    res = {'props': [], 'fail': None}
    try:
        u = graph.newNode('sbs::compositing::input_color')
        for cat in (SDPropertyCategory.Input, SDPropertyCategory.Output):
            props = u.getProperties(cat)
            for i in range(props.getSize()):
                p = props.getItem(i)
                try:
                    t = p.getType().getId()
                except BaseException:
                    t = '?'
                usg = ''
                try:
                    usg = str(p.getUsages().getItem(0).getId()) if \
                        p.getUsages().getSize() > 0 else ''
                except BaseException:
                    pass
                res['props'].append({'cat': str(cat).split('.')[-1],
                                     'id': p.getId(), 'type': t,
                                     'usage': usg})
    except BaseException:
        import traceback
        res['fail'] = traceback.format_exc()
    with open(os.path.join(VAL_DIR, 'ic_props.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
