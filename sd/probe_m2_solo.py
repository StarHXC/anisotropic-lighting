# -*- coding: utf-8 -*-
r"""M2 诊断 4 — 最小复现：load 正式包 → wrapper.compute()（默认参数）→ 落盘。
不做任何实例/参数操作，一次渲染。
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
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')]:
    del sys.modules[_k]

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
REPORT = {'probe': 'm2_solo', 'fail': None}


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')
    nodes = wrapper.getNodes()
    pp = None
    out_n = None
    for i in range(nodes.getSize()):
        n = nodes.getItem(i)
        d = str(n.getDefinition().getId())
        if d == 'sbs::compositing::pixelprocessor':
            pp = n
        elif d == 'sbs::compositing::output':
            out_n = n
    assert pp is not None and out_n is not None
    # 确认 wrapper output node
    is_out = None
    try:
        is_out = wrapper.isOutputNode(out_n)
    except BaseException:
        is_out = '<n/a>'
    REPORT['is_output'] = str(is_out)
    wrapper.setOutputNode(out_n, True)

    rb = compute_and_save(wrapper, pp, os.path.join(OUT_DIR, 'm2_solo.exr'))
    REPORT['render'] = rb
    REPORT['ok'] = rb['ok']


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm2_solo_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
