# -*- coding: utf-8 -*-
r"""图输入注册类型实验：逐一尝试候选类型/注解组合。
候选：SDTypeString+usage(image) / SDTypeTexture / SDTypeUsage / SDTypeBool...
判定哪种能创建出"图像输入"（保存 .sbs 后 XML 含 <input type="image">）。
输出：sd/validation/ginput_probe.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'ginput_probe.json')

report = {'probe': 'ginput', 'attempts': [], 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from sd.api.sdtypestring import SDTypeString
    from sd.api.sdtypebool import SDTypeBool
    from sd.api.sdtypeusage import SDTypeUsage
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdvalueusage import SDValueUsage
    from sd.api.sdusage import SDUsage
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph

    ctx = sd.getContext()
    app = ctx.getSDApplication()
    pkg_mgr = app.getPackageMgr()

    attempts = []

    def try_case(tag, fn):
        try:
            fn()
            attempts.append({'case': tag, 'ok': True})
        except BaseException as e:
            attempts.append({'case': tag, 'ok': False, 'err': repr(e)[:150]})

    # case 1: SDTypeString + usage annotation 'image'
    def case1():
        pkg = pkg_mgr.newUserPackage()
        g = SDSBSCompGraph.sNew(pkg)
        g.setIdentifier('gi_c1')
        prop = g.newProperty('in_img', SDTypeString.sNew(),
                             SDPropertyCategory.Input)
        g.setPropertyAnnotationValueFromId(
            prop, 'usages',
            _make_usage_array()) if False else None
        # usages 注解类型是 SDValueArray[SDTypeUsage] —— 单独实验
        pkg_mgr.unloadUserPackage(pkg)
    try_case('string_prop', case1)

    # case 2: SDTypeUsage 属性（image usage）
    def case2():
        pkg = pkg_mgr.newUserPackage()
        g = SDSBSCompGraph.sNew(pkg)
        g.setIdentifier('gi_c2')
        prop = g.newProperty('in_img2', SDTypeUsage.sNew(),
                             SDPropertyCategory.Input)
        g.setPropertyValue(prop, SDValueUsage.sNew(
            SDUsage.sNew('image', '', '')))
        pkg_mgr.unloadUserPackage(pkg)
    try_case('usage_prop', case2)

    report['attempts'] = attempts
    report['ok'] = all(a['ok'] for a in attempts)


def _make_usage_array():
    from sd.api.sdvaluearray import SDValueArray
    from sd.api.sdtypeusage import SDTypeUsage
    from sd.api.sdvalueusage import SDValueUsage
    from sd.api.sdusage import SDUsage
    arr = SDValueArray.sNew(SDTypeUsage.sNew(), 0)
    arr.pushBack(SDValueUsage.sNew(SDUsage.sNew('image', '', '')))
    return arr


try:
    main()
except BaseException:
    import traceback
    report['fail'] = traceback.format_exc()

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
