# -*- coding: utf-8 -*-
r"""validation_mask fixtures — 几何/参数 fixture 生成（SD 内运行）。

生成分析 fixture 图（幂次方形 2^n，manifest 同步驱动 texel 与输出）：
  - 普通平面（N=+Z，平面位置）
  - 斜向法线区（倾斜曲面：位置 y=x·slope）
  - 旋转/镜像 UV 区（通过切向导数符号翻转模拟镜像手性）
  - 孔洞（coverage=0 象限）
  - 末行列（coverage 收缩 1 texel，测 neighborValid 越界）
  - 退化邻域（法线零向量区 → fallback 路径）

输出（写到 validation_mask/fixtures/）：
  fx_position.png / fx_normalobj.png / fx_mask.png / fx_ao.png (16bit PNG RGBA)
  fx_manifest.json（尺寸/区域表/参数 fixtures）

16bit PNG 写入用 PIL（SD 宿主无 imageio；探针宿主 = SD Python 3.13）。
"""
from __future__ import annotations

import json
import math
import os
import struct
import zlib

FIX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def _write_png16(path, w, h, rgba_rows_u16):
    """手写 16bit RGBA PNG（SD 宿主无 PIL/imageio；无外部依赖）。"""
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b''
    for row in rgba_rows_u16:
        raw += b'\x00' + b''.join(struct.pack('>HHHH', *px) for px in row)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 6))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


def _u16(x):
    """float [0,1] → u16（舍入）。"""
    x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
    return int(round(x * 65535.0)) & 0xFFFF


