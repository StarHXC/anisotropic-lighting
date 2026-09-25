# -*- coding: utf-8 -*-
r"""恢复 p_light_azimuth_deg 默认值（-56.31，bake_report 快照推导值）。"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdvaluefloat import SDValueFloat

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.getUserPackageFromFilePath(SBS_OUT)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
    prop = wrapper.getPropertyFromId('p_light_azimuth_deg',
                                     SDPropertyCategory.Input)
    default = -56.309932708740234  # atan2(-0.6, 0.4) 完整精度
    wrapper.setPropertyValue(prop, SDValueFloat.sNew(default))
    got = wrapper.getPropertyValue(prop).get()
    with open(os.path.join(VAL_DIR, 'param_reset.json'), 'w',
              encoding='utf-8') as f:
        json.dump({'restored': float(got)}, f)
    print('[DONE] restored:', float(got))


main()
