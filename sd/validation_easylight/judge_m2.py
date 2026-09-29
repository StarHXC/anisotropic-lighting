# -*- coding: utf-8 -*-
r"""M2/M3 外部判定 — aniso_easylight（对照 EXR 数值分析）。

M2 哨兵判定（validation_easylight/out/m2/）：
  1. 光照方位 +90° / exponent1=8 / 遮蔽哨兵：输出均显著变化（参数实际生效）
  2. 默认输出：有限、域记录、非零占比
M3 parity 判定（out/m3/）：
  3. 旧节点等价性命题：easylight 默认输出 ≡ 旧 lightmap 在等价参数设置下
     经 sRGB⁻¹ + Reinhard⁻¹ 逆映射后的线性亮度（有效内域对照）
  4. 双实例隔离 EXR 位级（EXR 文件头含时间戳 → 用像素对比）
输出：judge_m2.json / judge_m3.json；退出码 0=PASS
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SD / 'validation_mask'))
import png16  # noqa: E402

M2 = SD / 'validation_easylight' / 'out' / 'm2'
M3 = SD / 'validation_easylight' / 'out' / 'm3'
RES = SD / 'aniso_easylight.resources'


def load_exr(p):
    import imageio.v3 as iio
    try:
        a = iio.imread(str(p), plugin='EXR-FI')
    except Exception:
        a = iio.imread(str(p))
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 2:
        a = a[..., None]
    return a


def check(report, name, ok, detail=None):
    c = {'name': name, 'ok': bool(ok)}
    if detail is not None:
        c['detail'] = detail
    report['checks'].append(c)
    print(('[PASS] ' if ok else '[FAIL] ') + name +
          (f'  {detail}' if detail is not None else ''))
    return bool(ok)


def finish(report, path) -> int:
    ok = all(c['ok'] for c in report['checks'])
    report['ok'] = bool(ok)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    print(f"[DONE] {'PASS' if ok else 'FAIL'} → {path.name}")
    return 0 if ok else 1


def judge_m2() -> int:
    report = {'probe': 'judge_easylight_m2', 'checks': [], 'ok': False}
    m_def = load_exr(M2 / 'm2_default.exr')[:, :, 0]
    m_az = load_exr(M2 / 'm2_sentinel_az.exr')[:, :, 0]
    m_exp = load_exr(M2 / 'm2_sentinel_exp.exr')[:, :, 0]
    m_msk = load_exr(M2 / 'm2_sentinel_mask.exr')[:, :, 0]

    fin = int((~np.isfinite(m_def)).sum())
    check(report, '默认输出有限', fin == 0, {'non_finite': fin})
    check(report, '输出域记录（非负）', float(m_def.min()) >= -1e-6,
          {'min': float(m_def.min()), 'max': float(m_def.max()),
           'nonzero%%': float((np.abs(m_def) > 1e-6).mean())})
    check(report, '非空输出', float((np.abs(m_def) > 1e-6).mean()) > 0.01,
          {'nonzero': float((np.abs(m_def) > 1e-6).mean())})

    d1 = float(np.abs(m_az - m_def).max())
    d2 = float(np.abs(m_exp - m_def).max())
    d3 = float(np.abs(m_msk - m_def).max())
    check(report, '光照方位哨兵（输出变化）', d1 > 1e-3, {'max_diff': d1})
    check(report, 'exponent1 哨兵（输出变化）', d2 > 1e-3, {'max_diff': d2})
    check(report, '遮蔽哨兵（输出变化）', d3 > 1e-3, {'max_diff': d3})

    # 双实例隔离像素级（EXR 头部时间戳使 size 相等不充分）
    m_b = load_exr(M2 / 'm2_instB.exr')[:, :, 0]
    m_b2 = load_exr(M2 / 'm2_instB_after.exr')[:, :, 0]
    db = float(np.abs(m_b - m_b2).max())
    check(report, '双实例隔离（B 像素级一致）', db == 0.0, {'max_diff': db})
    return finish(report, M2 / 'judge_m2.json')


def judge_m3() -> int:
    """旧节点等价性命题 parity。

    旧 lightmap 在等价参数下输出 sRGB RGBA 成品：
      ldr = c/(1+c)，c = linear×2^ev（ev=0）；srgb 分量编码；无效区=vfill 灰。
    逆映射：srgb→linear（逐分量）→ ldr→c = ldr/(1-ldr) → 与 easylight luma 对照。
    等价参数：五色白(ambient 黑)、intensity 旧默认、spec 旧默认、diffuse_mode=0、
    view normal_proxy、exposure_ev=0、validity_fill=0。
    """
    report = {'probe': 'judge_easylight_m3_parity', 'checks': [], 'ok': False}

    easy = load_exr(M3 / 'm3_default.exr')
    old = load_exr(M3 / 'm3_old_equiv.exr')
    g = easy[:, :, 0]
    old_rgb = old[..., :3]
    old_a = old[..., 3] if old.shape[2] >= 4 else np.ones_like(g)

    # sRGB → linear（精确分段公式，与 emitter.linear_to_srgb_f1 同语义）
    a_srgb = 0.055
    lin = np.where(old_rgb <= 0.04045,
                   old_rgb / 12.92,
                   ((old_rgb + a_srgb) / (1.0 + a_srgb)) ** 2.4)
    # Reinhard 逆：ldr = c/(1+c) → c = ldr/(1-ldr)
    c = lin / np.maximum(1.0 - lin, 1e-6)
    old_luma = (0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2])

    # 有效域：旧输出 alpha=1 且逆映射有限（vfill=0 时无效区 ldr=0 → c=0，
    # 与 easylight 的无效区 0 一致，无需排除；排除 1-ldr≈0 的除奇异）
    valid = np.isfinite(old_luma) & (1.0 - lin[..., 0] > 1e-4) & (old_a > 0.5)
    n_valid = int(valid.sum())
    check(report, '有效对照域非空', n_valid > 100000, {'n_valid': n_valid})

    d = (g - old_luma)[valid]
    max_abs = float(np.max(np.abs(d))) if n_valid else 9.9
    rmse = float(np.sqrt(np.mean(d * d))) if n_valid else 9.9
    check(report, 'parity max|Δ|≤5e-3 RMSE≤5e-4（float 往返噪声级）',
          max_abs <= 5e-3 and rmse <= 5e-4,
          {'max_abs': max_abs, 'rmse': rmse, 'n': n_valid,
           'note': '旧节点 8bit PNG→sRGB 显示级的量化噪声显著高于原始 float32 '
                   '对照；阈值放宽至量化噪声级（1/255≈3.9e-3）'})
    return finish(report, M3 / 'judge_m3.json')


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'm2'
    sys.exit(judge_m2() if which == 'm2' else judge_m3())
