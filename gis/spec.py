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

import calendar
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
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
# 制图规格（出版级布局要素，被 qgis / arcpy 两个 bridge 共同消费）
# ---------------------------------------------------------------------------

PAGE_SIZES = ("A4", "A3", "A2", "A1", "LETTER", "TABLOID")
ORIENTATIONS = ("landscape", "portrait")
LAYOUT_FORMATS = ("pdf", "png", "jpg")


@dataclass(frozen=True)
class LayoutSpec:
    """
    出版级制图要素契约 —— 与 RenderSpec 对称，呈现层规格。

    qgis_bridge 与 arcpy_bridge 共同消费，不允许各自私有的布局参数。
    呈现层字段**不参与指纹**（不影响像素值，见 tests/unit 的指纹守卫）。
    """

    title: str | None = None          # 图名；None → 用 spec.id
    frame: bool = True                # 图廓（地图外框）
    scalebar: bool = True             # 比例尺
    scalebar_length_cm: float = 4.0   # 比例尺目标条长（cm，页面单位）
    north_arrow: bool = True          # 指北针
    legend: bool = True               # 图例
    graticule: bool = False           # 经纬网
    dpi: int = 300
    page_size: str = "A4"
    orientation: str = "landscape"
    formats: tuple[str, ...] = ("pdf", "png")

    def __post_init__(self) -> None:
        if self.page_size not in PAGE_SIZES:
            raise SpecError(
                f"page_size={self.page_size!r} 不支持。可选：{', '.join(PAGE_SIZES)}"
            )
        if self.orientation not in ORIENTATIONS:
            raise SpecError(
                f"orientation={self.orientation!r} 不支持。可选：{', '.join(ORIENTATIONS)}"
            )
        if self.dpi <= 0 or self.dpi > 1200:
            raise SpecError(f"dpi 应在 1-1200 之间，收到 {self.dpi}。")
        if not (0 < self.scalebar_length_cm <= 30):
            raise SpecError(
                f"scalebar_length_cm 应在 0-30（不含 0）之间，收到 {self.scalebar_length_cm}。"
            )
        bad = [f for f in self.formats if f not in LAYOUT_FORMATS]
        if bad:
            raise SpecError(
                f"formats 含不支持的值 {bad}。可选：{', '.join(LAYOUT_FORMATS)}"
            )

    def to_dict(self) -> dict:
        d = {
            "title": self.title,
            "frame": self.frame,
            "scalebar": self.scalebar,
            "scalebar_length_cm": self.scalebar_length_cm,
            "north_arrow": self.north_arrow,
            "legend": self.legend,
            "graticule": self.graticule,
            "dpi": self.dpi,
            "page_size": self.page_size,
            "orientation": self.orientation,
            "formats": list(self.formats),
        }
        return {k: v for k, v in d.items() if v is not None}

    @staticmethod
    def from_dict(d: dict | None) -> "LayoutSpec | None":
        if not d:
            return None
        kw: dict[str, Any] = {}
        if d.get("title"):
            kw["title"] = d["title"]
        for k in ("frame", "scalebar", "north_arrow", "legend", "graticule"):
            if k in d:
                kw[k] = bool(d[k])
        if "dpi" in d:
            kw["dpi"] = int(d["dpi"])
        if "scalebar_length_cm" in d:
            kw["scalebar_length_cm"] = float(d["scalebar_length_cm"])
        for k in ("page_size", "orientation"):
            if d.get(k):
                kw[k] = d[k]
        if d.get("formats"):
            kw["formats"] = tuple(d["formats"])
        return LayoutSpec(**kw)


# ---------------------------------------------------------------------------
# 产 物 规 格
# ---------------------------------------------------------------------------

DTYPES = ("uint8", "int16", "uint16", "int32", "float32", "float64")

REDUCERS = ("median", "mean", "min", "max", "mosaic", "first", "mode", "sum")

