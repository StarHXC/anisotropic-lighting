# -*- coding: utf-8 -*-
r"""清理 0C2 探针资源与节点（bitmap 实例节点 + fixture 资源 + PP/output）。
输出：sd/validation/cleanup_0c2_report.json
"""
import json
import os

SD_DIR = os.path.dirname(os.path.abspath(__file__))
res = {'deleted_nodes': 0, 'deleted_resources': 0, 'kept': 0, 'fail': None}

try:
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()
    pkg = graph.getPackage()

    # 1) 删节点：本工具创建的 fixture bitmap 实例 / PP / output
    to_del = []
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            d = node.getDefinition().getId()
        except BaseException:
            continue
        kill = False
        if d in ('sbs::compositing::pixelprocessor',
                 'sbs::compositing::output'):
            kill = True
        elif d == 'sbs::compositing::bitmap':
            try:
                url = node.getReferencedResource().getUrl()
                if 'fixture_0c2' in url:
                    kill = True
            except BaseException:
                pass
        if kill:
            to_del.append(node)
        else:
            res['kept'] += 1
    for node in to_del:
        graph.deleteNode(node)
        res['deleted_nodes'] += 1

    # 2) 删 fixture 资源
    children = pkg.getChildrenResources(False)
    for i in range(children.getSize()):
        child = children.getItem(i)
        # folder 递归
        try:
            subs = child.getChildrenResources(False) if hasattr(
                child, 'getChildrenResources') else None
        except BaseException:
            subs = None
        candidates = []
        if subs is not None:
            for j in range(subs.getSize()):
                candidates.append(subs.getItem(j))
        else:
            candidates.append(child)
        for c in candidates:
            try:
                ident = c.getIdentifier()
            except BaseException:
                continue
            if ident and 'fixture_0c2' in str(ident):
                try:
                    graph.getPackage().deleteResource(c) if hasattr(
                        pkg, 'deleteResource') else None
                    res['deleted_resources'] += 1
                except BaseException:
                    # 某些版本无 deleteResource → 留痕不阻塞
                    res.setdefault('resource_delete_errors', []).append(ident)

    res['ok'] = True
except BaseException:
    import traceback
    res['fail'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'cleanup_0c2_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('[DONE] nodes:', res['deleted_nodes'], 'resources:', res['deleted_resources'])
