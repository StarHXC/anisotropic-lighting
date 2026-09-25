# -*- coding: utf-8 -*-
r"""GLSL 侧基准 dump（外部 Python 运行，非 SD 内执行）。

为 Stage 0 验收生成 GLSL 基准 .npy：
  --probe 0d   按 probe_0d_manifest.json 的同一张 case 表驱动，
               在 2048² 全屏 pass 中用 aniso.frag 同款配方计算每个 case
               的基准值，输出与 SD 侧 PP-A/PP-B 同含义的 float4 序列。

用法（在项目根目录）:
    python "sd/dump_glsl_ref.py" --probe 0d

关键点（SD_MIGRATION_PLAN §8.1）：
- 复用 gl/context.py 的 RenderContext/load_program defines 注入（:65-83），
  不修改任何现有文件。
- 每个 pass 读回后立即存盘，不复用可复写 FBO 当多份历史结果。
- 输出登记实际 RGBA 含义、尺寸、行序（首行为顶部）与模式。

0D 基准实现方式：dump 脚本【不】直接跑 aniso.frag（它需要贴图输入），
而是把 probe_0d_manifest 的 case 表逐条用 NumPy float64 计算参考值
（公式与 shaders/common.glsl §6 配方逐式对应），再与 SD 导出的 EXR
在 case 采样点对比。NumPy 参考实现同时被 check_export.py 用于
独立复核（两侧：GLSL-free 数学真值 + SD 实测）。

注意：本脚本的 NumPy 参考实现是【实数公式】级基准（PLAN §6.2 语义），
不声称与 GPU float32 位级相同；1e-4 内域容忍度覆盖该差异。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

PROJ_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = Path(__file__).resolve().parent / "validation"


# ================================================================ 0D 基准

def ref_safe_normalize(v, fallback, min_len=1e-12):
    """common.glsl safeNormalize 语义（float64 实数公式）。"""
    v = np.asarray(v, dtype=np.float64)
    fb = np.asarray(fallback, dtype=np.float64)
    len2 = float(np.dot(v, v))
    eps2 = min_len * min_len
    valid = 1.0 if len2 >= eps2 else 0.0
    if valid:
        inv = 1.0 / math.sqrt(max(len2, eps2))
        return np.array([v[i] * inv for i in range(3)] + [valid])
    return np.array([fb[0], fb[1], fb[2], valid])


def ref_plane_fallback(n):
    """§6 planeFallback（含 1e-6 偏置）。返回 (xyz, trigger)。

    use_y 语义以 GLSL 源 aniso.frag:156 为准：
        step(dot(n,n)*0.5, n.x*n.x) = (nx² >= len2*0.5)
    （此前本基准把比较方向写反，0D3 判定的 12 项 pf FAIL 皆源于此。）
    """
    n = np.asarray(n, dtype=np.float64)
    len2 = float(np.dot(n, n))
    use_y = 1.0 if (n[0] * n[0]) >= (len2 * 0.5) else 0.0
    ref = np.array([1.0 - use_y, use_y, 0.0])
    c = np.cross(n, ref) + np.array([0.0, 0.0, 1e-6])
    cn = ref_safe_normalize(c, np.array([0.0, 0.0, 1.0]), 1e-12)
    return cn[:3], cn[3]


def ref_cross3(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return np.cross(a, b)


def ref_pick_sign(x):
    x = float(x)
    sgn = 1.0 if x >= 0.0 else -1.0
    return sgn if abs(x) >= 1e-6 else 1.0


def ref_step(edge, x):
    return 1.0 if x >= edge else 0.0


def ref_pick3(m0, m1, m2, mode):
    s05 = ref_step(0.5, mode)
    s15 = ref_step(1.5, mode)
    is1 = s05 * (1.0 - s15)
    is2 = s15
    return m0 * (1.0 - s05) + m1 * is1 + m2 * is2


def ref_segmented(x, mode, e0, e1, thr):
    den = max(e1 - e0, 1e-5)
    t = min(max((x - e0) / den, 0.0), 1.0)
    smooth = t * t * (3.0 - 2.0 * t)
    hard = ref_step(thr, x)
    cont = min(max(x, 0.0), 1.0)
    return ref_pick3(cont, smooth, hard, mode)


def ref_linear_to_srgb(c):
    c = max(float(c), 0.0)
    lo = c * 12.92
    hi = 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return hi if c >= 0.0031308 else lo


def compute_case_outputs(case):
    """单 case 的全部配方输出（对应 SD 侧 PP-A/PP-B 打包分量）。"""
    v = np.asarray(case['v'], dtype=np.float64)
    fb = np.asarray(case['fallback'], dtype=np.float64)

    sn = ref_safe_normalize(v, fb, 1e-12)          # PP-A: rgb+valid
    pf, pf_trigger = ref_plane_fallback(v)
    cr = ref_cross3(v, fb)
    ps = ref_pick_sign(v[2])
    p3 = ref_pick3(np.array([0.1, 0.0, 0.0]),
                   np.array([0.0, 0.2, 0.0]),
                   np.array([0.0, 0.0, 0.3]),
                   float(case['mode']))
    seg = ref_segmented(0.5, case['mode'], case['e0'], case['e1'], case['thr'])

    ang = math.radians(case['angle'])
    A = np.array([1.0, 0.0, 0.0])
    cN = ref_cross3(np.array([0.0, 0.0, 1.0]), A)
    rot = A * math.cos(ang) + cN * math.sin(ang)

    srgb_in = 0.002
    # case 表的 srgb_in 序列（与 probe_0d.py select_scalar_b 列表一致）
    srgb_table = [0.002, 0.0031308, 0.5, 1.0, 2.0, 0.0, 0.003, 0.9, 0.1, 0.8, 0.33, 0.77]
    srgb_in = srgb_table[0]  # 占位：实际按 case 序号在批量函数里取

    return {
        'sn_xyz': sn[:3].tolist(), 'sn_valid': sn[3],
        'plane_fallback': pf.tolist(), 'pf_trigger': pf_trigger,
        'cross3': cr.tolist(),
        'pick_sign': ps,
        'pick3_center': p3.tolist(),
        'segmented_at_half': seg,
        'rot_x': float(rot[0]),
        'srgb': ref_linear_to_srgb(srgb_in),
    }


def dump_0d():
    man_path = VAL_DIR / "probe_0d_manifest.json"
    if not man_path.exists():
        raise FileNotFoundError(f"缺少 case 表: {man_path}（先在 SD 执行 probe_0d.py）")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    cases = man["cases"]

    ref_rows = []
    for i, case in enumerate(cases):
        out = compute_case_outputs(case)
        srgb_table = [0.002, 0.0031308, 0.5, 1.0, 2.0, 0.0, 0.003, 0.9, 0.1, 0.8, 0.33, 0.77]
        out['srgb'] = ref_linear_to_srgb(srgb_table[i])
        ref_rows.append({'case_index': i, 'name': case['name'], **out})

    out_path = VAL_DIR / "probe_0d_glsl_ref.json"
    payload = {
        'source': 'numpy float64 实数公式基准（§6 配方逐式对应）',
        'line_order': '不适用（case 表非图像）',
        'note': ('本基准供 check_export.py 在 SD 导出的 EXR case 采样点上对比；'
                 'SD 侧图内 case 布局见 probe_0d_manifest.json'),
        'cases': ref_rows,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[OK] 0D 基准 → {out_path}")
    print(f"     cases={len(ref_rows)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="GLSL/NumPy 基准 dump（Stage 0）")
    ap.add_argument('--probe', required=True, choices=['0d'],
                    help='探针名（当前支持 0d）')
    args = ap.parse_args()

    VAL_DIR.mkdir(parents=True, exist_ok=True)
    if args.probe == '0d':
        return dump_0d()
    raise NotImplementedError(args.probe)


if __name__ == "__main__":
    sys.exit(main())
