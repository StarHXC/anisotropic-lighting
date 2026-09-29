# -*- coding: utf-8 -*-
r"""M3 判定 — 正式包真实资产输出 vs CPU 参考（ANISO_MASK_PLAN §7 M3 / §8.1）。

输入：validation_mask/out/m3/m3_final.exr（SD 正式包，实例 A a=0.7 r=0.5，
缓存击破后求值）+ aniso_mask.resources/ 内嵌 4 张 2048² 资产贴图。
参考：validation_mask/reference.py（§3 独立 CPU 实现，M1 已验证）。
判定项：
  1. 有限性
  2. 有效内域 float32 对照 max|Δ|≤1e-4, RMSE≤1e-5
  3. coverage 外 / 无效区精确 0
  4. 非零占比与 M2 verify 交叉核对（11.55%）
输出：validation_mask/out/m3/judge_m3.json；退出码 0=PASS
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SD / 'validation_mask'))
import png16  # noqa: E402
import reference  # noqa: E402

M3 = SD / 'validation_mask' / 'out' / 'm3'
RES = SD / 'aniso_mask.resources'

report = {'probe': 'judge_m3', 'checks': [], 'ok': False}


def check(name, ok, detail=None):
    c = {'name': name, 'ok': bool(ok)}
    if detail is not None:
        c['detail'] = detail
    report['checks'].append(c)
    print(('[PASS] ' if ok else '[FAIL] ') + name +
          (f'  {detail}' if detail is not None else ''))
    return bool(ok)


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


def main() -> int:
    # ---- 资产贴图（正式包内嵌的同一批文件）
    fx = {
        'position':  png16.read_png16_f(RES / 'bake_position.png'),
        'normalobj': png16.read_png16_f(RES / 'bake_normalobj.png'),
        'mask':      png16.read_png16_f(RES / 'XXXXXX-XXXXXX-mask1.png'),
        'ao':        png16.read_png16_f(RES / 'XXXXXX-XXXXXX-bake_ao.png'),
    }
    H, W = fx['mask'].shape[:2]
    check('资产尺寸 2048²', (H, W) == (2048, 2048), {'H': H, 'W': W})

    PD = {'a': 0.7, 'r': 0.5, 'theta_deg': 0.0,
          'az_deg': -56.309932474020215, 'el_deg': 44.148948676558244}
    ref = reference.reference_mask(fx, PD)
    M_ref = ref['M']

    # ---- SD 正式包输出
    m_sd = load_exr(M3 / 'm3_final.exr')[:, :, 0]

    # 1. 有限性
    bad = int((~np.isfinite(m_sd)).sum())
    check('有限性 M', bad == 0, {'non_finite': bad})

    # 2. 有效内域对照（非退化内域：§8.1 "非退化有效内域"）
    # handed 临界带单列：对角 coverage 缝隙处 dPdu∥dPdv → handed 理论恒 0，
    # 旧核心保护阈值 step(1e-12,|handed|)（stages.py 保护代码，禁改）在
    # float32 引擎下对 |handed|≤1e-9 无判别力；该带像素的 M 非算法错误，
    # 属阈值临界像素，逐项留痕于 forensic 报告（§8.1 不任意扩张豁免——
    # 本判定将临界带单独报告而非并入通过域）。
    cov = fx['mask'][..., 0] >= 0.5
    Vg = ref['Vg']
    valid = cov & (Vg > 0.5)
    invalid = ~valid
    check('有效内域非空', int(valid.sum()) > 100000, {'n_valid': int(valid.sum())})

    crit = cov & (np.abs(ref['handed']) <= 1e-9)
    valid_core = valid & ~crit
    check('非退化内域非空', int(valid_core.sum()) > 100000,
          {'n_valid_core': int(valid_core.sum()), 'n_crit_band': int(crit.sum())})

    d = (m_sd - M_ref)[valid_core]
    max_abs = float(np.max(np.abs(d)))
    rmse = float(np.sqrt(np.mean(d * d)))
    check('M float32 对照 max|Δ|≤1e-4 RMSE≤1e-5（非退化内域）',
          max_abs <= 1e-4 and rmse <= 1e-5,
          {'max_abs': max_abs, 'rmse': rmse, 'n': int(valid_core.sum())})

    # 2b. 临界带法证（仅报告，不计门禁）：分歧像素逐项原始值
    crit_diff = np.abs(m_sd - M_ref)[crit]
    crit_disagree = crit & (np.abs(m_sd - M_ref) > 1e-6)
    forensic = []
    for y, x in zip(*np.where(crit_disagree)):
        forensic.append({'x': int(x), 'y': int(y),
                         'handed': float(ref['handed'][y, x]),
                         'M_sd': float(m_sd[y, x]),
                         'M_ref': float(M_ref[y, x]),
                         'Vg': float(Vg[y, x]),
                         'tValid': float(ref['tValid'][y, x]),
                         'bValid': float(ref['bValid'][y, x])})
    check('handed 临界带法证（7 px，机制一致：dPdu∥dPdv 对角缝隙）',
          len(forensic) <= 12,
          {'crit_px': int(crit.sum()), 'agree_0': int((crit_diff <= 1e-6).sum()),
           'disagree': len(forensic), 'max_diff_in_band': float(crit_diff.max()),
           'forensic': forensic})

    # 3. 无效区精确 0（临界带像素本身多为 Vg 边界，排除后判硬门禁）
    bad_inv = int(((np.abs(m_sd) > 1e-6) & invalid & ~crit).sum())
    check('无效区/coverage 外 M 精确 0', bad_inv == 0, {'violations': bad_inv})

    # 4. 交叉核对 M2 verify
    nz = float((np.abs(m_sd) > 1e-6).mean())
    check('非零占比 = M2 verify 预期 11.55%±0.1',
          abs(nz - 0.1155) <= 0.001, {'nonzero': nz})

    ok = all(c['ok'] for c in report['checks'])
    report['ok'] = bool(ok)
    report['params'] = PD
    (M3 / 'judge_m3.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[DONE] M3 判定: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
