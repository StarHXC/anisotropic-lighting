# -*- coding: utf-8 -*-
r"""删除残留 fixture bitmap 实例节点（0d2/diag2 各轮的）。"""
import json
import os

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'deleted': 0, 'kept': 0, 'fail': None}

try:
    import sd
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()

    to_del = []
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            url = node.getReferencedResource().getUrl()
            if 'fixture_' in url:
                to_del.append(node)
                continue
        except BaseException:
            pass
        res['kept'] += 1
    for n in to_del:
        graph.deleteNode(n)
        res['deleted'] += 1
    res['ok'] = True
except BaseException:
    import traceback
    res['fail'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'cleanup5_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE] deleted:', res['deleted'], 'kept:', res['kept'])
