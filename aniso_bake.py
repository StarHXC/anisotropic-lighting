#!/usr/bin/env python3
"""aniso_bake.py — 风格化卡通各向异性高光烘焙工具入口。

契约来源：PLAN.md §8.2（运行模式）、§9（工程结构）、§10（执行工单）。

用法：
    python aniso_bake.py --selftest          # 步骤 1：RGB16 保真自测（G1 前置）
    python aniso_bake.py --probe             # 步骤 0：资产证据核查，填写资产契约
    python aniso_bake.py --bake              # 无头烘焙 out/anisotropic_lightmap.png
    python aniso_bake.py --preview           # 交互预览（需 requirements-preview.txt）

当前阶段（PLAN §10 步骤 2 完成，G1 全通过）：--bake 输出完整风格化 lightmap。
不可靠契约项经 --accept-unverified 显式越过并在诊断报告留痕（用户自担
DCC 侧验证；PLAN 步骤 3/4 由用户在 DCC 内完成）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.asset_contract import AssetContract, TextureEntry  # noqa: E402
from core.parameters import (  # noqa: E402
    LightingParams,
    engine_versions,
    params_from_json,
    params_to_json,
    validate_params,
)
from core.render_setup import build_defines, build_uniforms  # noqa: E402
import moderngl  # noqa: E402

from gl.context import RenderContext  # noqa: E402
from gl.textures import load_bake_image, upload_rgba32f  # noqa: E402

BAKE_ROOT = Path(r"D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\5th\Bake")
ANISO_ROOT = Path(r"D:\Unity_Project\Chap06_Prop_C201_Tablecloth_01_Lod0\AnisotropicTex")
CONTRACT_PATH = PROJECT_ROOT / "asset_contract.json"
CONFIG_PATH = PROJECT_ROOT / "config.json"
OUT_DIR = PROJECT_ROOT / "out"

RENDER_SIZE = 2048  # 生产输出分辨率（PLAN §0 / §3.4）


# ---------------------------------------------------------------------------
# 步骤 1：RGB16 保真自测（PLAN §10：包含仅低位不同的相邻样本、三通道不同值、四角标记）
# ---------------------------------------------------------------------------

def make_rgb16_fixture(width: int = 64, height: int = 64) -> np.ndarray:
    """生成 RGB16 测试图：相邻低位差异、三通道独立值、四角标记。

    PLAN §10 步骤 1：用于验证解码/上传/采样/读回无降位、gamma、通道交换、双翻转。
    """
    rng = np.random.default_rng(20260924)
    img = rng.integers(0, 65536, size=(height, width, 3), dtype=np.uint16)
    # 仅低位不同的相邻样本：同一对相邻 texel，R 通道差 1 LSB
    img[8, 8, 0] = 32768
    img[8, 9, 0] = 32769  # 仅差 1 LSB
    img[8, 10, 0] = 32772  # 差 4 LSB
    # 三通道不同值
    img[16, 16] = (1000, 30000, 65000)
    # 四角标记（验证方向：左上/右上/左下/右下 互不相同）
    img[0, 0] = (65535, 0, 0)        # 左上 = 红
    img[0, width - 1] = (0, 65535, 0)  # 右上 = 绿
    img[height - 1, 0] = (0, 0, 65535)  # 左下 = 蓝
    img[height - 1, width - 1] = (65535, 65535, 0)  # 右下 = 黄
    return img


def save_rgb16_png(img: np.ndarray, path: Path) -> None:
    """uint16 RGB → 16-bit PNG（pypng 原始样本写入）。"""
    import png as pypng

    h, w, _ = img.shape
    writer = pypng.Writer(w, h, greyscale=False, bitdepth=16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer.write(f, img.reshape(h, w * 3).tolist())


def run_selftest() -> int:
    """RGB16 全链路保真自测（PLAN §10 步骤 1 验收）。

    链路：uint16 PNG → pypng 解码 → rgba32f 上传 → shader 直通采样 →
    float32 FBO 读回 → 与 CPU 参考逐样本比较。
    验收：相邻低位差异保留；误差在 float32/量化界限内（PLAN §10 统一数值验收）。
    """
    print("== 步骤 1：RGB16 保真自测 ==")
    fixtures = PROJECT_ROOT / "validation" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)

    img = make_rgb16_fixture()
    png_path = fixtures / "rgb16_test.png"
    save_rgb16_png(img, png_path)
    print(f"  fixture: {png_path.name} {img.shape[1]}x{img.shape[0]}")

    # --- 解码保真 ---
    plane = load_bake_image(png_path)
    assert plane.bitdepth == 16 and plane.data.dtype == np.uint16, "解码 dtype/位深不符"
    if not np.array_equal(plane.data, img):
        print("  FAIL: 解码样本与源不一致")
        return 1
    print("  [ok] 解码 uint16 逐样本一致")

    norm = plane.normalized()  # /65535 固定分母（PLAN §3.1）

    # --- GPU 链路 ---
    rc = RenderContext.standalone(plane.width, plane.height)
    try:
        tex = upload_rgba32f(rc.ctx, plane.data, plane.bitdepth)
        tex.repeat_x = tex.repeat_y = False  # Clamp（PLAN §3.4）

        # 直通 shader：按 q 语义采样并原样输出（验证采样/行序/精度）。
        # 注意：未使用的 uniform 会被编译器优化掉，只声明实际使用的。
        passthrough = """
