# -*- coding: utf-8 -*-
r"""Stage 0 / 0C — 位深保真全自动探针。

fixture（本脚本外部生成，SD 内只读文件路径）：
  A. RGB 16-bit PNG（相邻 uint16 差 1，三通道不同步进）——验证 16bit 源不被降位
  B. RGBA float32 TIFF（负值/HDR/A=0但RGB≠0 四象限）——验证 HDR/负值/alpha 不被裁剪
链路：SDResourceBitmap 导入 → PP 直通 → compute → SDTexture.save EXR → 外部逐位比对。
$format 实验组：bitmap 节点 $format=8bit默认 vs 3(32F) 各跑一遍。
输出：sd/validation/probe_0c2_report.json + fixture + 读回 EXR
"""
import json
import os
import struct
import sys
import zlib
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0c2_report.json')

report = {'probe': '0C2', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0C2 失败于: {name}  ({detail})')


# ------------------------------------------------------------ fixture 写出

def write_png16_rgb(path, w, h, rows):
    """16-bit RGB PNG。rows[y][x]=(r,g,b) uint16。"""
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', w, h, 16, 2, 0, 0, 0)
    raw = b''
    for row in rows:
        scan = b'\x00'
        for (r, g, b) in row:
            scan += struct.pack('>HHH', r, g, b)
        raw += scan
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def write_tiff_rgba32f(path, w, h, rows):
    """最小 RGBA float32 TIFF（无压缩， striped 简化为单 strip）。"""
    # TIFF 头：II*\0 offset；IFD 条目
    # 简化：用 ImageIO 不可行（本地有 imageio 但 SD 进程内不保证）——手写 TIFF
    W, H, BPS = w, h, 64  # 64 bit = 4 通道 float32
    # IFD entries: width height bitdepth sopbits photometric stripoffset
    #              samplesperpixel rowsperstrip stripbytecounts sampleformat extrashannels
    header = struct.pack('<2sHI', b'II', 42, 8)
    n_entries = 12
    ifd_size = 2 + n_entries * 12 + 4
    data_offset = 8 + ifd_size
    pixel_bytes = W * H * 16
    # 像素数据布局 TIFF strip: RGBAZ 交错 float32
    px = b''
    for row in rows:
        for (r, g, b, a) in row:
            px += struct.pack('<ffff', r, g, b, a)
    strip_off = data_offset
    # extra samples 条目需要（第 4 通道 = unassociated alpha）
    entries = [
        (256, 4, 1, W),            # ImageWidth LONG
        (257, 4, 1, H),            # ImageLength
        (258, 3, 4, 0),            # BitsPerSample → 4 个 SHORT 需外部存储
        (259, 3, 1, 1),            # Compression = none
        (262, 3, 1, 2),            # Photometric = RGB
        (273, 4, 1, strip_off),    # StripOffsets
        (277, 3, 1, 4),            # SamplesPerPixel = 4
        (278, 4, 1, H),            # RowsPerStrip
        (279, 4, 1, pixel_bytes),  # StripByteCounts
        (339, 3, 4, 0),            # SampleFormat → 4 个 SHORT (3=float IEEE)
        (338, 3, 1, 2),            # ExtraSamples = 2 (unassociated alpha)
        (271, 2, 0, 0),            # 占位（不用）→ 改为放 BitsPerSample/SampleFormat 外部数据
    ]
    # 外部数据区（紧跟 IFD）：BitsPerSample(4×SHORT) + SampleFormat(4×SHORT)
    extra_off = data_offset
    bps_data = struct.pack('<4H', 32, 32, 32, 32)
    sf_data = struct.pack('<4H', 3, 3, 3, 3)
    extra_len = len(bps_data) + len(sf_data)
    strip_off = data_offset + extra_len
    # 修正 StripOffsets 与外部指针
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
    ifd += struct.pack('<I', 0)  # next IFD = 0
    with open(path, 'wb') as f:
        f.write(header + ifd + bps_data + sf_data + px)


def build_png16_fixture():
    w = h = 8
    rows = []
    vals = []
    for y in range(h):
        row = []
        for x in range(w):
            i = y * w + x
            r = 32768 + (i % 3)        # 相邻差 1..3
            g = 32768 + ((i * 7) % 5)
            b = 65535 - (i % 4)
            row.append((r, g, b))
            vals.append((r, g, b))
        rows.append(row)
    return rows, vals


def build_f32_fixture():
    w = h = 8
    rows = []
    vals = []
    for y in range(h):
        row = []
        for x in range(w):
            top, left = y < 4, x < 4
            if top and left:
                v = (0.7, 0.3, 0.9, 0.0)       # A=0 RGB≠0
            elif top:
                v = (0.25, 0.5, 0.75, 1.0)
            elif left:
                v = (-0.5, -0.25, -1.0, 1.0)   # 负值
            else:
                v = (2.5, 10.0, 100.0, 1.0)    # HDR
            row.append(v)
            vals.append(v)
        rows.append(row)
    return rows, vals


def main():
    # ---- fixture 生成
    png_rows, png_vals = build_png16_fixture()
    png_path = os.path.join(VAL_DIR, 'fixture_16bit.png')
    write_png16_rgb(png_path, 8, 8, png_rows)
    step('16-bit PNG fixture', os.path.getsize(png_path) > 0, {'path': png_path})

    f32_rows, f32_vals = build_f32_fixture()
    tiff_path = os.path.join(VAL_DIR, 'fixture_f32.tiff')
    write_tiff_rgba32f(tiff_path, 8, 8, f32_rows)
    step('float32 TIFF fixture', os.path.getsize(tiff_path) > 0, {'path': tiff_path})

    # ---- SD 导入 + 直通 + 读回
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdvalueint import SDValueInt
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    step('SD 环境', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

    pkg = graph.getPackage()
    # Resources 文件夹
    folder = None
    children = pkg.getChildrenResources(False)
    for i in range(children.getSize()):
        child = children.getItem(i)
        if child.getIdentifier() == 'Resources':
            folder = child
            break
    if folder is None:
        from sd.api.sdresourcefolder import SDResourceFolder
        folder = SDResourceFolder.sNew(pkg)
        folder.setIdentifier('Resources')
    step('Resources 文件夹', folder is not None)

    # 实验矩阵：{名称: (文件, bitmap $format)}
    # $format=None → 不设置（默认 8bit? 读回验证）；3 → 32F
    matrix = [
        ('png16_default', png_path, None),
        ('png16_32f', png_path, 3),
        ('f32_default', tiff_path, None),
        ('f32_32f', tiff_path, 3),
    ]
    results = {}
    for tag, fpath, fmt in matrix:
        with SDAPI.undo_group(f'aniso_pp 0C2 {tag}'):
            resource = SDResourceBitmap.sNewFromFile(
                folder, fpath, EmbedMethod.CopiedAndLinked)
            resource.setIdentifier(f'fixture_{tag}')
            node = graph.newInstanceNode(resource)
            node.setPosition(float2(12600.0, -2600.0))
            if fmt is not None:
                prop = node.getPropertyFromId('$format', SDPropertyCategory.Input)
                node.setPropertyInheritanceMethod(prop,
                                                  SDPropertyInheritanceMethod.Absolute)
                node.setPropertyValue(prop, SDValueInt.sNew(fmt))
            pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=3)
            pp.setPosition(float2(13000.0, -2600.0))
            SDAPI.connect_pp_input(node, pp)
            out_node = graph.newNode('sbs::compositing::output')
            out_node.setPosition(float2(13400.0, -2600.0))
            pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                           'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(pp)
        pos = SDAPI.get_pos_node(fg)
        smp = SDAPI.samplecol_node(fg, pos, 0)
        SDAPI.fg_set_output(fg, smp)
        exr = os.path.join(VAL_DIR, f'probe_0c2_{tag}.exr')
        rb = compute_and_save(graph, pp, exr)
        results[tag] = {'ok': rb['ok'], 'exr': exr,
                        'err': (rb['error'] or '')[:150]}
        step(f'直通读回 {tag}', rb['ok'],
             {'size': rb['size'], 'err': (rb['error'] or '')[:120]})

    report['matrix'] = results
    report['expect'] = {
        'png16_vals_u16': [list(v) for v in png_vals],
        'f32_vals': [list(v) for v in f32_vals],
        'note': ('外部比对：png16_default/32f 读回/65535 vs u16/65535；'
                 'f32 组逐位。$format 默认组若丢失低位/裁剪 HDR → bitmap 节点'
                 '必须显式 $format=3（renderer 插件做法）'),
    }
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
