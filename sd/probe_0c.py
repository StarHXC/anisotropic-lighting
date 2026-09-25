# -*- coding: utf-8 -*-
r"""Stage 0 / 0C 探针 — 数据精度 / Raw / 导出读回。

前置：0A 通过。0B 的 idx 映射结论已知（脚本内引用其报告）。
在 SD Python 编辑器执行：
    exec(open(r'E:\AI_Project\Anisotropic Lighting\sd\probe_0c.py', encoding='utf-8').read())

验证内容（SD_MIGRATION_PLAN §7.2 / 0C、§8.1）：
  1. RGB16 低位 fixture 生成（相邻 uint16 差 1、三通道不同模式）
     → 用户 import SD（**Raw，无色彩管理**）→ Bitmap → PP 直通 → 导出
  2. EXR float32 负值/HDR/alpha 测试块（A=0 但 RGB≠0、HDR>1、负值）
     → 同链路 → 导出 EXR（float32，非 half）
  3. 外部 check_export.py 逐跳比对（导入→PP→导出每一跳位深保真）

脚本职责：生成两张 fixture PNG16/EXR 文件 + 打印用户操作序列 +
登记期望值 manifest。PP 构建与 0B 相同模式（直通输出 input0）。

输出：sd/validation/probe_0c_report.json、fixture 文件、期望 manifest。
"""
from __future__ import annotations

import json
import os
import struct
import sys
import zlib
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
VAL_DIR = os.path.join(SD_DIR, 'validation')

# SD 会话内重复执行时强制重读磁盘模块（否则拿到首次运行的旧缓存）
for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

REPORT_PATH = os.path.join(VAL_DIR, 'probe_0c_report.json')

