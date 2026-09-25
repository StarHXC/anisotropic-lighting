"""资产契约：输入/空间/语义登记与拒收检查。

契约来源：PLAN.md §2.3、§3.5、§8.3。

规则：
- 未知项保持 "unverified"，不得以猜测值冒充已确认值（PLAN §3.5）。
- 被启用功能所需的关键项未确认时，--bake 报错（PLAN §3.5）。
- 语义状态只允许 unverified / verified / art_directed（PLAN §2.2）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["SEMANTIC_STATES", "TextureEntry", "AssetContract"]

SEMANTIC_STATES = ("unverified", "verified", "art_directed")


@dataclass
class TextureEntry:
    """单张输入图的契约登记（PLAN §3.5 最小字段）。"""

    path: str
    width: int
    height: int
    source_bitdepth: int  # 每通道位深
    channels: int
    decoded_dtype: str  # 例如 "uint16" / "uint8"
    sha256: str = ""
    # 语义/空间登记；未知保持 unverified / null，不猜测。
    semantic_state: str = "unverified"  # unverified/verified/art_directed
    channel_semantics: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetContract:
    """整组输入资产的契约（PLAN §3.5）。"""

    textures: dict[str, TextureEntry] = field(default_factory=dict)
    # 位置编码：P = encodedP * positionScale + positionBias（PLAN §3.3）。
    position_scale: list[float] | None = None
    position_bias: list[float] | None = None
    position_space: str = "unverified"  # 局部物体空间登记（PLAN §3.3）
    position_unit: str = "unverified"
    # 法线约定（PLAN §3.3/§3.4：轴交换、绿色通道符号分别登记）。
    normalobj_axis_convention: str = "unverified"
    normalobj_green_sign: int = 0  # +1/-1，0 表示未确认
    uv_v_direction: str = "unverified"  # 图像 Y 翻转/网格 V/绿通道是三个独立问题
    uv_uniqueness_evidence: str = "unverified"
    coverage_source: str = "unverified"
    island_source: str = "none"
    # 采样状态（PLAN §3.4：mip 0、Nearest、Clamp）。
    sampling: dict[str, Any] = field(
        default_factory=lambda: {
            "mip_level": 0,
            "filter": "nearest",
            "address": "clamp",
            "q_origin": "top-left",
        }
    )

    # ------------------------------------------------------------------
    def set_texture(self, entry: TextureEntry) -> None:
        self.textures[Path(entry.path).name] = entry

    def texture(self, name: str) -> TextureEntry | None:
        return self.textures.get(name)

    def validate_for_bake(self) -> list[str]:
        """--bake 前置校验：返回阻断性错误列表（空列表=通过）。

        PLAN §3.5：被启用功能所需的关键项未确认时 --bake 应报错。
        """
        errors: list[str] = []
        if self.position_scale is None or self.position_bias is None:
            errors.append(
                "position scale/bias 未确认（position_scale/position_bias 为 null）；"
                "需上游提供位置归一化契约或由 --probe 定位证据"
            )
        if self.position_space == "unverified":
            errors.append("position_space 未确认；禁止在未决空间直接做点积（PLAN §3.3）")
        if self.normalobj_axis_convention == "unverified":
            errors.append(
                "normalobj_axis_convention 未确认；法线轴向不能只根据文件名判断"
            )
        for name in ("bake_position.png", "bake_normalobj.png", "mask1.png"):
            tex = self.texture(name)
            if tex is None:
                errors.append(f"缺少必需输入 {name}")
        return errors

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self._serialize(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "AssetContract":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        textures = {
            k: TextureEntry(**v) for k, v in data.pop("textures", {}).items()
        }
        obj = cls(**data)
        obj.textures = textures
        return obj

    def _serialize(self) -> dict[str, Any]:
        out = asdict(self)
        out["textures"] = {k: v for k, v in out["textures"].items()}
        return out