def build_fixtures(size=256):
    """生成全部 fixture 图与 manifest。"""
    os.makedirs(FIX_DIR, exist_ok=True)
    w = h = size
    texel = 1.0 / size

    pos = [[(0.0, 0.0, 0.0, 1.0)] * w for _ in range(h)]
    nrm = [[(0.5, 0.5, 1.0, 1.0)] * w for _ in range(h)]   # 解码前 0.5→+Z
    mask = [[(0.0, 0.0, 0.0, 1.0)] * w for _ in range(h)]
    ao = [[(1.0, 0.0, 0.0, 1.0)] * w for _ in range(h)]    # AO=1（有 AO 数据≠旧 KK 依赖）

    # 象限划分（左上/右上/左下/右下，图像行序=首行顶部）
    hx, hy = w // 2, h // 2
    regions = {
        'plane': (0, 0, hx, hy),            # 左上：平面 N=+Z
        'slope': (hx, 0, w, hy),            # 右上：斜面 z = 0.6·(x-cx)·texel
        'mirror': (0, hy, hx, h),           # 左下：镜像 UV（u 翻转的斜面）
        'hole': (hx, hy, w, h),             # 右下：coverage=0 孔洞
    }
    # slope 区：法线 = normalize(-dz/dx, 0, 1)，dz/dx=0.6
    sl = 0.6
    nl = math.sqrt(1.0 + sl * sl)
    slope_n = (0.5 - 0.5 * (sl / nl), 0.5, 0.5 + 0.5 * (1.0 / nl))
    # mirror 区：u 镜像 → dPdu 反向 → 法线 x 分量翻转（同一斜面镜像）
    mirror_n = (0.5 + 0.5 * (sl / nl), 0.5, 0.5 + 0.5 * (1.0 / nl))
    # 退化邻域：slope 区内 4×4 法线全零（触发 fallback）
    deg0 = (hx + 8, 8)
    deg1 = (hx + 12, 12)
    # 主瓣探针区：plane 区内 32×32 球面冠（法线随位置倾斜，扫过 H 方向 →
    # 中心附近产生 lobe≈1 的可见主瓣；探针区中心法线朝向 light 水平投影）
    # 冠半径: 法线从 +Z 倾斜到 ~55°（覆盖 H 与 N 夹角 23°）
    probe_c = (hx // 2, hy // 2)      # (x=64, y=64) 探针中心
    probe_r = 24                       # 半径 texel 数
    # 倾斜方向 = 光水平方位（az=-56.3° → 表面法线朝 (cos az, sin az, ·) 倾斜）
    tilt_az = math.radians(-56.309932474020215)

    last_row_valid = []  # 末行列 texel 坐标（mask 收缩验证）

    for y in range(h):
        for x in range(w):
            q_u = (x + 0.5) * texel
            q_v = (y + 0.5) * texel
            # 平面位置：z=0，xy 铺满 [0,1]（位置编码 RGB=xyz）
            px, py, pz = q_u, q_v, 0.0
            nx, ny, nz = 0.5, 0.5, 1.0
            cov = 1.0
            if x >= hx and y < hy:          # slope
                px = q_u
                pz = 0.6 * (q_u - (hx + 0.5) * texel)
                nx, ny, nz = slope_n
            elif x < hx and y >= hy:        # mirror
                pz = 0.6 * ((hx - 0.5) * texel - q_u)
                nx, ny, nz = mirror_n
            elif x >= hx and y >= hy:       # hole
                cov = 0.0
                nz = 1.0
            # 末行列（x=0 列与 y=0 行）在 mask 上保留，验证 neighborValid 越界
            if x == 0 or y == 0:
                last_row_valid.append((x, y))
            # 主瓣探针球冠：法线 = normalize(tilt·sinφ·dir, cosφ)，位置编码同步
            dx0 = x - probe_c[0]
            dy0 = y - probe_c[1]
            rr0 = math.hypot(dx0, dy0)
            if rr0 <= probe_r and y < hy and x < hx:
                phi = (rr0 / probe_r) * math.radians(55.0)
                tdir = (math.cos(tilt_az), math.sin(tilt_az))
                snx = math.sin(phi) * tdir[0]
                sny = math.sin(phi) * tdir[1]
                snz = math.cos(phi)
                nl0 = math.sqrt(snx * snx + sny * sny + snz * snz)
                nx, ny, nz = (0.5 + 0.5 * snx / nl0, 0.5 + 0.5 * sny / nl0,
                              0.5 + 0.5 * snz / nl0)
                # 球冠高度：z = rc - sqrt(rc²-r²) 近似平面小冠 → 位置 z 抬升
                rc = probe_r * texel / (1 - math.cos(math.radians(55.0)))
                rz2 = rc * rc - (rr0 * texel) ** 2
                pz = rc - math.sqrt(max(rz2, 0.0))
            # 退化邻域：法线零向量（解码后 (0,0,0)）
            if deg0[0] <= x < deg1[0] and deg0[1] <= y < deg1[1] and y < hy:
                nx, ny, nz = 0.5, 0.5, 0.5
                px, py, pz = q_u, q_v, 0.0
            pos[y][x] = (_u16(px), _u16(py), _u16(pz), _u16(1.0))
            nrm[y][x] = (_u16(nx), _u16(ny), _u16(nz), _u16(1.0))
            mask[y][x] = (_u16(cov), 0, 0, _u16(1.0))
            # AO：slope 区 0.5，其余 1.0（隔离验证：改 AO 不影响 Mask）
            aov = 0.5 if (x >= hx and y < hy) else 1.0
            ao[y][x] = (_u16(aov), 0, 0, _u16(1.0))

    files = {}
    for name, data in (('fx_position', pos), ('fx_normalobj', nrm),
                       ('fx_mask', mask), ('fx_ao', ao)):
        p = os.path.join(FIX_DIR, name + '.png')
        _write_png16(p, w, h, data)
        files[name] = p

    manifest = {
        'size': [w, h], 'texel': texel,
        'regions': {k: list(v) for k, v in regions.items()},
        'degenerate': {'from': list(deg0), 'to': list(deg1)},
        'slope_dzdx': sl,
        'probe': {'center': list(probe_c), 'radius': probe_r,
                  'tilt_az_deg': math.degrees(tilt_az),
                  'max_tilt_deg': 55.0},
        'last_row_valid_count': len(last_row_valid),
        'files': {k: os.path.basename(v) for k, v in files.items()},
    }
    with open(os.path.join(FIX_DIR, 'fx_manifest.json'), 'w',
              encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


if __name__ == '__main__':
    m = build_fixtures()
    print('[DONE]', json.dumps(m['size']), 'fixtures at', FIX_DIR)
