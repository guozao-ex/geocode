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
from .spec import ArtifactSpec, SpecError


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
    #
    # ★ SAR 豁免（C4 裁决）：红线 4「云掩膜必须在 select() 之前」约束的是**有掩膜时
    #   的施加次序**。SAR 数据集（S1）不存在云掩膜（微波穿透云层），预设取 None
    #   ⇒ 计算图里没有掩膜步骤 ⇒ 该红线在此路径上无从适用。豁免仅限此类数据集。
    cloud_mask: str | None = None
    # 反射率缩放：DN → 反射率要乘的系数。None 表示数据已是物理量。
    reflectance_scale: float | None = None

    # --- C4 新增：全部带默认值，缺省时既有预设的行为与像素输出逐字节不变 ---

    # 合成预设：asset 是本地键（不是 GEE 资产），真正要合并的集合列在这里。
    merge_assets: tuple[str, ...] | None = None
    # 逐波段 (scale, offset)：在 toFloat() 之后、clip 之前施加。与 reflectance_scale
    # 是同一类东西（都改像素值），预设二选一：
    #   reflectance_scale —— 单一乘系数（历史机制，既有预设在用）
    #   band_transforms   —— 逐波段 (乘, 加)，用于单位换算与带 offset 的辐射缩放
    band_transforms: tuple[tuple[str, float, float], ...] | None = None
    # 可能以**波段**形式出现的极化名（S1：VV/VH/HH/HV）。集合按 spec.bands 里实际
    # 请求的极化过滤 —— 不过滤时 select 会静默产出空结果（实测）。
    polarizations: tuple[str, ...] | None = None
    # 需要按 GEE 属性等值过滤的成像模式（S1：IW 干涉宽幅）。
    instrument_mode: str | None = None

    # 分类栅格语义：类码而非物理量。reducer 用 mode、不做数值缩放与拉伸。
    categorical: bool = False
    class_values: tuple[float, ...] | None = None     # 类码（WorldCover 的 10..100）
    class_palette: tuple[str, ...] | None = None      # 类色（十六进制，无 #），与类码等长
    class_names: tuple[str, ...] | None = None        # 类名（图例用），与类码等长

    # 集合模式下 spec.reducer 缺省时的归约算子（WorldCover=mode、ERA5-Land=mean）。
    default_reducer: str | None = None
    # 该资产是 ImageCollection：单景分支给出可读错误，而不是 GEE 的
    # "Asset ... is not an Image"（实测 GLO30 / WorldCover / LC08 都会撞上）。
    collection_only: bool = False
    # 集合内仅 1 景：整体塌缩安全且确定（WorldCover v200），单景分支可走 mosaic()。
    single_image_asset: bool = False

    def __post_init__(self) -> None:
        """契约自检。既有 8 条预设不触发其中任何一条。"""
        if self.categorical:
            if not self.class_values or not self.class_palette:
                raise ValueError(
                    f"{self.asset}: categorical=True 必须同时给出 class_values 与 class_palette。"
                )
            if len(self.class_values) != len(self.class_palette):
                raise ValueError(
                    f"{self.asset}: class_values（{len(self.class_values)}）与 "
                    f"class_palette（{len(self.class_palette)}）长度不等。"
                )
            if self.class_names and len(self.class_names) != len(self.class_values):
                raise ValueError(f"{self.asset}: class_names 与 class_values 长度不等。")
        if self.merge_assets and not self.collection_only:
            raise ValueError(f"{self.asset}: 合成预设必须声明 collection_only=True。")
        if self.single_image_asset and not self.collection_only:
            raise ValueError(f"{self.asset}: single_image_asset 蕴含 collection_only。")


