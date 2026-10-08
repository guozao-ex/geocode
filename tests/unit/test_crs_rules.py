"""crs_rules 的 CRS 纪律（交付内容 6 / A5 的一部分）。"""

import unittest

from tests.unit._helpers import BEIJING_AOI

from gis import crs_rules as cr


class CrsFactsTest(unittest.TestCase):
    def test_projected_vs_geographic(self):
        self.assertTrue(cr.is_projected("EPSG:32650"))
        self.assertFalse(cr.is_projected("EPSG:4326"))

    def test_metric_units(self):
        self.assertTrue(cr.is_metric("EPSG:32650"))
        self.assertEqual(cr.unit_of("EPSG:4326"), "degree")

    def test_describe(self):
        d = cr.describe("EPSG:32650")
        self.assertTrue(d["is_projected"])
        self.assertTrue(d["metric"])
        self.assertEqual(d["epsg"], 32650)


class UtmZoneTest(unittest.TestCase):
    def test_beijing_is_50n(self):
        self.assertEqual(cr.utm_epsg(116.4, 39.9), 32650)

    def test_southern_hemisphere_gets_327xx(self):
        self.assertEqual(cr.utm_epsg(151.2, -33.87), 32756)  # 悉尼 → 56S

    def test_out_of_range_clamped(self):
        self.assertEqual(cr.utm_epsg(999.0, 10.0), cr.utm_epsg(180.0, 10.0))


class OpClassifyTest(unittest.TestCase):
    def test_linear_ops(self):
        for op in ("buffer", "slope", "Area", "QGIS:native:buffer"):
            with self.subTest(op=op):
                self.assertEqual(cr.classify(op), "linear")

    def test_agnostic_ops(self):
        for op in ("ndvi", "dissolve", "clip", "totally_unknown_algo"):
            with self.subTest(op=op):
                self.assertEqual(cr.classify(op), "agnostic")


class CheckTest(unittest.TestCase):
    def test_linear_on_geographic_is_error(self):
        issues = cr.check("buffer", "EPSG:4326")
        self.assertTrue(
            any(i.level == "error" and i.code == "linear-op-on-geographic" for i in issues)
        )

    def test_linear_on_projected_metric_is_clean(self):
        self.assertEqual(cr.check("buffer", "EPSG:32650"), [])

    def test_agnostic_never_errors_on_gcs(self):
        self.assertEqual(
            [i for i in cr.check("dissolve", "EPSG:4326") if i.level == "error"], []
        )

    def test_unspecified_crs_gives_info_only(self):
        issues = cr.check("slope", None)
        self.assertTrue(issues)
        self.assertFalse(any(i.level == "error" for i in issues))

    def test_unresolvable_crs_gives_error(self):
        issues = cr.check("buffer", "EPSG:999999")
        self.assertTrue(any(i.level == "error" and i.code == "crs-unresolvable" for i in issues))


class SuggestCrsTest(unittest.TestCase):
    def test_beijing_utm(self):
        self.assertEqual(cr.suggest_crs(BEIJING_AOI), "EPSG:32650")

    def test_empty_aoi_falls_back(self):
        self.assertEqual(cr.suggest_crs(None, fallback="EPSG:4326"), "EPSG:4326")

    def test_cgcs2000_prefer_returns_projected(self):
        """CGCS2000 表随 PROJ 数据库版本而变：查到用 CGCS2000，查不到退 UTM——
        两个分支都必须给投影坐标系。"""
        got = cr.suggest_crs(BEIJING_AOI, prefer="cgcs2000")
        self.assertTrue(got.startswith("EPSG:"))
        self.assertTrue(cr.is_projected(got), got)

    def test_cgcs2000_mapping_consistent_with_central_meridian(self):
        """中央经线一致性属性校验（D7）：返回 EPSG 名称中的 CM 必须等于
        3*round(lon/3)。不硬编码码位，跨 PROJ 版本稳健；表为空时验证兜底。"""
        import re

        from pyproj import CRS

        lons = [76.0, 87.5, 99.2, 108.3, 117.4, 126.9, 134.8]  # 中国范围 75E–135E
        if not cr._cgcs2000_3deg_table():
            # PROJ 数据库缺 CGCS2000 条目 → 查询恒 None，suggest 应回落 UTM
            self.assertIsNone(cr.cgcs2000_3deg_epsg(117.4))
            self.assertEqual(cr.suggest_crs(BEIJING_AOI, prefer="cgcs2000"), "EPSG:32650")
            return
        for lon in lons:
            with self.subTest(lon=lon):
                code = cr.cgcs2000_3deg_epsg(lon)
                self.assertIsNotNone(code, f"lon={lon} 应查到 CGCS2000 3 度带")
                name = CRS.from_epsg(code).name.lower()
                m = re.search(r"cm\s+(\d{2,3})e", name)
                self.assertIsNotNone(m, f"EPSG:{code} 名称不含 CM：{name!r}")
                self.assertEqual(
                    int(m.group(1)), int(round(lon / 3.0) * 3),
                    f"EPSG:{code}（{name}）的中央经线与 lon={lon} 不匹配",
                )


class AuthorSelfTest(unittest.TestCase):
    def test_crs_rules_self_test_passes(self):
        self.assertEqual(cr.self_test(), [])


if __name__ == "__main__":
    unittest.main()
