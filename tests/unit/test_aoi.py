"""行政区 AOI 供给（C8 A4/A7）。

全部离线：admin_aoi 用合成 fixture 目录注入（fixture 明显标注非真实边界数据）；
osm_boundary_aoi 用假 transport + 内联合成边界响应（非中国）。
覆盖：adcode 唯一键、spec.validate + compute_grid 离线进契约、_ref 缺失
可读报错指向恢复程序、D2 country 守卫、osm3s 时戳走 meta 不进几何（D4）。
"""

import json
import pathlib
import unittest

from tests.unit._helpers import make_spec

from gis.aoi import ComplianceError, admin_aoi, osm_boundary_aoi, save_aoi_note
from gis.grid import compute_grid
from gis.spec import ArtifactSpec

ROOT = pathlib.Path(__file__).resolve().parents[2]
TINY = ROOT / "tests" / "unit" / "fixtures" / "admin_tiny"
DUP = ROOT / "tests" / "unit" / "fixtures" / "admin_dup"


class AdminAoiTest(unittest.TestCase):
    """A4：adcode 唯一键 → 物化 GeoJSON dict → 直接进 spec 契约。"""

    def test_county_level_hit(self):
        aoi = admin_aoi("110101", data_dir=TINY)
        self.assertEqual(aoi["type"], "Polygon")
        self.assertTrue(aoi["coordinates"])

    def test_int_adcode_and_levels(self):
        self.assertEqual(admin_aoi(110100, data_dir=TINY)["type"], "Polygon")   # 市
        self.assertEqual(admin_aoi(110000, data_dir=TINY)["type"], "Polygon")   # 省

    def test_aoi_enters_spec_contract_offline(self):
        aoi = admin_aoi("110101", data_dir=TINY)
        spec = ArtifactSpec(id="ut_aoi_contract", crs="EPSG:32650", scale=100.0,
                            aoi=aoi)
        spec.validate("map")            # 通过契约校验
        grid = compute_grid(spec)       # 离线可算出网格（AOI 只是喂料方）
        self.assertGreater(grid.width, 0)
        self.assertGreater(grid.height, 0)

    def test_adcode_not_found_readable(self):
        with self.assertRaises(ValueError) as ctx:
            admin_aoi("999999", data_dir=TINY)
        msg = str(ctx.exception)
        self.assertIn("999999", msg)
        self.assertIn("china_county.geojson", msg)

    def test_adcode_format_validated(self):
        with self.assertRaises(ValueError):
            admin_aoi("11010", data_dir=TINY)      # 5 位
        with self.assertRaises(ValueError):
            admin_aoi("abc123", data_dir=TINY)

    def test_duplicate_adcode_breaks_uniqueness(self):
        with self.assertRaises(RuntimeError) as ctx:
            admin_aoi("110101", data_dir=DUP)
        self.assertIn("唯一键", str(ctx.exception))

    def test_missing_dir_error_points_to_recovery(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            admin_aoi("110101", data_dir=ROOT / "tests" / "unit" / "fixtures" / "no_such_dir")
        msg = str(ctx.exception)
        # 可读且指向恢复程序（docs/knowledge/README.md「出处」节）
        self.assertIn("docs/knowledge/README.md", msg)
        self.assertIn("出处", msg)


class OsmBoundaryAoiTest(unittest.TestCase):
    """A7/D2：非中国边界可用；country 指向中国即拒绝；时戳走 meta（D4）。"""

    RAW = {
        "osm3s": {"timestamp_osm_base": "2026-10-07T08:00:00Z"},
        "elements": [
            {"type": "relation", "id": 9001, "tags": {
                "boundary": "administrative", "name": "Testgau", "admin_level": "8"},
             "members": [
                 {"type": "way", "ref": 9011, "role": "outer", "geometry": [
                     {"lat": 48.00, "lon": 7.80}, {"lat": 48.02, "lon": 7.80},
                     {"lat": 48.02, "lon": 7.84}, {"lat": 48.00, "lon": 7.80}]}]},
        ],
    }

    def _transport(self):
        def tr(endpoint, ql, timeout):
            return 200, json.dumps(self.RAW)
        tr.calls = []
        return tr

    def test_boundary_geometry_with_meta(self):
        tr = self._transport()
        geometry, meta = osm_boundary_aoi("Testgau", transport=tr, return_meta=True)
        self.assertEqual(geometry["type"], "Polygon")
        self.assertEqual(meta["osm3s_timestamp"], "2026-10-07T08:00:00Z")
        self.assertEqual(meta["osm_id"], 9001)
        # D4：几何 dict 里不得嵌时戳（否则指纹被数据时戳污染）
        self.assertNotIn("osm3s_timestamp", geometry)
        # meta 可拼成 note 片段
        note = save_aoi_note(geometry, meta)
        self.assertIn("osm3s_timestamp", json.loads(note))

    def test_default_returns_pure_geometry(self):
        geometry = osm_boundary_aoi("Testgau", transport=self._transport())
        self.assertEqual(set(geometry) >= {"type", "coordinates"}, True)
        self.assertNotIn("osm3s_timestamp", geometry)

    def test_name_not_found_readable(self):
        with self.assertRaises(ValueError) as ctx:
            osm_boundary_aoi("Nowhere", transport=self._transport())
        self.assertIn("Nowhere", str(ctx.exception))
        self.assertIn("admin_aoi", str(ctx.exception))

    def test_china_country_rejected_compliance(self):
        # D2 硬约束：country 指向中国一律拒绝 —— 守卫先于任何网络行为
        for marker in ("CN", "cn", "CHN", "中国", "中华人民共和国"):
            with self.subTest(marker=marker):
                with self.assertRaises(ComplianceError) as ctx:
                    osm_boundary_aoi("北京", country=marker,
                                     transport=self._transport())
                self.assertIn("admin_aoi", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
