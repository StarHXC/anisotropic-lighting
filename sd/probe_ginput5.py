# -*- coding: utf-8 -*-
r"""图像输入注册实验：SDTypeFloat4/ColorRGBA 属性（Input 类别）+ connectable，
保存后读 XML 验证 paraminput type="1"。
输出：sd/validation/ginput5.json + gi5.sbs
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'ginput5.json')
SBS_OUT = os.path.join(VAL_DIR, 'gi5.sbs')

report = {'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdtypefloat4 import SDTypeFloat4
    from sd.api.sdtypecolorrgba import SDTypeColorRGBA
    from sd.api.sdbasetypes import float4, ColorRGBA
    from sd.api.sdvaluefloat4 import SDValueFloat4
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph

    ctx = sd.getContext()
    pkg_mgr = ctx.getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    g = SDSBSCompGraph.sNew(pkg)
    g.setIdentifier('gi5')

    ok = {}
    # 候选 A：SDTypeFloat4
    try:
        prop = g.newProperty('in_img_f4', SDTypeFloat4.sNew(),
                             SDPropertyCategory.Input)
        g.setPropertyValue(prop, SDValueFloat4.sNew(float4(0, 0, 0, 1)))
        ok['float4'] = True
    except BaseException as e:
        ok['float4'] = repr(e)[:100]
    # 候选 B：SDTypeColorRGBA
    try:
        prop = g.newProperty('in_img_rgba', SDTypeColorRGBA.sNew(),
                             SDPropertyCategory.Input)
        g.setPropertyValue(prop, SDValueColorRGBA.sNew(
            ColorRGBA(0, 0, 0, 1)))
        ok['rgba'] = True
    except BaseException as e:
        ok['rgba'] = repr(e)[:100]

    pkg_mgr.savePackageAs(pkg, SBS_OUT)
    data = open(SBS_OUT, 'rb').read()
    report = {'types': ok,
              'has_paraminput': data.find(b'<paraminput>') > 0,
              'paraminput_snips': [],
              'ok': True}
    i = 0
    while True:
        i = data.find(b'<paraminput>', i)
        if i < 0:
            break
        report['paraminput_snips'].append(
            data[i:i+300].decode('utf-8', errors='replace'))
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
