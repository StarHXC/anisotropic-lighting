"""validation/diag_preview_black.py — 诊断 preview 黑屏问题。

逐环节验证：
1. core pass FBO 读回是否非黑
2. output pass FBO 读回是否非黑
3. display blit 链路（quad shader + 显示纹理）读回是否非黑
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

import moderngl  # noqa: E402
from core.parameters import LightingParams  # noqa: E402
from core.render_setup import build_defines, build_uniforms  # noqa: E402
from gl.context import RenderContext  # noqa: E402
from preview import PreviewTextures, make_display_texture  # noqa: E402


def stats(name: str, img: np.ndarray) -> None:
    rgb = img[..., :3].astype(np.float64)
    print(f"  {name}: mean={rgb.mean():.4f} max={rgb.max():.4f} "
          f"nonzero={(np.abs(rgb).sum(axis=-1) > 1e-6).mean() * 100:.1f}%")


def main() -> int:
    rc = RenderContext.standalone(512, 512)
    try:
        print("== 1. core pass（aniso.frag DEBUG_MODE=0）==")
        tex = PreviewTextures(rc.ctx)
        params = LightingParams()
        uniforms = build_uniforms(params)
        uniforms["u_texel"] = (1.0 / tex.size[0], 1.0 / tex.size[1])
        core_fbo = rc.run_pass(
            "aniso.frag", tex.size[0], tex.size[1],
            uniforms=uniforms, textures=tex.as_map(),
            defines=build_defines(params),
        )
        linear = rc.readback_top_first(core_fbo)
        stats("linear (core)", linear)
        print(f"  valid texel: {(linear[..., 3] > 0.5).mean() * 100:.1f}%")

        print("== 2. output pass（output.frag）==")
        tex_linear = rc.ctx.texture(
            (tex.size[0], tex.size[1]), 4, linear.astype(np.float32).tobytes(), dtype="f4")
        tex_linear.filter = (moderngl.NEAREST, moderngl.NEAREST)
        out_fbo = rc.run_pass(
            "output.frag", tex.size[0], tex.size[1],
            uniforms={"u_exposureEV": 0.0, "u_validityFill": 1.0},
            textures={"u_linear": tex_linear},
        )
        srgb = rc.readback_top_first(out_fbo)
        stats("srgb (output)", srgb)
        tex_linear.release()

        print("== 3. display blit（quad + display shader）==")
        prog = rc.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                in vec2 in_uv;
                out vec2 v_uv;
                void main() {
                    v_uv = in_uv;
                    gl_Position = vec4(in_pos, 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D u_tex;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    fragColor = texture(u_tex, v_uv);
                }
            """,
        )
        quad = np.array([-1, -1, 0, 1, 1, -1, 1, 0, -1, 1, 0, 0,
                         -1, 1, 0, 0, 1, -1, 1, 0, 1, 1, 1, 1], dtype=np.float32)
        vbo = rc.ctx.buffer(quad.tobytes())
        vao = rc.ctx.vertex_array(prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        disp_tex = make_display_texture(rc.ctx, srgb)

        win_fbo = rc.ctx.screen
        win_fbo.use()
        rc.ctx.viewport = (0, 0, 512, 512)
        rc.ctx.clear(0.0, 0.0, 0.0, 1.0)
        disp_tex.use(0)
        prog["u_tex"].value = 0
        vao.render(moderngl.TRIANGLES)
        img = np.frombuffer(win_fbo.read(components=4, dtype="f1"), dtype=np.uint8)
        img = np.flipud(img.reshape(512, 512, 4)).copy()
        stats("blit result", img)

        vao.release()
        vbo.release()
        disp_tex.release()
        tex.release()
        print("== 诊断完成 ==")
        return 0
    finally:
        rc.release()


if __name__ == "__main__":
    sys.exit(main())