# ESA WorldCover v200 的类表（2026-10-06 取自 GEE 资产属性 Map_class_values /
# Map_class_palette / Map_class_names，与官方目录 Class Table 一致）。
WORLDCOVER_CLASSES: tuple[tuple[int, str, str], ...] = (
    (10, "006400", "Tree cover"),
    (20, "ffbb22", "Shrubland"),
    (30, "ffff4c", "Grassland"),
    (40, "f096ff", "Cropland"),
    (50, "fa0000", "Built-up"),
    (60, "b4b4b4", "Bare / sparse vegetation"),
    (70, "f0f0f0", "Snow and ice"),
    (80, "0064c8", "Permanent water bodies"),
    (90, "0096a0", "Herbaceous wetland"),
    (95, "00cf75", "Mangroves"),
    (100, "fae6a0", "Moss and lichen"),
)

# Landsat C02 L2 光学 SR 波段缩放（官方目录 Bands 表：Scale 2.75e-05 / Offset -0.2）。
# 既有 LC08/LC09 与合并预设共用同一张表 —— 2026-10-06 修正了既有两条缺 offset 的问题
# （原先只乘不加减，反射率偏高约 +0.2），该修正触发 PROCESSING_VERSION 2 → 3。
LANDSAT_SR_SCALE, LANDSAT_SR_OFFSET = 0.0000275, -0.2
LANDSAT_SR_BANDS: tuple[str, ...] = ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7")
LANDSAT_SR_TRANSFORMS: tuple[tuple[str, float, float], ...] = tuple(
    (b, LANDSAT_SR_SCALE, LANDSAT_SR_OFFSET) for b in LANDSAT_SR_BANDS
)


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
    # ★ 2026-10-06 修正：这两条预设原先只做 reflectance_scale=0.0000275，缺官方
    #   offset -0.2，输出反射率偏高约 +0.2（实测 SR_B4：0.302 vs 正确的 0.102）。
    #   改用与合并预设同一张 band_transforms 表（DN*2.75e-05 - 0.2）。
    #   该修正改变既有像素输出 ⇒ PROCESSING_VERSION 2 → 3（红线 3）。
    "LANDSAT/LC09/C02/T1_L2": AssetPreset(
        "LANDSAT/LC09/C02/T1_L2", "Landsat 9 L2 地表反射率",
        scale=30, bands=LANDSAT_SR_BANDS,
        dtype="uint16", rgb=("SR_B4", "SR_B3", "SR_B2"),
        cloud_mask="qa_pixel", band_transforms=LANDSAT_SR_TRANSFORMS,
    ),
    "LANDSAT/LC08/C02/T1_L2": AssetPreset(
        "LANDSAT/LC08/C02/T1_L2", "Landsat 8 L2 地表反射率",
        scale=30, bands=LANDSAT_SR_BANDS,
        dtype="uint16", rgb=("SR_B4", "SR_B3", "SR_B2"),
        cloud_mask="qa_pixel", band_transforms=LANDSAT_SR_TRANSFORMS,
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

    # --- C4 新增（p2-presets）-------------------------------------------------
    # Sentinel-1 GRD（SAR）。GEE 目录已把值转成 dB，预处理链含 S1TBX 的
    # thermal noise removal + radiometric calibration + terrain correction，
    # 即**已地形校正**——本模块不再重复做地形校正（红线 6：不给自己加无谓的步骤）。
    # 数值口径由顺手的减法给出：dB 与 10*log10(线性) 互转，线性版供比值/统计用。
    # 极化组合随景变化（VV / HH / VV+VH / HH+HV），故必须按请求波段过滤，
    # 否则 select 会静默产出空结果（实测：北京 2024-06~09 全为 VV+VH）。
    "COPERNICUS/S1_GRD": AssetPreset(
        "COPERNICUS/S1_GRD", "Sentinel-1 GRD 后向散射（dB，IW）",
        scale=10, bands=("VV", "VH"), dtype="float32",
        rgb=("VV", "VH", "VV"),           # 双极化假彩色（R=VV, G=VH, B=VV）
        polarizations=("VV", "VH", "HH", "HV"), instrument_mode="IW",
        collection_only=True,
    ),
    "COPERNICUS/S1_GRD_FLOAT": AssetPreset(
        "COPERNICUS/S1_GRD_FLOAT", "Sentinel-1 GRD 后向散射（线性，IW）",
        scale=10, bands=("VV", "VH"), dtype="float32",
        rgb=("VV", "VH", "VV"),
        polarizations=("VV", "VH", "HH", "HV"), instrument_mode="IW",
        collection_only=True,
    ),
    # Landsat 8+9 合并（本地合成键，不是 GEE 资产）：LC08 与 LC09 的 C02 L2
    # 缩放系数一致，合并后重访由 16 天提到约 8 天。三条 Landsat 预设（L8 / L9 / 合并）
    # 现在共用同一张 LANDSAT_SR_TRANSFORMS，口径一致。
    "LANDSAT/LC08+LC09/C02/T1_L2": AssetPreset(
        "LANDSAT/LC08+LC09/C02/T1_L2", "Landsat 8+9 Collection 2 L2 地表反射率（合并）",
        scale=30, bands=LANDSAT_SR_BANDS,
        dtype="uint16", rgb=("SR_B4", "SR_B3", "SR_B2"),
        cloud_mask="qa_pixel",
        merge_assets=("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"),
        band_transforms=LANDSAT_SR_TRANSFORMS,
        collection_only=True,
    ),
    # ERA5-Land 逐日聚合（9km，陆地）。单位换算在计算图里做（改像素值 ⇒ 属于 source）：
    # 温度 K→°C、降水 m→mm；surface_pressure 等其余波段保持原生 Pa。
    # 逐日档而非逐时档：一个月 30 景 vs 720 景（实测），聚合口径也是气候统计的常用口径。
    "ECMWF/ERA5_LAND/DAILY_AGGR": AssetPreset(
        "ECMWF/ERA5_LAND/DAILY_AGGR", "ERA5-Land 逐日聚合（9km，陆地；温度 °C / 降水 mm）",
        scale=11132,
        bands=("temperature_2m", "total_precipitation_sum",
               "u_component_of_wind_10m", "v_component_of_wind_10m"),
        dtype="float32",
        band_transforms=(("temperature_2m", 1.0, -273.15),
                         ("total_precipitation_sum", 1000.0, 0.0)),
        default_reducer="mean",
        collection_only=True,
    ),
    # ESA WorldCover v200（2021，10m，11 类）。分类栅格：reducer=mode 保持精确类码
    # （mean 会产出 15 这类不存在的类），不做辐射缩放，dtype=uint8。
    # 类值与类色是资产自带属性（WorldCover v200 集合只有 1 景 ⇒ 整体塌缩安全）。
    "ESA/WorldCover/v200": AssetPreset(
        "ESA/WorldCover/v200", "ESA WorldCover v200 土地覆盖（2021，10m，11 类）",
        scale=10, bands=("Map",), dtype="uint8",
        categorical=True,
        class_values=tuple(v for v, _c, _n in WORLDCOVER_CLASSES),
        class_palette=tuple(c for _v, c, _n in WORLDCOVER_CLASSES),
        class_names=tuple(n for _v, _c, n in WORLDCOVER_CLASSES),
        default_reducer="mode",
        collection_only=True, single_image_asset=True,
    ),
}


