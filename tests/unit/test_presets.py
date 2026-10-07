"""数据集预设表（C4 `p2-presets`）：新增条目、既有预设语义与版本纪律的离线断言。

对应 docs/README.md §9.2 C4 行、§11 红线 3 / 8。**2026-10-06 范围变更**：修正既有
LC08/LC09 缺官方 offset 的遗留问题 ⇒ `PROCESSING_VERSION` 2 → 3、指纹金值更新；本文件同时
锚定"变更面仅来自版本号"这一不变量。本文件只覆盖**离线可测**的部分：

- 预设表结构与字段语义（分类栅格 / SAR / 逐波段缩放 / 集合保护）；
- 纯函数推导（极化过滤、逐波段变换、请求波段）；
- `defaults_for()` 的预设路径（零网络）；
- `RenderSpec.class_values` 的往返与校验。

ee 侧的计算图行为（合并集合、addBands 覆盖、mosaic）不在本文件验证 —— 那是
`tests/smoke_presets.py`（需网络）与 Verifier 的形状；此处严禁 import ee。
"""

import unittest
from unittest import mock

from gis import source
from gis import spec as spec_module
from gis.spec import PROCESSING_VERSION, ArtifactSpec, RenderSpec, SpecError, bbox_to_geojson

AOI = bbox_to_geojson(116.30, 39.95, 116.40, 40.02)

# 指纹金值。★ 2026-10-06 范围变更：修正既有 Landsat 的辐射缩放口径（补官方 offset -0.2）
# 改变了像素输出 ⇒ 红线 3 要求 PROCESSING_VERSION 2 → 3 ⇒ 金值随之更新。
# 旧金值 c9243efd40318c85 已作废，但它仍是"未受影响的既有预设语义不变"的对照基准——
# 把版本号替换回 2 后必须复现旧值（见 LegacyPresetsFrozenTest.test_change_surface_is_version_only）。
P0_GOLDEN_FINGERPRINT = "b91c09c9c6451c16"
P0_GOLDEN_FINGERPRINT_VERSION_2 = "c9243efd40318c85"

# P0 验收样本的参数（tests/smoke_emit.py 原样：小框 AOI + uint16 + 2024 夏季中值）。
P0_SPEC_DICT = {
    "id": "s2_beijing_test",
    "asset": "COPERNICUS/S2_SR_HARMONIZED",
    "bands": ["B4", "B3", "B2"],
    "scale": 10,
    "crs": "EPSG:32650",
    "dtype": "uint16",
    "time_range": ["2024-06-01", "2024-08-31"],
    "reducer": "median",
    "aoi": {
        "type": "Polygon",
        "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                         [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]],
    },
}


def make_p0_spec(**over) -> ArtifactSpec:
    """P0 样本 spec（本文件自带，不依赖其他测试的共享构造 —— 避免与并行 change 耦合）。"""
    kw = dict(P0_SPEC_DICT)
    kw.update(over)
    render = kw.pop("render", None)          # RenderSpec 对象不参与 from_dict 的 JSON 路径
    spec = ArtifactSpec.from_dict(kw)
    return spec if render is None else spec.with_(render=render)

NEW_ASSETS = (
    "COPERNICUS/S1_GRD",
    "COPERNICUS/S1_GRD_FLOAT",
    "LANDSAT/LC08+LC09/C02/T1_L2",
    "ECMWF/ERA5_LAND/DAILY_AGGR",
    "ESA/WorldCover/v200",
)

# 既有 8 条的字段冻结快照（label, scale, bands, dtype, rgb, cloud_mask, reflectance_scale）。
# ★ 2026-10-06 范围变更：LC08/LC09 两条的 SR 缩放口径被**有意修正**（补官方 offset -0.2，
#   reflectance_scale 让位给 band_transforms），故其 reflectance_scale 由 0.0000275 变为 None；
#   其余 6 条一字不动。这两条的缩放值由 test_affected_legacy_presets_use_official_scaling 断言。
LEGACY_SNAPSHOT = {
    "COPERNICUS/S2_SR_HARMONIZED": (
        "Sentinel-2 地表反射率（Harmonized）", 10, ("B2", "B3", "B4", "B8", "B11", "B12"),
        "uint16", ("B4", "B3", "B2"), "scl", 0.0001),
    "COPERNICUS/S2_HARMONIZED": (
        "Sentinel-2 大气顶反射率（Harmonized）", 10, ("B2", "B3", "B4", "B8", "B11", "B12"),
        "uint16", ("B4", "B3", "B2"), None, None),
    "LANDSAT/LC09/C02/T1_L2": (
        "Landsat 9 L2 地表反射率", 30, ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
        "uint16", ("SR_B4", "SR_B3", "SR_B2"), "qa_pixel", None),      # ← 缩放改走 band_transforms
    "LANDSAT/LC08/C02/T1_L2": (
        "Landsat 8 L2 地表反射率", 30, ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
        "uint16", ("SR_B4", "SR_B3", "SR_B2"), "qa_pixel", None),      # ← 同上
    "MODIS/061/MOD13Q1": (
        "MODIS 植被指数 16 天 250m", 250, ("NDVI", "EVI"), "int16", None, None, None),
    "MODIS/061/MOD11A2": (
        "MODIS 地表温度 8 天 1km", 1000, ("LST_Day_1km", "LST_Night_1km"), "uint16",
        None, None, None),
    "COPERNICUS/DEM/GLO30": (
        "Copernicus DEM GLO-30", 30, ("DEM",), "float32", None, None, None),
    "JRC/GSW1_4/GlobalSurfaceWater": (
        "JRC 全球地表水", 30, ("occurrence", "seasonality", "max_extent"), "uint8",
        None, None, None),
}

