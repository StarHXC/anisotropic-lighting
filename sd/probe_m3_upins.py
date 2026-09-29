# -*- coding: utf-8 -*-
r"""M3 诊断 2 — uniform 节点 setPropertyValue 路径实测（不猜 ID，直接试）。"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm3')
REPORT = {'probe': 'm3_upins2', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import int2, ColorRGBA
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA
    from aniso_pp import api as SDAPI

    test = SDAPI.get_current_graph()
    u = test.newNode('sbs::compositing::uniform')
    u.setPosition(float2(13000.0, 2000.0)) if False else u.setPosition(__import__('sd.api.sdbasetypes', fromlist=['float2']).float2(13000.0, 2000.0))

    results = {}
    # 1. outputcolor via setInputPropertyValueFromId
    try:
        u.setInputPropertyValueFromId('outputcolor', SDValueColorRGBA.sNew(ColorRGBA(1.0, 0.0, 0.0, 1.0)))
        results['outputcolor_setInput'] = 'OK'
    except BaseException as e:
        results['outputcolor_setInput'] = repr(e)

    # 2. $outputsize via setInputPropertyValueFromId
    try:
        u.setInputPropertyValueFromId('$outputsize', SDValueInt2.sNew(int2(11, 11)))
        results['outputsize_setInput'] = 'OK'
    except BaseException as e:
        results['outputsize_setInput'] = repr(e)

    # 3. $outputsize via property object
    try:
        pr = u.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
        results['outputsize_getProp'] = 'None' if pr is None else 'FOUND'
        if pr is not None:
            u.setPropertyValue(pr, SDValueInt2.sNew(int2(11, 11)))
            results['outputsize_setProp'] = 'OK'
    except BaseException as e:
        results['outputsize_setProp'] = repr(e)

    # 4. $format via property object (enum)
    try:
        from sd.api.sdvalueenum import SDValueEnum
        pr = u.getPropertyFromId('$format', SDPropertyCategory.Input)
        if pr is not None:
            u.setPropertyValue(pr, SDValueEnum.sFromValue('SDTypeSizePolynomial', 3))
            results['format_setProp'] = 'OK'
        else:
            results['format_setProp'] = 'prop None'
    except BaseException as e:
        results['format_setProp'] = repr(e)

    REPORT['results'] = results
    try:
        test.deleteNode(u)
    except BaseException:
        pass
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm3_upins2_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
