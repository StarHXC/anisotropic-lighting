# -*- coding: utf-8 -*-
"""0C 判定器自测：写一个"完美导出" EXR（fixture 原样）→ run_0c 应全 PASS。
同时写一个"half 降位" EXR（低位截断）→ 负值/HDR 专项应 FAIL。
运行：python "sd/validation/selftest_0c.py"
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

SD_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SD_DIR))

ns = {'__name__': 'chk', '__file__': str(SD_DIR / 'check_export.py')}
src = (SD_DIR / 'check_export.py').read_text(encoding='utf-8')
exec(compile(src, 'check_export.py', 'exec'), ns)

VAL = SD_DIR / 'validation'

# manifest 不存在时（SD 侧 probe_0c.py 未跑过）内联生成同源 fixture，
# 保证外部自测不依赖 SD。
man_path = VAL / 'probe_0c_manifest.json'
if not man_path.exists():
    sys.path.insert(0, str(SD_DIR))
    import importlib.util
    spec = importlib.util.spec_from_file_location('p0c', str(SD_DIR / 'probe_0c.py'))
    m = importlib.util.module_from_spec(spec)
    # 手动提取常量与 fixture 函数（probe_0c 顶层 main-guard 外会执行 main → 依赖 sd 包）
    p0c_src = (SD_DIR / 'probe_0c.py').read_text(encoding='utf-8')
    head = p0c_src.split('def main()')[0]
    ns0 = {'__name__': 'p0c_head', '__file__': str(SD_DIR / 'probe_0c.py')}
    exec(compile(head, 'probe_0c_head.py', 'exec'), ns0)
    png_rows, png_manifest = ns0['build_png16_fixture']()
    exr_rows, exr_manifest = ns0['build_exr_fixture']()
    VAL.mkdir(parents=True, exist_ok=True)
    ns0['write_png16'](str(VAL / 'fixture_lsb16.png'), 8, 8, png_rows)
    ns0['write_exr_f32'](str(VAL / 'fixture_neghdr.exr'), 8, 8, exr_rows)
    man = {
        'png16': {'file': 'fixture_lsb16.png', 'size': [8, 8],
                  'scale': 1.0 / 65535.0, 'bias': 0.0,
                  'values_u16': png_manifest['values']},
        'exr': {'file': 'fixture_neghdr.exr', 'size': [8, 8],
                'quadrants': exr_manifest['quadrants'],
                'values_rgba': [[list(v) for v in row] for row in exr_rows]},
    }
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2),
                        encoding='utf-8')
else:
    man = json.loads(man_path.read_text(encoding='utf-8'))


def write_exr(path, rows):
    """复用 probe_0c 的 EXR 写出（无压缩 RGBA float32）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'p0c', str(SD_DIR / 'probe_0c.py'))
    m = importlib.util.module_from_spec(spec)
    import types

    # 只执行头部常量与函数定义（probe_0c 顶层 try 在 __main__ guard 外会运行 main ——
    # 其 main 依赖 sd 包，不能整文件 import；改为本地复制写出逻辑）
    def _exr_chlist(channels):
        out = b''
        for name, ptype in channels:
            out += name.encode('ascii') + b'\x00' + struct.pack('<iBxxxii', ptype, 0, 1, 1)
        return out + b'\x00'

    def _exr_attr(name, typ, data):
        return name.encode('ascii') + b'\x00' + typ.encode('ascii') + b'\x00' + \
            struct.pack('<I', len(data)) + data

    w, h = len(rows[0]), len(rows)

    chlist = _exr_chlist([('B', 2), ('G', 2), ('R', 2), ('A', 2)])
    header = (
        _exr_attr('channels', 'chlist', chlist)
        + _exr_attr('compression', 'compression', struct.pack('<B', 0))
        + _exr_attr('dataWindow', 'box2i', struct.pack('<4i', 0, 0, w - 1, h - 1))
        + _exr_attr('displayWindow', 'box2i', struct.pack('<4i', 0, 0, w - 1, h - 1))
        + _exr_attr('lineOrder', 'lineOrder', struct.pack('<B', 0))
        + _exr_attr('pixelAspectRatio', 'float', struct.pack('<f', 1.0))
        + _exr_attr('screenWindowCenter', 'v2f', struct.pack('<2f', 0.0, 0.0))
        + _exr_attr('screenWindowWidth', 'float', struct.pack('<f', 1.0))
        + b'\x00'
    )
    body = b''
    for y, row in enumerate(rows):
        line = b''
        for (r, g, b, a) in row:
            line += struct.pack('<ffff', r, g, b, a)
        body += struct.pack('<ii', y, len(line)) + line
    # scanline offset table（EXR 规范：header 后每扫描线一个 uint64 偏移）
    h = len(rows)
    table_len = 8 * h
    offsets = []
    pos = table_len
    for blk_start in range(0, len(body), 1):
        pass
    # 逐块重算偏移（块长度 = 8 + 16*w 字节）
    blk_len = 8 + 16 * w
    offsets = [table_len + i * blk_len for i in range(h)]
    offset_table = b''.join(struct.pack('<Q', o) for o in offsets)
    with open(path, 'wb') as f:
        f.write(struct.pack('<I', 20000630) + struct.pack('<I', 2) + header
                + offset_table + body)


# ---- case 1: 完美导出（用 imageio freeimage + EXR_FLOAT 旗标写出标准文件）
import imageio.v2 as iio

ref = np.array(man['exr']['values_rgba'], dtype=np.float32)
p1 = VAL / 'selftest_perfect.exr'
iio.imwrite(str(p1), ref, format='EXR-FI', flags=1)  # EXR_FLOAT = 1
rc = ns['run_0c'](None, p1)
print(f'selftest perfect EXR → exit {rc}（期望 0）')

# ---- case 2: half 降位（float32→float16→float32 截断 HDR）
rows_half = ref.astype(np.float16).astype(np.float32)
p2 = VAL / 'selftest_half.exr'
iio.imwrite(str(p2), rows_half, format='EXR-FI', flags=1)
rc2 = ns['run_0c'](None, p2)
print(f'selftest half-truncated EXR → exit {rc2}（期望非 0：HDR=100 应被截断）')
