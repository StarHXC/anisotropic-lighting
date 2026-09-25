# -*- coding: utf-8 -*-
r"""实例求值排查 v3：test.compute() 两次 + 逐 Output 属性 + 时间窗重试。
输出：sd/validation/stage2_verify3.json
"""
import json
import os
import sys
import time

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from aniso_pp import api as SDAPI

    res = {'tries': []}
    try:
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
        if inst is None:
            res['fail'] = 'instance not found'
        else:
            outs = inst.getProperties(SDPropertyCategory.Output)
            prop = outs.getItem(0)
            for attempt in range(3):
                test.compute()
                v = inst.getPropertyValue(prop)
                tex = v.get() if v is not None else None
                size = None
                if tex is not None:
                    sz = tex.getSize()
                    size = (sz.x, sz.y)
                    if size != (0, 0):
                        tex.save(os.path.join(
                            VAL_DIR, 'stage2_inst.exr'), '')
                res['tries'].append({'attempt': attempt,
                                     'value_none': v is None,
                                     'tex_none': tex is None,
                                     'size': size})
                if tex is not None and size != (0, 0):
                    break
                time.sleep(1.0)
            res['ok'] = True
    except BaseException:
        import traceback
        res['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'stage2_verify3.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
