# -*- coding: utf-8 -*-
r"""Stage 0 / 0D 第三版 — 3 参数图架构（0B6 bitmap 多连接模型直接适用）。

  P1 = 16×1: (vx, vy, vz, fbz)      sample(0)
  P2 = 16×1: (mode, e0, e1, thr)    sample(1)
  P3 = 16×1: (angle_deg, srgb_in, seg_x, 0)  sample(2)
  5 个计算 PP（16×1，1:1 零重采样），每 PP 3 连接。
  像素 x = case x（u=(x+0.5)/16 → texel x）。
输出：sd/validation/probe_0d3_report.json + pp1..pp5.exr
"""
import json
import math
import os
import struct
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0d3_report.json')

report = {'probe': '0D3', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0D3 失败于: {name}  ({detail})')


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


SRGB_TABLE = [0.002, 0.0031308, 0.5, 1.0, 2.0, 0.0,
              0.003, 0.9, 0.1, 0.8, 0.33, 0.77]


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sdbasetypes import float2

    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

    man = json.load(open(os.path.join(VAL_DIR, 'probe_0d_manifest.json'),
                         encoding='utf-8'))
    cases = man['cases']
    step('case 表', len(cases) == 12, {'cases': len(cases)})

    # 4 张 16×1 参数图（P4=完整 fallback 向量——基准 cross3(v, fb) 用完整 fb）
    W = 16
    p1 = [[(0.0, 0.0, 0.0, 1.0) for _ in range(W)]]
    p2 = [[(0.0, 0.0, 0.0, 1.0) for _ in range(W)]]
    p3 = [[(0.0, 0.0, 0.0, 1.0) for _ in range(W)]]
    p4 = [[(0.0, 0.0, 1.0, 0.0) for _ in range(W)]]
    for i, c in enumerate(cases):
        vx, vy, vz = c['v']
        fbx, fby, fbz = c['fallback']
        p1[0][i] = (vx, vy, vz, fbz)
        p2[0][i] = (float(c['mode']), c['e0'], c['e1'], c['thr'])
        p3[0][i] = (float(c['angle']), SRGB_TABLE[i], 0.5, 0.0)
        p4[0][i] = (fbx, fby, fbz, 0.0)

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

    param_nodes = []
    for tag, rows in (('p1', p1), ('p2', p2), ('p3', p3), ('p4', p4)):
        tiff = os.path.join(VAL_DIR, f'probe_0d3_{tag}.tiff')
        write_tiff_rgba32f(tiff, W, 1, rows)
        resource = SDResourceBitmap.sNewFromFile(folder, tiff,
                                                 EmbedMethod.CopiedAndLinked)
        resource.setIdentifier(f'fixture_0d3_{tag}')
        node = graph.newInstanceNode(resource)
        node.setPosition(float2(12600.0, 200.0))
        param_nodes.append(node)
    step('4 参数图导入', len(param_nodes) == 4)

    def make_pp(tag, body_fn):
        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=4)  # 16×1
        pp.setPosition(float2(13000.0, -2600.0))
        for pn in param_nodes:
            SDAPI.connect_pp_input(pn, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(13400.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope=f'0d3_{tag}')
        pos = SDAPI.get_pos_node(fg)
        p2ref = NodeRef(pos, 'f2')
        # 当前像素 case = 本像素；texel uv = $pos（1:1）
        def sample(k):
            s = fg.newNode('sbs::function::samplecol')
            SDAPI.fg_connect(p2ref, s, 'pos')
            s.setInputPropertyValueFromId('__constant__',
                                          __import__('sd.api.sdvalueint2',
                                                     fromlist=['SDValueInt2'])
                                          .SDValueInt2.sNew(
                                              __import__('sd.api.sdbasetypes',
                                                         fromlist=['int2'])
                                              .int2(k, 0)))
            return NodeRef(s, 'f4')
        tA, tB, tC, tD = sample(0), sample(1), sample(2), sample(3)
        packed = body_fn(em, fg, tA, tB, tC, tD)
        fg.setOutputNode(packed.node, True)
        return pp

    pps = {}

    def body_sn(em, fg, tA, tB, tC, tD):
        v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
        fb = em.v3(em.sw1(tD, 0), em.sw1(tD, 1), em.sw1(tD, 2))
        sn = em.safe_normalize(v, fb, 1e-12)
        return em.v4_from_f3(em.swizzle3_from_f4(sn), em.sw1(sn, 3))
    pps['pp1_sn'] = make_pp('pp1', body_sn)
    step('PP1 safeNormalize', True)

    def body_pf(em, fg, tA, tB, tC, tD):
        v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
        pf = em.plane_fallback(v)
        trig = em._expr_cache.get('planeFallback_trigger', [None])[-1]
        trig_w = em.sw1(trig, 3) if trig is not None else em.c_f1(0.0)
        return em.v4_from_f3(pf, trig_w)
    pps['pp2_pf'] = make_pp('pp2', body_pf)
    step('PP2 planeFallback', True)

    def body_cr(em, fg, tA, tB, tC, tD):
        v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
        fb = em.v3(em.sw1(tD, 0), em.sw1(tD, 1), em.sw1(tD, 2))
        cr = em.cross3(v, fb)
        ps = em.pick_sign(em.sw1(tA, 2))
        return em.v4_from_f3(cr, ps)
    pps['pp3_cr'] = make_pp('pp3', body_cr)
    step('PP3 cross3+pickSign', True)

    def body_rot(em, fg, tA, tB, tC, tD):
        ang = em.mul(em.sw1(tC, 0), em.c_f1(math.pi / 180.0))
        rot_y = em.sin(ang)
        rot_x = em.cos(ang)
        seg = em.segmented(em.sw1(tC, 2), em.sw1(tB, 0),
                           em.sw1(tB, 1), em.sw1(tB, 2), em.sw1(tB, 3))
        srgb = em.linear_to_srgb_f1(em.sw1(tC, 1))
        return em.v4_from_f3(em.v3(rot_x, rot_y, seg), srgb)
    pps['pp4_rot'] = make_pp('pp4', body_rot)
    step('PP4 rot+segmented+sRGB', True)

    def body_p3(em, fg, tA, tB, tC, tD):
        mode = em.sw1(tB, 0)
        p3 = em.pick3(em.v3(em.c_f1(0.1), em.c_f1(0.0), em.c_f1(0.0)),
                      em.v3(em.c_f1(0.0), em.c_f1(0.2), em.c_f1(0.0)),
                      em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(0.3)), mode)
        return em.v4_from_f3(p3, em.c_f1(0.0))
    pps['pp5_p3'] = make_pp('pp5', body_p3)
    step('PP5 pick3', True)

    readbacks = {}
    for tag, pp in pps.items():
        exr = os.path.join(VAL_DIR, f'probe_0d3_{tag}.exr')
        rb = compute_and_save(graph, pp, exr)
        readbacks[tag] = {'ok': rb['ok'], 'exr': exr, 'size': rb['size'],
                          'err': (rb['error'] or '')[:150]}
        step(f'读回 {tag}', rb['ok'], {'size': rb['size']})

    report['readbacks'] = readbacks
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
