# -*- coding: utf-8 -*-
r"""M2 诊断 — 正式包 PP FG 内部通道级输出（一次 build_core + kernel 中间量）。

直接 load aniso_mask.sbs，在 PP perpixel FG 上临时把输出切到
中间量（hn/ht/hb/Vg/Vh），求值落盘后恢复 M 输出（不保存包）。
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
REPORT = {'probe': 'm2_channels', 'fail': None}


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
    nodes = wrapper.getNodes()
    pp = None
    for i in range(nodes.getSize()):
        n = nodes.getItem(i)
        if str(n.getDefinition().getId()) == 'sbs::compositing::pixelprocessor':
            pp = n
            break
    assert pp is not None, 'PP 未找到'
    fg = pp.getPropertyGraph(pp.getPropertyFromId('perpixel', SDPropertyCategory.Input))

    # 枚举 FG 输出节点（M = setOutputNode 的当前节点）与关键节点类型统计
    fgnodes = fg.getNodes()
    kinds = {}
    for i in range(fgnodes.getSize()):
        d = str(fgnodes.getItem(i).getDefinition().getId())
        kinds[d] = kinds.get(d, 0) + 1
    REPORT['fg_kinds'] = kinds

    # samplecol 槽位检查：找全部 samplecol 的 __constant__ int2 值
    samples = []
    for i in range(fgnodes.getSize()):
        n = fgnodes.getItem(i)
        if str(n.getDefinition().getId()) == 'sbs::function::samplecol':
            v = n.getInputPropertyValueFromId('__constant__')
            iv = v.get() if v is not None else None
            samples.append((iv.x, iv.y) if iv is not None else None)
    REPORT['samplecol_slots'] = samples

    # PP 输入引脚连接（哪些 bitmap 连到哪些槽）
    pins = SDAPI.enumerate_input_pins(pp)
    REPORT['pp_pins'] = pins
    conns = []
    for pid_ in pins:
        prop = pp.getPropertyFromId(pid_, SDPropertyCategory.Input)
        c = pp.getPropertyConnections(prop)
        if c.getSize() > 0:
            src = c.getItem(0).getInputPropertyNode()
            rid = '<fg>'
            try:
                rr = src.getReferencedResource()
                if rr is not None:
                    rid = str(rr.getUrl())
            except BaseException:
                pass
            conns.append({pid_: rid})
    REPORT['pp_connections'] = conns

    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm2_channels_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
