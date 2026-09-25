# -*- coding: utf-8 -*-
r"""Stage 0 / 0D — §6 配方实装验证（参数图驱动，单份展开）。

设计（依据 0B/0C 裁定）：
  参数图：36×1 float32 TIFF，每 case 3 texel：
    texelA=(vx,vy,vz,fb_z) texelB=(mode,e0,e1,angle_deg) texelC=(thr,srgb_in,seg_x,0)
  主链：5 个计算 PP 共享参数图（每 PP 单连接 bitmap → sample(0) 恒可靠）：
    PP1: safeNormalize(v,fb)         → (sn.xyz, valid)
    PP2: planeFallback(v)            → (pf.xyz, pf_trigger)
    PP3: cross3(v,fb) + pickSign(vz) → (cr.xyz, ps)
    PP4: 旋转 + segmented + sRGB     → (rot.x, rot.y, seg(seg_x), srgb(srgb_in))
    PP5: pick3(mode)                 → (p3.xyz, 0)
  case 索引：cx = floor(u*12)，texel uv = ((case*3+k)+0.5)/36
  验收：外部与 NumPy 基准（probe_0d_glsl_ref.json）逐 case 对比 1e-4。
输出：sd/validation/probe_0d2_report.json + pp1..pp5.exr
"""
import json
import math
import os
import struct
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0d2_report.json')

