# -*- coding: utf-8 -*-
r"""加载 SD 自带 atom（slope_blur，有 image input），枚举其图输入属性类型。
输出：sd/validation/lib_input_probe.json
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

    out = {'props': [], 'fail': None}
    try:
        app = sd.getContext().getSDApplication()
        pkg_mgr = app.getPackageMgr()
        res_dir = app.getPath(SDApplicationPath.DefaultResourcesDir)
        pkg = pkg_mgr.loadUserPackage(
            os.path.join(res_dir, 'packages', 'slope_blur.sbs'),
            True, True)
        if pkg is None:
            raise RuntimeError('loadUserPackage None')
        res = pkg.findResourceFromUrl('pkg:///slope_blur_grayscale')
        if res is None:
            raise RuntimeError('slope_blur_grayscale not found')

        def dump_props(owner, label):
            props = owner.getProperties(SDPropertyCategory.Input)
            for i in range(props.getSize()):
                p = props.getItem(i)
                try:
                    t = p.getType().getId()
                except BaseException:
                    t = '?'
                usages = []
                try:
                    uu = p.getUsages()
                    for j in range(uu.getSize()):
                        usages.append(str(uu.getItem(j).getId()))
                except BaseException:
                    pass
                out['props'].append({'owner': label, 'id': str(p.getId()),
                                     'type': str(t), 'usages': usages,
                                     'variadic': bool(p.isVariadic())})

        dump_props(res, 'graph')
    except BaseException:
        import traceback
        out['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'lib_input_probe.json'), 'w',
              encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
