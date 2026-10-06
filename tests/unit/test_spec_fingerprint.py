"""指纹行为与向后兼容守卫（A3 / A4）。

对应 docs/README.md §3.3 与红线 3 / 8：
- 指纹 = 决定输出因素的白名单哈希 + PROCESSING_VERSION
- 元信息（id/note/tags/render）不参与指纹
- 新增字段必须显式决定归属（白名单或排除名单），守卫测试负责拦截
"""

import dataclasses
import unittest
from unittest import mock

from _helpers import make_spec
from gis import spec as spec_module
from gis.spec import PROCESSING_VERSION, ArtifactSpec

# ★ 守卫名单：给 ArtifactSpec 新增字段时，必须把新字段挪进其中一组。
# 白名单 = 决定像素输出的字段（参与哈希）；排除名单 = 不影响像素值的字段。
# 注意 nodata：当前 spec.fingerprint() 的 payload 显式排除它（与 id/note/tags/render
# 同类）。若未来认定 nodata 影响像素输出，需按红线 8 把它移入白名单——那是一次
# 契约变更，须评估对历史缓存指纹的影响。
FINGERPRINT_FIELDS = {
    "asset", "band_expr", "crs", "scale", "aoi",
    "dtype", "bands", "time_range", "reducer",
}
EXCLUDED_FIELDS = {"id", "note", "tags", "render", "nodata"}


class FingerprintStabilityTest(unittest.TestCase):
    """A3：元信息不影响指纹；重复计算稳定；处理逻辑版本参与。"""

    def test_meta_fields_do_not_change_fingerprint(self):
        base = make_spec().fingerprint()
        variants = [
            make_spec(id="another-id"),
            make_spec(note="other-note"),
            make_spec(tags=("x", "y")),
            make_spec(render=None),
        ]
        for v in variants:
            with self.subTest(spec_id=v.id):
                self.assertEqual(v.fingerprint(), base)

    def test_repeated_calls_stable(self):
        s = make_spec()
        self.assertEqual(s.fingerprint(), s.fingerprint())

    def test_processing_version_changes_fingerprint(self):
        s = make_spec()
        base = s.fingerprint()
        with mock.patch.object(spec_module, "PROCESSING_VERSION", PROCESSING_VERSION + 1):
            self.assertNotEqual(s.fingerprint(), base)

    def test_output_fields_change_fingerprint(self):
        base = make_spec().fingerprint()
        variants = {
            "asset": make_spec(asset="LANDSAT/LC08/C02/T1_L2"),
            "band_expr": make_spec(band_expr="B8-B4/(B8+B4)"),
            "crs": make_spec(crs="EPSG:32647"),
            "scale": make_spec(scale=20.0),
            "aoi": make_spec(aoi={
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
            }),
            "dtype": make_spec(dtype="uint8"),
            "bands": make_spec(bands=("B8",)),
            "time_range": make_spec(time_range=("2023-01-01", "2023-12-31")),
            "reducer": make_spec(reducer="mean"),
        }
        for name, v in variants.items():
            with self.subTest(field=name):
                self.assertNotEqual(v.fingerprint(), base)


class FingerprintForwardCompatGuardTest(unittest.TestCase):
    """A4：红线 8 守卫 —— dataclass 字段全集必须有指纹归属。"""

    def test_every_dataclass_field_is_accounted_for(self):
        fields = {f.name for f in dataclasses.fields(ArtifactSpec)}
        unaccounted = fields - (FINGERPRINT_FIELDS | EXCLUDED_FIELDS)
        self.assertFalse(
            unaccounted,
            "ArtifactSpec 存在未决定指纹归属的新字段："
            f"{sorted(unaccounted)}。\n"
            "  按红线 8 处理：决定像素输出的字段加入 FINGERPRINT_FIELDS"
            f"（当前 {sorted(FINGERPRINT_FIELDS)}）；不影响像素的字段加入 "
            f"EXCLUDED_FIELDS（当前 {sorted(EXCLUDED_FIELDS)}）。"
            "移动后确认旧 spec 指纹不变（在本文件补一条回归断言）。",
        )

    def test_rosters_consistent_with_dataclass(self):
        fields = {f.name for f in dataclasses.fields(ArtifactSpec)}
        overlap = FINGERPRINT_FIELDS & EXCLUDED_FIELDS
        self.assertFalse(overlap, f"白名单与排除名单重叠：{sorted(overlap)}")
        self.assertTrue(FINGERPRINT_FIELDS <= fields, "指纹白名单包含 dataclass 不存在的字段")
        self.assertTrue(EXCLUDED_FIELDS <= fields, "排除名单包含 dataclass 不存在的字段")


if __name__ == "__main__":
    unittest.main()
