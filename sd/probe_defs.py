# -*- coding: utf-8 -*-
r"""枚举当前 graph 可用的节点定义 id（含 constant/uniform/passthrough 关键字）。
通过桥执行：python sd/run_probe.py defs
输出：sd/validation/node_defs_probe.json
"""
import json
import os
import traceback

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
    out = []
    for i in range(n):
        d = defs.getItem(i)
        try:
            did = d.getId()
        except BaseException:
            continue
        low = did.lower()
        if any(k in low for k in ('constant', 'uniform', 'passthrough')):
            out.append(did)
    res['defs'] = out
    res['total'] = n
except BaseException:
    res['fail'] = traceback.format_exc()

out_path = os.path.join(SD_DIR, 'validation', 'node_defs_probe.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE] node defs →', out_path, 'matches:', len(res['defs']))
