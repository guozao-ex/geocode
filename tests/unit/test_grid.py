"""grid.compute_grid 确定性与 Grid.matches（交付内容 5 / A5 的一部分）。

对应红线 2：网格必须由 compute_grid 统一算定。
"""

import unittest

from _helpers import make_spec
from gis import grid as grid_module
from gis.grid import Grid, GridError, compute_grid


class ComputeGridTest(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.grid = compute_grid(self.spec)

    def test_deterministic(self):
        """同一 spec → 同一网格（crs/scale/尺寸/transform 全等）。"""
        self.assertEqual(self.grid, compute_grid(self.spec))

    def test_origin_snapped_to_scale_multiples(self):
        g = self.grid
        for name, v in (("xmin", g.xmin), ("ymax", g.ymax)):
            self.assertAlmostEqual(
                v / g.scale, round(v / g.scale), places=9, msg=name
            )

    def test_self_consistent(self):
        g = self.grid
        self.assertAlmostEqual(g.xmax, g.xmin + g.width * g.scale, places=6)
        self.assertAlmostEqual(g.ymin, g.ymax - g.height * g.scale, places=6)

    def test_north_up_transform(self):
        a, b, c, d, e, f = self.grid.transform
        self.assertGreater(a, 0)      # 像元宽为正
        self.assertLess(e, 0)         # y 轴向下（北向上）
        self.assertEqual(b, 0.0)
        self.assertEqual(d, 0.0)

    def test_shape_2d_is_height_width(self):
        h, w = self.grid.shape_2d
        self.assertEqual((h, w), (self.grid.height, self.grid.width))

    def test_pad_enlarges_grid(self):
        g2 = compute_grid(self.spec, pad_pixels=2)
        self.assertGreater(g2.width, self.grid.width)
        self.assertGreater(g2.height, self.grid.height)

    def test_positive_dimensions(self):
        self.assertGreater(self.grid.width, 0)
        self.assertGreater(self.grid.height, 0)


class ComputeGridErrorsTest(unittest.TestCase):
    def test_missing_crs(self):
        with self.assertRaises(GridError) as cm:
            compute_grid(make_spec(crs=None))
        self.assertIn("crs", str(cm.exception))

    def test_nonpositive_scale(self):
        with self.assertRaises(GridError):
            compute_grid(make_spec(scale=0))

    def test_missing_aoi(self):
        with self.assertRaises(GridError):
            compute_grid(make_spec(aoi=None))

    def test_geographic_crs_with_metric_scale_rejected(self):
        """EPSG:4326 + 米 scale 会把『度』当『米』——必须拒绝而不是给错结果。"""
        with self.assertRaises(GridError):
            compute_grid(make_spec(crs="EPSG:4326"))


class GridMatchesTest(unittest.TestCase):
    """Grid.matches 是"校验 GEE 是否照给的网格执行"的判据（红线 2 侧面）。"""

    def setUp(self):
        self.grid = compute_grid(make_spec())

    def test_matching_params_pass(self):
        ok, problems = self.grid.matches(
            crs=self.grid.crs, bounds=self.grid.bounds, shape=self.grid.shape_2d
        )
        self.assertTrue(ok)
        self.assertEqual(problems, [])

    def test_crs_comparison_is_case_insensitive(self):
        ok, _ = self.grid.matches(
            crs="epsg:32650", bounds=self.grid.bounds, shape=self.grid.shape_2d
        )
        self.assertTrue(ok)

    def test_wrong_shape_detected(self):
        h, w = self.grid.shape_2d
        ok, problems = self.grid.matches(
            crs=self.grid.crs, bounds=self.grid.bounds, shape=(h, w + 1)
        )
        self.assertFalse(ok)
        self.assertTrue(any("尺寸" in p for p in problems))

    def test_wrong_crs_detected(self):
        ok, problems = self.grid.matches(
            crs="EPSG:32647", bounds=self.grid.bounds, shape=self.grid.shape_2d
        )
        self.assertFalse(ok)
        self.assertTrue(any("CRS" in p for p in problems))

    def test_within_tolerance_shift_not_flagged(self):
        """容差语义固化（D8）：matches() 用 rtol=1e-3 相对容差 +
        abs_tol=max(rtol, scale*0.01)，UTM 坐标量级（~1e5-1e6）下米级小偏移
        不报警——这是文档化的现状；收紧容差属生产语义变更，另立 change。"""
        xmin, ymin, xmax, ymax = self.grid.bounds
        eps = 1.0  # 1 米，远小于 0.1% 坐标值
        ok, problems = self.grid.matches(
            crs=self.grid.crs,
            bounds=(xmin + eps, ymin, xmax + eps, ymax),
            shape=self.grid.shape_2d,
        )
        self.assertTrue(ok, problems)

    def test_shifted_bounds_detected(self):
        xmin, ymin, xmax, ymax = self.grid.bounds
        # matches() 用 rtol=1e-3 的相对容差，UTM 坐标量级 ~1e5-1e6，
        # 偏移量必须远大于 0.1% 坐标值才能被可靠检出
        shift = abs(xmin) * 0.05
        ok, problems = self.grid.matches(
            crs=self.grid.crs,
            bounds=(xmin + shift, ymin, xmax + shift, ymax),
            shape=self.grid.shape_2d,
        )
        self.assertFalse(ok)
        self.assertTrue(problems)


class AuthorSelfTest(unittest.TestCase):
    """模块自带 self_test 一并纳入套件，防止回归。"""

    def test_grid_self_test_passes(self):
        self.assertEqual(grid_module.self_test(), [])


if __name__ == "__main__":
    unittest.main()
