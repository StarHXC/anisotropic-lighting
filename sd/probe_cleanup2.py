# -*- coding: utf-8 -*-
r"""清理 output 节点 + 尝试删 fixture 资源（含 Resources 文件夹内）。
"""
import json
import os

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'deleted': {}, 'kept': 0, 'fail': None}

try:
    import sd
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    pkg = graph.getPackage()

    to_del = []
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            d = node.getDefinition().getId()
        except BaseException:
            continue
        if d == 'sbs::compositing::output':
            to_del.append(node)
        else:
            res['kept'] += 1
    for n in to_del:
        graph.deleteNode(n)
    res['deleted']['output'] = len(to_del)

    # fixture 资源：Resources 文件夹内 identifier 含 fixture_0c2
    def walk(folder, depth=0):
        n = 0
        try:
            children = folder.getChildrenResources(False)
        except BaseException:
            return 0
        for i in range(children.getSize()):
            c = children.getItem(i)
            try:
                ident = str(c.getIdentifier())
            except BaseException:
                continue
            if 'fixture_0c2' in ident:
                try:
                    c.delete() if hasattr(c, 'delete') else None
                    n += 1
                except BaseException:
                    pass
            else:
                n += walk(c, depth + 1)
        return n

    res['deleted']['resources'] = walk(pkg)
    res['ok'] = True
except BaseException:
    import traceback
    res['fail'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'cleanup2_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE]', res.get('deleted'))
