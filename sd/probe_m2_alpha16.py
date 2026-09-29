# -*- coding: utf-8 -*-
r"""M2 诊断 9 — 16bit RGB vs 16bit RGBA 梯度图受控实验。

同一梯度分别写 16bit RGBA (ct=6) 与 16bit RGB (ct=2)，单连直通，
判定 16bit 无 alpha 的解码行为。
"""
import json
import os
import struct
import sys
import traceback
import zlib

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

FIX = os.path.join(SD_DIR, 'validation_mask', 'fixtures')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
REPORT = {'probe': 'm2_alpha16', 'fail': None}


def write_png16(path, w, h, colortype, rows_bytes):
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, colortype, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(rows_bytes, 6))
           + chunk(b'IEND', b''))
    open(path, 'wb').write(png)


def main():
    w = h = 256
    rows_rgba = b''
    rows_rgb = b''
    for y in range(h):
        row_a = b'\x00'
        row_b = b'\x00'
        for x in range(w):
            r = x * 65535 // (w - 1)
            g = y * 65535 // (h - 1)
            row_a += struct.pack('>HHHH', r, g, 32768, 65535)
            row_b += struct.pack('>HHH', r, g, 32768)
        rows_rgba += row_a
        rows_rgb += row_b
    p_rgba = os.path.join(FIX, 'grad16_rgba.png')
    p_rgb = os.path.join(FIX, 'grad16_rgb.png')
    write_png16(p_rgba, w, h, 6, rows_rgba)
    write_png16(p_rgb, w, h, 2, rows_rgb)

    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    wg = SDSBSCompGraph.sNew(pkg)
    wg.setIdentifier('m2_alpha16_test')

    for tag, p in (('rgba', p_rgba), ('rgb', p_rgb)):
        res = SDResourceBitmap.sNewFromFile(pkg, p, EmbedMethod.CopiedAndLinked)
        res.setIdentifier(f'src_g16_{tag}')
        pp, _ = SDAPI.create_pp(wg, colorswitch=True, size_log2=8)
        pp.setPosition(float2(300.0 + (600.0 if tag == 'rgb' else 0.0), 0.0))
        n = wg.newInstanceNode(res)
        n.setPosition(float2(300.0, 0.0))
        SDAPI.connect_pp_input(n, pp)
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope=f'm2_a16_{tag}')
        pos_n = SDAPI.get_pos_node(fg)
        s0 = SDAPI.samplecol_node(fg, pos_n, 0)
        packed = em.v4_from_f3(em.swizzle3_from_f4(NodeRef(s0, 'f4')), em.c_f1(1.0))
        fg.setOutputNode(packed.node, True)
        on = wg.newNode('sbs::compositing::output')
        on.setPosition(float2(1000.0 + (600.0 if tag == 'rgb' else 0.0), 0.0))
        pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
        wg.setOutputNode(on, True)
        out_p = os.path.join(OUT_DIR, f'm2_g16_{tag}.exr')
        rb = compute_and_save(wg, pp, out_p)
        REPORT[f'{tag}_render'] = rb
        REPORT[f'{tag}_path'] = out_p
        wg.deleteNode(on)
        wg.deleteNode(pp)
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_alpha16_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
