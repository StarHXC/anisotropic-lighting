# -*- coding: utf-8 -*-
r"""0D2 诊断二：拆解 sw1 与 v3 组装。
PP 输出 = (sw1(tA,0), sw1(tA,1), sw1(tA,2), sw1(tA,3))  ← 直接 swizzle
（texel uv 固定 0.5/64，参数图重制为 64×1）
输出：sd/validation/diag2.exr
"""
import json
import os
import struct
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0d2diag2_report.json')


def write_tiff_rgba32f(path, w, h, rows):
    header = struct.pack('<2sHI', b'II', 42, 8)
    n_entries = 12
    ifd_size = 2 + n_entries * 12 + 4
    data_offset = 8 + ifd_size
    pixel_bytes = w * h * 16
    px = b''
    for row in rows:
        for (r, g, b, a) in row:
            px += struct.pack('<ffff', r, g, b, a)
    entries = [
        (256, 4, 1, w), (257, 4, 1, h),
        (258, 3, 4, 0), (259, 3, 1, 1), (262, 3, 1, 2),
        (273, 4, 1, 0), (277, 3, 1, 4), (278, 4, 1, h),
        (279, 4, 1, pixel_bytes), (339, 3, 4, 0),
        (338, 3, 1, 2), (271, 2, 0, 0),
    ]
    extra_off = data_offset
    bps_data = struct.pack('<4H', 32, 32, 32, 32)
    sf_data = struct.pack('<4H', 3, 3, 3, 3)
    strip_off = data_offset + len(bps_data) + len(sf_data)
    entries[5] = (273, 4, 1, strip_off)
    entries[2] = (258, 3, 4, extra_off)
    entries[9] = (339, 3, 4, extra_off + len(bps_data))
    ifd = struct.pack('<H', n_entries)
    for (tag, typ, cnt, val) in entries:
        ifd += struct.pack('<HHI', tag, typ, cnt)
        if typ == 3 and cnt == 1:
            ifd += struct.pack('<HH', val, 0)
        else:
            ifd += struct.pack('<I', val)
    ifd += struct.pack('<I', 0)
    with open(path, 'wb') as f:
        f.write(header + ifd + bps_data + sf_data + px)


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    res = {'fail': None}
    try:
        graph = SDAPI.get_current_graph()

        # 64×1 参数图（case i 的 texelA 在 x=i*3? 不——64 布局：texel i 直接放
        # (i/64 中心)。简化：texel k 放值 (k+1)/64 于 r，其余 0 → 判定映射。
        W = 64
        rows = [[(float(x + 1) / 64.0, 0.0, 0.0, 1.0) for x in range(W)]]
        tiff = os.path.join(VAL_DIR, 'diag2_params.tiff')
        write_tiff_rgba32f(tiff, W, 1, rows)

        pkg = graph.getPackage()
        folder = None
        children = pkg.getChildrenResources(False)
        for i in range(children.getSize()):
            if children.getItem(i).getIdentifier() == 'Resources':
                folder = children.getItem(i)
                break
        if folder is None:
            from sd.api.sdresourcefolder import SDResourceFolder
            folder = SDResourceFolder.sNew(pkg)
            folder.setIdentifier('Resources')
        from sd.api.sdresourcebitmap import SDResourceBitmap
        from sd.api.sdresource import EmbedMethod
        resource = SDResourceBitmap.sNewFromFile(folder, tiff,
                                                 EmbedMethod.CopiedAndLinked)
        resource.setIdentifier('fixture_diag2')
        param_node = graph.newInstanceNode(resource)
        param_node.setPosition(float2(14800.0, -2600.0))

        # PP 64×1（log2=6）
        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=6)
        pp.setPosition(float2(15200.0, -2600.0))
        SDAPI.connect_pp_input(param_node, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(15600.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(pp)
        pos = SDAPI.get_pos_node(fg)
        em = Emitter(fg, cache_scope='diag2')
        p2 = NodeRef(pos, 'f2')
        s0 = SDAPI.samplecol_node(fg, pos, 0)   # $pos 原样采样
        # 输出：sample 原样 float4（r 应=(x+1)/64）
        fg.setOutputNode(s0, True)
        rb = compute_and_save(graph, pp, os.path.join(VAL_DIR, 'diag2.exr'))
        res = {'rb': {'ok': rb['ok'], 'err': (rb['error'] or '')[:150]}}
    except BaseException:
        import traceback as tb
        res = {'fail': tb.format_exc()}

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
