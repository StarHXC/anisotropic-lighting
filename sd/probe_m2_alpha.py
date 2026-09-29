# -*- coding: utf-8 -*-
r"""M2 诊断 8 — 受控 alpha 实验同一梯度图生成 RGBA 与 RGB 两个版本，
分别单连直通渲染，判定无 alpha PNG 的解码行为。

梯度: R = u (水平), G = v (垂直), B = 0.5。
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
REPORT = {'probe': 'm2_alpha', 'fail': None}


def write_png(path, w, h, colortype, rows_bytes):
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, colortype, 0, 0, 0))
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
            r = x * 255 // (w - 1)
            g = y * 255 // (h - 1)
            row_a += bytes([r, g, 128, 255])
            row_b += bytes([r, g, 128])
        rows_rgba += row_a
        rows_rgb += row_b
    p_rgba = os.path.join(FIX, 'grad_rgba.png')
    p_rgb = os.path.join(FIX, 'grad_rgb.png')
    write_png(p_rgba, w, h, 6, rows_rgba)
    write_png(p_rgb, w, h, 2, rows_rgb)

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
    wrapper_g = SDSBSCompGraph.sNew(pkg)
    wrapper_g.setIdentifier('m2_alpha_test')

    for tag, p in (('rgba', p_rgba), ('rgb', p_rgb)):
        res = SDResourceBitmap.sNewFromFile(pkg, p, EmbedMethod.CopiedAndLinked)
        res.setIdentifier(f'src_grad_{tag}')
        pp, _ = SDAPI.create_pp(wrapper_g, colorswitch=True, size_log2=8)
        pp.setPosition(float2(300.0 + (600.0 if tag == 'rgb' else 0.0), 0.0))
        n = wrapper_g.newInstanceNode(res)
        n.setPosition(float2(300.0, 0.0))
        SDAPI.connect_pp_input(n, pp)
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope=f'm2_a_{tag}')
        pos_n = SDAPI.get_pos_node(fg)
        s0 = SDAPI.samplecol_node(fg, pos_n, 0)
        packed = em.v4_from_f3(em.swizzle3_from_f4(NodeRef(s0, 'f4')), em.c_f1(1.0))
        fg.setOutputNode(packed.node, True)
        on = wrapper_g.newNode('sbs::compositing::output')
        on.setPosition(float2(1000.0 + (600.0 if tag == 'rgb' else 0.0), 0.0))
        pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
        wrapper_g.setOutputNode(on, True)
        out_p = os.path.join(OUT_DIR, f'm2_grad_{tag}.exr')
        rb = compute_and_save(wrapper_g, pp, out_p)
        REPORT[f'{tag}_render'] = rb
        REPORT[f'{tag}_path'] = out_p
        wrapper_g.deleteNode(on)
        wrapper_g.deleteNode(pp)
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_alpha_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