def preset_for(asset: str) -> AssetPreset | None:
    """查预设。支持带时间戳的 collection 路径（如 .../S2_SR_HARMONIZED/... 不会命中，返回 None）。"""
    return DEFAULT_ASSETS.get(asset)


def _preset_summary(preset: AssetPreset) -> dict:
    """预设 → 给人/agent 看的摘要（describe_asset 与 TUI 消费）。既有预设的键集不变。"""
    d = {
        "label": preset.label, "scale": preset.scale,
        "bands": list(preset.bands), "dtype": preset.dtype, "rgb": preset.rgb,
    }
    if preset.merge_assets:
        d["merge_assets"] = list(preset.merge_assets)
    if preset.categorical:
        d["categorical"] = True
        d["class_values"] = list(preset.class_values or ())
        d["class_palette"] = list(preset.class_palette or ())
        d["class_names"] = list(preset.class_names or ())
    if preset.polarizations:
        d["polarizations"] = list(preset.polarizations)
        d["instrument_mode"] = preset.instrument_mode
    if preset.default_reducer:
        d["default_reducer"] = preset.default_reducer
    return d


# ---------------------------------------------------------------------------
# 预设驱动的集合约定（C4）
# ---------------------------------------------------------------------------
#
# 这一节只做"预设 + spec 字段 → 具体约定"的推导，全部是纯函数（离线可测）；
# 真正构建 ee 对象的动作集中在 build_image / build_collection 里（红线 1）。

