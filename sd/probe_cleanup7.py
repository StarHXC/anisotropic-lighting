# -*- coding: utf-8 -*-
r"""清理 test graph 的实例节点与 input_color 残留（保留用户 4 bitmap）。
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
    ctx = sd.getContext()
    app = ctx.getSDApplication()
    ui = app.getUIMgr()
    graph = ui.getCurrentGraph()

    res = {'deleted': 0, 'kept': 0, 'fail': None}
    try:
        to_del = []
        nodes = graph.getNodes()
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            try:
                d = str(node.getDefinition().getId())
            except BaseException:
                continue
            if d in ('sbs::compositing::sbscompgraph_instance',
                     'sbs::compositing::input_color'):
                to_del.append(node)
                continue
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

    with open(os.path.join(VAL_DIR, 'cleanup7_report.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE] deleted:', res['deleted'], 'kept:', res['kept'])


main()
