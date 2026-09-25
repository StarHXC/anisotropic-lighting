# -*- coding: utf-8 -*-
r"""枚举 slope_blur 的 comp graph 对象（找 input_color 实例与图输入挂载）。
输出：sd/validation/sb_objects.json
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
    from sd.api.sdapplication import SDApplicationPath

    out = {'objects': [], 'fail': None}
    try:
        app = sd.getContext().getSDApplication()
        pkg_mgr = app.getPackageMgr()
        res_dir = app.getPath(SDApplicationPath.DefaultResourcesDir)
        pkg = pkg_mgr.loadUserPackage(
            os.path.join(res_dir, 'packages', 'slope_blur.sbs'), True, True)
        graph = pkg.findResourceFromUrl('pkg:///slope_blur_grayscale')

        nodes = graph.getNodes()
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            d = node.getDefinition().getId()
            info = {'def': d}
            if d == 'sbs::compositing::input_color':
                # 图输入绑定属性读值
                try:
                    v = node.getInputPropertyValueFromId(
                        'bitmapresourcepath')
                    info['bitmapresourcepath'] = str(v.get()) if v else None
                except BaseException:
                    pass
            out['objects'].append(info)
    except BaseException:
        import traceback
        out['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'sb_objects.json'), 'w',
              encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