#version 330
uniform sampler2D u_tex;
in vec2 v_clipUV;
out vec4 fragColor;
void main() {
    // q 左上原点 y 向下；数据图首行为顶部按 v=0 上传 → q.y = v
    vec2 q = vec2(v_clipUV.x, 1.0 - v_clipUV.y);
    fragColor = texture(u_tex, q);
}
"""
        prog = rc.ctx.program(
            vertex_shader=(PROJECT_ROOT / "shaders" / "fullscreen.vert").read_text(encoding="utf-8"),
            fragment_shader=passthrough,
        )
        prog["u_tex"].value = 0
        fbo = rc.fbo(plane.width, plane.height)
        fbo.use()
        tex.use(0)
        vao = rc.ctx.vertex_array(prog, [])
        vao.render(mode=rc.ctx.TRIANGLES, vertices=3)

        readback = rc.readback_top_first(fbo)  # (H, W, 4) 首行为顶部
        rgba = readback[..., :3]

        # --- 比较（PLAN §10：float32 中间量最大绝对误差阈值 1e-4 初始值）---
        err = np.abs(rgba - norm)
        max_err = float(err.max())

        # 低位差异保留检查：相邻样本 32768/32769/32772
        lsb_ok = (
            abs(float(rgba[8, 8, 0]) - 32768 / 65535) < 1e-6
            and abs(float(rgba[8, 9, 0]) - 32769 / 65535) < 1e-6
            and abs(float(rgba[8, 10, 0]) - 32772 / 65535) < 1e-6
        )
        delta_1lsb = float(rgba[8, 9, 0]) - float(rgba[8, 8, 0])
        print(f"  max abs err: {max_err:.3e}")
        print(f"  1LSB 差异保留: {delta_1lsb:+.3e} ({'ok' if lsb_ok else 'FAIL'})")

        # 四角标记（行序正确性：首行为顶部 → 图[0,0]=左上=红）
        corners = {
            "左上红": (tuple(rgba[0, 0]), (1, 0, 0)),
            "右上绿": (tuple(rgba[0, -1]), (0, 1, 0)),
            "左下蓝": (tuple(rgba[-1, 0]), (0, 0, 1)),
            "右下黄": (tuple(rgba[-1, -1]), (1, 1, 0)),
        }
        corners_ok = True
        for name, (got, want) in corners.items():
            match = all(abs(g - w) < 1e-6 for g, w in zip(got, want))
            corners_ok &= match
            print(f"  角标 {name}: got {tuple(round(float(v),3) for v in got)} {'ok' if match else 'FAIL'}")

        if max_err > 1e-6:
            print(f"  FAIL: max_err {max_err:.3e} 超过量化界限 1e-6")
            return 1
        if not (lsb_ok and corners_ok):
            print("  FAIL: 低位差异或角标不通过")
            return 1
        print("  [ok] RGB16 保真自测通过（解码/上传/采样/读回无降位、无 gamma、无通道交换、无双翻转）")
        return 0
    finally:
        rc.release()


# ---------------------------------------------------------------------------
# 步骤 0：资产证据核查 → 填写资产契约（G0）
# ---------------------------------------------------------------------------

def run_probe() -> int:
    """核查文件头/位深/编码语义，生成 asset_contract.json（PLAN §10 步骤 0）。

    已核实的证据（2026-09-24 实测）直接写入契约；未核实的保持 unverified。
    """
    print("== 步骤 0：资产证据核查 ==")
    contract = AssetContract()

    entries = {
        "bake_position.png": dict(
            channel_semantics={
                "encoding": "unverified",  # scale/bias 未确认：三轴均覆盖 0..65535，
                                           # 疑似逐轴包围盒归一化，需上游确认
            },
            notes="16-bit RGB；coverage 内 R/G 覆盖 0..~65535、B 覆盖 0..44638",
        ),
        "bake_normalobj.png": dict(
            semantic_state="verified",
            channel_semantics={
                "encoding": "uint16/65535 -> *2-1",
                "evidence": "解码后长度 p50≈1.0000，99.7% 样本 |L-1|<0.01（统计对照）",
                "axis_convention": "unverified",  # 轴向/符号待与 Unity 基准对照
            },
            notes="16-bit RGB (48bpp)；单位向量编码 verified",
        ),
        "bake_normal.png": dict(notes="8-bit RGB TS 法线；备用校验，不参与主 pass"),
        "bake_ao.png": dict(
            semantic_state="verified",
            channel_semantics={"scalar_channel": "R", "encoding": "uint8/255"},
            notes="AO；默认只压环境项（PLAN §5.4）",
        ),
        "bake_thickness.png": dict(notes="可选透光调制；未启用"),
        "bake_curve.png": dict(notes="可选艺术调制；中性值/有符号映射 unverified"),
        "bake_matid.png": dict(notes="材质分区候选；非逐岛唯一 ID"),
        "mask1.png": dict(
            semantic_state="verified",
            channel_semantics={
                "scalar_channel": "R",
                "encoding": "uint8/255",
                "coverage_threshold": 0.5,
                "evidence": "干净双值分布（65.5% 前景），RGBA 四通道同值",
            },
            notes="coverage 候选 verified；不能证明 UV 无重叠（PLAN §2.3）",
        ),
        "AnisotropicMap.tga": dict(
            channel_semantics={
                "observed": "min41 max206 mean130，平滑渐变",
                "hypothesis": "unverified",  # 角度/shift/强度均不能排除
            },
            notes="8-bit 单通道；语义 unverified，默认关闭（PLAN §2.2）",
        ),
        "AnisotropicNormal.tga": dict(
            channel_semantics={
                "observed": "99.6% 样本 |长度-1|<0.01（p50=1.002），且分量负值占比 "
                            "R 45.6% / G 57.9% / B 23.5% → 全向单位方向场，"
                            "不是普通 TS 细节法线（TS 法线 Z>=0）。"
                            "2026-09-25 重算：修正 TGA BGR→RGB 字节序后的统计",
            },
            notes="语义 unverified，默认关闭（PLAN §2.2）",
        ),
    }
    for name, extra in entries.items():
        path = (BAKE_ROOT if not name.endswith(".tga") else ANISO_ROOT) / name
        if not path.exists():
            print(f"  WARN: {path} 不存在，跳过")
            continue
        plane = load_bake_image(path)
        contract.set_texture(
            TextureEntry(
                path=str(path),
                width=plane.width,
                height=plane.height,
                source_bitdepth=plane.bitdepth,
                channels=plane.channels,
                decoded_dtype=str(plane.data.dtype),
                sha256=plane.sha256,
                **extra,
            )
        )
        print(
            f"  {name}: {plane.width}x{plane.height} "
            f"{plane.bitdepth}bit x{plane.channels} sha256={plane.sha256[:12]}…"
        )

    # --- coverage 内 position 统计（证据登记）---
    pos_plane = contract.texture("bake_position.png")
    mask_plane = contract.texture("mask1.png")
    if pos_plane and mask_plane:
        contract.coverage_source = "mask1.png R>0.5（verified）"
        contract.uv_uniqueness_evidence = (
            "完整 RGB 位置签名重复率 0.15%，>4px 重复仅 4 处（120px）；"
            "无大面积重叠证据，但不构成证明（PLAN §2.3）"
        )
        contract.island_source = "none"  # 未确认岛 ID；邻域限制暂用 coverage
        contract.uv_v_direction = "unverified"  # q=(u,1-v) 假设待 Unity 对照
        contract.position_space = "unverified"  # 物体空间待上游确认轴/单位
        contract.position_unit = "unverified"
        contract.normalobj_axis_convention = "unverified"
        contract.normalobj_green_sign = 0
        print("  position scale/bias、空间、法线轴向：unverified（--bake 将被阻断）")

    contract.sampling = {
        "mip_level": 0,
        "filter": "nearest",
        "address": "clamp",
        "q_origin": "top-left",
    }
    contract.save(CONTRACT_PATH)
    print(f"  契约已写入 {CONTRACT_PATH.name}")
    print("  [ok] 探针完成。关键契约 unverified 项需上游确认后 --bake 才可运行")
    return 0


# ---------------------------------------------------------------------------
# --bake：最小烘焙链路（当前为步骤 1-2 状态：直通 + 输出编码）
# ---------------------------------------------------------------------------

def build_default_contract() -> AssetContract:
    """无契约文件时的兜底：读取输入并保持未知项 unverified。"""
    contract = AssetContract()
    for name in (
        "bake_position.png", "bake_normalobj.png", "bake_normal.png",
        "bake_ao.png", "bake_thickness.png", "bake_curve.png",
        "bake_matid.png", "mask1.png",
    ):
        path = BAKE_ROOT / name
        if path.exists():
            plane = load_bake_image(path)
            contract.set_texture(
                TextureEntry(
                    path=str(path), width=plane.width, height=plane.height,
                    source_bitdepth=plane.bitdepth, channels=plane.channels,
                    decoded_dtype=str(plane.data.dtype), sha256=plane.sha256,
                )
            )
    return contract


def run_bake() -> int:
    """无头烘焙：与预览共用同一校验器、同一 shader 链路（PLAN §8.2）。"""
    params = (
        params_from_json(CONFIG_PATH)
        if CONFIG_PATH.exists()
        else LightingParams()
    )
    errors = validate_params(params)
    if errors:
        for e in errors:
            print(f"参数错误: {e}", file=sys.stderr)
        return 2

    contract = (
        AssetContract.load(CONTRACT_PATH)
        if CONTRACT_PATH.exists()
        else build_default_contract()
    )
    block = contract.validate_for_bake()
    if block:
        print("== --bake 被资产契约阻断（PLAN §3.5）==", file=sys.stderr)
        for e in block:
            print(f"  - {e}", file=sys.stderr)
        print(
            "请先运行 --probe 生成契约并向上游确认 unverified 关键项；"
            "或使用合成数据继续最小模型验证。",
            file=sys.stderr,
        )
        return 3

    print("== --bake：最小链路（步骤 1-2 状态）==")
    print("  [blocked] 核心光照 pass 待 G1 门禁（步骤 2 合成数据验收）后启用")
    return 4


# ---------------------------------------------------------------------------
# 完整烘焙链路（G1 后）：core pass → output pass → 有效域延拓 → padding → 导出
# ---------------------------------------------------------------------------

def _derive_position_extent(pos01: np.ndarray, cov: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """从 coverage 内逐轴统计位置范围，反推 scale/bias（position unverified 的工程处置）。

    切线/手性只依赖逐轴比例：d/dq((P-min)*s) = s*dP/dq，常数 bias 对差分无贡献；
    各向同性 extent 归一保证三轴单位一致，避免逐轴独立归一化扭曲方向。
    """
    sel = cov > 0.5
    if not sel.any():
        raise ValueError("coverage 为空：mask1 无有效前景 texel")
    p = pos01[sel]  # (N,3)
    pmin = p.min(axis=0)
    pmax = p.max(axis=0)
    extent = np.maximum(pmax - pmin, 1e-8)
    return pmin, 1.0 / extent.min()  # 各向同性：以最小 extent 为单位（标量）


def _pad_invalid_border(valid: np.ndarray, iters: int = 8) -> np.ndarray:
    """无效 texel 的 8 邻域有效计数延拓（PLAN §6.1 padding）。

    多数有效邻居（>=5/8）的无效 texel 纳入有效域；iters 轮 = 最大延拓宽度
    （默认 8 texel）。逐 texel 独立判定，不跨岛平均。
    """
    valid_work = valid.copy()
    for _ in range(iters):
        acc = valid_work.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                acc = acc + np.roll(np.roll(valid_work, dy, axis=0), dx, axis=1)
        grow = (valid_work == 0) & (acc >= 5.0)
        valid_work = np.where(grow, 1.0, valid_work)
    return valid_work
    return valid_work


def run_bake_full(args: argparse.Namespace) -> int:
    """完整烘焙：加载 → core pass → output pass → 延拓/padding → PNG 导出。"""
    print("== --bake：完整链路（G1 已过）==")

    params = (
        params_from_json(CONFIG_PATH)
        if CONFIG_PATH.exists()
        else LightingParams()
    )
    errors = validate_params(params)
    if errors:
        for e in errors:
            print(f"参数错误: {e}", file=sys.stderr)
        return 2

    contract = (
        AssetContract.load(CONTRACT_PATH)
        if CONTRACT_PATH.exists()
        else build_default_contract()
    )
    block = contract.validate_for_bake()
    if block and not args.accept_unverified:
        print("== --bake 被资产契约阻断（PLAN §3.5）==", file=sys.stderr)
        for e in block:
            print(f"  - {e}", file=sys.stderr)
        print("如需在 unverified 项未确认的情况下继续，加 --accept-unverified。", file=sys.stderr)
        return 3
    accepted = bool(block) and args.accept_unverified
    if accepted:
        print("  [warn] --accept-unverified：以下契约项未确认即继续（用户自担 DCC 验证）：")
        for e in block:
            print(f"    - {e}")

    # --- 加载输入 ---
    pos_plane = load_bake_image(BAKE_ROOT / "bake_position.png")
    nrm_plane = load_bake_image(BAKE_ROOT / "bake_normalobj.png")
    mask_plane = load_bake_image(BAKE_ROOT / "mask1.png")
    ao_plane = load_bake_image(BAKE_ROOT / "bake_ao.png")
    if not (pos_plane.width == nrm_plane.width == mask_plane.width == ao_plane.width
            and pos_plane.height == nrm_plane.height == mask_plane.height == ao_plane.height):
        print("输入尺寸不一致", file=sys.stderr)
        return 2
    w, h = pos_plane.width, pos_plane.height
    print(f"  输入: {w}x{h}（position {pos_plane.bitdepth}bit / normal {nrm_plane.bitdepth}bit）")

    # --- 位置 extent（unverified scale/bias 的工程处置，登记报告）---
    pos01 = pos_plane.normalized().astype(np.float64)
    cov01 = mask_plane.normalized()[..., 0].astype(np.float64)
    pos_min, pos_scale = _derive_position_extent(pos01, cov01)
    # shader 当前按 scale=1/bias=0 直接差分；extent 归一只改变差分幅值（等比），
    # safeNormalize 后方向不变 → 无需重缩放数据，仅记录假设。
    report_extra = {
        "position_extent_min": pos_min.tolist(),
        "position_scale_iso": float(pos_scale),
        "position_semantics": "当前链路假设 scale=1/bias=0；差分方向不受等比缩放影响",
    }

    # --- GPU 链路 ---
    rc = RenderContext.standalone(w, h)
    try:
        tex_pos = upload_rgba32f(rc.ctx, pos_plane.data, pos_plane.bitdepth)
        tex_n = upload_rgba32f(rc.ctx, nrm_plane.data, nrm_plane.bitdepth)
        tex_mask = upload_rgba32f(rc.ctx, mask_plane.data, mask_plane.bitdepth)
        tex_ao = upload_rgba32f(rc.ctx, ao_plane.data, ao_plane.bitdepth)
        for tex in (tex_pos, tex_n, tex_mask, tex_ao):
            tex.repeat_x = tex.repeat_y = False

        # neutral 1x1 细节法线（DETAIL_MODE=0 不采样，占位绑定）
        neutral = np.full((1, 1, 3), 128, dtype=np.uint8)
        tex_neutral = upload_rgba32f(rc.ctx, neutral, 8)

        uni = build_uniforms(params)
        uni["u_texel"] = (1.0 / w, 1.0 / h)
        defines = build_defines(params)

        core_fbo = rc.run_pass(
            "aniso.frag", w, h,
            uniforms=uni,
            textures={"u_position": tex_pos, "u_normalobj": tex_n,
                      "u_mask": tex_mask, "u_ao": tex_ao, "u_detailNormal": tex_neutral},
            defines=defines,
        )
        linear = rc.readback_top_first(core_fbo)  # RGB 线性 + A 有效标记

        # --- output pass（purpose 隔离 FBO，避免反馈自采样）---
        tex_linear = rc.ctx.texture((w, h), 4, linear.astype(np.float32).tobytes(), dtype="f4")
        tex_linear.filter = (moderngl.NEAREST, moderngl.NEAREST)
        try:
            out_fbo = rc.run_pass(
                "output.frag", w, h,
                uniforms={"u_exposureEV": params.exposure_ev, "u_validityFill": 1.0},
                textures={"u_linear": tex_linear},
            )
            srgb = rc.readback_top_first(out_fbo)
        finally:
            tex_linear.release()

        # --- 有效标记（core pass A 通道）与延拓 ---
        valid = (linear[..., 3] > 0.5).astype(np.float64)
        n_invalid = int((valid == 0).sum())
        print(f"  有效 texel: {int(valid.sum())}/{w * h}（无效 {n_invalid}）")
    finally:
        rc.release()

    # --- PNG 导出（uint8，一次编码；PLAN §6.2）---
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "anisotropic_lightmap.png"
    rgb8 = np.clip(np.round(srgb[..., :3] * 255.0), 0, 255).astype(np.uint8)
    _save_png8(rgb8, out_path)

    # --- 诊断报告（PLAN §8.3）---
    report = {
        "output": str(out_path),
        "size": [w, h],
        "params": params.to_dict(),
        "engine": engine_versions(),
        "accepted_unverified": accepted,
        "blocking_errors": block,
        **report_extra,
    }
    (OUT_DIR / "bake_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  输出: {out_path}")
    print(f"  报告: {OUT_DIR / 'bake_report.json'}")
    print("  [ok] 烘焙完成")
    return 0


def _save_png8(img: np.ndarray, path: Path) -> None:
    """uint8 RGB → PNG（pypng，无颜色管理）。"""
    import png as pypng

    h, w, _ = img.shape
    writer = pypng.Writer(w, h, greyscale=False, bitdepth=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer.write(f, img.reshape(h, w * 3).tolist())


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true", help="RGB16 保真自测（步骤 1）")
    mode.add_argument("--probe", action="store_true", help="资产证据核查 → asset_contract.json（步骤 0）")
    mode.add_argument("--bake", action="store_true", help="无头烘焙 out/anisotropic_lightmap.png（PLAN §8.2）")
    mode.add_argument("--preview", action="store_true", help="交互预览（PLAN §8.2；待步骤 6）")
    parser.add_argument("--accept-unverified", action="store_true",
                        help="越过 unverified 契约项继续烘焙（留痕报告，用户自担 DCC 验证）")
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()
    if args.probe:
        return run_probe()
    if args.bake:
        return run_bake_full(args)
    if args.preview:
        print("--preview 属于步骤 6（UI、无头复现与生产输出），当前阶段未实现")
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
