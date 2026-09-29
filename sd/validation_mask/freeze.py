# -*- coding: utf-8 -*-
r"""M0 — 保护清单冻结/核对（ANISO_MASK_PLAN §6 保护要求）。

外部运行（项目根或 sd/ 均可）:
    python validation_mask/freeze.py freeze   → 生成 baseline_frozen.json（首次）
    python validation_mask/freeze.py check    → 与 baseline 比对，零变化=PASS

覆盖：旧 SBS、旧 .resources 全部文件、stage3_pp2.py、aniso_pp/**、GLSL、
stages.py（连同本次唯一允许的 frame_out 扩展前后状态可分别记录）。
输出：sd/validation_mask/out/baseline_frozen.json + freeze_check.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

SD = Path(__file__).resolve().parent.parent
OUT = SD / 'validation_mask' / 'out'
BASELINE = OUT / 'baseline_frozen.json'

# 相对 sd/ 的受保护路径（目录=整棵树）
PROTECTED = [
    'aniso_lightmap.sbs',
    'aniso_lightmap.resources',
    'stage3_pp2.py',
    'aniso_pp',
    'stages.py',
]
GLSL_DIR = SD.parent / 'shaders'


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _snapshot() -> dict:
    snap = {}
    for rel in PROTECTED:
        p = SD / rel
        if p.is_dir():
            for f in sorted(p.rglob('*')):
                if f.is_file():
                    key = f'{rel}/{f.relative_to(p).as_posix()}'
                    snap[key] = _hash_file(f)
        elif p.is_file():
            snap[rel] = _hash_file(p)
    if GLSL_DIR.is_dir():
        for f in sorted(GLSL_DIR.rglob('*')):
            if f.is_file() and f.suffix in ('.frag', '.vert', '.glsl'):
                key = f'shaders/{f.relative_to(GLSL_DIR).as_posix()}'
                snap[key] = _hash_file(f)
    return snap


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    snap = _snapshot()
    if mode == 'freeze':
        BASELINE.write_text(json.dumps(snap, ensure_ascii=False, indent=2),
                            encoding='utf-8')
        print(f'[FREEZE] {len(snap)} files hashed -> {BASELINE}')
        return 0
    # check
    if not BASELINE.exists():
        print('[FAIL] baseline 不存在 —— 先运行 freeze')
        return 2
    old = json.loads(BASELINE.read_text(encoding='utf-8'))
    added = sorted(set(snap) - set(old))
    removed = sorted(set(old) - set(snap))
    changed = sorted(k for k in set(snap) & set(old) if snap[k] != old[k])
    # stages.py 允许且有且仅有 frame_out 兼容出口 —— 差异白名单
    allowed = {'stages.py'}
    bad_changed = [k for k in changed if k not in allowed]
    report = {
        'files_total': len(snap), 'added': added, 'removed': removed,
        'changed': changed, 'changed_allowed_only': sorted(allowed),
        'violations': bad_changed or ([] if not added and not removed
                                      else ['added/removed 见上']),
        'ok': not bad_changed and not added and not removed,
    }
    (OUT / 'freeze_check.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[{'PASS' if report['ok'] else 'FAIL'}] "
          f"total={report['files_total']} changed={changed} "
          f"added={added} removed={removed}")
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