# 本次范围变更**未受影响**的既有预设（计算语义与像素输出不变，指纹变化仅来自版本号）
UNAFFECTED_LEGACY = (
    "COPERNICUS/S2_SR_HARMONIZED",
    "COPERNICUS/S2_HARMONIZED",
    "MODIS/061/MOD13Q1",
    "MODIS/061/MOD11A2",
    "COPERNICUS/DEM/GLO30",
    "JRC/GSW1_4/GlobalSurfaceWater",
)
# 本次被有意修正的既有预设（补官方 offset）
AFFECTED_LEGACY = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")

# ESA WorldCover v200 的类表（GEE 资产属性 Map_class_values / Map_class_palette /
# Map_class_names，2026-10-06 实测；与官方目录 Class Table 一致）。
WORLDCOVER_GOLDEN = (
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


class LegacyPresetsFrozenTest(unittest.TestCase):
    """A5：既有 8 条预设一字节不动 —— C4 只增不改。"""

    def test_legacy_snapshot_matches(self):
        for asset, snap in LEGACY_SNAPSHOT.items():
            with self.subTest(asset=asset):
                p = source.preset_for(asset)
                self.assertIsNotNone(p, f"{asset} 的预设丢了")
                got = (p.label, p.scale, p.bands, p.dtype, p.rgb, p.cloud_mask,
                       p.reflectance_scale)
                self.assertEqual(got, snap)

    def test_unaffected_legacy_presets_carry_no_c4_fields(self):
        """未受影响的 6 条既有预设不得被新机制碰到（新字段缺省 ⇒ 行为逐字节不变）。"""
        for asset in UNAFFECTED_LEGACY:
            with self.subTest(asset=asset):
                p = source.preset_for(asset)
                self.assertFalse(p.categorical)
                self.assertIsNone(p.merge_assets)
                self.assertIsNone(p.band_transforms)
                self.assertIsNone(p.polarizations)
                self.assertIsNone(p.instrument_mode)
                self.assertIsNone(p.class_values)
                self.assertIsNone(p.class_palette)
                self.assertIsNone(p.class_names)
                self.assertIsNone(p.default_reducer)
                self.assertFalse(p.collection_only)
                self.assertFalse(p.single_image_asset)

    def test_affected_legacy_presets_use_official_scaling(self):
        """A2(b)/A5：LC08/LC09 的缩放口径已被有意修正为官方 `DN*2.75e-05 - 0.2`。"""
        want = {b: (0.0000275, -0.2) for b in
                ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7")}
        merged = source.band_transforms_for(
            source.preset_for("LANDSAT/LC08+LC09/C02/T1_L2"),
            ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"))
        for asset in AFFECTED_LEGACY:
            with self.subTest(asset=asset):
                p = source.preset_for(asset)
                self.assertIsNone(p.reflectance_scale, "旧的单一乘系数写法应已让位")
                self.assertEqual(source.band_transforms_for(p, p.bands), want)
                # 与合并预设口径一致 —— 三条 Landsat 预设不该有两套反射率量纲
                self.assertEqual(source.band_transforms_for(p, p.bands), merged)

    def test_processing_version_is_3(self):
        # 修正既有 Landsat 缩放 ⇒ 红线 3 的 bump 必须落实（2 → 3）。
        self.assertEqual(PROCESSING_VERSION, 3)

    def test_p0_golden_fingerprint_current(self):
        self.assertEqual(make_p0_spec().fingerprint(), P0_GOLDEN_FINGERPRINT)

    def test_change_surface_is_version_only(self):
        """
        A5 的核心断言：本次 bump 之外，未受影响的既有 spec 的哈希 payload 一字未动 ——
        把版本号替换回 2，必须复现旧金值 c9243efd40318c85。
        """
        with mock.patch.object(spec_module, "PROCESSING_VERSION", 2):
            self.assertEqual(make_p0_spec().fingerprint(), P0_GOLDEN_FINGERPRINT_VERSION_2)
        # 版本号确实参与哈希：正常路径下与旧值不同
        self.assertNotEqual(make_p0_spec().fingerprint(), P0_GOLDEN_FINGERPRINT_VERSION_2)


class NewPresetsTest(unittest.TestCase):
    """A1–A4：5 条新增条目的字段语义。"""

    def test_table_contains_legacy_and_new(self):
        self.assertEqual(len(source.DEFAULT_ASSETS), 13)
        for asset in NEW_ASSETS:
            with self.subTest(asset=asset):
                self.assertIn(asset, source.DEFAULT_ASSETS)
                self.assertIsNotNone(source.preset_for(asset))

    def test_s1_presets(self):
        db = source.preset_for("COPERNICUS/S1_GRD")
        lin = source.preset_for("COPERNICUS/S1_GRD_FLOAT")
        for p in (db, lin):
            with self.subTest(asset=p.asset):
                self.assertEqual(p.scale, 10)
                self.assertEqual(p.bands, ("VV", "VH"))
                self.assertEqual(p.polarizations, ("VV", "VH", "HH", "HV"))
                self.assertEqual(p.instrument_mode, "IW")
                self.assertTrue(p.collection_only)
                # SAR 豁免（红线 4）：SAR 无云掩膜，计算图里没有掩膜步骤
                self.assertIsNone(p.cloud_mask)
                self.assertIsNone(p.reflectance_scale)
                self.assertIsNone(p.band_transforms)
        # 两条预设只差资产与单位口径，波段/过滤一致
        self.assertNotEqual(db.asset, lin.asset)
        self.assertEqual(db.bands, lin.bands)

    def test_landsat_merged_preset(self):
        p = source.preset_for("LANDSAT/LC08+LC09/C02/T1_L2")
        self.assertEqual(p.merge_assets,
                         ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"))
        self.assertTrue(p.collection_only)
        self.assertEqual(p.cloud_mask, "qa_pixel")
        self.assertEqual(p.scale, 30)
        self.assertEqual(p.bands, ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"))
        # 官方缩放：DN * 2.75e-05 - 0.2
        self.assertEqual(source.band_transforms_for(p, p.bands),
                         {b: (0.0000275, -0.2) for b in p.bands})
        # 三条 Landsat 预设口径一致（2026-10-06 范围变更后，既有两条也补上了 offset）
        for legacy in AFFECTED_LEGACY:
            self.assertEqual(source.band_transforms_for(source.preset_for(legacy), p.bands),
                             source.band_transforms_for(p, p.bands))

    def test_era5_preset(self):
        p = source.preset_for("ECMWF/ERA5_LAND/DAILY_AGGR")
        self.assertEqual(p.scale, 11132)
        self.assertEqual(p.default_reducer, "mean")
        self.assertTrue(p.collection_only)
        self.assertEqual(source.band_transforms_for(p, p.bands), {
            "temperature_2m": (1.0, -273.15),          # K → °C
            "total_precipitation_sum": (1000.0, 0.0),  # m → mm
        })
        # 未列出的波段必须保持原生单位（Pa）
        self.assertNotIn("surface_pressure", dict(
            (b, s) for b, s, _o in (p.band_transforms or ())))

    def test_worldcover_preset(self):
        p = source.preset_for("ESA/WorldCover/v200")
        self.assertTrue(p.categorical)
        self.assertTrue(p.collection_only)
        self.assertTrue(p.single_image_asset)
        self.assertEqual(p.default_reducer, "mode")
        self.assertEqual(p.dtype, "uint8")           # 类码用整数 dtype
        self.assertEqual(p.bands, ("Map",))
        self.assertIsNone(p.cloud_mask)
        self.assertIsNone(p.reflectance_scale)
        self.assertIsNone(p.band_transforms)         # 分类栅格不做数值缩放
        self.assertEqual(tuple(zip(p.class_values, p.class_palette, p.class_names)),
                         WORLDCOVER_GOLDEN)

    def test_new_presets_are_collections(self):
        """三个出口都要走集合路径 —— 这些资产在 GEE 里都不是单景 Image。"""
        for asset in NEW_ASSETS:
            with self.subTest(asset=asset):
                self.assertTrue(source.preset_for(asset).collection_only)


class PresetHelpersTest(unittest.TestCase):
    """预设 → 具体约定的纯函数（离线可测，是 smoke 的前置）。"""

    def test_request_bands_prefers_spec(self):
        p = source.preset_for("COPERNICUS/S1_GRD")
        self.assertEqual(source.request_bands(p, ("VV",)), ("VV",))
        self.assertEqual(source.request_bands(p, ()), ("VV", "VH"))
        self.assertEqual(source.request_bands(None, ()), ())

    def test_polarization_filter_follows_requested_bands(self):
        p = source.preset_for("COPERNICUS/S1_GRD")
        self.assertEqual(source.polarization_filter_bands(p, ("VV", "VH")), ("VV", "VH"))
        self.assertEqual(source.polarization_filter_bands(p, ("HH", "HV")), ("HH", "HV"))
        self.assertEqual(source.polarization_filter_bands(p, ("VV", "angle")), ("VV",))
        # 非极化数据集不得凭空产生过滤条件
        self.assertEqual(
            source.polarization_filter_bands(source.preset_for("COPERNICUS/S2_SR_HARMONIZED"),
                                             ("B4", "B3", "B2")), ())
        self.assertEqual(source.polarization_filter_bands(None, ("VV",)), ())

    def test_band_transforms_filtered_by_requested_bands(self):
        p = source.preset_for("ECMWF/ERA5_LAND/DAILY_AGGR")
        self.assertEqual(source.band_transforms_for(p, ("temperature_2m",)),
                         {"temperature_2m": (1.0, -273.15)})
        self.assertEqual(source.band_transforms_for(p, ("surface_pressure",)), {})
        self.assertEqual(source.band_transforms_for(p, ()), {})
        self.assertEqual(
            source.band_transforms_for(source.preset_for("COPERNICUS/S2_SR_HARMONIZED"),
                                       ("B4",)), {})


class DefaultsForPresetTest(unittest.TestCase):
    """A1–A4：`defaults_for()` 的预设路径（零网络）派生正确。"""

    def test_legacy_defaults_unchanged(self):
        d = source.defaults_for("COPERNICUS/S2_SR_HARMONIZED", AOI)
        self.assertEqual(d["dtype"], "float32")
        self.assertEqual(d["render"], {"bands": ["B4", "B3", "B2"], "stretch": "stddev"})
        self.assertNotIn("reducer", d)

    def test_new_presets_defaults(self):
        s1 = source.defaults_for("COPERNICUS/S1_GRD", AOI)
        self.assertEqual(s1["bands"], ["VV", "VH"])
        self.assertNotIn("reducer", s1)         # 无 time_range 时不得带 reducer
        era = source.defaults_for("ECMWF/ERA5_LAND/DAILY_AGGR", AOI)
        self.assertEqual(era["scale"], 11132)
        self.assertNotIn("reducer", era)        # 否则会把 1950 至今全卷进一次归约
        lan = source.defaults_for("LANDSAT/LC08+LC09/C02/T1_L2", AOI)
        self.assertEqual(lan["render"], {"bands": ["SR_B4", "SR_B3", "SR_B2"],
                                         "stretch": "stddev"})

    def test_worldcover_defaults_carry_class_render(self):
        d = source.defaults_for("ESA/WorldCover/v200", AOI)
        self.assertEqual(d["dtype"], "uint8")
        self.assertEqual(d["reducer"], "mode")   # 单景集合：整体塌缩安全
        self.assertEqual(d["render"]["palette"], [c for _v, c, _n in WORLDCOVER_GOLDEN])
        self.assertEqual(d["render"]["class_values"], [float(v) for v, _c, _n in WORLDCOVER_GOLDEN])
        self.assertIsNone(d["render"]["bands"])
        # 这些默认值必须能被 spec 直接吃下（往返一致）
        spec = ArtifactSpec.from_dict({"id": "wc", "crs": "EPSG:32650",
                                       "aoi": AOI, **d})
        spec.validate("file")
        self.assertEqual(spec.reducer, "mode")
        self.assertEqual(tuple(spec.render.class_values),
                         tuple(float(v) for v, _c, _n in WORLDCOVER_GOLDEN))


class RenderSpecClassValuesTest(unittest.TestCase):
    """A4：分类取值表的契约（render 不入指纹，红线 8 不受影响）。"""

    def test_roundtrip(self):
        r = RenderSpec(palette=("006400", "fa0000"), class_values=(10.0, 50.0))
        d = r.to_dict()
        self.assertEqual(d["class_values"], [10.0, 50.0])
        self.assertEqual(RenderSpec.from_dict(d), r)

    def test_validation(self):
        with self.assertRaises(SpecError):
            RenderSpec(class_values=(10.0,))                       # 缺 palette
        with self.assertRaises(SpecError):
            RenderSpec(palette=("006400",), class_values=(10.0, 20.0))   # 长度不等
        with self.assertRaises(SpecError):
            RenderSpec(palette=("006400", "fa0000"), class_values=(10.0, 10.0))  # 类值重复

    def test_render_does_not_enter_fingerprint(self):
        base = make_p0_spec(render=RenderSpec(bands=("B4", "B3", "B2")))
        classified = make_p0_spec(render=RenderSpec(palette=("006400", "fa0000"),
                                                    class_values=(10.0, 50.0)))
        self.assertEqual(base.fingerprint(), classified.fingerprint())
        self.assertEqual(classified.fingerprint(), P0_GOLDEN_FINGERPRINT)


class PresetContractTest(unittest.TestCase):
    """契约自检：写错的预设必须在构造时就炸，而不是等到 GEE 报错。"""

    def test_categorical_requires_class_tables(self):
        with self.assertRaises(ValueError):
            source.AssetPreset("X", "缺表", 10, ("Map",), categorical=True)

    def test_categorical_requires_matching_lengths(self):
        with self.assertRaises(ValueError):
            source.AssetPreset("X", "长度不等", 10, ("Map",), categorical=True,
                               class_values=(10, 20), class_palette=("006400",))
        with self.assertRaises(ValueError):
            source.AssetPreset("X", "类名长度不等", 10, ("Map",), categorical=True,
                               class_values=(10,), class_palette=("006400",),
                               class_names=("a", "b"))

    def test_merge_requires_collection_only(self):
        with self.assertRaises(ValueError):
            source.AssetPreset("X", "合成但没标集合", 30, ("B1",),
                               merge_assets=("A", "B"))

    def test_single_image_requires_collection_only(self):
        with self.assertRaises(ValueError):
            source.AssetPreset("X", "单景集但没标集合", 10, ("Map",),
                               single_image_asset=True)


class ClassPaletteRenderTest(unittest.TestCase):
    """A4 的渲染面：类值 → 颜色精确映射（纯 numpy，离线可测）。

    分类栅格不能走 `_stretch` + 固定 viridis 色带 —— 那会把离散类码渲染成
    一条连续色带，跟图例对不上。这里验证精确取色、非类值与 nodata 的落点。
    """

    def _fn(self):
        from gis.emit import _apply_class_palette
        return _apply_class_palette

    def test_exact_class_colors(self):
        import numpy as np

        r = RenderSpec(palette=("006400", "fa0000"), class_values=(10.0, 50.0))
        data = np.array([[10.0, 50.0], [0.0, 30.0]])     # 0 与 30 都不在类表里
        rgb = self._fn()(data, r)
        np.testing.assert_allclose(rgb[0, 0], [0x00 / 255, 0x64 / 255, 0x00 / 255], atol=1e-6)
        np.testing.assert_allclose(rgb[0, 1], [0xfa / 255, 0x00 / 255, 0x00 / 255], atol=1e-6)
        # 未列出的类值落到底色（缺省黑），不得被吸附到最近的类
        np.testing.assert_allclose(rgb[1, 0], [0.0, 0.0, 0.0], atol=1e-6)
        np.testing.assert_allclose(rgb[1, 1], [0.0, 0.0, 0.0], atol=1e-6)

    def test_nodata_color_and_nan(self):
        import numpy as np

        r = RenderSpec(palette=("006400",), class_values=(10.0,), nodata_color="ffffff")
        data = np.array([[10.0, np.nan]])
        rgb = self._fn()(data, r)
        np.testing.assert_allclose(rgb[0, 0], [0x00 / 255, 0x64 / 255, 0.0], atol=1e-6)
        np.testing.assert_allclose(rgb[0, 1], [1.0, 1.0, 1.0], atol=1e-6)   # NaN → 底色

    def test_whole_worldcover_table_maps_one_to_one(self):
        import numpy as np

        p = source.preset_for("ESA/WorldCover/v200")
        r = RenderSpec(palette=p.class_palette, class_values=p.class_values)
        data = np.array([p.class_values], dtype="float64")     # 11 个类各一格
        rgb = self._fn()(data, r)
        for i, (_v, hexcol, _n) in enumerate(WORLDCOVER_GOLDEN):
            want = [int(hexcol[j:j + 2], 16) / 255.0 for j in (0, 2, 4)]
            np.testing.assert_allclose(rgb[0, i], want, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
