"""
ArtifactSpec —— 三个出口共用的唯一产物契约。

这是整套架构的枢纽。设计要点：

1. **aoi 存 GeoJSON dict，不存 ee.Geometry**
   理由：spec 必须可 JSON 序列化（跨 socket、落盘、给 C# 侧）。
   C# 的 add-in 捕获视图范围时直接产出 GeoJSON，两侧契约一致。
   转成 ee.Geometry 的动作推迟到 source.py 的边界处做一次。

2. **frozen dataclass**
   spec 是契约不是草稿。要改就新建一份 —— 这样"同一份 spec 走三个出口"
   的验收判据才有意义。

3. **三个出口都从同一份 spec 生成**
   emit_array / emit_file / emit_map 各自读同一 spec，
   保证 CRS / 分辨率 / 范围 / 抽样像素值一致。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal

# ★ 处理逻辑版本。
#
# 指纹 = 决定输出的**全部因素**的哈希。它既包含 spec 字段，也必须包含
# 处理逻辑的版本 —— 否则我们改了算法（例如加了云掩膜），同一个 spec
# 本应产出不同结果，缓存却会命中旧产物。
#
# 实测教训：加了云掩膜 + 反射率缩放后重跑，产物数值纹丝不动 ——
# 因为 _ensure_raster 看到同名文件在，直接复用了旧的。
#
# 规则：任何会改变像素输出的代码改动，都必须 +1。
PROCESSING_VERSION = 2   # 2 = 加云掩膜(SCL/QA_PIXEL) + 反射率缩放

Exit = Literal["array", "file", "map"]
EXITS: tuple[Exit, ...] = ("array", "file", "map")

# 出口对 spec 的额外要求
_EXIT_REQUIRES: dict[str, tuple[str, ...]] = {
    "array": ("crs", "scale", "aoi"),
    "file": ("crs", "scale", "aoi"),
    "map": ("aoi",),          # 地图只要范围；crs/scale 可缺省
}


class SpecError(ValueError):
    """spec 不合法。消息是给人和 agent 看的，要说清怎么修。"""


# ---------------------------------------------------------------------------
# 渲染规格（只被 map 出口消费）
# ---------------------------------------------------------------------------

Stretch = Literal["none", "minmax", "stddev", "percentile"]


@dataclass(frozen=True)
class RenderSpec:
    """可视化的全部自由度。与数据规格解耦 —— 同一份数据可出多张图。"""

    bands: tuple[str, ...] | None = None      # RGB 波段组合，如 ("B4","B3","B2")
    stretch: Stretch = "stddev"
    percentile: tuple[float, float] = (2.0, 98.0)
    palette: tuple[str, ...] | None = None    # 单波段伪彩，十六进制色值序列
    vmin: float | None = None
    vmax: float | None = None
    nodata_color: str | None = None

    def to_dict(self) -> dict:
        d = {
            "bands": list(self.bands) if self.bands else None,
            "stretch": self.stretch,
            "percentile": list(self.percentile),
            "palette": list(self.palette) if self.palette else None,
            "vmin": self.vmin,
            "vmax": self.vmax,
            "nodata_color": self.nodata_color,
        }
        return {k: v for k, v in d.items() if v is not None}

    @staticmethod
    def from_dict(d: dict | None) -> "RenderSpec | None":
        if not d:
            return None
        kw: dict[str, Any] = {}
        if d.get("bands"):
            kw["bands"] = tuple(d["bands"])
        if "stretch" in d:
            kw["stretch"] = d["stretch"]
        if d.get("percentile"):
            kw["percentile"] = tuple(d["percentile"])
        if d.get("palette"):
            kw["palette"] = tuple(d["palette"])
        for k in ("vmin", "vmax", "nodata_color"):
            if d.get(k) is not None:
                kw[k] = d[k]
        return RenderSpec(**kw)


# ---------------------------------------------------------------------------
# 产 物 规 格
# ---------------------------------------------------------------------------

DTYPES = ("uint8", "int16", "uint16", "int32", "float32", "float64")

REDUCERS = ("median", "mean", "min", "max", "mosaic", "first", "mode", "sum")


@dataclass(frozen=True)
class ArtifactSpec:
    """
    一次 GEE 计算的完整描述，也是三个出口的唯一输入。

    字段分四组：标识 / 源 / 空间 / 数据 / 时间 / 渲染。
    空值一律用 None 而不是哨兵值 —— JSON 往返后能原样恢复。
    """

    id: str

    # --- 源 ---
    asset: str | None = None                 # GEE asset id，如 "COPERNICUS/S2_SR_HARMONIZED"
    band_expr: str | None = None             # 可选：表达式，如 "B8-B4/(B8+B4)"

    # --- 空间 ---
    crs: str | None = None                   # "EPSG:4326" / "EPSG:32650"
    scale: float | None = None               # 米
    aoi: dict | None = None                  # GeoJSON geometry dict

    # --- 数据 ---
    dtype: str = "float32"
    nodata: float | int | None = None
    bands: tuple[str, ...] = ()

    # --- 时间 ---
    time_range: tuple[str, str] | None = None   # (ISO 起, ISO 止)
    reducer: str | None = None

    # --- 渲染 ---
    render: RenderSpec | None = None

    # --- 元信息（不参与计算，仅供追踪）---
    note: str = ""
    tags: tuple[str, ...] = ()

    # ---------------------------------------------------------------- 校验

    def validate(self, exit: Exit | None = None) -> None:
        """
        失败就抛 SpecError，消息里必须写清楚怎么修 —— 这是给 agent 看的。
        传 exit 时额外检查该出口的要求。
        """
        if not self.id or not self.id.strip():
            raise SpecError("spec.id 不能为空。给个短标识，如 's2_median_2024'。")

        if self.dtype not in DTYPES:
            raise SpecError(f"dtype={self.dtype!r} 不支持。可选：{', '.join(DTYPES)}")

        if self.scale is not None and self.scale <= 0:
            raise SpecError(f"scale 必须是正数（米），收到 {self.scale}。")

        if self.time_range is not None:
            if len(self.time_range) != 2:
                raise SpecError("time_range 必须是长度为 2 的 (起, 止)。")
            a, b = self.time_range
            if a > b:
                raise SpecError(f"time_range 起点晚于终点：{a} > {b}")

        if self.reducer is not None and self.reducer not in REDUCERS:
            raise SpecError(
                f"reducer={self.reducer!r} 不认识。可选：{', '.join(REDUCERS)}"
            )

        if self.aoi is not None:
            if not isinstance(self.aoi, dict) or "type" not in self.aoi:
                raise SpecError(
                    "aoi 必须是 GeoJSON geometry dict（含 'type' 键），"
                    "例如 {'type':'Polygon','coordinates':[[[...]]]}。"
                )

        if exit is not None:
            if exit not in EXITS:
                raise SpecError(f"exit 必须是 {EXITS} 之一，收到 {exit!r}")
            missing = [f for f in _EXIT_REQUIRES[exit] if getattr(self, f) in (None, "")]
            if missing:
                raise SpecError(
                    f"出口 {exit!r} 需要这些字段但缺失：{', '.join(missing)}\n"
                    f"  提示：可以用 spec.defaults(asset) 推导默认值。"
                )

    @property
    def is_collection(self) -> bool:
        """有 time_range 或 reducer 就按 ImageCollection 处理。"""
        return self.time_range is not None or self.reducer is not None

    # ---------------------------------------------------------------- 指纹

    def fingerprint(self) -> str:
        """
        内容指纹：忽略 id / note / tags / render（不影响像素值），
        只对决定输出的字段取哈希。

        用途：验证"同一 spec 的三个出口产物一致"时，
        三个出口报出来的 fingerprint 必须相同。
        """
        payload = {
            "_processing_version": PROCESSING_VERSION,
            "asset": self.asset,
            "band_expr": self.band_expr,
            "crs": self.crs,
            "scale": self.scale,
            "aoi": self.aoi,
            "dtype": self.dtype,
            "bands": list(self.bands),
            "time_range": list(self.time_range) if self.time_range else None,
            "reducer": self.reducer,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # ---------------------------------------------------------------- 序列化

    def to_dict(self, *, include_meta: bool = True) -> dict:
        d = {
            "id": self.id,
            "asset": self.asset,
            "band_expr": self.band_expr,
            "crs": self.crs,
            "scale": self.scale,
            "aoi": self.aoi,
            "dtype": self.dtype,
            "nodata": self.nodata,
            "bands": list(self.bands),
            "time_range": list(self.time_range) if self.time_range else None,
            "reducer": self.reducer,
            "render": self.render.to_dict() if self.render else None,
        }
        if include_meta:
            d["note"] = self.note
            d["tags"] = list(self.tags)
            d["fingerprint"] = self.fingerprint()
        return d

    @staticmethod
    def from_dict(d: dict) -> "ArtifactSpec":
        tr = d.get("time_range")
        return ArtifactSpec(
            id=d.get("id") or "unnamed",
            asset=d.get("asset"),
            band_expr=d.get("band_expr"),
            crs=d.get("crs"),
            scale=d.get("scale"),
            aoi=d.get("aoi"),
            dtype=d.get("dtype", "float32"),
            nodata=d.get("nodata"),
            bands=tuple(d.get("bands") or ()),
            time_range=tuple(tr) if tr else None,
            reducer=d.get("reducer"),
            render=RenderSpec.from_dict(d.get("render")),
            note=d.get("note", ""),
            tags=tuple(d.get("tags") or ()),
        )

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def from_json(s: str) -> "ArtifactSpec":
        return ArtifactSpec.from_dict(json.loads(s))

    def with_(self, **changes) -> "ArtifactSpec":
        """不可变更新。spec = spec.with_(scale=20)"""
        return replace(self, **changes)

    @property
    def slug(self) -> str:
        """安全文件名。"""
        keep = [c if (c.isalnum() or c in "-_") else "-" for c in self.id]
        s = "".join(keep).strip("-") or "unnamed"
        return s


# ---------------------------------------------------------------------------
# 便捷构造
# ---------------------------------------------------------------------------

def bbox_to_geojson(west: float, south: float, east: float, north: float) -> dict:
    """(西, 南, 东, 北) 经纬度 -> GeoJSON Polygon。"""
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south],
        ]],
    }


def aoi_bbox(aoi: dict | None) -> tuple[float, float, float, float] | None:
    """GeoJSON geometry -> (西, 南, 东, 北)。只做平面扫掠，够用且不依赖 shapely。"""
    if not aoi:
        return None

    def walk(node):
        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
                yield float(node[0]), float(node[1])
            else:
                for child in node:
                    yield from walk(child)
        elif isinstance(node, dict):
            yield from walk(node.get("coordinates", []))

    xs, ys = [], []
    for x, y in walk(aoi):
        xs.append(x)
        ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
