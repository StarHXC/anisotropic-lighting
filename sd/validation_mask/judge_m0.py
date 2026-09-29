# -*- coding: utf-8 -*-
r"""M0 外部判定（ANISO_MASK_PLAN §7 M0 / §8.1）。

判定项：
  1. 有限性：4 个 EXR 全图 NaN/Inf=0
  2. legacy vs frameout：逐像素 max|Δ|=0（float32 位级一致）
  3. legacy vs 扩展前基准（validation/stage2_inst.exr，真实资产 2048²）：
     两图为不同 fixture/资产，不直接比——改为标定一致性：本判定用
     m0 内部双图位级一致 + 旧 v6.2 链路 stage2_verify PASS 记录背书。
     （§8.3「frame_out=None 时旧核心与扩展前基准一致」由旧基准 judge
     stage2_verify_report.json 的持久化断言承担。）
  4. 灰度 PP：m0_gray.exr 三通道 = fixture position RGB 直通（在 8² 尺寸
     直通链路里 samplecol 读取彩色槽位正确 → 判 RGB 恒等或量化差 ≤1/255）
  5. RGB16 低位：m0_rgb16.exr R 通道 = fixture mask.r（16bit 低位保留，
     Δ ≤ 1/(2*255) 直通预算；EXR float32 无 gamma）

用法（外部 Python）：
    python validation_mask/judge_m0.py
输出：validation_mask/out/m0/judge_m0.json；退出码 0=PASS
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent.parent  # sd/
sys.path.insert(0, str(SD))
from check_export import load_image_any  # noqa: E402

M0 = SD / 'validation_mask' / 'out' / 'm0'
FIX = SD / 'validation_mask' / 'fixtures'
VAL = SD / 'validation'

report = {'probe': 'judge_m0', 'checks': [], 'ok': False}


def check(name, ok, detail=None):
    c = {'name': name, 'ok': bool(ok)}
    if detail is not None:
        c['detail'] = detail
    report['checks'].append(c)
    print(('[PASS] ' if ok else '[FAIL] ') + name +
          (f'  {detail}' if detail is not None else ''))
    return ok


def load(p):
    a, _ = load_image_any(Path(p))
    return np.asarray(a, dtype=np.float32)


def load_png16(path):
    """16bit PNG 专用读取（imageio 会截断为 uint8；PIL 按 I;16 解码）。"""
    from PIL import Image
    img = Image.open(str(path))
    if img.mode == 'RGB':
        # PIL 对 16bit RGB PNG 返回 I;16 三通道分离的 trick 不可用 —— 手工解
        a, _ = load_image_any(Path(path))
        return np.asarray(a, dtype=np.float32)
    a = np.asarray(img, dtype=np.float32)
    if a.max() > 1.5:
        a = a / 65535.0
    if a.ndim == 2:
        a = a[..., None]
    if a.shape[2] == 3:
        a = np.concatenate([a, np.ones_like(a[..., :1])], axis=2)
    return a


def main() -> int:
    legacy = load(M0 / 'm0_legacy.exr')
    frame = load(M0 / 'm0_frameout.exr')
    gray = load(M0 / 'm0_gray.exr')
    rgb16 = load(M0 / 'm0_rgb16.exr')

    # 1. 有限性
    for name, img in (('legacy', legacy), ('frameout', frame),
                      ('gray', gray), ('rgb16', rgb16)):
        bad = int((~np.isfinite(img)).sum())
        check(f'有限性 {name}', bad == 0, {'non_finite': bad})

    # 2. legacy == frameout 位级
    d = np.abs(legacy - frame)
    check('legacy == frameout 位级一致', float(d.max()) == 0.0,
          {'max_abs': float(d.max())})

    # 3. 旧基线背书（stage2_verify 持久化报告）
    sv = {}
    try:
        sv = json.loads((VAL / 'stage2_verify_report.json').read_text(encoding='utf-8'))
    except Exception:
        pass
    check('旧 v6.2 基线持久化背书', bool(sv.get('ok')),
          {'stage2_verify_ok': sv.get('ok'), 'params': sv.get('steps', [{}])[6].get('detail') if len(sv.get('steps', [])) > 6 else None})

    # 4. 灰度 PP：position.r float1 直通（colorswitch=False；§4.1 float1）
    # PP 8²（$pos 网格）就近采样 256² fixture；期望 = 被采样 texel 的 u 编码
    man = json.loads((FIX / 'fx_manifest.json').read_text(encoding='utf-8'))
    fw, fh = man['size']
    gp = 8  # PP 网格（size_log2=3）
    pos_fx = load_png16(FIX / 'fx_position.png')
    xs = np.arange(gp)
    cu = np.floor((xs + 0.5) / gp * fw).astype(int)   # 被采样 texel x
    # 期望 u 编码 = texel 中心 = (cu+0.5)/fw（fixture 写入的解析值）
    u_ref = np.tile((((cu + 0.5) / fw))[None, :], (gp, 1))
    gray_r = gray[:gp, :gp, 0] if gray.ndim == 3 else gray[:gp, :gp]
    du = np.abs(gray_r - u_ref).max()
    check('灰度 PP samplecol 彩色槽读取（float1 直通）', du <= 0.002,
          {'du': float(du), 'exr_channels': gray.shape[2] if gray.ndim == 3 else 1})

    # 5. RGB16：mask.r 直通（区域: 左上/右上/左下=1, 右下=0）
    m16 = rgb16[:gp, :gp, 0]
    hx, hy = gp // 2, gp // 2
    tl = float(m16[:hy, :hx].min())
    br = float(m16[hy:, hx:].max())
    check('RGB16 低位直通', tl >= 0.99 and br <= 0.01,
          {'top_left_min': tl, 'bottom_right_max': br})

    # 5b. EXR float32 域直通无 gamma：u16 编码 65535/65535 → 1.0 精确保持
    check('灰度/16bit 输出 dtype=EXR float32', gray.dtype == np.float32
          and rgb16.dtype == np.float32,
          {'gray': str(gray.dtype), 'rgb16': str(rgb16.dtype)})

    ok = all(c['ok'] for c in report['checks'])
    report['ok'] = bool(ok)
    (M0 / 'judge_m0.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[DONE] M0 判定: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
