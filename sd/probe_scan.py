# -*- coding: utf-8 -*-
r"""扫描 test graph 中的用户节点（贴图 Bitmap 等），留痕类型与属性。
输出：sd/validation/graph_scan.json
"""
import json
import os
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'nodes': [], 'fail': None}

try:
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    res['graph'] = graph.getIdentifier() if hasattr(graph, 'getIdentifier') else '?'
    nodes = graph.getNodes()
    n = nodes.getSize()
    for i in range(n):
        node = nodes.getItem(i)
        try:
            defn = node.getDefinition().getId()
            pos = node.getPosition()
            entry = {'def': defn, 'pos': [round(pos.x, 1), round(pos.y, 1)]}
            # Bitmap 类节点记录资源 url
            if 'bitmap' in defn.lower() or 'instance' in defn.lower():
                try:
                    res_ref = node.getReferencedResource()
                    if res_ref is not None:
                        entry['resource'] = res_ref.getUrl()
                except BaseException:
                    pass
            res['nodes'].append(entry)
        except BaseException:
            continue
    res['total'] = n
except BaseException:
    res['fail'] = traceback.format_exc()

out_path = os.path.join(SD_DIR, 'validation', 'graph_scan.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE] nodes:', len(res['nodes']))
