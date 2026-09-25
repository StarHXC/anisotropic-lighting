#!/usr/bin/env python3
"""preview.py — 交互预览界面（PLAN §8.2 --preview；步骤 6）。

契约来源：PLAN.md §8.2：预览与 --bake 共用同一计算与编码链路：
- 同一 core→output 双 pass（固定 2048² FBO 计算，窗口只显示缩放结果）；
- 同一 uniform/define 映射（core/render_setup.py，唯一映射点）；
- 同一参数校验器（core/parameters.py validate_params）；
- 保存到 config.json 后由 --bake 复现，像素级同源。

交互设计（PLAN §0：实时调整参数）：
- aniso_angle 滑块（旋转各向异性条纹方向，绕 +Ns 右手）；
- light_dir 球坐标控制（旋转光源位置 → 高光在布面上的位置）；
- 曝光/漫反射/高光强度等实时调参；
- 保存 config.json（供 --bake 复现）；
- 导出 PNG（直接写 out/anisotropic_lightmap.png 供 DCC 验证）。

实现说明（偏差登记）：
- PLAN §8.2 写的是 moderngl-window + 可选 imgui；moderngl-window 3.1.1
  底层是 GLFW，本实现直接用 GLFW + imgui_bundle.GlfwRenderer 事件桥接，
  避免 multi-window/事件转发引入的不确定性；FBO 计算侧仍是 moderngl。
- imgui_bundle 1.92+ 的 API-ified 模式与独立滑块并存，本实现用独立滑块
  以贴近 PLAN §8.1「可见滑块 + 全参数入快照」的语义。
- 窗口 vs FBO 行序：窗口侧一次 glViewport 翻转（物理翻转），
  FBO 读回侧一次 readback_top_first()；这两个是同一行序契约的两个面，
  只在预览模块内成对处理。

用法：
    python preview.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import glfw  # noqa: E402
import moderngl  # noqa: E402
import numpy as np  # noqa: E402
from imgui_bundle import imgui  # noqa: E402
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer  # noqa: E402

from aniso_bake import (  # noqa: E402
    BAKE_ROOT,
    CONFIG_PATH,
    OUT_DIR,
    _pad_invalid_border,
    build_default_contract,
)
from core.asset_contract import AssetContract  # noqa: E402
from core.parameters import LightingParams, params_from_json, params_to_json, validate_params  # noqa: E402
from core.render_setup import build_defines, build_uniforms  # noqa: E402
from gl.context import RenderContext  # noqa: E402
from gl.textures import load_bake_image, upload_rgba32f  # noqa: E402

BAKE_SIZE = 2048          # 固定烘焙分辨率（PLAN §8.2：核心仍在固定分辨率 FBO 计算）
MIN_REBAKE_INTERVAL_S = 0.1  # 参数变化触发的重算最小间隔（秒），拖动滑块时节流

VIEW_MODES = ("directional", "perspective", "normal_proxy")
SPEC_MODES = ("continuous", "smooth", "hard")
AXIS_MODES = ("u", "v")

# UI 中文字体（Dear ImGui 默认 ProggyClean 仅覆盖 ASCII，中文会渲染为 ?）。
# 按 FONTS.md：先声明 glyph ranges 再 AddFont，加载微软雅黑覆盖中文。
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",    # 微软雅黑（Win10/11 标配）
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体（兜底）
    r"C:\Windows\Fonts\simsun.ttc",  # 宋体（再兜底）
)


def _load_chinese_font() -> None:
    """加载系统字体以支持中文 UI 文本；全部失败时保留默认字体（英文回退）。"""
    io = imgui.get_io()
    for font_path in _FONT_CANDIDATES:
        if Path(font_path).exists():
            io.fonts.add_font_from_file_ttf(font_path, 16.0)
            return
    print("[warn] 未找到系统中文字体，界面文本将以英文默认字体显示（中文可能为问号）")


# ---------------------------------------------------------------------------
# 纹理加载（与 --bake 同源；惰性缓存避免重复上传）
# ---------------------------------------------------------------------------

class PreviewTextures:
    """烘焙输入纹理集：加载一次，复用于预览/烘焙双链路。"""

    def __init__(self, ctx: moderngl.Context):
        pos = load_bake_image(BAKE_ROOT / "bake_position.png")
        nrm = load_bake_image(BAKE_ROOT / "bake_normalobj.png")
        mask = load_bake_image(BAKE_ROOT / "mask1.png")
        ao = load_bake_image(BAKE_ROOT / "bake_ao.png")
        if not (pos.width == nrm.width == mask.width == ao.width
                and pos.height == nrm.height == mask.height == ao.height):
            raise ValueError("输入尺寸不一致")
        self.size = (pos.width, pos.height)

        neutral = np.full((1, 1, 3), 128, dtype=np.uint8)
        self.tex_position = upload_rgba32f(ctx, pos.data, pos.bitdepth)
        self.tex_normal = upload_rgba32f(ctx, nrm.data, nrm.bitdepth)
        self.tex_mask = upload_rgba32f(ctx, mask.data, mask.bitdepth)
        self.tex_ao = upload_rgba32f(ctx, ao.data, ao.bitdepth)
        self.tex_neutral = upload_rgba32f(ctx, neutral, 8)
        for t in (self.tex_position, self.tex_normal, self.tex_mask,
                  self.tex_ao, self.tex_neutral):
            t.repeat_x = t.repeat_y = False  # Clamp（PLAN §3.4）

    def as_map(self) -> dict:
        return {
            "u_position": self.tex_position,
            "u_normalobj": self.tex_normal,
            "u_mask": self.tex_mask,
            "u_ao": self.tex_ao,
            "u_detailNormal": self.tex_neutral,
        }

    def release(self) -> None:
        for t in (self.tex_position, self.tex_normal, self.tex_mask,
                  self.tex_ao, self.tex_neutral):
            t.release()


# ---------------------------------------------------------------------------
# 窗口显示纹理（把 FBO 结果转 GPU 纹理用于窗口 blit）
# ---------------------------------------------------------------------------

def make_display_texture(ctx: moderngl.Context, rgba_f32: np.ndarray) -> moderngl.Texture:
    """(H, W, 4) float32 → RGBA32F 纹理（窗口显示用；行序由 vert 翻转处理）。"""
    tex = ctx.texture((rgba_f32.shape[1], rgba_f32.shape[0]), 4,
                      rgba_f32.astype(np.float32).tobytes(), dtype="f4")
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    return tex


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------

class PreviewApp:
    """交互预览：imgui 调参 + 同源 FBO 链路 + 窗口缩放显示。"""

    def __init__(self, window, ctx: moderngl.Context):
        self.window = window
        self.ctx = ctx
        self.status_msg = "加载输入纹理（bake_position / normalobj / mask1 / ao）..."
        self.status_error = False
        print(f"[*] {self.status_msg}")
        self._draw_boot_screen()
        self.rc = RenderContext(ctx, BAKE_SIZE, BAKE_SIZE)
        self.textures = PreviewTextures(ctx)

        # --- 参数与状态 ---
        self.params = (
            params_from_json(CONFIG_PATH) if CONFIG_PATH.exists() else LightingParams()
        )
        self.status_msg = "就绪。调参后点击「保存配置并烘焙」导出。"
        self.status_error = False
        self._dirty = True          # 参数变化 → 需要重算 FBO
        self._last_render = 0.0
        self._last_srgb: np.ndarray | None = None  # 最近一次 FBO 结果（首行在顶）

        # --- 显示链路 ---
        self.display_tex: moderngl.Texture | None = None
        self._display_prog = ctx.program(
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
        self._quad_vbo = ctx.buffer(quad.tobytes())
        self._quad_vao = ctx.vertex_array(
            self._display_prog,
            [(self._quad_vbo, "2f 2f", "in_pos", "in_uv")],
        )

        # --- 启动屏（黑窗期间给用户可见反馈）---
        self._boot_prog = ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                void main() {
                    gl_Position = vec4(in_pos, 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                out vec4 fragColor;
                void main() {
                    fragColor = vec4(0.08, 0.08, 0.10, 1.0);
                }
            """,
        )
        self._boot_vao = ctx.vertex_array(self._boot_prog,
                                          [(self._quad_vbo, "2f", "in_pos")])

        self._first_render()

    def _draw_boot_screen(self) -> None:
        """启动阶段清屏为深色底（imgui 上下文此时尚未就绪，不能绘制文本；
        进度信息打印到终端 + 主循环首帧的 UI 状态栏可见）。"""
        self.ctx.screen.use()
        w, h = glfw.get_framebuffer_size(self.window)
        self.ctx.viewport = (0, 0, w, h)
        self.ctx.clear(0.08, 0.08, 0.10, 1.0)

    def _first_render(self) -> None:
        """首次烘焙（core pass 2048² 需数秒，终端打印避免黑窗误解）。"""
        self.status_msg = "首次计算 core→output pass（2048²，数秒）..."
        print(f"[*] {self.status_msg}")
        self._draw_boot_screen()
        self._render_fbo()
        self.status_msg = "就绪。调参后点击「保存配置并烘焙」导出。"
        self.status_error = False
        print("[*] 预览就绪")

    # ------------------------------------------------------------------
    # FBO 计算（与 --bake 同源链路）
    # ------------------------------------------------------------------
    def _render_fbo(self) -> None:
        """跑 core → output 双 pass，产出显示纹理。与 run_bake_full 共用映射。"""
        defines = build_defines(self.params)
        uniforms = build_uniforms(self.params)
        uniforms["u_texel"] = (1.0 / self.textures.size[0], 1.0 / self.textures.size[1])

        core_fbo = self.rc.run_pass(
            "aniso.frag", self.textures.size[0], self.textures.size[1],
            uniforms=uniforms, textures=self.textures.as_map(), defines=defines,
        )
        linear = self.rc.readback_top_first(core_fbo)

        tex_linear = self.ctx.texture(
            (self.textures.size[0], self.textures.size[1]), 4,
            linear.astype(np.float32).tobytes(), dtype="f4",
        )
        tex_linear.filter = (moderngl.NEAREST, moderngl.NEAREST)
        try:
            out_fbo = self.rc.run_pass(
                "output.frag", self.textures.size[0], self.textures.size[1],
                uniforms={"u_exposureEV": self.params.exposure_ev, "u_validityFill": 1.0},
                textures={"u_linear": tex_linear},
            )
            srgb = self.rc.readback_top_first(out_fbo)
        finally:
            tex_linear.release()

        # 有效域延拓 + 无效域白底（与 --bake 导出语义一致）
        valid = (linear[..., 3] > 0.5).astype(np.float64)
        valid_pad = _pad_invalid_border(valid, iters=8)
        srgb = srgb.copy()
        srgb[valid_pad == 0.0] = 1.0
        self._last_srgb = srgb  # 首行在顶（readback 已转换），供导出直接使用

        if self.display_tex is not None:
            self.display_tex.release()
        self.display_tex = make_display_texture(self.ctx, srgb)
        self._dirty = False

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _draw_ui(self) -> None:
        imgui.set_next_window_size((360, 0), imgui.Cond_.first_use_ever)
        imgui.begin("各向异性高光预览")

        # --- 光照方向（球坐标控制）---
        imgui.separator_text("光照方向")
        changed, theta_deg = imgui.slider_float(
            "方位角##light", np.degrees(np.arctan2(self.params.light_dir[1],
                                                    self.params.light_dir[0])),
            -180.0, 180.0, "%.1f°")
        if changed:
            self._set_light_dir(theta_deg, self._light_elev_deg())
        changed, elev_deg = imgui.slider_float(
            "仰角##light", self._light_elev_deg(), -89.0, 89.0, "%.1f°")
        if changed:
            self._set_light_dir(self._light_azim_deg(), elev_deg)

        # --- 各向异性 ---
        imgui.separator_text("各向异性")
        changed, angle_deg = imgui.slider_float(
            "条纹角度##aniso", np.degrees(self.params.aniso_angle),
            -180.0, 180.0, "%.1f°")
        if changed:
            self.params.aniso_angle = float(np.radians(angle_deg))
            self._dirty = True
        if imgui.begin_combo("主轴##axis", AXIS_MODES[self._axis_index()]):
            for i, m in enumerate(AXIS_MODES):
                if imgui.selectable(m, i == self._axis_index())[0]:
                    self.params.aniso_axis = m
                    self._dirty = True
            imgui.end_combo()
        changed, amount = imgui.slider_float(
            "各向异性程度", self.params.aniso_amount, 0.0, 1.0, "%.2f")
        if changed:
            self.params.aniso_amount = float(amount)
            self._dirty = True

        # --- 高光 ---
        imgui.separator_text("高光")
        changed, v = imgui.slider_float("强度1", self.params.spec1_intensity, 0.0, 4.0, "%.2f")
        if changed:
            self.params.spec1_intensity = float(v)
            self._dirty = True
        changed, v = imgui.slider_float("强度2", self.params.spec2_intensity, 0.0, 4.0, "%.2f")
        if changed:
            self.params.spec2_intensity = float(v)
            self._dirty = True
        changed, v = imgui.slider_float("锐度1##exp1", self.params.exponent1, 1.0, 256.0, "%.0f")
        if changed:
            self.params.exponent1 = float(v)
            self._dirty = True
        changed, v = imgui.slider_float("锐度2##exp2", self.params.exponent2, 1.0, 256.0, "%.0f")
        if changed:
            self.params.exponent2 = float(v)
            self._dirty = True

        # --- 漫反射与曝光 ---
        imgui.separator_text("漫反射 / 曝光")
        changed, v = imgui.slider_float("曝光 EV", self.params.exposure_ev, -3.0, 3.0, "%.2f")
        if changed:
            self.params.exposure_ev = float(v)
            self._dirty = True
        changed, v = imgui.slider_float("光强", self.params.light_intensity, 0.0, 4.0, "%.2f")
        if changed:
            self.params.light_intensity = float(v)
            self._dirty = True

        # --- 观察模式 ---
        imgui.separator_text("观察模式")
        if imgui.begin_combo("模式##view", self.params.view_mode):
            for m in VIEW_MODES:
                if imgui.selectable(m, m == self.params.view_mode)[0]:
                    self.params.view_mode = m
                    self._dirty = True
            imgui.end_combo()

        # --- 操作区 ---
        imgui.separator_text("操作")
        if imgui.button("保存配置"):
            self._save_config()
        if imgui.button("保存并烘焙 PNG"):
            self._bake_png()
        imgui.spacing()
        if imgui.button("重置为默认参数"):
            self.params = LightingParams()
            self._dirty = True

        # 状态栏
        imgui.separator()
        if self.status_error:
            imgui.push_style_color(imgui.Col_.text, (1.0, 0.35, 0.35, 1.0))
        imgui.text_wrapped(self.status_msg)
        if self.status_error:
            imgui.pop_style_color()
        imgui.end()

    # ------------------------------------------------------------------
    def _light_azim_deg(self) -> float:
        return float(np.degrees(np.arctan2(self.params.light_dir[1],
                                           self.params.light_dir[0])))

    def _light_elev_deg(self) -> float:
        xy = np.hypot(self.params.light_dir[0], self.params.light_dir[1])
        return float(np.degrees(np.arctan2(self.params.light_dir[2], xy)))

    def _set_light_dir(self, azim_deg: float, elev_deg: float) -> None:
        azim = np.radians(azim_deg)
        elev = np.radians(elev_deg)
        d = np.array([np.cos(elev) * np.cos(azim),
                      np.cos(elev) * np.sin(azim),
                      np.sin(elev)], dtype=np.float64)
        self.params.light_dir = tuple(d.tolist())
        self._dirty = True

    def _axis_index(self) -> int:
        return 0 if self.params.aniso_axis == "u" else 1

    def _validate(self) -> list[str]:
        return validate_params(self.params)

    def _save_config(self) -> None:
        errors = self._validate()
        if errors:
            self.status_msg = "配置未保存——参数校验失败: " + "; ".join(errors)
            self.status_error = True
            return
        params_to_json(self.params, CONFIG_PATH)
        self.status_msg = f"已保存 {CONFIG_PATH.name}。可用 --bake 复现同一结果。"
        self.status_error = False

    def _bake_png(self) -> None:
        errors = self._validate()
        if errors:
            self.status_msg = "无法烘焙——参数校验失败: " + "; ".join(errors)
            self.status_error = True
            return
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUT_DIR / "anisotropic_lightmap.png"
            # 直接复用 FBO 结果（与本帧显示同源），PNG 写盘走 --bake 同一编码。
            rgba8 = np.clip(
                np.round(self._last_srgb * 255.0), 0, 255
            ).astype(np.uint8) if self._last_srgb is not None else None
            if rgba8 is None:
                self.status_msg = "尚无渲染结果"
                self.status_error = True
                return
            import png as pypng
            h, w, _ = rgba8.shape
            writer = pypng.Writer(w, h, greyscale=False, bitdepth=8)
            with open(out_path, "wb") as f:
                writer.write(f, rgba8.reshape(h, w * 3).tolist())
            self._save_config()
            self.status_msg = f"已导出 {out_path.name} 并保存配置。"
            self.status_error = False
        except Exception as exc:  # noqa: BLE001 —— UI 层兜底报错
            self.status_msg = f"导出失败: {exc}"
            self.status_error = True

    # ------------------------------------------------------------------
    # 渲染循环
    # ------------------------------------------------------------------
    def draw(self) -> None:
        # 仅在参数变化时重烘 FBO（2048² 全链路代价高，不做逐帧重算）；
        # 最小间隔节流，避免拖动滑块时连续排队重算。
        if self._dirty and time.monotonic() - self._last_render > MIN_REBAKE_INTERVAL_S:
            self._render_fbo()
            self._last_render = time.monotonic()

        # 关键修复：core/output pass 结束后离屏 FBO 仍处于绑定状态，
        # 必须显式切回窗口默认 framebuffer，否则 clear/blit/UI 全部
        # 画进 FBO → 窗口全黑（ctx.screen 在 standalone 上下文为 None，
        # 窗口上下文必有）。
        self.ctx.screen.use()

        w, h = glfw.get_framebuffer_size(self.window)
        self.ctx.viewport = (0, 0, w, h)
        self.ctx.clear(0.08, 0.08, 0.10, 1.0)
        self.ctx.disable(moderngl.DEPTH_TEST)

        if self.display_tex is not None:
            # 保持宽高比居中显示（窗口只做缩放，不改烘焙分辨率——PLAN §3.4/§8.2）
            tex_w, tex_h = self.textures.size
            scale = min(w / tex_w, h / tex_h)
            disp_w, disp_h = tex_w * scale, tex_h * scale
            x0, y0 = (w - disp_w) * 0.5, (h - disp_h) * 0.5
            self.ctx.viewport = (int(x0), int(y0), int(disp_w), int(disp_h))
            self.display_tex.use(0)
            self._display_prog["u_tex"].value = 0
            self._quad_vao.render(moderngl.TRIANGLES)
            self.ctx.viewport = (0, 0, w, h)

        self._draw_ui()

    def shutdown(self) -> None:
        if self.display_tex is not None:
            self.display_tex.release()
        self._quad_vao.release()
        self._quad_vbo.release()
        self._display_prog.release()
        self.textures.release()
        self.rc.release()