def request_bands(preset: AssetPreset | None, spec_bands) -> tuple[str, ...]:
    """本次请求实际涉及的波段：spec.bands 优先，缺省回落到预设的波段表。"""
    if spec_bands:
        return tuple(spec_bands)
    return tuple(preset.bands) if preset else ()


def polarization_filter_bands(preset: AssetPreset | None, bands) -> tuple[str, ...]:
    """
    请求波段里属于极化波段的那些（S1）。

    为什么必须过滤（实测，2026-10-06）：S1 的极化组合随景变化（VV / HH / VV+VH / HH+HV）。
    不加过滤直接 select(['HH','HV'])，集合里那些只有 VV+VH 的景会被静默丢掉波段，
    产物看起来像"这个地区没数据"，而不是报错。所以按请求波段逐项过滤 —— 请求了什么
    极化，就只要含该极化的景。
    """
    if not preset or not preset.polarizations or not bands:
        return ()
    known = set(preset.polarizations)
    return tuple(b for b in bands if b in known)


def band_transforms_for(preset: AssetPreset | None, bands) -> dict[str, tuple[float, float]]:
    """按请求波段挑出要施加的逐波段 (scale, offset)。纯函数，离线可测。"""
    if not preset or not preset.band_transforms or not bands:
        return {}
    table = {b: (float(s), float(o)) for b, s, o in preset.band_transforms}
    return {b: table[b] for b in bands if b in table}


def _asset_collection(ee, preset: AssetPreset | None, asset: str):
    """预设 → ee.ImageCollection。合成预设（merge_assets）在这里合并多个真实集合。"""
    if preset and preset.merge_assets:
        col = ee.ImageCollection(preset.merge_assets[0])
        for other in preset.merge_assets[1:]:
            col = col.merge(ee.ImageCollection(other))
        return col
    return ee.ImageCollection(asset)


def _filter_collection(ee, preset: AssetPreset | None, col, bands):
    """按极化与成像模式过滤集合（S1）。必须在 select() 之前 —— 这些信息在元数据上。"""
    if not preset:
        return col
    for pol in polarization_filter_bands(preset, bands):
        col = col.filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
    if preset.instrument_mode:
        col = col.filter(ee.Filter.eq("instrumentMode", preset.instrument_mode))
    return col


