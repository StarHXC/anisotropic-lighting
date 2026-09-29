# -*- coding: utf-8 -*-
r"""排查 34 参数驻留包被什么钉住（v2）：经 graph view 枚举全部打开图，
逐图扫 aniso 实例引用与参数计数。
输出：sd/validation/pkgpin_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

REPORT = {'probe': 'pkgpin2', 'views': [], 'ok': False}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory

    ui = sd.getContext().getSDApplication().getUIMgr()

    n_views = ui.getGraphViewIDCount()
    REPORT['n_views'] = n_views
    for v in range(n_views):
        vid = ui.getGraphViewIDAt(v)
        info = {'view_index': v, 'view_id': str(vid)}
        try:
            gr = ui.getGraphFromGraphViewID(vid)
            if gr is None:
                info['graph'] = None
            else:
                ident = '?'
                for a in ('getIdentifier', 'getUrl'):
                    f2 = getattr(gr, a, None)
                    if f2 is not None:
                        try:
                            ident = str(f2())
                            break
                        except BaseException:
                            pass
                info['graph'] = ident
                refs = []
                nodes = gr.getNodes()
                for k in range(nodes.getSize()):
                    nd = nodes.getItem(k)
                    try:
                        rr = nd.getReferencedResource()
                        if rr is not None and 'aniso_lightmap' in str(rr.getUrl()):
                            # 该实例引用的资源属于哪个包：数其参数
                            pkg = rr.getPackage()
                            np_ = -1
                            try:
                                gg = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
                                if gg is not None:
                                    ps = gg.getProperties(SDPropertyCategory.Input)
                                    np_ = sum(1 for q in range(ps.getSize())
                                              if str(ps.getItem(q).getId()).startswith('p_'))
                            except BaseException:
                                pass
                            refs.append({'node': k, 'pkg_params': np_})
                    except BaseException:
                        pass
                info['aniso_refs'] = refs
        except BaseException as e:
            info['err'] = repr(e)[:200]
        REPORT['views'].append(info)

    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = repr(e)
    REPORT['tb'] = traceback.format_exc()

with open(os.path.join(SD_DIR, 'validation', 'pkgpin_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
