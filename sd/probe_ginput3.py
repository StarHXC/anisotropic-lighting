# -*- coding: utf-8 -*-
r"""图输入类型穷举：遍历全部 SDType 子类，逐个 newProperty 试 Input 类别。
输出：sd/validation/ginput3.json（每个类型成功/失败清单）
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'ginput3.json')

report = {'types': [], 'fail': None}


def main():
    import sd
    import importlib
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph

    ctx = sd.getContext()
    pkg_mgr = ctx.getSDApplication().getPackageMgr()

    type_mods = [
        ('SDTypeFloat', 'sd.api.sdtypefloat', 'SDTypeFloat'),
        ('SDTypeFloat2', 'sd.api.sdtypefloat2', 'SDTypeFloat2'),
        ('SDTypeFloat3', 'sd.api.sdtypefloat3', 'SDTypeFloat3'),
        ('SDTypeFloat4', 'sd.api.sdtypefloat4', 'SDTypeFloat4'),
        ('SDTypeInt', 'sd.api.sdtypeint', 'SDTypeInt'),
        ('SDTypeBool', 'sd.api.sdtypebool', 'SDTypeBool'),
        ('SDTypeString', 'sd.api.sdtypestring', 'SDTypeString'),
        ('SDTypeTexture', 'sd.api.sdtypetexture', 'SDTypeTexture'),
        ('SDTypeUsage', 'sd.api.sdtypeusage', 'SDTypeUsage'),
        ('SDTypeEnum', 'sd.api.sdtypeenum', 'SDTypeEnum'),
        ('SDTypeColorRGB', 'sd.api.sdtypecolorrgb', 'SDTypeColorRGB'),
        ('SDTypeColorRGBA', 'sd.api.sdtypecolorrgba', 'SDTypeColorRGBA'),
        ('SDTypeVoid', 'sd.api.sdtypevoid', 'SDTypeVoid'),
        ('SDTypeArray', 'sd.api.sdtypearray', 'SDTypeArray'),
        ('SDTypeStruct', 'sd.api.sdtypestruct', 'SDTypeStruct'),
        ('SDTypeCustom', 'sd.api.sdtypecustom', 'SDTypeCustom'),
        ('SDTypeMaterial', 'sd.api.sdtypematerial', 'SDTypeMaterial'),
        ('SDTypeScene', 'sd.api.sdresourcescene', 'SDTypeScene'),
    ]
    for name, mod, cls in type_mods:
        entry = {'type': name}
        try:
            m = importlib.import_module(mod)
            t = getattr(m, cls).sNew()
            pkg = pkg_mgr.newUserPackage()
            g = SDSBSCompGraph.sNew(pkg)
            g.setIdentifier(f'gi3_{name}')
            try:
                prop = g.newProperty(f'in_t_{name}', t,
                                     SDPropertyCategory.Input)
                entry['input_ok'] = prop is not None
            except BaseException as e:
                entry['input_ok'] = False
                entry['input_err'] = repr(e)[:100]
            pkg_mgr.unloadUserPackage(pkg)
        except BaseException as e:
            entry['error'] = repr(e)[:120]
        report['types'].append(entry)
    report['ok'] = True


try:
    main()
except BaseException:
    import traceback
    report['fail'] = traceback.format_exc()

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
