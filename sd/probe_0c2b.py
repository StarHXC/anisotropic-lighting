# -*- coding: utf-8 -*-
r"""0C2b — 8bit PNG 加载转换曲线锁定。
fixture：256×1 灰度条（r=g=b=v/255 全值域）+ 16bit 版本对照。
SD 直通读回 → 外部画转换曲线。
输出：sd/validation/probe_0c2b_report.json + curve8.exr / curve16.exr
"""
import json
import os
import struct
import sys
import zlib

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0c2b_report.json')

report = {'probe': '0C2b', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0C2b 失败于: {name}  ({detail})')


def write_png_gray(path, w, h, bitdepth, values):
    """灰度 PNG（单通道）。values[y][x] 为整数像素值。"""
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    ct = 0 if bitdepth == 8 else 0  # grayscale
    ihdr = struct.pack('>IIBBBBB', w, h, bitdepth, 0, 0, 0, 0)
    raw = b''
    for row in values:
        scan = b'\x00'
        for v in row:
            scan += struct.pack('>H' if bitdepth == 16 else 'B', v)
        raw += scan
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


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
    # fixtures：256×1（2 幂宽）——8bit 全值域 + 16bit 等比值 + float TIFF
    W = 256
    v8 = [[v for v in range(W)]]
    v16 = [[v * 257 for v in range(W)]]      # 0..65535 全域
    vf = [[(v / 255.0, 0.0, 0.0, 1.0) for v in range(W)]]

    p8 = os.path.join(VAL_DIR, 'fixture_gray8.png')
    p16 = os.path.join(VAL_DIR, 'fixture_gray16.png')
    pf = os.path.join(VAL_DIR, 'fixture_grayf.tiff')
    write_png_gray(p8, W, 1, 8, v8)
    write_png_gray(p16, W, 1, 16, v16)
    write_tiff_rgba32f(pf, W, 1, vf)
    step('fixtures 生成', all(os.path.getsize(p) > 0 for p in (p8, p16, pf)))

    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint import SDValueInt
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    graph = SDAPI.get_current_graph()
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

    # 三个直通 PP（256×1 同尺寸 1:1），bitmap 各异；16bit PNG 版本各 $format 试
    cases = [
        ('gray8', p8, None),
        ('gray16', p16, None),
        ('gray16_32f', p16, 3),
        ('grayf', pf, None),
    ]
    outs = {}
    for tag, fpath, fmt in cases:
        with SDAPI.undo_group(f'aniso_pp 0C2b {tag}'):
            resource = SDResourceBitmap.sNewFromFile(folder, fpath,
                                                     EmbedMethod.CopiedAndLinked)
            resource.setIdentifier(f'fixture_0c2b_{tag}')
            node = graph.newInstanceNode(resource)
            node.setPosition(float2(21000.0, -2600.0))
            if fmt is not None:
                prop = node.getPropertyFromId('$format', SDPropertyCategory.Input)
                node.setPropertyInheritanceMethod(
                    prop, SDPropertyInheritanceMethod.Absolute)
                node.setPropertyValue(prop, SDValueInt.sNew(fmt))
            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=8)  # 256×1
            pp.setPosition(float2(21400.0, -2600.0))
            SDAPI.connect_pp_input(node, pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(21800.0, -2600.0))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(pp)
        pos = SDAPI.get_pos_node(fg)
        smp = SDAPI.samplecol_node(fg, pos, 0)
        fg.setOutputNode(smp, True)
        exr = os.path.join(VAL_DIR, f'curve_{tag}.exr')
        rb = compute_and_save(graph, pp, exr)
        outs[tag] = {'ok': rb['ok'], 'exr': exr}
        step(f'读回 {tag}', rb['ok'], {'size': rb['size']})

    report['outs'] = outs
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
