# -*- coding: utf-8 -*-
r"""图输入 usage 驱动实验：创建 float4 属性 → 枚举其全部注解 → 找 usages 槽 →
设置 usage(image) → 保存验证 paraminput type 变 1。
输出：sd/validation/ginput6.json + gi6.sbs
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'ginput6.json')
SBS_OUT = os.path.join(VAL_DIR, 'gi6.sbs')

report = {'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdtypefloat4 import SDTypeFloat4
    from sd.api.sdbasetypes import float4
    from sd.api.sdvaluefloat4 import SDValueFloat4
    from sd.api.sdtypeusage import SDTypeUsage
    from sd.api.sdvalueusage import SDValueUsage
    from sd.api.sdvaluearray import SDValueArray
    from sd.api.sdusage import SDUsage
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph

    ctx = sd.getContext()
    pkg_mgr = ctx.getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    g = SDSBSCompGraph.sNew(pkg)
    g.setIdentifier('gi6')

    prop = g.newProperty('in_img', SDTypeFloat4.sNew(),
                         SDPropertyCategory.Input)
    g.setPropertyValue(prop, SDValueFloat4.sNew(float4(0, 0, 0, 1)))

    # 枚举该属性的全部注解（找 usages 槽真实 id）
    anns = g.getPropertyAnnotations(prop)
    ann_ids = []
    for i in range(anns.getSize()):
        ann_ids.append(str(anns.getItem(i).getId()))
    report['annotations'] = ann_ids

    # 尝试 usages 数组注解（复用官方 output 节点的用法）
    try:
        arr = SDValueArray.sNew(SDTypeUsage.sNew(), 0)
        arr.pushBack(SDValueUsage.sNew(SDUsage.sNew('$image', 'RGBA', 'linear')))
        g.setPropertyAnnotationValueFromId(prop, 'usages', arr)
        report['usages_set'] = True
    except BaseException as e:
        report['usages_set'] = repr(e)[:150]

    # isConnectable 断言（图像输入必须可连接）
    try:
        report['is_connectable'] = bool(prop.isConnectable())
    except BaseException as e:
        report['is_connectable'] = repr(e)[:100]

    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    data = open(SBS_OUT, 'rb').read()
    report['paraminput_snips'] = []
    i = 0
    while True:
        i = data.find(b'<paraminput>', i)
        if i < 0:
            break
        report['paraminput_snips'].append(
            data[i:i+320].decode('utf-8', errors='replace'))
        i += 12
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
