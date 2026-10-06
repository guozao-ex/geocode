"""
GEE 侧：计算图构建 + 资产发现。

职责边界：
    本模块负责 spec → ee 对象。**只描述计算，不物化。**
    物化交给三个出口（emit_array / emit_file / emit_map），
    它们共享本模块产出的 ee 对象和 spec，从而保证三者对齐。

设计要点：
1. GeoJSON dict → ee.Geometry 的转换只在这里发生一次。
2. build_image() 是纯函数：同 spec 必然产出同图（不含随机性）。
3. 常见数据集的波段约定放在 DEFAULT_ASSETS —— 让 spec.defaults() 能推导，
   省掉 agent 每次查文档。这是 GeoCode 用 skill 文件做的事，这里做进代码。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import geoenv
from .spec import ArtifactSpec, SpecError, _iso_to_millis, _parse_iso_date, time_periods

# ---------------------------------------------------------------------------
# 常见数据集约定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssetPreset:
    """一个 GEE 数据集的常用约定。"""
    asset: str
    label: str
    scale: float                  # 原生分辨率（米）
    bands: tuple[str, ...]        # 常用反射率/科学波段
    dtype: str = "float32"
    nodata: float | int | None = None
    rgb: tuple[str, str, str] | None = None   # 真彩色组合
    index_expr: str | None = None             # 常用指数的表达（占位说明用）
    # 云掩膜方案：
    #   "scl"      —— Sentinel-2 场景分类波段（SR 数据的标准做法）
    #   "qa_pixel" —— Landsat Collection 2 的 QA_PIXEL 位标志
    #   None       —— 该数据集无云掩膜
    cloud_mask: str | None = None
    # 反射率缩放：DN → 反射率要乘的系数。None 表示数据已是物理量。
    reflectance_scale: float | None = None


DEFAULT_ASSETS: dict[str, AssetPreset] = {
    "COPERNICUS/S2_SR_HARMONIZED": AssetPreset(
        "COPERNICUS/S2_SR_HARMONIZED", "Sentinel-2 地表反射率（Harmonized）",
        scale=10, bands=("B2", "B3", "B4", "B8", "B11", "B12"),
        dtype="uint16", rgb=("B4", "B3", "B2"),
        cloud_mask="scl", reflectance_scale=0.0001,
    ),
    "COPERNICUS/S2_HARMONIZED": AssetPreset(
        "COPERNICUS/S2_HARMONIZED", "Sentinel-2 大气顶反射率（Harmonized）",
        scale=10, bands=("B2", "B3", "B4", "B8", "B11", "B12"),
        dtype="uint16", rgb=("B4", "B3", "B2"),
    ),
    "LANDSAT/LC09/C02/T1_L2": AssetPreset(
        "LANDSAT/LC09/C02/T1_L2", "Landsat 9 L2 地表反射率",
        scale=30, bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
        dtype="uint16", rgb=("SR_B4", "SR_B3", "SR_B2"),
        cloud_mask="qa_pixel", reflectance_scale=0.0000275,
    ),
    "LANDSAT/LC08/C02/T1_L2": AssetPreset(
        "LANDSAT/LC08/C02/T1_L2", "Landsat 8 L2 地表反射率",
        scale=30, bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
        dtype="uint16", rgb=("SR_B4", "SR_B3", "SR_B2"),
        cloud_mask="qa_pixel", reflectance_scale=0.0000275,
    ),
    "MODIS/061/MOD13Q1": AssetPreset(
        "MODIS/061/MOD13Q1", "MODIS 植被指数 16 天 250m",
        scale=250, bands=("NDVI", "EVI"), dtype="int16",
    ),
    "MODIS/061/MOD11A2": AssetPreset(
        "MODIS/061/MOD11A2", "MODIS 地表温度 8 天 1km",
        scale=1000, bands=("LST_Day_1km", "LST_Night_1km"), dtype="uint16",
    ),
    "COPERNICUS/DEM/GLO30": AssetPreset(
        "COPERNICUS/DEM/GLO30", "Copernicus DEM GLO-30",
        scale=30, bands=("DEM",), dtype="float32",
    ),
    "JRC/GSW1_4/GlobalSurfaceWater": AssetPreset(
        "JRC/GSW1_4/GlobalSurfaceWater", "JRC 全球地表水",
        scale=30, bands=("occurrence", "seasonality", "max_extent"), dtype="uint8",
    ),
}


def preset_for(asset: str) -> AssetPreset | None:
    """查预设。支持带时间戳的 collection 路径（如 .../S2_SR_HARMONIZED/... 不会命中，返回 None）。"""
    return DEFAULT_ASSETS.get(asset)


# ---------------------------------------------------------------------------
# 几何
# ---------------------------------------------------------------------------

def to_ee_geometry(aoi: dict | None):
    """GeoJSON geometry dict -> ee.Geometry。None 原样返回。"""
    if aoi is None:
        return None
    ee, _ = geoenv.init_ee()
    return ee.Geometry(aoi)


# ---------------------------------------------------------------------------
# 资产发现
# ---------------------------------------------------------------------------

def describe_asset(asset_id: str, *, deep: bool = False, max_bands: int = 40) -> dict:
    """
    探测一个 GEE 资产：类型、波段、时间范围、属性。

    ⚠️ 性能约束（实测得出，不是猜的）：
      - `ee.data.getAsset()`                ~1.2s   单次 REST 调用
      - `collection.first().bandNames()`    ~1.2s   取一景的波段
      - `collection.size()`                 **>90s** 全量元数据扫描
      - `reduceColumns(minMax, time_start)` **>90s** 全量元数据扫描
    所以默认路径**绝不**碰后两个；时间范围改从 asset properties 的
    `date_range` 读（getAsset 免费带回来的）。

    deep=True 才做全量扫描，且明确告知代价。
    """
    ee, project = geoenv.init_ee()

    info = ee.data.getAsset(asset_id)
    atype = info.get("type", "")
    props = dict(info.get("properties") or {})

    out: dict[str, Any] = {
        "asset": asset_id,
        "type": atype,
        "id": info.get("id"),
        "name": info.get("name"),
        "size_bytes": _int(info.get("sizeBytes")),
        "update_time": info.get("updateTime"),
        "title": props.get("title") or props.get("system:title"),
        "tags": props.get("tags") or props.get("keywords") or [],
        "properties": {k: v for k, v in props.items()
                       if k not in ("description", "thumb", "system:thumbnail")},
        "description": _strip_html(props.get("description") or "")[:400] or None,
        "preset": None,
        "deep": deep,
    }

    # 免费的时间范围：asset properties 里的 date_range 是毫秒
    dr = props.get("date_range")
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        out["date_range"] = [_ms_to_date(x) for x in dr]
        out["date_range_source"] = "properties"
    else:
        out["date_range"] = None

    preset = preset_for(asset_id)
    if preset:
        out["preset"] = {
            "label": preset.label, "scale": preset.scale,
            "bands": list(preset.bands), "dtype": preset.dtype, "rgb": preset.rgb,
        }

    if atype == "IMAGE":
        out["bands"] = _band_details(ee.Image(asset_id), ee, max_bands)
        out["is_collection"] = False
    elif atype == "IMAGE_COLLECTION":
        col = ee.ImageCollection(asset_id)
        out["is_collection"] = True
        out["bands"] = _band_details(col.first(), ee, max_bands)
        if deep:
            # 全量扫描，分钟级。只在用户明确要求时做。
            out["count"] = _safe(lambda: int(col.size().getInfo()), None)
            out["date_range_full"] = _safe(lambda: _scan_date_range(ee, col), None)
            out["date_range_source"] = "scan"
        else:
            out["count"] = None
            out["count_note"] = (
                "集合大小需要全量元数据扫描（实测 >90s），默认不取。"
                "需要时用 deep=True。"
            )
    else:
        out["is_collection"] = False
        out["bands"] = []
        out["note"] = f"资产类型 {atype!r} 不是影像或影像集合，本工具只处理这两类。"

    return out


def _scan_date_range(ee, col) -> list[str] | None:
    """全量扫描真实时间范围。>90s，仅 deep=True 时调用。"""
    rng = col.reduceColumns(
        reducer=ee.Reducer.minMax(),
        selectors=["system:time_start"],
    ).getInfo()
    lo, hi = rng.get("min"), rng.get("max")
    if lo is None or hi is None:
        return None
    return [_ms_to_date(lo), _ms_to_date(hi)]


def _ms_to_date(ms) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(float(ms) / 1000, _dt.timezone.utc).strftime("%Y-%m-%d")


def _strip_html(s: str) -> str:
    """GEE 的 description 字段是 HTML，去掉标签和多余空白。"""
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _band_details(ee_img, ee, limit: int = 40) -> list[dict]:
    """波段清单 + 类型/单位。bandNames + 属性字典一次取回。"""
    try:
        names = ee_img.bandNames().getInfo() or []
    except Exception:
        return []
    if not names:
        return []
    try:
        props = ee_img.toDictionary().getInfo() or {}
    except Exception:
        props = {}
    out = []
    for b in names[:limit]:
        out.append({
            "name": b,
            "type": props.get(f"{b}_type") or props.get(f"{b}_CLASS") or None,
            "units": props.get(f"{b}_units") or props.get(f"{b}_UNITS") or None,
            "scale": _num(props.get(f"{b}_scale") or props.get(f"{b}_SCALE")),
            "offset": _num(props.get(f"{b}_offset") or props.get(f"{b}_OFFSET")),
        })
    if len(names) > limit:
        out.append({"name": f"...（还有 {len(names) - limit} 个波段未列出）"})
    return out


# ---------------------------------------------------------------------------
# 云掩膜
# ---------------------------------------------------------------------------

# Sentinel-2 SCL 类别
SCL_NODATA, SCL_SATURATED, SCL_SHADOW_DARK, SCL_CLOUD_SHADOW = 0, 1, 2, 3
SCL_VEGETATION, SCL_BARE, SCL_WATER, SCL_UNCLASSIFIED = 4, 5, 6, 7
SCL_CLOUD_MED, SCL_CLOUD_HIGH, SCL_CIRRUS, SCL_SNOW = 8, 9, 10, 11

# 默认保留：植被 / 裸地 / 水 / 未分类。
# 剔除：无数据 / 饱和 / 暗区 / 云阴影 / 中高概率云 / 卷云 / 雪
SCL_KEEP_DEFAULT = (SCL_VEGETATION, SCL_BARE, SCL_WATER, SCL_UNCLASSIFIED)


def mask_clouds(collection, scheme: str, *, keep=SCL_KEEP_DEFAULT):
    """
    给 ImageCollection 逐景加云掩膜。

    ⚠️ 必须在 select() 之前调用 —— 云掩膜依赖 SCL / QA_PIXEL 这些
    不在用户波段列表里的波段。

    不做这一步的后果（实测）：Sentinel-2 直接取中值，云会残留在合成图里，
    看起来像一片青蓝色的"气体"。第一版就是没做，被一眼看出来。
    """

    def _scl(img):
        scl = img.select("SCL")
        m = scl.eq(keep[0])
        for v in keep[1:]:
            m = m.Or(scl.eq(v))
        return img.updateMask(m)

    def _qa_pixel(img):
        # Landsat Collection 2 QA_PIXEL 位：
        #   1=膨胀云 3=云 4=云阴影 —— 这些位为 0 才算干净
        qa = img.select("QA_PIXEL")
        m = (qa.bitwiseAnd(1 << 1).eq(0)
             .And(qa.bitwiseAnd(1 << 3).eq(0))
             .And(qa.bitwiseAnd(1 << 4).eq(0)))
        return img.updateMask(m)

    fn = {"scl": _scl, "qa_pixel": _qa_pixel}.get(scheme)
    return collection.map(fn) if fn else collection


# ---------------------------------------------------------------------------
# 计算图构建
# ---------------------------------------------------------------------------

def build_image(spec: ArtifactSpec):
    """
    spec → ee.Image（单景）或 ee.ImageCollection（时序）。

    这是"唯一真相源"的具体实现：三个出口都调它，拿到同一个 ee 对象。
    纯函数 —— 同 spec 必得同图。
    """
    if not spec.asset:
        raise SpecError(
            "spec.asset 为空，无法构建计算图。\n"
            "  例：asset='COPERNICUS/S2_SR_HARMONIZED'"
        )
    ee, _ = geoenv.init_ee()

    aoi = to_ee_geometry(spec.aoi)
    preset = preset_for(spec.asset)

    # --- 单景 vs 时序 ---
    if spec.is_collection:
        col = ee.ImageCollection(spec.asset)
        if spec.time_range:
            col = col.filterDate(spec.time_range[0], spec.time_range[1])
        if aoi is not None:
            col = col.filterBounds(aoi)

        # ★ 云掩膜必须在 select 之前 —— 它要用的 SCL / QA_PIXEL
        #   通常不在用户请求的波段里
        scheme = preset.cloud_mask if preset else None
        if scheme:
            col = mask_clouds(col, scheme)

        if spec.bands:
            col = col.select(list(spec.bands))

        reducer = spec.reducer or "median"
        img = getattr(col, reducer)()
    else:
        img = ee.Image(spec.asset)
        if spec.bands:
            img = img.select(list(spec.bands))

    # --- 统一为浮点 ---
    #
    # 必须做，否则三个出口会对不上：GEE 的 GEO_TIFF 导出会把整数值的浮点
    # 强制码成 int32，把小数位截掉；而 xee 走 computePixels，保留 float32。
    # 实测差异：GeoTIFF=881.0 vs NetCDF=881.5，出现在 3.9% 的像素上。
    # 显式 toFloat() 让三出口看到同一份数据。
    img = img.toFloat()

    # --- 反射率缩放：DN → 反射率（0-1）---
    # 不做的话输出是 0-10000 量纲的 DN 值，不是物理量。
    if preset and preset.reflectance_scale:
        img = img.multiply(preset.reflectance_scale)

    # --- 裁剪 ---
    if aoi is not None:
        img = img.clip(aoi)

    # --- 保证有默认投影 ---
    #
    # updateMask() + 归约之后，影像可能失去默认投影，导致
    # getDownloadURL / reduceRegion 报 "Image is unbounded"。
    # 显式设一个默认投影把它钉住（不影响已指定 crs+scale 的下载）。
    if preset and preset.cloud_mask:
        try:
            img = img.setDefaultProjection("EPSG:4326", None, 1)
        except Exception:
            pass

    # --- 波段表达式（可选）---
    if spec.band_expr:
        img = img.expression(spec.band_expr)

    # 类型转换**不在这里做**。
    #
    # 这里曾经有过 img.cast({"*": spec.dtype})，是个陷阱：
    #   - '*' 是 EE 的波段通配符，但当前 API 版本把它当正则拒绝
    #     （Invalid regular expression: '*'）
    #   - 错误是**惰性**的 —— cast() 当场不报，到 .compute()/getDownloadURL()
    #     时才爆，所以包一层 try/except 根本抓不住
    #   - 而且 GEE 的 GEO_TIFF 下载本来就会返回 int32，服务端转换收益有限
    #
    # dtype 改由出口层在写盘时施加（rasterio/GDAL 的 dtype 参数），
    # 既可靠又可控。

    return img


def build_collection(spec: ArtifactSpec):
    """需要逐景处理时用（如时序统计、逐景分类）。"""
    ee, _ = geoenv.init_ee()
    col = ee.ImageCollection(spec.asset)
    if spec.time_range:
        col = col.filterDate(spec.time_range[0], spec.time_range[1])
    if spec.aoi:
        col = col.filterBounds(to_ee_geometry(spec.aoi))
    if spec.bands:
        col = col.select(list(spec.bands))
    return col


def build_cube(spec: ArtifactSpec):
    """
    时序 spec → ee.ImageCollection：每期窗口内按单期语义塌缩，期与期堆叠。

    ⚠️ 红线 1：ee 对象只在 source.py 构建 —— 三个出口都消费本函数的返回值，
    不允许出口自己拼 ee 对象。

    每期算子序列与 build_image 的 collection 分支**逐算子一致**（只是作用在
    该期窗口上），保证"立方体第 i 期 ≈ 单期产物"的对齐判据成立：
        filterDate(期) → filterBounds → 云掩膜(select 之前, 红线 4)
        → select → reducer → toFloat → 反射率缩放 → clip
        → setDefaultProjection → band_expr
    期窗口由 spec.time_periods() 纯函数推导（离线可测）。

    每期设置 system:time_start（期起点，xee 的时间坐标来源）与
    system:index（期起点 YYYYMMDD，toBands() 的波段前缀来源）。

    刻意不复用/重构 build_image：单期路径一个字节都不动（红线 3 —— 不含
    时序字段的 spec 的像素输出必须逐位不变），这里的重复是有意的。
    """
    ee, _ = geoenv.init_ee()
    return ee.ImageCollection.fromImages(_cube_period_images(spec))


def build_cube_periods(spec: ArtifactSpec) -> list:
    """
    逐期 ee.Image 列表（与 build_cube 完全同一算子序列）。

    文件出口用它逐期拉取后**本地合并**成单张 N×B 波段 GeoTIFF ——
    实测（2026-10-06）：toBands() 的 9 波段单请求 54.6MB 被 GEE 的
    50MB 请求上限拒绝；逐期请求与单期同限，稳。
    """
    if not spec.is_timeseries:
        raise SpecError(
            "build_cube_periods 需要时序 spec（time_step 或 time_ranges 任一设置）。\n"
            "  单期计算请用 build_image。"
        )
    return _cube_period_images(spec)


def diagnose_cube(spec: ArtifactSpec) -> dict:
    """
    逐期影像数诊断（只拉元数据，不拉像素）。

    供出口层在拉取失败时给出精确错误（哪期是空期 / 各期影像数）；
    成功路径不调用 —— 每期一次元数据查询，N 大时不便宜。
    """
    if not spec.is_timeseries:
        raise SpecError("diagnose_cube 需要时序 spec（time_step 或 time_ranges 任一设置）。")
    if not spec.asset:
        raise SpecError("spec.asset 为空，无法诊断。")
    ee, _ = geoenv.init_ee()
    aoi = to_ee_geometry(spec.aoi)
    periods = time_periods(spec)

    entries = []
    for ps, pe in periods:
        col = ee.ImageCollection(spec.asset).filterDate(ps, pe)
        if aoi is not None:
            col = col.filterBounds(aoi)
        try:
            n = int(col.count().getInfo())
        except Exception:
            n = None   # 诊断自身失败不掩盖原始错误
        entries.append({"period": [ps, pe], "n_scenes": n})
    return {
        "periods": entries,
        "empty": [e["period"] for e in entries if e["n_scenes"] == 0],
    }


def _cube_period_images(spec: ArtifactSpec) -> list:
    """期窗口 → 逐期 ee.Image（红线 1：ee 构建只在这里发生）。"""
    if not spec.asset:
        raise SpecError(
            "spec.asset 为空，无法构建时序计算图。\n"
            "  例：asset='COPERNICUS/S2_SR_HARMONIZED'"
        )
    ee, _ = geoenv.init_ee()

    aoi = to_ee_geometry(spec.aoi)
    preset = preset_for(spec.asset)
    scheme = preset.cloud_mask if preset else None
    reducer = spec.reducer or "median"
    periods = time_periods(spec)

    images = []
    for ps, pe in periods:
        col = ee.ImageCollection(spec.asset).filterDate(ps, pe)
        if aoi is not None:
            col = col.filterBounds(aoi)
        # ★ 云掩膜必须在 select 之前（红线 4）—— SCL / QA_PIXEL 不在用户波段里
        if scheme:
            col = mask_clouds(col, scheme)
        if spec.bands:
            col = col.select(list(spec.bands))
        img = getattr(col, reducer)()

        img = img.toFloat()
        if preset and preset.reflectance_scale:
            img = img.multiply(preset.reflectance_scale)
        if aoi is not None:
            img = img.clip(aoi)
        if scheme:
            try:
                img = img.setDefaultProjection("EPSG:4326", None, 1)
            except Exception:
                pass
        if spec.band_expr:
            img = img.expression(spec.band_expr)

        img = img.set({
            "system:time_start": _iso_to_millis(ps),
            "system:index": _parse_iso_date(ps).strftime("%Y%m%d"),
        })
        images.append(img)

    return images


# ---------------------------------------------------------------------------
# spec 默认值推导
# ---------------------------------------------------------------------------

def defaults_for(asset: str, aoi: dict | None = None, *, prefer_crs: str = "utm") -> dict:
    """
    从一个 asset id 推 spec 的合理默认值。
    有预设走预设（零网络）；没有就查资产（一次网络往返）。
    """
    from . import crs_rules

    preset = preset_for(asset)
    if preset:
        return {
            "asset": asset,
            "scale": preset.scale,
            "bands": list(preset.bands),
            "dtype": "float32",            # 下载用浮点，避免整数缩放的坑
            "crs": crs_rules.suggest_crs(aoi, prefer=prefer_crs),
            "render": {"bands": list(preset.rgb) if preset.rgb else None, "stretch": "stddev"},
            "source": "preset",
        }

    info = describe_asset(asset)
    bands = [b["name"] for b in info.get("bands", []) if not b["name"].startswith("...")]
    scale = None
    for b in info.get("bands", []):
        if b.get("scale"):
            scale = b["scale"]
            break
    return {
        "asset": asset,
        "scale": scale,
        "bands": bands,
        "dtype": "float32",
        "crs": crs_rules.suggest_crs(aoi, prefer=prefer_crs),
        "source": "probed",
        "type": info.get("type"),
        "count": info.get("count"),
        "date_range": info.get("date_range"),
    }


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m gis.source <asset_id>")
        print("预设数据集:")
        for k, v in DEFAULT_ASSETS.items():
            print(f"  {k:34s} {v.scale:>6.0f}m  {v.label}")
        sys.exit(0)

    print(json.dumps(describe_asset(sys.argv[1]), indent=2, ensure_ascii=False))