def main() -> int:
    if not glfw.init():
        print("GLFW 初始化失败", file=sys.stderr)
        return 1
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    window = glfw.create_window(1600, 900, "Anisotropic Lighting Preview", None, None)
    if not window:
        glfw.terminate()
        print("窗口创建失败", file=sys.stderr)
        return 1
    glfw.make_context_current(window)
    ctx = moderngl.create_context()

    # imgui 上下文先于 PreviewApp 创建（启动屏需要绘制文本）
    imgui.create_context()
    _load_chinese_font()
    try:
        app = PreviewApp(window, ctx)
    except Exception as exc:  # noqa: BLE001
        print(f"预览初始化失败: {exc}", file=sys.stderr)
        glfw.destroy_window(window)
        glfw.terminate()
        return 1

    try:
        renderer = GlfwRenderer(window)
    except Exception as exc:  # noqa: BLE001
        print(f"imgui GLFW 后端初始化失败: {exc}", file=sys.stderr)
        app.shutdown()
        glfw.destroy_window(window)
        glfw.terminate()
        return 1

    while not glfw.window_should_close(window):
        glfw.poll_events()
        renderer.process_inputs()
        imgui.new_frame()
        app.draw()
        imgui.render()
        renderer.render(imgui.get_draw_data())
        glfw.swap_buffers(window)

    app.shutdown()
    renderer.shutdown()
    glfw.destroy_window(window)
    glfw.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
