# -*- coding: utf-8 -*-
r"""图输入定案实验：SDTypeString 属性 + usage(image) 注解 + usages 数组注解，
保存 .sbs 后读 XML 验证 <input type="image"> 是否出现。
输出：sd/validation/ginput2.json + gi_test.sbs
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'ginput2.json')
SBS_OUT = os.path.join(VAL_DIR, 'gi_test.sbs')

report = {'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdtypestring import SDTypeString
    from sd.api.sdtypeusage import SDTypeUsage
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdvalueusage import SDValueUsage
    from sd.api.sdvaluearray import SDValueArray
    from sd.api.sdusage import SDUsage
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph

    ctx = sd.getContext()
    pkg_mgr = ctx.getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    g = SDSBSCompGraph.sNew(pkg)
    g.setIdentifier('gi_test')

    # 图像输入候选：string 属性 + usage 注解数组（image）
    prop = g.newProperty('in_bake_position', SDTypeString.sNew(),
                         SDPropertyCategory.Input)
    arr = SDValueArray.sNew(SDTypeUsage.sNew(), 0)
    arr.pushBack(SDValueUsage.sNew(SDUsage.sNew('image', '', '')))
    g.setPropertyAnnotationValueFromId(prop, 'usages', arr)
    g.setPropertyValue(prop, SDValueString.sNew(''))

    # 对照：无 usage 注解的 string 属性
    prop2 = g.newProperty('in_plain_string', SDTypeString.sNew(),
                          SDPropertyCategory.Input)

    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    xml = open(SBS_OUT, encoding='utf-8', errors='replace').read()
    report = {
        'has_image_input_tag': '<input' in xml and 'image' in xml,
        'input_tags': [seg[:120] for seg in
                       xml.split('<input')[1:4]],
        'ok': True,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[DONE]')


try:
    main()
except BaseException:
    import traceback
    report = {'fail': traceback.format_exc()}
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[ABORT]')