def _guard_empty_collection(ee, preset: AssetPreset | None, col, bands, asset: str,
                            unfiltered=None) -> None:
    """
    过滤后集合为空 ⇒ 可读的 SpecError，并报出该区域实际出现的极化。

    只对"做了极化过滤"的预设生效（多一次 size() 元数据调用，~1s）。这一步不能省：
    静默的空产物是本项目明确要消灭的失败形态（看起来像数据缺失，实则是请求口径不对）。
    """
    if not polarization_filter_bands(preset, bands):
        return
    if _safe(lambda: int(col.size().getInfo()), None) != 0:
        return

    # 失败路径上再花一次聚合，把"这个区域到底有什么"直接摆到用户面前
    seen = None
    if unfiltered is not None:
        seen = _safe(lambda: sorted({tuple(p) for p in
                                     unfiltered.aggregate_array(
                                         "transmitterReceiverPolarisation").getInfo()}), None)
    hint = (f"  该区域该时段实际出现的极化：{seen}。\n" if seen else
            f"  该数据集全局可选的极化：{list(preset.polarizations)}。\n")
    raise SpecError(
        f"{asset} 在给定的时间/区域内没有包含所请求极化的景：{list(bands)}。\n"
        + hint +
        "  处理：把 spec.bands 换成上面列出的其中一组（多数陆地是 ('VV','VH')，"
        "部分地区是 ('HH','HV') 或单极化）。"
    )


def _apply_band_transforms(img, transforms: dict[str, tuple[float, float]]):
    """
    逐波段 (scale, offset)：img.multiply(scale).add(offset)。

    用 addBands(..., overwrite=True) 就地替换 —— 实测（2026-10-06）该调用**保持波段
    原位置**，因此 spec.bands 的顺序与产物波段顺序仍一一对应（出口按位置取波段）。
    """
    for band, (scale, offset) in (transforms or {}).items():
        img = img.addBands(img.select([band]).multiply(scale).add(offset), [band], True)
    return img


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
    preset = preset_for(asset_id)
    if preset and preset.merge_assets:
        # 合成预设（如 LANDSAT/LC08+LC09/C02/T1_L2）是本地键，不是 GEE 资产 ——
        # getAsset 必然失败，所以在这里短路。全程零网络。
        return {
            "asset": asset_id,
            "type": "MERGED_IMAGE_COLLECTION",
            "id": asset_id,
            "name": asset_id,
            "size_bytes": None,
            "update_time": None,
            "title": preset.label,
            "tags": [],
            "properties": {"merge_assets": list(preset.merge_assets)},
            "description": None,
            "preset": _preset_summary(preset),
            "deep": deep,
            "date_range": None,
            "bands": [{"name": b, "type": None, "units": None, "scale": None, "offset": None}
                      for b in preset.bands],
            "is_collection": True,
            "count": None,
            "note": (
                "合成预设：由本模块把 merge_assets 列出的集合合并后使用，"
                "不是一个 GEE 资产 id。"
            ),
        }

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

    if preset:
        out["preset"] = _preset_summary(preset)

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
    bands = request_bands(preset, spec.bands)

    # --- 单景 vs 时序 ---
    if spec.is_collection:
        col = _asset_collection(ee, preset, spec.asset)
        if spec.time_range:
            col = col.filterDate(spec.time_range[0], spec.time_range[1])
        if aoi is not None:
            col = col.filterBounds(aoi)

        # ★ 云掩膜必须在 select 之前 —— 它要用的 SCL / QA_PIXEL
        #   通常不在用户请求的波段里
        scheme = preset.cloud_mask if preset else None
        if scheme:
            col = mask_clouds(col, scheme)

        # ★ 极化/成像模式过滤同样必须在 select 之前 —— 极化信息在**元数据**上，
        #   不在波段里；不过滤时 select 会静默丢景（见 polarization_filter_bands）
        unfiltered = col
        col = _filter_collection(ee, preset, col, bands)
        _guard_empty_collection(ee, preset, col, bands, spec.asset, unfiltered)

        if spec.bands:
            col = col.select(list(spec.bands))

        reducer = spec.reducer or (preset.default_reducer if preset else None) or "median"
        img = getattr(col, reducer)()
    else:
        # 这些资产在 GEE 里是 ImageCollection，ee.Image(asset) 会报
        # "Asset ... is not an Image"（实测：GLO30 / WorldCover / LC08 都会撞上）。
        # 单景集（WorldCover v200 只有 1 景）走 mosaic，其余给可读的错误。
        if preset and preset.single_image_asset:
            img = _asset_collection(ee, preset, spec.asset).mosaic()
        elif preset and preset.collection_only:
            raise SpecError(
                f"{spec.asset} 是影像集合（ImageCollection），不能按单景使用。\n"
                "  处理：设置 time_range（必要时再加 reducer）走集合路径；\n"
                "  例：time_range=('2024-06-01','2024-08-31'), reducer='median'"
            )
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

    # --- 逐波段 (scale, offset)（C4）---
    # 单位换算与带 offset 的辐射缩放。与上面的 reflectance_scale 是同一层的东西，
    # 都必须在 clip 之前、band_expr 之前 —— 它们改的是像素值本身。
    img = _apply_band_transforms(img, band_transforms_for(preset, bands))

    # 分类栅格的 dtype 说明（2026-10-06 实测，两次对照下载）：
    #   spec.dtype=uint8 → 计算图 int8 → 产物仍 **float32**（50 KB）
    #   spec.dtype=float32 → 计算图 float → 产物 float32（65 KB）
    # 即 GEO_TIFF 下载的**容器 dtype 由导出路径决定，不由 spec.dtype 决定**
    # （既有预设同理：S2 的 P0 产物声明 dtype=uint16，文件实为 float64）。
    # 为此**不**在计算图里加一层只会自欺的 cast —— 类码值本身已经是精确整数
    # （实测产物取值 ⊆ {10,…,100}），下游按整数读不会有任何损失；
    # 要真正控制容器 dtype 得改出口层的写盘，那是独立 change 的事（见 README）。

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
    preset = preset_for(spec.asset)
    col = _asset_collection(ee, preset, spec.asset)
    if spec.time_range:
        col = col.filterDate(spec.time_range[0], spec.time_range[1])
    if spec.aoi:
        col = col.filterBounds(to_ee_geometry(spec.aoi))
    col = _filter_collection(ee, preset, col, request_bands(preset, spec.bands))
    if spec.bands:
        col = col.select(list(spec.bands))
    return col


