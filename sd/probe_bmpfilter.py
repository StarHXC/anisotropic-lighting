# -*- coding: utf-8 -*-
r"""枚举 bitmap 实例节点与资源的全部属性（找 filtering/tiling 控制）。
输出：sd/validation/bmp_props.json
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

    res = {'node_props': [], 'resource_props': [], 'fail': None}
    try:
        bmp = None
        nodes = graph.getNodes()
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            try:
                url = node.getReferencedResource().getUrl()
                if '/bake_position' in url:
                    bmp = node
                    break
            except BaseException:
                continue
        if bmp is None:
            raise RuntimeError('bitmap not found')

        for cat in (SDPropertyCategory.Input, SDPropertyCategory.Output):
            props = bmp.getProperties(cat)
            for i in range(props.getSize()):
                p = props.getItem(i)
                try:
                    t = p.getType().getId()
                except BaseException:
                    t = '?'
                res['node_props'].append(
                    {'cat': str(cat).split('.')[-1], 'id': p.getId(),
                     'type': t})

        resource = bmp.getReferencedResource()
        for cat in (SDPropertyCategory.Input, SDPropertyCategory.Output,
                    SDPropertyCategory.Annotation):
            props = resource.getProperties(cat)
            for i in range(props.getSize()):
                p = props.getItem(i)
                try:
                    t = p.getType().getId()
                except BaseException:
                    t = '?'
                res['resource_props'].append(
                    {'cat': str(cat).split('.')[-1], 'id': p.getId(),
                     'type': t})
    except BaseException:
        import traceback
        res['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'bmp_props.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
