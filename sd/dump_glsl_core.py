# -*- coding: utf-8 -*-
r"""Stage 1 GLSL 基准 dump — 复用现有烘焙链路，DEBUG_MODE 0/2/9 三 pass 输出 .npy。

外部运行（项目根目录）:
    python "sd/dump_glsl_core.py"

复用 aniso_bake.run_bake_full 的加载与 RenderContext（不改现有文件）；
defines 用 DEBUG_MODE override 逐 pass 渲染并立即保存（审核稿 §8.1）。
输出: sd/validation/glsl_core_debug{0,2,9}.npy  (H,W,4) float32 首行为顶部
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

import moderngl  # noqa: E402

from aniso_bake import (  # noqa: E402
    BAKE_ROOT, _derive_position_extent,
)
from core.asset_contract import AssetContract  # noqa: E402
from core.parameters import LightingParams, params_from_json, validate_params  # noqa: E402
from core.render_setup import build_defines, build_uniforms  # noqa: E402
from gl.context import RenderContext  # noqa: E402
from gl.textures import load_bake_image, upload_rgba32f  # noqa: E402

VAL = Path(__file__).resolve().parent / "validation"
CONFIG = PROJ / "config.json"


def main() -> int:
    params = (params_from_json(CONFIG) if CONFIG.exists() else LightingParams())
    errors = validate_params(params)
    if errors:
        print("参数错误:", errors, file=sys.stderr)
        return 2

    pos_plane = load_bake_image(BAKE_ROOT / "bake_position.png")
    nrm_plane = load_bake_image(BAKE_ROOT / "bake_normalobj.png")
    mask_plane = load_bake_image(BAKE_ROOT / "mask1.png")
    ao_plane = load_bake_image(BAKE_ROOT / "bake_ao.png")
    w, h = pos_plane.width, pos_plane.height

    rc = RenderContext.standalone(w, h)
    try:
        tex_pos = upload_rgba32f(rc.ctx, pos_plane.data, pos_plane.bitdepth)
        tex_n = upload_rgba32f(rc.ctx, nrm_plane.data, nrm_plane.bitdepth)
        tex_mask = upload_rgba32f(rc.ctx, mask_plane.data, mask_plane.bitdepth)
        tex_ao = upload_rgba32f(rc.ctx, ao_plane.data, ao_plane.bitdepth)
        for tex in (tex_pos, tex_n, tex_mask, tex_ao):
            tex.repeat_x = tex.repeat_y = False
        neutral = np.full((1, 1, 3), 128, dtype=np.uint8)
        tex_neutral = upload_rgba32f(rc.ctx, neutral, 8)

        uni = build_uniforms(params)
        uni["u_texel"] = (1.0 / w, 1.0 / h)
        textures = {"u_position": tex_pos, "u_normalobj": tex_n,
                    "u_mask": tex_mask, "u_ao": tex_ao,
                    "u_detailNormal": tex_neutral}

        outs = {}
        for dbg in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
            defines = build_defines(params)
            defines["DEBUG_MODE"] = str(dbg)
            fbo = rc.run_pass("aniso.frag", w, h, uniforms=uni,
                              textures=textures, defines=defines)
            arr = rc.readback_top_first(fbo)
            outs[dbg] = arr
            np.save(VAL / f"glsl_core_debug{dbg}.npy", arr)
            print(f"[OK] DEBUG_MODE={dbg} → glsl_core_debug{dbg}.npy "
                  f"({arr.shape})")
    finally:
        rc.release()

    # 快照记录（对比时的参数与输入哈希）
    import hashlib
    meta = {
        'params': {
            'light_dir': list(params.light_dir),
            'view_mode': params.view_mode,
            'spec_mode': params.spec_mode,
            'diffuse_mode': params.diffuse_mode,
        },
        'inputs_sha': {
            f: hashlib.sha256((BAKE_ROOT / f).read_bytes()).hexdigest()[:16]
            for f in ('bake_position.png', 'bake_normalobj.png', 'mask1.png',
                      'bake_ao.png')
        },
        'size': [w, h],
    }
    (VAL / 'glsl_core_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[DONE]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
