# -*- coding: utf-8 -*-
r"""colortest 第 2 轮：float3 min/max 注解 + 无 valueInterpretation 的 editor=color。
输出：sd/validation/colortest_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

REPORT = {'probe': 'colortest2', 'results': [], 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdtypefloat3 import SDTypeFloat3
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdvaluestring import SDValueString
    from sd.api.sdvaluebool import SDValueBool
    from sd.api.sdbasetypes import float3

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    g = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
    if g is None:
        pkg2 = pkg_mgr.loadUserPackage(os.path.join(SD_DIR, 'aniso_lightmap.sbs'), True, True)
        g = pkg2.findResourceFromUrl('pkg:///aniso_lightmap')
    REPORT['graph'] = g is not None

    prop = g.newProperty('p_colortest2', SDTypeFloat3.sNew(),
                         SDPropertyCategory.Input)
    g.setPropertyValue(prop, SDValueFloat3.sNew(float3(1.0, 0.5, 0.0)))

    trials = [
        ('editor', SDValueString.sNew('color')),
        ('group', SDValueString.sNew('01_test')),
        ('clamp', SDValueBool.sNew(True)),
        ('min', SDValueFloat3.sNew(float3(0.0, 0.0, 0.0))),
        ('max', SDValueFloat3.sNew(float3(1.0, 1.0, 1.0))),
    ]
    for key, val in trials:
        try:
            g.setPropertyAnnotationValueFromId(prop, key, val)
            try:
                back = g.getPropertyAnnotationValueFromId(prop, key)
                got = tuple(back.get()) if back is not None else None
                if isinstance(got, tuple):
                    got = tuple(round(float(c), 4) for c in got)
            except BaseException as e2:
                got = f'<readback fail: {e2!r}>'
            REPORT['results'].append([key, 'OK', repr(got)])
        except BaseException as e:
            REPORT['results'].append([key, 'FAIL', repr(e)[:300]])

    try:
        g.deleteProperty(prop)
        REPORT['cleanup'] = 'deleted'
    except BaseException as e:
        REPORT['cleanup'] = repr(e)[:200]

    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = repr(e)
    REPORT['tb'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'colortest_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
