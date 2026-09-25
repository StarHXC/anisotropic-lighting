"""高精度 PNG/TGA 读取与 GPU 纹理上传。

契约来源：PLAN.md §3.1「高精度加载：禁止隐式降位」。

硬规则：
- 16-bit RGB PNG 走 PyPNG 原始样本路径，返回 uint16 ndarray，绝不经过
  Pillow RGB（每通道 8 位）转换；分母固定 65535，不依赖解码器自动选取。
- 8-bit 图走 Pillow，分母固定 255。
- 所有数据图禁止 sRGB 解码与自动颜色管理（PLAN §3.2）。
- 上传 GPU 使用 rgba32f（PLAN §3.1：基准实现将数据上传为 float32 纹理）。

命名约定（PLAN §8.3）：原始数据调试文件与着色预览分开，本模块只产原始数据。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import moderngl
import numpy as np
import png  # pypng
from PIL import Image

__all__ = [
    "ImagePlane",
    "read_png_u16",
    "read_png_u8",
    "read_tga_raw",
    "load_bake_image",
    "upload_r32f",
    "upload_rgba32f",
    "upload_rgb32f",
]


@dataclass(frozen=True)
class ImagePlane:
    """解码后的数据图。

    attributes:
        data: 归一化前的原始样本 (H, W, C)，uint16 或 uint8。
        bitdepth: 每通道源位深（8 或 16）。
        channels: 通道数。
        source: 源文件路径。
        sha256: 源文件哈希（资产契约登记用，PLAN §3.5）。
    """

    data: np.ndarray
    bitdepth: int
    channels: int
    source: Path
    sha256: str

    @property
    def height(self) -> int:
        return self.data.shape[0]

    @property
    def width(self) -> int:
        return self.data.shape[1]

    def normalized(self) -> np.ndarray:
        """按 PLAN §3.1 固定分母归一化为 float32。

        16 位分母 65535、8 位分母 255；禁止依赖解码器自动选取分母。
        """
        denom = 65535.0 if self.bitdepth == 16 else 255.0
        return self.data.astype(np.float32) / denom


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_png_u16(path: str | Path) -> ImagePlane:
    """读取 16-bit PNG，保留原始 uint16 样本。

    使用 PyPNG asDirect() 的原始行数据路径（PLAN §3.1 指定的默认后端）。
    返回的数组形状为 (H, W, C)。
    """
    path = Path(path)
    reader = png.Reader(filename=str(path))
    width, height, rows, info = reader.asDirect()
    bitdepth = info["bitdepth"]
    planes = info["planes"]
    if bitdepth != 16:
        raise ValueError(
            f"{path.name}: 期望 16-bit PNG，实际 bitdepth={bitdepth}；"
            "8-bit 图请走 read_png_u8，避免混用分母"
        )
    # asDirect 保证交织(interlace)已展开、行是平面样本序列。
    arr = np.array(list(rows), dtype=np.uint16)
    expected = height * width * planes
    if arr.size != expected:
        raise ValueError(f"{path.name}: 样本数 {arr.size} != 期望 {expected}")
    plane = ImagePlane(
        data=arr.reshape(height, width, planes),
        bitdepth=16,
        channels=planes,
        source=path,
        sha256=_sha256(path),
    )
    return plane


def read_png_u8(path: str | Path) -> ImagePlane:
    """读取 8-bit PNG（AO/curve/thickness/matid/mask 等辅助图）。"""
    path = Path(path)
    img = Image.open(path)
    if img.mode in ("RGB", "RGBA", "L", "LA"):
        arr = np.array(img)
    else:
        # P 等调色板模式先转 RGBA，避免隐式调色板语义残留。
        arr = np.array(img.convert("RGBA"))
    if arr.ndim == 2:
        arr = arr[..., None]
    bitdepth = 8  # Pillow 这些模式均为每通道 8 位（PLAN §3.1 对 RGB 模式的判断）
    return ImagePlane(
        data=arr.astype(np.uint8),
        bitdepth=bitdepth,
        channels=arr.shape[-1],
        source=path,
        sha256=_sha256(path),
    )


def read_tga_raw(path: str | Path) -> ImagePlane:
    """读取未压缩 TGA，处理底行在前(origin bit=0)到「首行为顶部」的规范（PLAN §3.4）。

    说明：PLAN §3.4 要求 TGA 原点由解码器处理到规范坐标，不要看到原点
    标志就无条件再翻一次。此处按 header 的 origin bit 显式处理：
    bit=0 → 底行在前 → 翻转；bit=1 → 顶行在前 → 不翻转。

    字节序：TGA type 2（彩色）按 spec 存储 BGR(A)，此处转为规范 RGB(A)；
    type 3（灰度）单通道无字节序问题。原点翻转与通道交换相互独立。
    """
    path = Path(path)
    with open(path, "rb") as f:
        head = f.read(18)
        id_len = head[0]
        img_type = head[2]
        width, height = struct.unpack("<HH", head[12:16])
        bpp = head[16]
        desc = head[17]
        if id_len:
            f.read(id_len)
        top_origin = bool(desc & 0x20)
        bytes_pp = bpp // 8
        raw = f.read(width * height * bytes_pp)
    if img_type not in (2, 3):
        raise ValueError(
            f"{path.name}: 仅支持未压缩 TGA（ImgType 2/3），实际 {img_type}；"
            "压缩 TGA 需另行验证解码器行为"
        )
    dtype = np.uint8  # 本项目两张 aniso 图为 8/24 bit
    channels = bytes_pp
    arr = np.frombuffer(raw, dtype=dtype).reshape(height, width, channels).copy()
    if img_type == 2 and channels >= 3:
        # BGR(A) → RGB(A)（TGA spec 字节序）；A 通道（若有）保持在位。
        swapped = np.ascontiguousarray(arr[..., :3][..., ::-1])
        arr = np.concatenate([swapped, arr[..., 3:]], axis=-1) if channels == 4 else swapped
    if not top_origin:
        arr = arr[::-1]
    return ImagePlane(
        data=arr,
        bitdepth=8,
        channels=channels,
        source=path,
        sha256=_sha256(path),
    )


def load_bake_image(path: str | Path) -> ImagePlane:
    """按扩展名与实际位深分发读取（bake 数据图统一入口）。

    位深以文件头为准而非扩展名：16-bit 走 pypng，其余走 Pillow。
    """
    path = Path(path)
    if path.suffix.lower() == ".tga":
        return read_tga_raw(path)
    if path.suffix.lower() != ".png":
        raise ValueError(f"{path.name}: 不支持的格式 {path.suffix}，本项目只消费 PNG/TGA")
    reader = png.Reader(filename=str(path))
    _, _, _, info = reader.asDirect()
    if info["bitdepth"] == 16:
        return read_png_u16(path)
    return read_png_u8(path)


# ---------------------------------------------------------------------------
# GPU 上传（PLAN §3.1：基准为 float32 纹理，禁止先降 8 位或 half 再扩大）
# ---------------------------------------------------------------------------

def _to_rgba_f32(data: np.ndarray, bitdepth: int) -> np.ndarray:
    """(H, W, C<=4) 原始样本 → 归一化 float32 RGBA，缺失通道补默认值。

    补值语义：RGB 图 A=1；不足 3 通道的标量图复制到 RGB 便于调试查看，
    数据语义仍以 R 通道为准（登记在 asset_contract.json）。
    """
    denom = 65535.0 if bitdepth == 16 else 255.0
    h, w, c = data.shape
    if c > 4:
        raise ValueError(f"通道数 {c} > 4，无法作为单张 RGBA 上传")
    out = np.zeros((h, w, 4), dtype=np.float32)
    out[..., :c] = data.astype(np.float32) / denom
    if c < 4:
        out[..., 3] = 1.0
    if c == 1:
        out[..., 1] = out[..., 0]
        out[..., 2] = out[..., 0]
    elif c == 2:
        out[..., 2] = 0.0
    return out


def upload_rgba32f(ctx, data: np.ndarray, bitdepth: int):
    """上传为 rgba32f 纹理。首行为顶部直接按行序上传（见 gl/context.py 的 q 约定）。"""
    rgba = _to_rgba_f32(data, bitdepth)
    tex = ctx.texture((rgba.shape[1], rgba.shape[0]), 4, rgba.tobytes(), dtype="f4")
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    return tex


def upload_rgb32f(ctx, data: np.ndarray, bitdepth: int):
    """上传为 rgb32f 纹理（仅用于明确需要 3 通道存储的场景；基准主链路用 rgba32f）。"""
    denom = 65535.0 if bitdepth == 16 else 255.0
    rgb = data.astype(np.float32) / denom
    tex = ctx.texture((rgb.shape[1], rgb.shape[0]), 3, rgb.tobytes(), dtype="f4")
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    return tex


def upload_r32f(ctx, data: np.ndarray, bitdepth: int):
    """上传单通道 r32f 纹理（标量图数据语义通道）。"""
    denom = 65535.0 if bitdepth == 16 else 255.0
    r = data[..., 0].astype(np.float32) / denom
    tex = ctx.texture((r.shape[1], r.shape[0]), 1, r.tobytes(), dtype="f4")
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    return tex
