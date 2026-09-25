# -*- coding: utf-8 -*-
r"""0C2c — 8bit RGB（三通道）PNG 加载判定：复刻 position.png 结构。
fixture：8×1 RGB 三通道独立递增 + 全图对照（用真实 position.png 直通）。
输出：sd/validation/probe_0c2c_report.json + rgb8.exr / pos_direct.exr
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
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0c2c_report.json')

report = {'probe': '0C2c', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0C2c 失败于: {name}  ({detail})')


def write_png_rgb8(path, w, h, rows):
    """8-bit RGB PNG。rows[y][x]=(r,g,b)"""
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    raw = b''
    for row in rows:
        scan = b'\x00'
        for (r, g, b) in row:
            scan += struct.pack('BBB', r, g, b)
        raw += scan
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main():
    W = 256
    rows = [[((v * 3) % 256, (v * 7) % 256, (v * 11) % 256) for v in range(W)]]
    p = os.path.join(VAL_DIR, 'fixture_rgb8.png')
    write_png_rgb8(p, W, 1, rows)
    step('8bit RGB fixture', os.path.getsize(p) > 0, {'path': p})

    import sd
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sdbasetypes import float2
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

    # fixture RGB8 直通
    resource = SDResourceBitmap.sNewFromFile(folder, p,
                                             EmbedMethod.CopiedAndLinked)
    resource.setIdentifier('fixture_0c2c_rgb8')
    node = graph.newInstanceNode(resource)
    node.setPosition(float2(22600.0, -2600.0))

    with SDAPI.undo_group('aniso_pp 0C2c: build'):
        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=8)
        pp.setPosition(float2(23000.0, -2600.0))
        SDAPI.connect_pp_input(node, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(23400.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
    fg, _ = SDAPI.get_perpixel_graph(pp)
    pos = SDAPI.get_pos_node(fg)
    smp = SDAPI.samplecol_node(fg, pos, 0)
    fg.setOutputNode(smp, True)
    rb = compute_and_save(graph, pp, os.path.join(VAL_DIR, 'rgb8.exr'))
    step('RGB8 直通读回', rb['ok'], {'size': rb['size']})

    # 真实 position.png 直通（2048²）
    bmps = {}
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        n2 = nodes.getItem(i)
        try:
            url = n2.getReferencedResource().getUrl()
        except BaseException:
            continue
        if '/bake_position' in url:
            with SDAPI.undo_group('aniso_pp 0C2c: pos direct'):
                pp2, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
                pp2.setPosition(float2(24000.0, -2600.0))
                SDAPI.connect_pp_input(n2, pp2)
                o2 = graph.newNode('sbs::compositing::output')
                o2.setPosition(float2(24400.0, -2600.0))
                pp2.newPropertyConnectionFromId('unique_filter_output', o2,
                                                'inputNodeOutput')
            fg2, _ = SDAPI.get_perpixel_graph(pp2)
            pos2 = SDAPI.get_pos_node(fg2)
            s2 = SDAPI.samplecol_node(fg2, pos2, 0)
            fg2.setOutputNode(s2, True)
            rb2 = compute_and_save(graph, pp2,
                                   os.path.join(VAL_DIR, 'pos_direct.exr'))
            step('position 直通读回', rb2['ok'], {'size': rb2['size']})
            break

    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