report = {'probe': '0C', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0C 探针失败于: {name}  ({detail})')


# ---------------------------------------------------------------- PNG16 写出

def write_png16(path: str, w: int, h: int, rgb16_rows):
    """最小 16-bit RGB PNG（无辅助块）。rgb16_rows[y][x] = (r,g,b) uint16。"""
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack('>IIBBBBB', w, h, 16, 2, 0, 0, 0)  # bitdepth16, RGB
    raw = b''
    for row in rgb16_rows:
        scan = b'\x00'  # filter none
        for (r, g, b) in row:
            scan += struct.pack('>HHH', r, g, b)
        raw += scan
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', ihdr)
           + chunk(b'IDAT', zlib.compress(raw))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


# ---------------------------------------------------------------- EXR 写出

def _exr_chlist(channels):
    """channel name\0 pixeltype(4) pLinear(1) reserved(3) xSampling(4) ySampling(4)"""
    out = b''
    for name, ptype in channels:
        out += name.encode('ascii') + b'\x00' + struct.pack('<iBxxxii', ptype, 0, 1, 1)
    return out + b'\x00'


def _exr_attr(name: str, typ: str, data: bytes) -> bytes:
    return name.encode('ascii') + b'\x00' + typ.encode('ascii') + b'\x00' + \
        struct.pack('<I', len(data)) + data


def write_exr_f32(path: str, w: int, h: int, rgba_rows):
    """最小 scanline EXR（NO_COMPRESSION），RGBA 全 FLOAT。
    rgba_rows[y][x] = (r,g,b,a) float。
    结构：magic + version + header + [offset table (uint64/scanline)] + 块序列。
    每块：y(int32) + dataSize(int32) + data(RGBA float)。"""
    # half 无；pixel type 2 = FLOAT
    chlist = _exr_chlist([('B', 2), ('G', 2), ('R', 2), ('A', 2)])
    header = (
        _exr_attr('channels', 'chlist', chlist)
        + _exr_attr('compression', 'compression', struct.pack('<B', 0))  # NO_COMPRESSION
        + _exr_attr('dataWindow', 'box2i', struct.pack('<4i', 0, 0, w - 1, h - 1))
        + _exr_attr('displayWindow', 'box2i', struct.pack('<4i', 0, 0, w - 1, h - 1))
        + _exr_attr('lineOrder', 'lineOrder', struct.pack('<B', 0))      # INCREASING_Y
        + _exr_attr('pixelAspectRatio', 'float', struct.pack('<f', 1.0))
        + _exr_attr('screenWindowCenter', 'v2f', struct.pack('<2f', 0.0, 0.0))
        + _exr_attr('screenWindowWidth', 'float', struct.pack('<f', 1.0))
        + b'\x00'
    )
    # 每扫描线: y(int) dataSize(int) data(RGBA float)
    blocks = []
    for y, row in enumerate(rgba_rows):
        line = b''
        for (r, g, b, a) in row:
            line += struct.pack('<ffff', r, g, b, a)
        blocks.append(struct.pack('<ii', y, len(line)) + line)
    # offset table：每块在文件中的绝对偏移（header 之后开始计）
    table_len = 8 * h
    offsets = []
    pos = table_len
    for blk in blocks:
        offsets.append(pos)
        pos += len(blk)
    offset_table = b''.join(struct.pack('<Q', o) for o in offsets)
    magic = struct.pack('<I', 20000630) + struct.pack('<I', 2)  # magic + version
    with open(path, 'wb') as f:
        f.write(magic + header + offset_table + b''.join(blocks))


# ---------------------------------------------------------------- fixtures

SIZE = 8


def build_png16_fixture():
    """相邻 uint16 差 1 的三通道不同模式，值域 [0,1]。"""
    rows = []
    manifest = {'values': []}
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            base = (y * SIZE + x) * 3
            # 三通道各自 +1 步进、不同起点：R 从 10000、G 从 30000、B 从 60000
            r = 10000 + (base % 7)
            g = 30000 + (base % 5)
            b = 60000 + (base % 3)
            row.append((r, g, b))
            manifest['values'].append([r, g, b])
        rows.append(row)
    return rows, manifest


def build_exr_fixture():
    """四象限：负值 / HDR>1 / A=0但RGB≠0 / 常规 [0,1]。"""
    rows = []
    manifest = {'quadrants': {
        'bottom_left':  'negative (r=-0.5, g=-0.25, b=-1.0, a=1)',
        'bottom_right': 'hdr (r=2.5, g=10.0, b=100.0, a=1)',
        'top_left':     'alpha0_rgb_nonzero (r=0.7, g=0.3, b=0.9, a=0)',
        'top_right':    'normal (r=0.25, g=0.5, b=0.75, a=1)',
    }}
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            top = y < SIZE // 2
            left = x < SIZE // 2
            if top and left:
                v = (0.7, 0.3, 0.9, 0.0)
            elif top:
                v = (0.25, 0.5, 0.75, 1.0)
            elif left:
                v = (-0.5, -0.25, -1.0, 1.0)
            else:
                v = (2.5, 10.0, 100.0, 1.0)
            row.append(v)
        rows.append(row)
    return rows, manifest


def main():
    step('fixture 尺寸', SIZE == 8, {'size': [SIZE, SIZE]})

    os.makedirs(VAL_DIR, exist_ok=True)

    # 生成 fixture 文件
    png_rows, png_manifest = build_png16_fixture()
    png_path = os.path.join(VAL_DIR, 'fixture_lsb16.png')
    write_png16(png_path, SIZE, SIZE, png_rows)
    step('PNG16 低位 fixture 生成', os.path.getsize(png_path) > 0,
         {'path': png_path, 'pattern': 'R=10000+n G=30000+n B=60000+n（模小步进）'})

    exr_rows, exr_manifest = build_exr_fixture()
    exr_path = os.path.join(VAL_DIR, 'fixture_neghdr.exr')
    write_exr_f32(exr_path, SIZE, SIZE, exr_rows)
    step('EXR float32 负值/HDR/alpha fixture 生成', os.path.getsize(exr_path) > 0,
         {'path': exr_path, 'quadrants': exr_manifest['quadrants']})

    # 期望 manifest（check_export.py 的比较基准）
    expect = {
        'png16': {
            'file': os.path.basename(png_path),
            'size': [SIZE, SIZE],
            'scale': 1.0 / 65535.0, 'bias': 0.0,
            'note': ('导入必须 Raw：值映射 u16/65535，禁 sRGB 解码。'
                     'PNG16 是 16-bit 整数格式（§8.1），仅因本 fixture 已知 [0,1] 才可用；'
                     '量化预算 |Δ|≤ s/(2*65535) + 链路量化'),
            'values_u16': png_manifest['values'],
        },
        'exr': {
            'file': os.path.basename(exr_path),
            'size': [SIZE, SIZE],
            'note': ('RGBA 全 FLOAT；负值与 HDR 必须原样往返；A=0 但 RGB≠0 的象限'
                     '验证非预乘通路。若导出 EXR 是 half，低位全失 → 阻断'),
            'quadrants': exr_manifest['quadrants'],
            'values_rgba': [[list(v) for v in row] for row in exr_rows],
        },
    }
    man_path = os.path.join(VAL_DIR, 'probe_0c_manifest.json')
    with open(man_path, 'w', encoding='utf-8') as f:
        json.dump(expect, f, ensure_ascii=False, indent=2)
    step('期望值 manifest 写出', True, {'path': man_path})

    # SD 侧构建 PP 直通图
    from aniso_pp import api as SDAPI
    from sd.api.sdbasetypes import float2

    step('SD 环境登记', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('当前 graph', 'CompGraph' in type(graph).__name__,
         {'class': type(graph).__name__, 'id': SDAPI.get_graph_title(graph)})

    with SDAPI.undo_group('aniso_pp 0C: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=3)  # 8×8
        pp.setPosition(float2(0.0, 0.0))
        SDAPI.connect_pp_input_placeholder_note = (
            'input0 由用户把 fixture 资源接上（Bitmap/资源节点）——'
            '0C 验证的就是导入资源这条跳板，不自动绕过')
    step('PP 8×8 直通图创建', True, ev)

    fg, created = SDAPI.get_perpixel_graph(pp)
    pos = SDAPI.get_pos_node(fg)
    smp = SDAPI.samplecol_node(fg, pos, 0)
    SDAPI.fg_set_output(fg, smp)
    step('直通函数图（samplecol input0 原样输出 float4）', True,
         {'created': created})

    report['manual_checks'] = [
        f'① 把 {png_path} import 进当前 .sbs（导入设置：Raw / sRGB 关闭 / 16-bit 保留），'
        '将资源节点接进 PP 的 input0。',
        '② 导出 PP 输出为 16-bit PNG（或 TIFF16）到 sd/validation/probe_0c_out_png16.png，'
        '导出设置关色彩变换。',
        f'③ 把 {exr_path} 同样 import（Raw/float32 保留）替换接进 input0，'
        '导出为 EXR（float32，非 half）到 sd/validation/probe_0c_out.exr。'
        '导出对话框如出现 alpha/预乘选项：选非预乘（Straight）。',
        '④ 通知执行者跑 check_export.py --probe 0c 完成逐跳比对。',
    ]
    for m in report['manual_checks']:
        print('[手动] ' + m)

    report['ok'] = True


# ---------------------------------------------------------------- 运行
try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT] ' + repr(e))
    print(traceback.format_exc())

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'[DONE] 报告已写入 {REPORT_PATH}')
