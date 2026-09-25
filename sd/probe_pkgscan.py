# -*- coding: utf-8 -*-
r"""枚举 SD 内存中全部用户包：标识/URL/aniso 参数计数。
输出：sd/validation/pkgscan_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

REPORT = {'probe': 'pkgscan', 'packages': [], 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkgs = pkg_mgr.getPackages()
    n = pkgs.getSize()
    REPORT['total'] = n
    for i in range(n):
        p = pkgs.getItem(i)
        info = {}
        try:
            info['identifier'] = str(p.getIdentifier())
        except BaseException as e:
            info['identifier'] = f'<{e!r}>'
        try:
            info['url'] = str(p.getUrl())
        except BaseException as e:
            info['url'] = f'<{e!r}>'
        try:
            g = p.findResourceFromUrl('pkg:///aniso_lightmap')
            if g is not None:
                ps = g.getProperties(SDPropertyCategory.Input)
                info['aniso_params'] = sum(
                    1 for k in range(ps.getSize())
                    if str(ps.getItem(k).getId()).startswith('p_'))
                info['aniso_uid'] = str(g.getUid())
            else:
                info['aniso_params'] = None
        except BaseException as e:
            info['aniso_err'] = repr(e)[:150]
        REPORT['packages'].append(info)

    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = repr(e)
    REPORT['tb'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'pkgscan_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
