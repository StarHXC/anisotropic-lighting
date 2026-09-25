# -*- coding: utf-8 -*-
r"""slope_blur_grayscale 的图输入参数枚举（getInputIdentifiers/getProperties 全类别）。
输出：sd/validation/sb_inputs.json
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
    from sd.api.sdapplication import SDApplicationPath

    out = {'input_ids': [], 'props_by_cat': {}, 'fail': None}
    try:
        app = sd.getContext().getSDApplication()
        pkg_mgr = app.getPackageMgr()
        res_dir = app.getPath(SDApplicationPath.DefaultResourcesDir)
        pkg = pkg_mgr.loadUserPackage(
            os.path.join(res_dir, 'packages', 'slope_blur.sbs'), True, True)
        graph = pkg.findResourceFromUrl('pkg:///slope_blur_grayscale')

        ids = graph.getInputIdentifiers()
        for i in range(ids.getSize()):
            item = ids.getItem(i)
            try:
                out['input_ids'].append(str(item.get()))
            except BaseException:
                try:
                    out['input_ids'].append(str(item.getValue()))
                except BaseException:
                    out['input_ids'].append(str(item))

        for cat in SDPropertyCategory.__members__:
            try:
                props = graph.getProperties(SDPropertyCategory[cat])
                lst = []
                for i in range(props.getSize()):
                    p = props.getItem(i)
                    t = '?'
                    try:
                        t = p.getType().getId()
                    except BaseException:
                        pass
                    lst.append({'id': str(p.getId()), 'type': str(t)})
                if lst:
                    out['props_by_cat'][cat] = lst
            except BaseException:
                pass
    except BaseException:
        import traceback
        out['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'sb_inputs.json'), 'w',
              encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
