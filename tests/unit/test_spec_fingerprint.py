"""指纹行为与向后兼容守卫（C1 A3/A4 延续 + C3 A5/A6）。

对应 docs/README.md §3.3 与红线 3 / 8：
- 指纹 = 决定输出因素的白名单哈希 + PROCESSING_VERSION
- 元信息（id/note/tags/render）不参与指纹
- 新增字段必须显式决定归属（白名单或排除名单），守卫测试负责拦截
"""

import dataclasses
import unittest
from unittest import mock

from _helpers import make_p0_spec, make_spec

from gis import spec as spec_module
from gis.spec import PROCESSING_VERSION, ArtifactSpec, LayoutSpec

# ★ 守卫名单：给 ArtifactSpec 新增字段时，必须把新字段挪进其中一组。
# 白名单 = 决定像素输出的字段（参与哈希）；排除名单 = 不影响像素值的字段。
# 注意 nodata（D5 议题，2026-10-06 C3 结案）：维持排除 —— 调查确认
# spec.nodata 在计算与出口全链路零消费（仅出现在 spec.to_dict 序列化与
# emit 的元信息报告），不影响像素值；若未来要按 nodata 烧写填充值再移入
# 白名单，需评估设值 spec 的历史缓存失效面。
# layout（2026-10-06，C2）：呈现层规格（图廓/比例尺/图例等），与 render 同类，排除。
# time_step / time_ranges（2026-10-06，C3）：决定期窗口 → 决定像素输出，入白名单；
# 缺省时在 fingerprint() payload 中整个键缺席 → 旧 spec 指纹不变（金指纹锚定）。
FINGERPRINT_FIELDS = {
    "asset", "band_expr", "crs", "scale", "aoi",
    "dtype", "bands", "time_range", "reducer",
    "time_step", "time_ranges",
}
EXCLUDED_FIELDS = {"id", "note", "tags", "render", "nodata", "layout"}

# P0 样本 spec 的指纹金值（data/derived/ 既有缓存 c9243efd 的完整指纹）。
# 新增字段若意外参与旧 spec 哈希，此断言首先失败。
P0_GOLDEN_FINGERPRINT = "c9243efd40318c85"


class FingerprintStabilityTest(unittest.TestCase):
    """A3：元信息不影响指纹；重复计算稳定；处理逻辑版本参与。"""

    def test_meta_fields_do_not_change_fingerprint(self):
        base = make_spec().fingerprint()
        variants = [
            make_spec(id="another-id"),
            make_spec(note="other-note"),
            make_spec(tags=("x", "y")),
            make_spec(render=None),
            make_spec(layout=LayoutSpec(title="论文图 1")),   # C2：呈现层不影响指纹
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
            "time_step": make_spec(time_step="month"),
            "time_ranges": make_spec(time_ranges=(("2024-01-01", "2024-03-31"),)),
        }
        for name, v in variants.items():
            with self.subTest(field=name):
                self.assertNotEqual(v.fingerprint(), base)


class GoldenFingerprintTest(unittest.TestCase):
    """C3 A5：旧 spec 指纹不变 —— 金指纹锚定 P0 缓存产物。"""

    def test_p0_golden_fingerprint_unchanged(self):
        # P0 样本参数（tests/smoke_emit.py 原样）→ 既有缓存 s2_beijing_test.c9243efd.*
        # 任一新字段意外参与缺省 spec 的哈希，这里首先红。
        self.assertEqual(make_p0_spec().fingerprint(), P0_GOLDEN_FINGERPRINT)

    def test_timeseries_fields_absent_by_default(self):
        # 缺省（None）的时序字段不得改变指纹 —— 与金指纹互为表里的显式断言
        base = make_p0_spec().fingerprint()
        self.assertEqual(
            make_p0_spec(time_step=None, time_ranges=None).fingerprint(), base
        )

    def test_timeseries_fields_change_fingerprint(self):
        base = make_p0_spec().fingerprint()
        self.assertNotEqual(
            make_p0_spec(time_step="month").fingerprint(), base
        )
        self.assertNotEqual(
            make_p0_spec(time_ranges=(("2024-06-01", "2024-07-01"),)).fingerprint(), base
        )


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
