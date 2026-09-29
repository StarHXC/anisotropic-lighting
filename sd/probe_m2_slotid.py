# -*- coding: utf-8 -*-
r"""M2 诊断 5 — 槽位索引判定：单一槽连接，逐 slot 读 R 通道特征值。

每次只连 1 张 bitmap 到全新 PP，读 slot0..3 的 R —— 判定 samplecol(i)
与物理引脚的真实映射（正式包场景）。
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.')
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')
           or k == 'stages']:
    del sys.modules[_k]

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
REPORT = {'probe': 'm2_slotid', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')

    bmps = []
    for rid in ('src_bake_position', 'src_bake_normalobj', 'src_mask1', 'src_bake_ao'):
        r = pkg.findResourceFromUrl(f'pkg:///{rid}')
        assert r is not None, rid
        bmps.append(r)

    # 每个 slot 一个 PP，全部 4 图独立 PP 直读 slot0.R
    outs = {}
    for si, res in enumerate(bmps):
        pp, _ = SDAPI.create_pp(wrapper, colorswitch=False, size_log2=11)
        pp.setPosition(float2(2600.0 + 400.0 * si, 1200.0))
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(2600.0 + 400.0 * si, 1200.0))
        SDAPI.connect_pp_input(n, pp)
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope=f'm2_sid{si}')
        pos_n = SDAPI.get_pos_node(fg)
        # 读所有 4 个 slot 索引（当前 PP 只有 1 个连接 → slot>0 应该黑）
        s0 = SDAPI.samplecol_node(fg, pos_n, 0)
        v = em.sw1(NodeRef(s0, 'f4'), 0)
        fg.setOutputNode(v.node, True)
        on = wrapper.newNode('sbs::compositing::output')
        on.setPosition(float2(3200.0 + 400.0 * si, 1200.0))
        pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
        wrapper.setOutputNode(on, True)
        p = os.path.join(OUT_DIR, f'm2_sid{si}.exr')
        rb = compute_and_save(wrapper, pp, p)
        outs[si] = {'bitmap': str(res.getUrl()) if hasattr(res, 'getUrl') else si,
                    'render': rb, 'exr': p}
        wrapper.deleteNode(on)
        wrapper.deleteNode(pp)
    REPORT['outs'] = {k: {kk: vv for kk, vv in v.items() if kk != 'exr'}
                      for k, v in outs.items()}
    REPORT['paths'] = {k: v['exr'] for k, v in outs.items()}
    REPORT['ok'] = all(v['render']['ok'] for v in outs.values())


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_slotid_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
