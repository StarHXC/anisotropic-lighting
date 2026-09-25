# -*- coding: utf-8 -*-
r"""Stage 0 / 0E — DAG 成本实测（0B/0D 修订版）。

用 0D3 已验证的配方装配模式构建代表性 DAG @2048²：
  深度链 40 层 + 扇出 32 + pick3 全候选 + sample 链。
全部在单 PP（bitmap 参数图 1 输入，sample(0) 恒可靠）。
实测：构建耗时、fg 节点数、compute 耗时、EXR 落盘耗时。
输出：sd/validation/probe_0e2_report.json
"""
import json
import os
import sys
import time
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0e2_report.json')

report = {'probe': '0E2', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0E2 失败于: {name}  ({detail})')


def write_tiff_rgba32f(path, w, h, rows):
    import struct
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
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

    # 源图（用 bake_position 采样做非常数依赖，防死码消除）
    src_bmp = None
    nodes = graph.getNodes()
    for i in range(nodes.getSize()):
        node = nodes.getItem(i)
        try:
            url = node.getReferencedResource().getUrl()
            if '/bake_position' in url:
                src_bmp = node
                break
        except BaseException:
            continue
    step('源 bitmap', src_bmp is not None)

    # ---- 构建（计耗时）
    t0 = time.perf_counter()
    with SDAPI.undo_group('aniso_pp 0E2: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pp.setPosition(float2(20000.0, -2600.0))
        SDAPI.connect_pp_input(src_bmp, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(20400.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
    t_struct = time.perf_counter() - t0
    step('PP 结构创建', True, {'seconds': round(t_struct, 3)})

    fg, _ = SDAPI.get_perpixel_graph(pp)
    em = Emitter(fg, cache_scope='0e2')
    pos = SDAPI.get_pos_node(fg)
    p2 = NodeRef(pos, 'f2')
    u = em.sw1(p2, 0)
    s0 = SDAPI.samplecol_node(fg, pos, 0)
    s0 = NodeRef(s0, 'f4')
    src = em.sw1(s0, 0)  # position.r —— 非常数依赖

    t1 = time.perf_counter()
    # 深度链 40 层
    x = src
    for i in range(40):
        x = em.add(x, em.mul(src, em.c_f1(0.001)))
    n_depth = em.node_count
    # 扇出 32
    acc = em.c_f1(0.0)
    for i in range(32):
        acc = em.add(acc, em.mul(x, em.c_f1(1.0 / 32.0)))
    n_fanout = em.node_count
    # pick3 全候选（未选中分支含深链）
    c0 = acc
    c1 = u
    c2 = em.mul(x, x)
    picked = em.pick3(c0, c1, c2, em.c_f1(1.0))
    t_emit = time.perf_counter() - t1
    total_nodes = em.node_count
    step('DAG 发射（深度40+扇出32+pick3）', True,
         {'fg_nodes': total_nodes, 'after_depth': n_depth,
          'after_fanout': n_fanout, 'emit_seconds': round(t_emit, 3)})

    packed = em.v4_from_f3(em.bc_f3(picked), u)
    fg.setOutputNode(packed.node, True)
    step('输出设置', True)

    # ---- compute（首次编译+求值，计耗时）
    t2 = time.perf_counter()
    exr = os.path.join(VAL_DIR, 'probe_0e2.exr')
    rb = compute_and_save(graph, pp, exr)
    t_compute = time.perf_counter() - t2
    step('首次 compute+save', rb['ok'],
         {'seconds': round(t_compute, 3), 'size': rb['size'],
          'err': (rb['error'] or '')[:150]})

    # ---- 二次 compute（热缓存）
    t3 = time.perf_counter()
    rb2 = compute_and_save(graph, pp, exr + '.2.exr')
    t_compute2 = time.perf_counter() - t3
    step('二次 compute（热）', rb2['ok'], {'seconds': round(t_compute2, 3)})

    report['metrics'] = {
        'fg_nodes': total_nodes,
        'depth_layers': 40,
        'fanout': 32,
        'candidates': 3,
        'struct_seconds': round(t_struct, 3),
        'emit_seconds': round(t_emit, 3),
        'first_compute_seconds': round(t_compute, 3),
        'warm_compute_seconds': round(t_compute2, 3),
        'output': '2048²',
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