# ---------------------------------------------------------------------------
# spec 默认值推导
# ---------------------------------------------------------------------------

def _default_render(preset: AssetPreset) -> dict:
    """预设 → RenderSpec 的默认渲染建议。既有预设的键集与取值不变。"""
    if preset.categorical:
        # 分类栅格：给类值 + 类色（精确映射，非拉伸）。stretch 在类值路径上不参与运算，
        # 这里显式写 "none" 以免读的人以为还有一次拉伸。
        return {
            "bands": None,
            "palette": list(preset.class_palette or ()),
            "class_values": list(preset.class_values or ()),
            "stretch": "none",
        }
    return {"bands": list(preset.rgb) if preset.rgb else None, "stretch": "stddev"}


def defaults_for(asset: str, aoi: dict | None = None, *, prefer_crs: str = "utm") -> dict:
    """
    从一个 asset id 推 spec 的合理默认值。
    有预设走预设（零网络）；没有就查资产（一次网络往返）。
    """
    from . import crs_rules

    preset = preset_for(asset)
    if preset:
        out = {
            "asset": asset,
            "scale": preset.scale,
            "bands": list(preset.bands),
            # 下载用浮点，避免整数缩放的坑；分类栅格例外 —— 类码用整数 dtype 才符合
            # 下游（重分类/统计/出图图例）的预期。
            "dtype": preset.dtype if preset.categorical else "float32",
            "crs": crs_rules.suggest_crs(aoi, prefer=prefer_crs),
            "render": _default_render(preset),
            "source": "preset",
        }
        # 只在"整体塌缩安全"（集合仅 1 景）时给出 reducer：否则"有 reducer 无
        # time_range"会把整个历史集合卷进一次归约（ERA5-Land 是 1950 至今）。
        if preset.single_image_asset and preset.default_reducer:
            out["reducer"] = preset.default_reducer
        return out

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
