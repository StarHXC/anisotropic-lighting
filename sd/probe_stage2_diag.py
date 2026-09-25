# -*- coding: utf-8 -*-
r"""实例输出 None 诊断：枚举 wrapper 的 output 标记、实例节点的 Output 属性与值。
输出：sd/validation/stage2_diag.json
"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')

report = {'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from aniso_pp import api as SDAPI

    res = {}
    try:
        pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
        pkg = pkg_mgr.getUserPackageFromFilePath(SBS_OUT)
        wrapper = pkg.findResourceFromUrl('pkg:///aniso_lightmap')

        # wrapper 的 output 节点是否 setOutputNode？
        out_nodes = wrapper.getOutputNodes()
        res['wrapper_output_nodes'] = out_nodes.getSize()
        # 输出 identifier
        oids = wrapper.getOutputIdentifiers()
        res['output_ids'] = [str(oids.getItem(i).get())
                             for i in range(oids.getSize())]

        # test graph 里找实例节点
        test = SDAPI.get_current_graph()
        nodes = test.getNodes()
        inst = None
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            try:
                rr = node.getReferencedResource()
                if rr is not None and 'aniso_lightmap' in rr.getUrl():
                    inst = node
                    break
            except BaseException:
                continue
        res['inst_found'] = inst is not None
        if inst is not None:
            outs = inst.getProperties(SDPropertyCategory.Output)
            lst = []
            for i in range(outs.getSize()):
                p = outs.getItem(i)
                v = None
                try:
                    v = inst.getPropertyValue(p)
                except BaseException as e:
                    v = f'ERR {e!r}'[:80]
                lst.append({'id': str(p.getId()),
                            'type': str(p.getType().getId()),
                            'value': str(v)[:80]})
            res['inst_outputs'] = lst
    except BaseException:
        import traceback
        res['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'stage2_diag.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
