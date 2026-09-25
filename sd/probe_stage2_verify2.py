# -*- coding: utf-8 -*-
r"""Stage 2 隔离诊断 v2：
  1. wrapper graph 自身 compute + 输出读回（不经实例）
  2. 实例属性 input 连接状态枚举
输出：sd/validation/stage2_verify2.json + stage2_wrapper_self.exr
"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'stage2_verify2.json')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    res = {}
    try:
        pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
        pkg = pkg_mgr.getUserPackageFromFilePath(SBS_OUT)
        wrapper = pkg.findResourceFromUrl('pkg:///aniso_lightmap')

        # 1) wrapper 自身 compute
        out_nodes = wrapper.getOutputNodes()
        if out_nodes.getSize() > 0:
            out_node = out_nodes.getItem(0)
            rb = compute_and_save(wrapper, out_node,
                                  os.path.join(VAL_DIR,
                                               'stage2_wrapper_self.exr'))
            res['wrapper_self'] = {'ok': rb['ok'], 'size': rb['size'],
                                   'err': (rb['error'] or '')[:250]}

        # 2) test 实例的输入连接状态
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
        if inst is not None:
            conns = []
            props = inst.getProperties(SDPropertyCategory.Input)
            for i in range(props.getSize()):
                p = props.getItem(i)
                pid = str(p.getId())
                if pid.startswith('p_') or pid in ('output',):
                    continue
                cc = inst.getPropertyConnections(p)
                conns.append({'input': pid, 'connections': cc.getSize()})
            res['inst_inputs'] = conns
        res['ok'] = True
    except BaseException:
        import traceback
        res['fail'] = traceback.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