# ---------------------------------------------------------------------------
# 时序模式（C3：多时相堆栈）
# ---------------------------------------------------------------------------
#
# 两种互斥的表达方式（2026-10-06 Shape 裁决）：
#   time_step   节奏切片：以 time_range[0] 为起点按步长切出连续等宽窗口，
#               N 由（起止÷步长）确定性推导；每期内 reducer 塌缩。
#   time_ranges 显式多段：窗口逐条给出，允许不等长（如生长季），N = 条目数。
#
# 期窗口推导是纯函数（time_periods），离线可测；serve 侧消费见 source.build_cube。

TIME_STEPS = ("day", "week", "month", "year")

# 期数上限：每期 = 一次独立的像素拉取（xee 逐期 computePixels）， runaway 的
# N 会拖垮配额与时长。超出报错并提示缩小范围 / 加大步长。
MAX_TIME_PERIODS = 120


def _parse_iso_date(s: str) -> date:
    """'2024-06-01' 或 ISO datetime 字符串 → date。"""
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        return datetime.fromisoformat(str(s)).date()


def _iso_to_millis(s: str) -> int:
    """ISO 日期(时间)字符串 → UTC 毫秒（GEE system:time_start 的量纲）。"""
    txt = str(s)
    try:
        d = date.fromisoformat(txt)
        dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _add_step(d: date, step: str, k: int = 1) -> date:
    """日期加 k 个步长。月/年用年月加法，日超过当月天数时钳制到月末。"""
    if step == "day":
        return d + timedelta(days=k)
    if step == "week":
        return d + timedelta(weeks=k)
    months = k * (12 if step == "year" else 1)
    total = d.month - 1 + months
    y = d.year + total // 12
    m = total % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def time_periods(spec: "ArtifactSpec") -> tuple[tuple[str, str], ...]:
    """
    时序 spec → 期窗口序列 [(起, 止), ...]，[起, 止) 语义（GEE filterDate 同款）。

    纯函数，只做字符串/日期运算 —— 期窗口决定逐期计算图，也决定指纹以外的
    验收对齐（立方体第 i 期 ↔ 单期 spec 的 time_range=第 i 期窗口）。
    """
    if spec.time_ranges:
        windows = tuple((str(a), str(b)) for a, b in spec.time_ranges)
        if len(windows) > MAX_TIME_PERIODS:
            raise SpecError(
                f"期数 {len(windows)} 超过上限 {MAX_TIME_PERIODS}。\n"
                f"  每期都是一次独立的像素拉取；请合并窗口或拆分任务。"
            )
        return windows

    if spec.time_step:
        if not spec.time_range:
            raise SpecError(
                "time_step 模式需要 time_range（起, 止）作为切片范围。"
            )
        t0 = _parse_iso_date(spec.time_range[0])
        t1 = _parse_iso_date(spec.time_range[1])
        starts: list[date] = []
        s = t0
        while s < t1:
            starts.append(s)
            s = _add_step(s, spec.time_step)
        if not starts:
            raise SpecError(
                f"时序模式推出的期数为 0（{t0} ~ {t1}，步长 {spec.time_step}）。\n"
                "  起止相同没有可切分的期；请给出真实的范围。"
            )
        if len(starts) > MAX_TIME_PERIODS:
            raise SpecError(
                f"期数 {len(starts)} 超过上限 {MAX_TIME_PERIODS}。\n"
                f"  每期都是一次独立的像素拉取；请缩小 time_range 或加大 time_step。"
            )
        windows: list[tuple[str, str]] = []
        for i, st in enumerate(starts):
            en = starts[i + 1] if i + 1 < len(starts) else _add_step(starts[-1], spec.time_step)
            windows.append((st.isoformat(), en.isoformat()))
        return tuple(windows)

    raise SpecError(
        "spec 未声明时序（time_step / time_ranges 均缺省），没有期窗口可推导。\n"
        "  单期计算请走 build_image；时序模式请设置 time_step 或 time_ranges。"
    )


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
    # --- 时序（C3：多时相堆栈；两字段互斥，任一设置即进入时序模式）---
    time_step: str | None = None                # "day"/"week"/"month"/"year"
    time_ranges: tuple[tuple[str, str], ...] | None = None   # 显式多段窗口

    # --- 渲染 ---
    render: RenderSpec | None = None

    # --- 制图（呈现层；不参与指纹）---
    layout: LayoutSpec | None = None

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

        # --- 时序字段（C3）---
        if self.time_step is not None and self.time_ranges is not None:
            raise SpecError(
                "time_step 与 time_ranges 互斥：节奏切片和多段显式窗口二选一。\n"
                "  连续等宽堆栈用 time_step；不等长窗口（如生长季）用 time_ranges。"
            )
        if self.is_timeseries:
            if self.time_step is not None:
                if self.time_step not in TIME_STEPS:
                    raise SpecError(
                        f"time_step={self.time_step!r} 不支持。可选：{', '.join(TIME_STEPS)}"
                    )
                if self.time_range is None:
                    raise SpecError(
                        "time_step 模式需要 time_range（起, 止）作为切片范围。\n"
                        "  例：time_range=('2024-01-01','2024-12-31'), time_step='month'"
                    )
            if self.time_ranges is not None:
                if not isinstance(self.time_ranges, (tuple, list)) or not self.time_ranges:
                    raise SpecError(
                        "time_ranges 必须是非空的 (起, 止) 窗口序列，"
                        "如 (('2024-01-01','2024-03-31'), ('2024-06-01','2024-09-30'))。"
                    )
                for i, p in enumerate(self.time_ranges):
                    if not isinstance(p, (tuple, list)) or len(p) != 2:
                        raise SpecError(
                            f"time_ranges[{i}] 必须是 (起, 止) 二元组，收到 {p!r}。"
                        )
                    if str(p[0]) > str(p[1]):
                        raise SpecError(
                            f"time_ranges[{i}] 起点晚于终点：{p[0]} > {p[1]}。"
                        )
                if len(self.time_ranges) > MAX_TIME_PERIODS:
                    raise SpecError(
                        f"time_ranges 期数 {len(self.time_ranges)} 超过上限 {MAX_TIME_PERIODS}。"
                    )
            # 期窗口推导也在校验期跑一遍：零期数、N 上限这类"推导才能发现"的
            # 问题在 spec_set 时就报出来，而不是等到构建计算图才炸。
            time_periods(self)

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
    def is_timeseries(self) -> bool:
        """时序模式：time_step 或 time_ranges 任一设置（两字段互斥，见 validate）。"""
        return self.time_step is not None or self.time_ranges is not None

    @property
    def is_collection(self) -> bool:
        """有 time_range / reducer / 时序字段就按 ImageCollection 处理。"""
        return (
            self.time_range is not None
            or self.reducer is not None
            or self.is_timeseries
        )

    # ---------------------------------------------------------------- 指纹

    def fingerprint(self) -> str:
        """
        内容指纹：忽略 id / note / tags / render / layout（不影响像素值），
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
        # 时序字段（C3，红线 8：决定每期窗口 → 决定像素输出 → 入白名单）。
        # ⚠️ 缺省时整个键必须缺席（而不是写 None）——payload 逐键与旧版完全相同，
        #    旧 spec 的指纹才不变（A5 守卫 / 金指纹 c9243efd40318c85 锚定）。
        if self.time_step is not None:
            payload["time_step"] = self.time_step
        if self.time_ranges is not None:
            payload["time_ranges"] = [list(p) for p in self.time_ranges]
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
            "time_step": self.time_step,
            "time_ranges": [list(p) for p in self.time_ranges] if self.time_ranges else None,
            "render": self.render.to_dict() if self.render else None,
            "layout": self.layout.to_dict() if self.layout else None,
        }
        if include_meta:
            d["note"] = self.note
            d["tags"] = list(self.tags)
            d["fingerprint"] = self.fingerprint()
        return d

    @staticmethod
    def from_dict(d: dict) -> "ArtifactSpec":
        tr = d.get("time_range")
        trs = d.get("time_ranges")
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
            time_step=d.get("time_step"),
            time_ranges=tuple((str(p[0]), str(p[1])) for p in trs) if trs else None,
            render=RenderSpec.from_dict(d.get("render")),
            layout=LayoutSpec.from_dict(d.get("layout")),
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
