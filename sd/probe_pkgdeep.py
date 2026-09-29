# -*- coding: utf-8 -*-
r"""驻留包深度诊断：枚举全部含 aniso 的包 + 逐一 unload 返回值 + unload 后重查。
输出：sd/validation/pkgdeep_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

REPORT = {'probe': 'pkgdeep', 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    def scan():
        out = []
        pkgs = pkg_mgr.getPackages()
        for i in range(pkgs.getSize()):
            p = pkgs.getItem(i)
            try:
                g = p.findResourceFromUrl('pkg:///aniso_lightmap')
                if g is not None:
                    ps = g.getProperties(SDPropertyCategory.Input)
                    n = sum(1 for k in range(ps.getSize())
                            if str(ps.getItem(k).getId()).startswith('p_'))
                    out.append({'idx': i, 'params': n, 'obj': repr(p)[:60]})
            except BaseException:
                pass
        return out

    REPORT['before'] = scan()

    # 逐一 unload（记录每次返回值）
    log = []
    for _round in range(4):
        before = scan()
        if not before:
            break
        for ent in before:
            p = pkg_mgr.getPackages().getItem(ent['idx'])
            try:
                ret = pkg_mgr.unloadUserPackage(p)
                log.append({'round': _round, 'idx': ent['idx'],
                            'params': ent['params'], 'ret': repr(ret)})
            except BaseException as e:
                log.append({'round': _round, 'idx': ent['idx'],
                            'params': ent['params'], 'exc': repr(e)[:150]})
        # unload 后 SDArray 索引变化 → 重扫（scan() 每次重新枚举，安全）
    REPORT['unload_log'] = log
    REPORT['after'] = scan()

    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = repr(e)
    REPORT['tb'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'pkgdeep_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
