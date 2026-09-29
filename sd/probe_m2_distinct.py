# -*- coding: utf-8 -*-
r"""M2 诊断 7（决定性）— 4 张可区分常数图连 4 槽 → 读回 slot0..3.R。

常数图生成（PIL→PNG8 灰度）：0.1/0.3/0.6/0.9。
直接判 samplecol(i) ↔ 连接顺序的映射。
"""
import json
import os
import sys
import traceback
import struct
import zlib

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

FIX = os.path.join(SD_DIR, 'validation_mask', 'fixtures')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm2_distinct', 'fail': None}


def write_gray_png8(path, w, h, val_u8):
    """RGBA 16bit 常数图（复用 M0 已验证的 16bit 写入路径）。"""
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    v = val_u8 << 8
    px = struct.pack('>HHHH', v, v, v, 65535)
    raw = b'\x00' + px * w
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 6))
           + chunk(b'IEND', b''))
    open(path, 'wb').write(png)


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save
    from aniso_pp.emitter import Emitter, NodeRef

    vals = [0.1, 0.3, 0.6, 0.9]
    paths = []
    for i, v in enumerate(vals):
        p = os.path.join(FIX, f'const_{i}.png')
        # 256²（SD 对非 2 幂尺寸敏感；与已验证 fixture 同规格）
        write_gray_png8(p, 256, 256, int(round(v * 255)))
        paths.append(p)

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    pkg = pkg_mgr.newUserPackage()
    wrapper = SDSBSCompGraph.sNew(pkg)
    wrapper.setIdentifier('m2_distinct')

    pp, _ = SDAPI.create_pp(wrapper, colorswitch=True, size_log2=6)
    pp.setPosition(float2(300.0, 0.0))
    for p in paths:
        res = SDResourceBitmap.sNewFromFile(pkg, p, EmbedMethod.CopiedAndLinked)
        res.setIdentifier('src_' + os.path.basename(p).replace('.png', ''))
        n = wrapper.newInstanceNode(res)
        n.setPosition(float2(300.0, 0.0))
        SDAPI.connect_pp_input(n, pp)
    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='m2_dist')
    pos_n = SDAPI.get_pos_node(fg)
    reads = []
    for i in range(4):
        s = SDAPI.samplecol_node(fg, pos_n, i)
        reads.append(em.sw1(NodeRef(s, 'f4'), 0))
    packed = em.v4_from_f3(em.v3(reads[0], reads[1], reads[2]), reads[3])
    fg.setOutputNode(packed.node, True)
    on = wrapper.newNode('sbs::compositing::output')
    on.setPosition(float2(900.0, 0.0))
    pp.newPropertyConnectionFromId('unique_filter_output', on, 'inputNodeOutput')
    wrapper.setOutputNode(on, True)
    p = os.path.join(OUT_DIR, 'm2_distinct.exr')
    rb = compute_and_save(wrapper, pp, p)
    REPORT['render'] = rb
    REPORT['expect'] = 'slot i 读到 vals[i]（若恒等映射）'
    REPORT['ok'] = rb['ok']


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}

with open(os.path.join(OUT_DIR, 'm2_distinct_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
