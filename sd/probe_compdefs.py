# -*- coding: utf-8 -*-
r"""列出全部 compositing 节点定义（找通道合并类节点）。"""
import json
import os

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'defs': [], 'fail': None}

try:
    import sd
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    defs = graph.getNodeDefinitions()
    n = defs.getSize()
    for i in range(n):
        d = defs.getItem(i)
        try:
            res['defs'].append(d.getId())
        except BaseException:
            continue
    res['total'] = n
except BaseException as e:
    res['fail'] = repr(e)

with open(os.path.join(SD_DIR, 'validation', 'all_comp_defs.json'), 'w',
          encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE]', len(res['defs']))
