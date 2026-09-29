# -*- coding: utf-8 -*-
r"""16bit RGBA PNG 严格读取器（外部验证用）。

PIL/imageio 对 16bit RGBA PNG 会静默降为 8bit（高字节截断）；
本读取器手工解 IDAT（全部 5 种 filter），保真 u16。
"""
from __future__ import annotations

import struct
import zlib

import numpy as np


def read_png16(path):
    """返回 (np.uint16 [H,W,C], bitdepth, colortype)。"""
    raw = open(path, 'rb').read()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    i = 8
    idat = b''
    w = h = bd = ct = None
    while i < len(raw):
        ln = struct.unpack('>I', raw[i:i + 4])[0]
        tag = raw[i + 4:i + 8]
        data = raw[i + 8:i + 8 + ln]
        if tag == b'IHDR':
            w, h, bd, ct = struct.unpack('>IIBB', data[:10])
        elif tag == b'IDAT':
            idat += data
        i += 12 + ln
    assert bd in (8, 16), f'expect 8/16bit, got {bd}'
    nch = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    stride = w * nch * (bd // 8)
    dec = zlib.decompress(idat)
    out = np.zeros((h, w, nch), dtype=np.uint16)
    prev = np.zeros(stride, dtype=np.int64)
    pos = 0
    unit = nch * (bd // 8)           # 每整像素字节数 bpp（PNG spec §6：Sub/Avg/Paeth 按 bpp 回溯）
    # PNG 过滤器算术按字节 mod 256（spec §6），与位深无关；
    # 16 位图此处曾是 0xFFFF → 单字节和不回绕，重建流损坏（M3 real-asset bug）
    mask_v = 0xFF
    for y in range(h):
        ft = dec[pos]
        pos += 1
        row = np.frombuffer(dec[pos:pos + stride], dtype=np.uint8).astype(np.int64)
        pos += stride
        if ft == 0:
            pass
        elif ft == 1:      # Sub
            for c in range(unit, stride):
                row[c] = (row[c] + row[c - unit]) & mask_v
        elif ft == 2:      # Up
            row = (row + prev) & mask_v
        elif ft == 3:      # Average
            for c in range(stride):
                a = row[c - unit] if c >= unit else 0
                row[c] = (row[c] + ((a + prev[c]) >> 1)) & mask_v
        elif ft == 4:      # Paeth
            for c in range(stride):
                a = row[c - unit] if c >= unit else 0
                b = prev[c]
                cc = prev[c - unit] if c >= unit else 0
                p = a + b - cc
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - cc)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else cc)
                row[c] = (row[c] + pr) & mask_v
        else:
            raise ValueError(f'filter {ft}')
        if bd == 16:
            # u16 大端网络序 → (hi,lo) 对还原
            rowhi = row.reshape(w, nch, 2)
            vals = (rowhi[..., 0] << 8) | rowhi[..., 1]
            out[y] = vals.astype(np.uint16)
        else:
            out[y] = row.reshape(w, nch).astype(np.uint16)
        prev = row
    return out, bd, ct


def read_png16_f(path):
    """u16/u8 → float32 [0,1]（按位深归一）。"""
    a, bd, _ct = read_png16(path)
    return a.astype(np.float32) / (65535.0 if bd == 16 else 255.0)
