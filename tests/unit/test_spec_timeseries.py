"""时序字段行为：期窗口推导、校验、序列化往返（A7，离线）。

对应 docs/comet/changes/p2-timeseries/spec.md 的时序字段规格：
- time_step 节奏切片：N 由（起止÷步长）推导，月末/年末钳制，N 上限
- time_ranges 显式多段：条目原样使用，允许不等长
- 两字段互斥；校验消息写清怎么修
"""

import json
import unittest

from _helpers import make_spec

from gis.spec import (
    MAX_TIME_PERIODS,
    ArtifactSpec,
    SpecError,
    time_periods,
)


def cube_spec(**over) -> ArtifactSpec:
    """时序基准 spec（月度切片）。"""
    kw = dict(time_step="month", time_range=("2024-06-01", "2024-08-31"))
    kw.update(over)
    return make_spec(**kw)


class TimePeriodDerivationTest(unittest.TestCase):
    """期窗口推导：确定性、月末钳制、N 上限、零期数。"""

    def test_monthly_slices_contiguous_windows(self):
        ps = time_periods(cube_spec())
        self.assertEqual(ps, (
            ("2024-06-01", "2024-07-01"),
            ("2024-07-01", "2024-08-01"),
            ("2024-08-01", "2024-09-01"),
        ))

    def test_last_window_may_extend_beyond_end(self):
        # 08-31 的终点被最后一期的完整窗口（至 09-01）覆盖——保证末段整窗
        ps = time_periods(cube_spec())
        self.assertEqual(ps[-1][1], "2024-09-01")

    def test_month_end_clamped(self):
        ps = time_periods(cube_spec(time_range=("2024-01-31", "2024-04-30")))
        self.assertEqual(ps[0], ("2024-01-31", "2024-02-29"))   # 闰年月末钳制
        self.assertEqual(ps[1], ("2024-02-29", "2024-03-29"))

    def test_year_step_and_boundary(self):
        ps = time_periods(cube_spec(time_step="year",
                                    time_range=("2022-05-10", "2024-05-10")))
        self.assertEqual(ps, (
            ("2022-05-10", "2023-05-10"),
            ("2023-05-10", "2024-05-10"),
        ))

    def test_week_and_day_steps(self):
        ps = time_periods(cube_spec(time_step="week",
                                    time_range=("2024-01-01", "2024-01-22")))
        self.assertEqual(len(ps), 3)
        self.assertEqual(ps[0], ("2024-01-01", "2024-01-08"))
        ps = time_periods(cube_spec(time_step="day",
                                    time_range=("2024-01-01", "2024-01-04")))
        self.assertEqual(ps, (
            ("2024-01-01", "2024-01-02"),
            ("2024-01-02", "2024-01-03"),
            ("2024-01-03", "2024-01-04"),
        ))

    def test_time_ranges_passthrough_uneven_windows(self):
        tr = (("2024-01-01", "2024-03-31"), ("2024-06-01", "2024-09-30"))
        ps = time_periods(cube_spec(time_step=None, time_range=None, time_ranges=tr))
        self.assertEqual(ps, tr)

    def test_time_ranges_with_gaps_and_overlap_allowed(self):
        tr = (("2024-01-01", "2024-02-01"), ("2024-01-15", "2024-03-01"))
        ps = time_periods(cube_spec(time_step=None, time_range=None, time_ranges=tr))
        self.assertEqual(ps, tr)

    def test_zero_periods_raises(self):
        with self.assertRaises(SpecError) as cm:
            time_periods(cube_spec(time_range=("2024-06-01", "2024-06-01")))
        self.assertIn("期数为 0", str(cm.exception))

    def test_period_cap_raises(self):
        with self.assertRaises(SpecError) as cm:
            time_periods(cube_spec(time_step="day",
                                   time_range=("2000-01-01", "2035-01-01")))
        self.assertIn(str(MAX_TIME_PERIODS), str(cm.exception))

    def test_non_timeseries_raises(self):
        with self.assertRaises(SpecError):
            time_periods(make_spec(time_step=None, time_ranges=None))


class TimeSeriesValidationTest(unittest.TestCase):
    """互斥、合法值、必需依赖；SpecError 消息给得出路。"""

    def test_mutual_exclusion(self):
        with self.assertRaises(SpecError) as cm:
            cube_spec(time_ranges=(("2024-01-01", "2024-02-01"),)).validate()
        self.assertIn("互斥", str(cm.exception))

    def test_invalid_step(self):
        with self.assertRaises(SpecError) as cm:
            cube_spec(time_step="hour").validate()
        self.assertIn("day", str(cm.exception))   # 消息列出可选项

    def test_step_requires_time_range(self):
        with self.assertRaises(SpecError) as cm:
            cube_spec(time_range=None).validate()
        self.assertIn("time_range", str(cm.exception))

    def test_time_ranges_rejects_start_after_end(self):
        with self.assertRaises(SpecError) as cm:
            cube_spec(time_step=None, time_range=None,
                      time_ranges=(("2024-09-01", "2024-01-01"),)).validate()
        self.assertIn("起点晚于终点", str(cm.exception))

    def test_time_ranges_rejects_non_pair(self):
        with self.assertRaises(SpecError):
            cube_spec(time_step=None, time_range=None,
                      time_ranges=(("2024-01-01",),)).validate()

    def test_time_ranges_rejects_empty(self):
        with self.assertRaises(SpecError):
            cube_spec(time_step=None, time_range=None, time_ranges=()).validate()

    def test_valid_specs_pass_validate(self):
        cube_spec().validate()
        cube_spec(time_step=None, time_range=None,
                  time_ranges=(("2024-01-01", "2024-03-31"),)).validate()
        # 单期 spec（无时序字段）照常通过
        make_spec().validate()


class TimeSeriesSerializationTest(unittest.TestCase):
    """to_dict / from_dict 往返保真；is_timeseries / is_collection 标志。"""

    def test_roundtrip_time_step(self):
        s = cube_spec()
        r = ArtifactSpec.from_dict(json.loads(json.dumps(s.to_dict())))
        self.assertEqual(r.time_step, "month")
        self.assertIsNone(r.time_ranges)
        self.assertEqual(r.time_range, s.time_range)
        self.assertEqual(r.fingerprint(), s.fingerprint())

    def test_roundtrip_time_ranges(self):
        tr = (("2024-01-01", "2024-03-31"), ("2024-06-01", "2024-09-30"))
        s = cube_spec(time_step=None, time_range=None, time_ranges=tr)
        r = ArtifactSpec.from_dict(json.loads(json.dumps(s.to_dict())))
        self.assertEqual(r.time_ranges, tr)
        self.assertIsNone(r.time_step)
        self.assertEqual(r.fingerprint(), s.fingerprint())

    def test_flags(self):
        self.assertTrue(cube_spec().is_timeseries)
        self.assertTrue(cube_spec().is_collection)
        self.assertTrue(make_spec(reducer=None).is_timeseries is False)
        self.assertFalse(make_spec(time_step=None).is_timeseries)
        self.assertTrue(make_spec(time_step=None, time_ranges=(("2024-01-01", "2024-02-01"),)
                                  ).is_timeseries)
        # 单期 spec（time_range + reducer，无时序字段）仍是 collection 但非时序
        self.assertTrue(make_spec().is_collection)
        self.assertFalse(make_spec().is_timeseries)


if __name__ == "__main__":
    unittest.main()
