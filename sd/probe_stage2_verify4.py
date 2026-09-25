# -*- coding: utf-8 -*-
r"""实例求值排查 v4：给实例接 test 的 output 节点 → test.compute() → 读值。
输出：sd/validation/stage2_verify4.json + stage2_inst.exr
"""
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
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI

    res = {}
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

        out_node = test.newNode('sbs::compositing::output')
        out_node.setPosition(float2(5600.0, 2000.0))
        # 实例输出引脚 id = wrapper 的输出 identifier（'output'），动态枚举
        outs = inst.getProperties(SDPropertyCategory.Output)
        out_pin = str(outs.getItem(0).getId())
        inst.newPropertyConnectionFromId(out_pin, out_node, 'inputNodeOutput')
        test.compute()

        outs = inst.getProperties(SDPropertyCategory.Output)
        prop = outs.getItem(0)
        v = inst.getPropertyValue(prop)
        tex = v.get() if v is not None else None
        size = None
        if tex is not None:
            sz = tex.getSize()
            size = (sz.x, sz.y)
            tex.save(os.path.join(VAL_DIR, 'stage2_inst.exr'), '')
        res = {'value_none': v is None, 'tex_none': tex is None,
               'size': size, 'ok': tex is not None}
    except BaseException:
        import traceback
        res = {'fail': traceback.format_exc()}

    with open(os.path.join(VAL_DIR, 'stage2_verify4.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