report = {'probe': '0D2', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0D2 失败于: {name}  ({detail})')


# ------------------------------------------------ 参数图 TIFF (float32 RGBA)

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


# ------------------------------------------------ case 表（与基准同源）

def load_cases():
    man = json.load(open(os.path.join(VAL_DIR, 'probe_0d_manifest.json'),
                         encoding='utf-8'))
    return man['cases'], man['layout']


SRGB_TABLE = [0.002, 0.0031308, 0.5, 1.0, 2.0, 0.0,
              0.003, 0.9, 0.1, 0.8, 0.33, 0.77]


def build_param_image(cases):
    """64×1（2 幂，与计算 PP 同尺寸 1:1 无重采样）：每 case 3 texel，其余 0。
    返回 (rows, W, meta)。"""
    n = len(cases)
    W = 64
    rows = [[(0.0, 0.0, 0.0, 1.0) for _ in range(W)]]
    meta = []
    for i, c in enumerate(cases):
        vx, vy, vz = c['v']
        fbz = c['fallback'][2]
        texA = (vx, vy, vz, fbz)
        texB = (float(c['mode']), c['e0'], c['e1'], float(c['angle']))
        texC = (c['thr'], SRGB_TABLE[i], 0.5, 0.0)   # thr, srgb_in, seg_x, 0
        base = i * 3
        for k, t in enumerate((texA, texB, texC)):
            rows[0][base + k] = t
        meta.append({'case': i, 'texel_base': base,
                     'texels': [list(texA), list(texB), list(texC)]})
    return rows, W, meta


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdresourcebitmap import SDResourceBitmap
    from sd.api.sdresource import EmbedMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvalueint2 import SDValueInt2

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('graph', 'CompGraph' in type(graph).__name__,
         {'id': SDAPI.get_graph_title(graph)})

    cases, layout = load_cases()
    step('case 表载入', len(cases) == 12, {'cases': len(cases)})

    # 参数图
    rows, W, meta = build_param_image(cases)
    tiff_path = os.path.join(VAL_DIR, 'probe_0d2_params.tiff')
    write_tiff_rgba32f(tiff_path, W, 1, rows)
    step('参数图生成', os.path.getsize(tiff_path) > 0,
         {'path': tiff_path, 'W': W})

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

    # 导入参数图（bitmap 直连！）
    resource = SDResourceBitmap.sNewFromFile(folder, tiff_path,
                                             EmbedMethod.CopiedAndLinked)
    resource.setIdentifier('fixture_0d2_params')
    param_node = graph.newInstanceNode(resource)
    param_node.setPosition(float2(12600.0, 400.0))

    # ------------------------------------------------ 公共发射器构件

    def make_pp(tag, body_fn):
        """建一个 PP（64×1，单输入=参数图，1:1 采样零重采样）。
        body_fn(em, fg, tA, tB, tC) → 打包 NodeRef。"""
        pp, _ = SDAPI.create_pp(graph, colorswitch=True, size_log2=6)  # 64×1
        pp.setPosition(float2(13000.0, -2600.0))
        SDAPI.connect_pp_input(param_node, pp)
        out_node = graph.newNode('sbs::compositing::output')
        out_node.setPosition(float2(13400.0, -2600.0))
        pp.newPropertyConnectionFromId('unique_filter_output', out_node,
                                       'inputNodeOutput')
        fg, _ = SDAPI.get_perpixel_graph(pp)
        em = Emitter(fg, cache_scope=f'0d2_{tag}')
        pos = SDAPI.get_pos_node(fg)
        p2 = NodeRef(pos, 'f2')
        u = em.sw1(p2, 0)
        # 像素 x∈[0,64)：case = floor(u*64/3)=floor(x/3)，slot=x%3
        # texel uv 直接 = $pos（1:1 对齐，无任何换算）
        def sample_texel(offset):
            """采样当前像素 u 偏移 offset 个 texel 的参数图值。
            case c 占 texel c*3..c*3+2；PP 像素 x 的 u=(x+0.5)/64。
            texel uv = u + offset/64 —— 像素组内偏移到 tA/tB/tC。"""
            s = fg.newNode('sbs::function::samplecol')
            uv = em.add(p2, em.bc_f2(em.div(em.c_f1(float(offset)),
                                            em.c_f1(64.0))))
            SDAPI.fg_connect(uv, s, 'pos')
            s.setInputPropertyValueFromId('__constant__',
                                          SDValueInt2.sNew(int2(0, 0)))
            return NodeRef(s, 'f4')
        # 当前像素属于 slot = (x % 3)；但配方需要整组 tA/tB/tC。
        # 让每像素取同组三 texel：x0 = floor(u*64/3)*3 + 0.5 → 折回像素组头。
        # 简化实现：group_base = floor(u*64/3)*3；tA uv=(group_base+0.5)/64 …
        grp = em.mul(em._unary_floor(em.mul(u, em.div(em.c_f1(64.0),
                                                      em.c_f1(3.0)))),
                     em.c_f1(3.0))
        def texel_uv(k):
            num = em.add(grp, em.c_f1(float(k) + 0.5))
            return em.div(num, em.c_f1(64.0))
        def sample_texel(k):
            s = fg.newNode('sbs::function::samplecol')
            uv = em.bc_f2(texel_uv(k))
            SDAPI.fg_connect(uv, s, 'pos')
            s.setInputPropertyValueFromId('__constant__',
                                          SDValueInt2.sNew(int2(0, 0)))
            return NodeRef(s, 'f4')
        tA, tB, tC = (sample_texel(0), sample_texel(1), sample_texel(2))
        packed = body_fn(em, fg, tA, tB, tC)
        SDAPI.fg_set_output(fg, packed.node)
        return pp

    pps = {}

    # PP1: safeNormalize(v, fb=(0,0,fbz)) → (sn.xyz, valid)
    def body_sn(em, fg, tA, tB, tC):
        v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
        fb = em.v3(em.c_f1(0.0), em.c_f1(0.0), em.sw1(tA, 3))
        sn = em.safe_normalize(v, fb, 1e-12)
        return em.v4_from_f3(em.swizzle3_from_f4(sn), em.sw1(sn, 3))
    pps['pp1_sn'] = make_pp('pp1', body_sn)
    step('PP1 safeNormalize 构建', True, None)

    # PP2: planeFallback(v) → (pf.xyz, trigger)
    def body_pf(em, fg, tA, tB, tC):
        v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
        pf = em.plane_fallback(v)
        # trigger：plane_fallback 内部 safeNormalize 的 valid —— 重新暴露：
        # emitter 的 plane_fallback 已把 cn 存进 _expr_cache['planeFallback_trigger']
        trig_nodes = em._expr_cache.get('planeFallback_trigger', [])
        trig = trig_nodes[-1] if trig_nodes else None
        trig_w = em.sw1(trig, 3) if trig is not None else em.c_f1(0.0)
        return em.v4_from_f3(pf, trig_w)
    pps['pp2_pf'] = make_pp('pp2', body_pf)
    step('PP2 planeFallback 构建', True, None)

    # PP3: cross3(v, fb) + pickSign(vz) → (cr.xyz, ps)
    def body_cr(em, fg, tA, tB, tC):
        v = em.v3(em.sw1(tA, 0), em.sw1(tA, 1), em.sw1(tA, 2))
        fb = em.v3(em.c_f1(0.0), em.c_f1(0.0), em.sw1(tA, 3))
        cr = em.cross3(v, fb)
        ps = em.pick_sign(em.sw1(tA, 2))
        return em.v4_from_f3(cr, ps)
    pps['pp3_cr'] = make_pp('pp3', body_cr)
    step('PP3 cross3+pickSign 构建', True, None)

    # PP4: 旋转 + segmented + sRGB
    def body_rot(em, fg, tA, tB, tC):
        ang = em.mul(em.sw1(tB, 3), em.c_f1(math.pi / 180.0))
        ca, sa = em.cos(ang), em.sin(ang)
        # rot = A*cos + cross(Nz,A)*sin，A=(1,0,0)，cross(Nz,A)=(0,1,0)
        rot_x = ca
        rot_y = sa
        seg_x = em.sw1(tC, 2)
        seg = em.segmented(seg_x, em.sw1(tB, 0),
                           em.sw1(tB, 1), em.sw1(tB, 2), em.sw1(tC, 0))
        srgb = em.linear_to_srgb_f1(em.sw1(tC, 1))
        return em.v4_from_f3(em.v3(rot_x, rot_y, seg), srgb)
    pps['pp4_rot'] = make_pp('pp4', body_rot)
    step('PP4 rot+segmented+sRGB 构建', True, None)

    # PP5: pick3(mode) → (p3.xyz, 0)
    def body_p3(em, fg, tA, tB, tC):
        mode = em.sw1(tB, 0)
        p3 = em.pick3(em.v3(em.c_f1(0.1), em.c_f1(0.0), em.c_f1(0.0)),
                      em.v3(em.c_f1(0.0), em.c_f1(0.2), em.c_f1(0.0)),
                      em.v3(em.c_f1(0.0), em.c_f1(0.0), em.c_f1(0.3)), mode)
        return em.v4_from_f3(p3, em.c_f1(0.0))
    pps['pp5_p3'] = make_pp('pp5', body_p3)
    step('PP5 pick3 构建', True, None)

    # 读回
    readbacks = {}
    for tag, pp in pps.items():
        exr = os.path.join(VAL_DIR, f'probe_0d2_{tag}.exr')
        rb = compute_and_save(graph, pp, exr)
        readbacks[tag] = {'ok': rb['ok'], 'exr': exr, 'size': rb['size'],
                          'err': (rb['error'] or '')[:150]}
        step(f'读回 {tag}', rb['ok'], {'size': rb['size']})

    report['readbacks'] = readbacks
    report['param_meta'] = meta
    report['acceptance'] = {'max_abs': 1e-4, 'rmse': 1e-5}
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
