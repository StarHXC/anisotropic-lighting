"""moderngl context、FBO、纹理格式与显示/读回适配。

契约来源：PLAN.md §3.4（q 坐标与行序）、§6.1（float4 有效负载）、§8.2（--preview/--bake）。

q 坐标约定（PLAN §3.4）：
- 规范采样坐标 q 为左上原点、x 向右、y 向下；输入按「首行为顶部」上传。
- fragCoord.y 自下而上，因此片元里用 q.y = 1 - fragCoord.y/H 恢复语义；
  FBO 渲染到纹理再读回时读回缓冲行序自下而上，读回后翻转一次恢复
  「首行为顶部」。翻转只发生一次，预览适配不得重复翻转。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import moderngl
import numpy as np

__all__ = ["RenderContext", "SHADER_DIR"]

SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders"


class RenderContext:
    """离屏渲染管线：standalone context（--bake）与窗口 context（--preview）共用。

    计算全部发生在固定烘焙分辨率的 float32 FBO 中；窗口只显示缩放结果
    （PLAN §8.2：核心仍在固定烘焙分辨率 FBO 中计算）。
    """

    def __init__(self, ctx: moderngl.Context, width: int, height: int):
        self.ctx = ctx
        self.width = width
        self.height = height
        self.prog_fullscreen: moderngl.Program | None = None
        self.vao_fullscreen: moderngl.VertexArray | None = None
        # VAO 按 program 实例缓存（VAO 绑定 program，跨 program 复用会绑定错误）。
        self._vao_by_program: dict[int, moderngl.VertexArray] = {}
        # FBO 按用途独立：core pass（核心光照）与 output pass（编码输出）各一张，
        # 避免 output pass 采样 u_linear 的同时写回同一张颜色附件（反馈未定义）。
        self._fbo_cache: dict[tuple[str, int, int], moderngl.Framebuffer] = {}

    @classmethod
    def standalone(cls, width: int, height: int) -> "RenderContext":
        """--bake：无窗口 standalone context（PLAN §8.2；无窗口仍需 GPU/驱动）。"""
        ctx = moderngl.create_context(standalone=True)
        return cls(ctx, width, height)

    # ------------------------------------------------------------------
    def fbo(self, width: int, height: int, purpose: str = "core") -> moderngl.Framebuffer:
        """获取（或创建）float32 RGBA FBO（PLAN §3.1：中间/输出显式 32F 基准）。

        purpose 区分 core / output：同尺寸不同用途必须持有独立颜色附件，
        否则 output pass 一边采样 u_linear 一边写回同一纹理 = 反馈/自采样。
        """
        key = (purpose, width, height)
        if key not in self._fbo_cache:
            tex = self.ctx.texture((width, height), 4, dtype="f4")
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            fbo = self.ctx.framebuffer(color_attachments=[tex])
            self._fbo_cache[key] = fbo
        return self._fbo_cache[key]

    def load_program(self, name: str, defines: dict[str, str] | None = None) -> moderngl.Program:
        """编译 shaders/ 下的程序；defines 以 #define 注入，保证预览/无头同源。

        #include <file.glsl> 由本方法展开（GLSL 无 include，宿主负责拼接；
        PLAN §7 C5/C6：共享语义集中在 common.glsl，注入点唯一）。
        """
        source = self._resolve_includes((SHADER_DIR / name).read_text(encoding="utf-8"))
        if defines:
            lines = source.splitlines(keepends=True)
            # 注入到 #version 行之后（GLSL 要求 #version 最前）。
            for i, line in enumerate(lines):
                if line.startswith("#version"):
                    inject = "".join(f"#define {k} {v}\n" for k, v in defines.items())
                    lines.insert(i + 1, inject)
                    break
            else:
                raise ValueError(f"{name}: 缺少 #version 行，无法注入 defines")
            source = "".join(lines)
        return self.ctx.program(vertex_shader=_read_vert(), fragment_shader=source)

    @staticmethod
    def _resolve_includes(source: str) -> str:
        """展开 `#include <name.glsl>` 为 shaders/ 下文件内容（一层即可，common 不再嵌套）。"""
        import re

        pattern = re.compile(r'^#include\s+<([^>]+)>\s*$', re.MULTILINE)

        def repl(m: "re.Match[str]") -> str:
            inc_path = SHADER_DIR / m.group(1)
            return inc_path.read_text(encoding="utf-8")

        return pattern.sub(repl, source)

    def fullscreen_vao(self, prog: moderngl.Program) -> moderngl.VertexArray:
        """全屏三角形 VAO（无顶点缓冲，gl_VertexID 展开三顶点）。

        VAO 绑定到具体 program，不得跨 program 复用（不同 DEBUG_MODE
        会产生多个 program）；按 program 弱缓存，随 program 生命周期释放。
        """
        key = id(prog)
        if key not in self._vao_by_program:
            self._vao_by_program[key] = self.ctx.vertex_array(prog, [])
        return self._vao_by_program[key]

    def run_pass(
        self,
        frag_name: str,
        width: int,
        height: int,
        uniforms: dict[str, Any] | None = None,
        textures: dict[str, moderngl.Texture] | None = None,
        defines: dict[str, str] | None = None,
    ) -> moderngl.Framebuffer:
        """执行一次全屏 pass，渲染到指定尺寸 float32 FBO。

        PLAN §7 C7：每 pass 单一 float4 输出；调试量分 pass。
        """
        prog = self.load_program(frag_name, defines)
        for name, value in (uniforms or {}).items():
            if name in prog:
                prog[name].value = value
        fbo = self.fbo(width, height)
        fbo.use()
        textures = textures or {}
        for unit, (name, tex) in enumerate(textures.items()):
            tex.use(unit)
            if name in prog:
                prog[name].value = unit
        vao = self.fullscreen_vao(prog)
        vao.render(mode=moderngl.TRIANGLES, vertices=3)
        return fbo

    def readback_top_first(self, fbo: moderngl.Framebuffer) -> np.ndarray:
        """读回 FBO 并转成「首行为顶部」float32 (H, W, 4)。

        PLAN §3.4：FBO 读回时明确一次行序转换；只翻一次。
        显式 components=4 + dtype='f4'：默认 read() 会把 RGBA32F 截成 RGB float。
        """
        raw = np.frombuffer(fbo.read(components=4, dtype="f4"), dtype=np.float32)
        img = raw.reshape(fbo.height, fbo.width, 4)
        return np.flipud(img).copy()

    def release(self) -> None:
        for fbo in self._fbo_cache.values():
            fbo.release()
        self._fbo_cache.clear()
        for vao in self._vao_by_program.values():
            vao.release()
        self._vao_by_program.clear()


def _read_vert() -> str:
    return (SHADER_DIR / "fullscreen.vert").read_text(encoding="utf-8")
