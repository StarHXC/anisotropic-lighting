# -*- coding: utf-8 -*-
r"""参数生效性终验：改 p_light_azimuth_deg（0→90°）→ test.compute() →
读实例输出与默认值输出对比（高光位置应显著移动）。
输出：sd/validation/param_effect.json + param_azim90.exr
"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdvaluefloat import SDValueFloat
    from aniso_pp import api as SDAPI

    res = {}
    try:
        pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
        pkg = pkg_mgr.getUserPackageFromFilePath(SBS_OUT)
        wrapper = pkg.findResourceFromUrl('pkg:///aniso_lightmap')

        # 改参数（wrapper 图层）
        prop = wrapper.getPropertyFromId('p_light_azimuth_deg',
                                         SDPropertyCategory.Input)
        before = wrapper.getPropertyValue(prop).get()
        wrapper.setPropertyValue(prop, SDValueFloat.sNew(90.0))
        after = wrapper.getPropertyValue(prop).get()
        res['param_change'] = {'before': float(before),
                               'after': float(after)}

        # test graph 里实例重算（自建 output 连接防死码消除）
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
        from sd.api.sdbasetypes import float2
        out_node = test.newNode('sbs::compositing::output')
        out_node.setPosition(float2(5600.0, 2400.0))
        outs = inst.getProperties(SDPropertyCategory.Output)
        out_pin = str(outs.getItem(0).getId())
        inst.newPropertyConnectionFromId(out_pin, out_node, 'inputNodeOutput')
        test.compute()
        v = inst.getPropertyValue(outs.getItem(0))
        tex = v.get()
        sz = tex.getSize()
        tex.save(os.path.join(VAL_DIR, 'param_azim90.exr'), '')
        res['saved'] = (sz.x, sz.y)
        res['ok'] = True
    except BaseException:
        import traceback
        res['fail'] = traceback.format_exc()

    with open(os.path.join(VAL_DIR, 'param_effect.json'), 'w',
              encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
