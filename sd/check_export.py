# -*- coding: utf-8 -*-
r"""外部验收比对器（Stage 0）—— 在项目根目录用本地 Python 运行。

职责（SD_MIGRATION_PLAN §8.2 判定顺序）：
  1. 有限性：NaN/Inf 必须为 0（比较域为空/尺寸不匹配 → 直接 FAIL）
  2. 有效性：0/1 标记必须精确一致（不做交集豁免）
  3. 数值：有效内域 max|Δ| ≤ 1e-4、RMSE ≤ 1e-5（0D）
     成品层阈值（≤2 LSB）属 Stage 4，本脚本预留参数。

用法：
    python "sd/check_export.py" --probe 0d --sd-exr <PP_A导出.exr> [--sd-exr-b <PP_B导出.exr>]
    python "sd/check_export.py" --probe 0b --sd-image <导出.png|tiff|exr>
    python "sd/check_export.py" --probe 0c --png16 <导出.png> --exr <导出.exr>

EXR 读取优先 imageio（freeimage plugin）；不可用时回退 OpenEXR；
都没有则报错并提示安装（不静默降级为"跳过"）。
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

PROJ_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = Path(__file__).resolve().parent / "validation"

TOL_MAX_ABS = 1e-4
TOL_RMSE = 1e-5


# ---------------------------------------------------------------- 图像读取

def load_image_any(path: Path) -> tuple[np.ndarray, str]:
    """读取 PNG16/TIFF/EXR 为 float32 HxWx4（RGBA），保留负值/HDR。

    返回 (img, fmt)；img 通道不足 4 则补齐（alpha=1）。
    """
    suffix = path.suffix.lower()
    if suffix == '.exr':
        arr = _load_exr(path)
        fmt = 'exr'
    else:
        arr = _load_png16_or_tiff(path)
        fmt = suffix.lstrip('.')
    if arr.ndim == 2:
        arr = arr[..., None]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones_like(arr[..., :1])], axis=2)
    return arr.astype(np.float32), fmt


def _load_exr(path: Path) -> np.ndarray:
    try:
        import imageio.v3 as iio
        try:
            return iio.imread(path, plugin='EXR-FI')  # freeimage：float32 原样
        except Exception:
            return iio.imread(path)  # 其他可用后端
    except ImportError:
        pass
    try:
        import OpenEXR  # type: ignore
        import Imath  # type: ignore
        f = OpenEXR.InputFile(str(path))
        dw = f.header()['dataWindow']
        w, h = dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1
        pt = Imath.PixelType(Imath.PixelType.FLOAT)
        chans = [np.frombuffer(f.channel(c, pt), dtype=np.float32).reshape(h, w)
                 for c in ('R', 'G', 'B', 'A')]
        return np.stack(chans, axis=2)
    except ImportError:
        raise SystemExit(
            '读取 EXR 需要 imageio（含 freeimage）或 OpenEXR 包：\n'
            '  pip install imageio imageio-freeimage\n'
            '不静默跳过 —— 验收必须读回真实导出数据。')


def _load_png16_or_tiff(path: Path) -> np.ndarray:
    try:
        import imageio.v3 as iio
        return iio.imread(path)  # uint16 原样（不缩放）
    except ImportError:
        raise SystemExit('读取 PNG16/TIFF 需要 imageio：pip install imageio')


# ---------------------------------------------------------------- 判定

def check_finiteness(img: np.ndarray, label: str) -> dict:
    bad = ~np.isfinite(img)
    n_bad = int(bad.sum())
    return {'label': label, 'non_finite': n_bad, 'ok': n_bad == 0,
            'positions': np.argwhere(bad)[:20].tolist() if n_bad else []}


def check_valid_exact(sd_valid: np.ndarray, ref_valid: np.ndarray) -> dict:
    """0/1 有效性必须精确一致（§8.2 第 2 条；禁止交集豁免）。"""
    mismatch = sd_valid != ref_valid
    n = int(mismatch.sum())
    return {'mismatches': n, 'ok': n == 0,
            'false_valid': int(((sd_valid == 1) & (ref_valid == 0)).sum()),
            'false_invalid': int(((sd_valid == 0) & (ref_valid == 1)).sum()),
            'positions': np.argwhere(mismatch)[:20].tolist() if n else []}


def check_numeric(sd: np.ndarray, ref: np.ndarray, domain: np.ndarray | None,
                  tol_abs: float = TOL_MAX_ABS, tol_rmse: float = TOL_RMSE) -> dict:
    """有效内域数值对比；比较域为空必须 FAIL（§8.2：不得零误差假通过）。"""
    if domain is None:
        domain = np.ones(sd.shape[:2], dtype=bool)
    n = int(domain.sum())
    if n == 0:
        return {'ok': False, 'error': '比较域为空 —— 按审核稿必须失败，不得视为通过',
                'n': 0}
    d = (sd - ref)[domain]
    max_abs = float(np.max(np.abs(d)))
    rmse = float(np.sqrt(np.mean(d * d)))
    n_over = int((np.abs(d) > tol_abs).sum())
    return {'ok': max_abs <= tol_abs and rmse <= tol_rmse,
            'n': n, 'max_abs': max_abs, 'rmse': rmse,
            'n_over_tol': n_over, 'tol_abs': tol_abs, 'tol_rmse': tol_rmse}


# ---------------------------------------------------------------- 0D

def run_0d(sd_exr: Path, sd_exr_b: Path | None) -> int:
    """0D：SD 导出的 case 图 → 逐 case 采样点提取 → 与 NumPy 基准对比。"""
    man = json.loads((VAL_DIR / 'probe_0d_manifest.json').read_text(encoding='utf-8'))
    ref_doc = json.loads((VAL_DIR / 'probe_0d_glsl_ref.json').read_text(encoding='utf-8'))
    layout = man['layout']
    cases_x, cases_y = layout['cases_x'], layout['cases_y']
    h, w = layout['size'][1], layout['size'][0]

    img_a, fmt_a = load_image_any(sd_exr)
    report = {'probe': '0D', 'fmt': fmt_a, 'size': list(img_a.shape[:2]),
              'checks': [], 'ok': False}

    fin = check_finiteness(img_a, 'PP-A 导出')
    report['checks'].append({'finite': fin})
    if not fin['ok']:
        print('[FAIL] 有限性:', fin['non_finite'], '个非有限值；样例位置:',
              fin['positions'][:5])
        _write_report(report, 'probe_0d_check.json')
        return 1

    # case 采样点：每个 case 中心（区域中心 → 网格整数坐标）
    # 图像行序按「首行为顶部」处理（SD 导出经 check_export 读取约定，0B 已锁定）
    cy_pix = int(0.5 * h / cases_y)
    cx_pix = int(0.5 * w / cases_x)
    sd_vals, ref_vals, valid_sd, valid_ref = [], [], [], []
    for i, ref_case in enumerate(ref_doc['cases']):
        gy = i // cases_x
        gx = i % cases_x
        py = gy * int(h / cases_y) + cy_pix
        px = gx * int(w / cases_x) + cx_pix
        sd_vals.append(img_a[py, px, :])
        ref_vals.append(np.array(
            ref_case['sn_xyz'] + [ref_case['sn_valid']], dtype=np.float32))
        valid_sd.append(img_a[py, px, 3])
        valid_ref.append(ref_case['sn_valid'])

    sd_v = np.stack(sd_vals)
    ref_v = np.stack(ref_vals)

    # 有效性：sn_valid 分量
    vchk = check_valid_exact(sd_v[:, 3] > 0.5, np.array(valid_ref) > 0.5)
    report['checks'].append({'valid': vchk})
    print(('[PASS] ' if vchk['ok'] else '[FAIL] ') +
          f"有效性（sn_valid）: mismatches={vchk['mismatches']} "
          f"(false_valid={vchk['false_valid']}, false_invalid={vchk['false_invalid']})")

    # 数值：全部 case 中心点（0D 无"内域"概念，全部比较）
    num = check_numeric(sd_v, ref_v, None)
    report['checks'].append({'numeric': num})
    print(('[PASS] ' if num['ok'] else '[FAIL] ') +
          f"数值（PP-A sn.xyz/valid @ {num['n']} case 点）: "
          f"max|Δ|={num['max_abs']:.3e} RMSE={num['rmse']:.3e} "
          f"超差={num['n_over_tol']}")

    # 逐 case 明细
    detail = []
    for i in range(len(sd_v)):
        d = float(np.max(np.abs(sd_v[i] - ref_v[i])))
        detail.append({'case': ref_doc['cases'][i]['name'], 'max_abs': d,
                       'ok': d <= TOL_MAX_ABS})
    report['case_detail'] = detail
    for d in detail:
        print(f"  {'PASS' if d['ok'] else 'FAIL'}  {d['case']:<12} max|Δ|={d['max_abs']:.3e}")

    if sd_exr_b is not None:
        img_b, fmt_b = load_image_any(sd_exr_b)
        fin_b = check_finiteness(img_b, 'PP-B 导出')
        report['checks'].append({'finite_B': fin_b})
        print(('[PASS] ' if fin_b['ok'] else '[FAIL] ') +
              f"PP-B 有限性: non_finite={fin_b['non_finite']}")
        # PP-B: R=pickSign G=rot.x B=segmented A=srgb —— 同样抽 case 点对比
        ps_sd = img_b[:, :, 0]
        rot_sd = img_b[:, :, 1]
        seg_sd = img_b[:, :, 2]
        srgb_sd = img_b[:, :, 3]
        ps_ref = np.zeros_like(ps_sd)
        rot_ref = np.zeros_like(rot_sd)
        seg_ref = np.zeros_like(seg_sd)
        srgb_ref = np.zeros_like(srgb_sd)
        srgb_table = [0.002, 0.0031308, 0.5, 1.0, 2.0, 0.0, 0.003, 0.9, 0.1, 0.8, 0.33, 0.77]
        for i, ref_case in enumerate(ref_doc['cases']):
            gy, gx = i // cases_x, i % cases_x
            py = gy * int(h / cases_y) + cy_pix
            px = gx * int(w / cases_x) + cx_pix
            ps_ref[py, px] = ref_case['pick_sign']
            rot_ref[py, px] = ref_case['rot_x']
            seg_ref[py, px] = ref_case['segmented_at_half']
            srgb_ref[py, px] = srgb_table[i]
        for label, sd_c, ref_c in (('pickSign', ps_sd, ps_ref),
                                   ('rot.x', rot_sd, rot_ref),
                                   ('segmented', seg_sd, seg_ref),
                                   ('linearToSRGB', srgb_sd, srgb_ref)):
            num_b = check_numeric(sd_c, ref_c, None)
            report['checks'].append({label: num_b})
            print(('[PASS] ' if num_b['ok'] else '[FAIL] ') +
                  f"{label}: max|Δ|={num_b['max_abs']:.3e} RMSE={num_b['rmse']:.3e} "
                  f"超差={num_b['n_over_tol']}")

    ok = all(c.get('ok', True) for chk in report['checks'] for c in ([chk] if 'ok' in chk else list(chk.values())))
    report['ok'] = bool(ok)
    _write_report(report, 'probe_0d_check.json')
    print(f"[DONE] 0D 判定: {'PASS' if ok else 'FAIL'} → {VAL_DIR / 'probe_0d_check.json'}")
    return 0 if ok else 1


# ---------------------------------------------------------------- 0B/0C

def run_0b(sd_image: Path) -> int:
    """0B：4×4 打包导出验证 idx 映射（期望 R=G=B=A=1，特征签名定位错位）。"""
    img, fmt = load_image_any(sd_image)
    report = {'probe': '0B', 'fmt': fmt, 'size': list(img.shape[:2]), 'ok': False}
    fin = check_finiteness(img, '0B 导出')
    report['finite'] = fin
    if not fin['ok']:
        print('[FAIL] 有限性:', fin)
        _write_report(report, 'probe_0b_check.json')
        return 1
    center = img[img.shape[0] // 2, img.shape[1] // 2, :]
    r, g, b, a = (float(x) for x in center[:4])
    report['center_rgba'] = [r, g, b, a]
    sig = {
        (1, 1, 1, 1): 'idx 映射正确（R=s0红 G=s1绿 B=s2蓝 A=s3黄r）',
        (0, 1, 1, 1): 'idx 错位特征 1',
        (1, 0, 1, 1): 'idx 错位特征 2',
        (0, 0, 0, 0): '全部槽位未接/采样失败',
    }
    key = tuple(int(round(v)) for v in (r, g, b, a))
    report['verdict'] = sig.get(key, f'非预期读回 {key} —— 需人工分析')
    ok = key == (1, 1, 1, 1)
    report['ok'] = ok
    print(f"[{'PASS' if ok else 'FAIL'}] 中心读回 RGBA={key}: {report['verdict']}")
    _write_report(report, 'probe_0b_check.json')
    return 0 if ok else 1


def run_0c(png16: Path | None, exr: Path | None) -> int:
    """0C：PNG16 低位往返 + EXR 负值/HDR/alpha 往返。"""
    man = json.loads((VAL_DIR / 'probe_0c_manifest.json').read_text(encoding='utf-8'))
    report = {'probe': '0C', 'ok': False, 'checks': []}

    if png16 is not None:
        img, fmt = load_image_any(png16)
        ref = np.array(man['png16']['values_u16'], dtype=np.float32) / 65535.0
        h, w = ref.shape[:2]
        sd = img[:h, :w, :3].reshape(ref.shape)
        qbudget = 1.0 / (2 * 65535)
        num = check_numeric(sd, ref, None, tol_abs=qbudget * 2, tol_rmse=qbudget)
        num['quantization_budget'] = qbudget
        num['note'] = 'PNG16 整数量化预算 |Δ|≤1/(2*65535)/通道，2 倍内视为纯量化'
        report['checks'].append({'png16': {'fmt': fmt, **num}})
        print(('[PASS] ' if num['ok'] else '[FAIL] ') +
              f"PNG16 往返: max|Δ|={num['max_abs']:.3e} (预算 {qbudget:.3e}) 超差={num['n_over_tol']}")

    if exr is not None:
        img, fmt = load_image_any(exr)
        ref_rows = np.array(man['exr']['values_rgba'], dtype=np.float32)
        h, w = ref_rows.shape[:2]
        sd = img[:h, :w, :]
        fin = check_finiteness(sd, 'EXR 往返')
        report['checks'].append({'exr_finite': fin})
        print(('[PASS] ' if fin['ok'] else '[FAIL] ') +
              f"EXR 有限性: non_finite={fin['non_finite']}")
        num = check_numeric(sd, ref_rows, None, tol_abs=1e-6, tol_rmse=1e-7)
        num['note'] = 'float32 往返应接近位级；A=0 但 RGB≠0 象限验证非预乘'
        report['checks'].append({'exr': num})
        print(('[PASS] ' if num['ok'] else '[FAIL] ') +
              f"EXR 往返: max|Δ|={num['max_abs']:.3e} RMSE={num['rmse']:.3e} 超差={num['n_over_tol']}")
        # 负值/HDR 保留专项
        neg_kept = float(sd[4, 0, 0]) < 0
        hdr_kept = float(sd[4, 7, 2]) > 50.0
        alpha0_rgb = float(sd[0, 0, 0]) > 0.5 and float(sd[0, 0, 3]) == 0.0
        report['checks'].append({'exr_special': {
            'negative_kept': neg_kept, 'hdr_kept': hdr_kept,
            'alpha0_rgb_nonzero_straight': alpha0_rgb}})
        print(('[PASS] ' if (neg_kept and hdr_kept and alpha0_rgb) else '[FAIL] ') +
              f"负值保留={neg_kept} HDR保留={hdr_kept} 非预乘A0RGB≠0={alpha0_rgb}")

    ok = True
    for chk in report['checks']:
        for v in chk.values():
            if isinstance(v, dict) and v.get('ok') is False:
                ok = False
            if isinstance(v, dict):
                for vv in v.values():
                    if vv is False:
                        ok = False
    report['ok'] = ok
    _write_report(report, 'probe_0c_check.json')
    print(f"[DONE] 0C 判定: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def _write_report(report: dict, name: str) -> None:
    VAL_DIR.mkdir(parents=True, exist_ok=True)
    (VAL_DIR / name).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description='Stage 0 外部验收比对器')
    ap.add_argument('--probe', required=True, choices=['0b', '0c', '0d'])
    ap.add_argument('--sd-exr', type=Path, default=None, help='0D: PP-A 导出 EXR')
    ap.add_argument('--sd-exr-b', type=Path, default=None, help='0D: PP-B 导出 EXR')
    ap.add_argument('--sd-image', type=Path, default=None, help='0B: 4×4 打包导出')
    ap.add_argument('--png16', type=Path, default=None, help='0C: PNG16 导出')
    ap.add_argument('--exr', type=Path, default=None, help='0C: EXR 导出')
    args = ap.parse_args()

    if args.probe == '0d':
        if args.sd_exr is None:
            ap.error('--probe 0d 需要 --sd-exr')
        return run_0d(args.sd_exr, args.sd_exr_b)
    if args.probe == '0b':
        if args.sd_image is None:
            ap.error('--probe 0b 需要 --sd-image')
        return run_0b(args.sd_image)
    if args.probe == '0c':
        if args.png16 is None and args.exr is None:
            ap.error('--probe 0c 需要 --png16 和/或 --exr')
        return run_0c(args.png16, args.exr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
