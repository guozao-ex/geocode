"""C6 离线单测：emit_array 大网格分块。

覆盖：
  - plan_chunks 纯函数（预算上界、请求侧上限、确定性、边界输入）
  - 路径选择（阈值 64M、GEOCODE_ARRAY_PATH 强制与非法值、指纹不受影响）
  - 分块路径写回（产物可读回、与 direct 路径逐像素一致、NaN 语义、
    xee 原始 attrs / scale_factor / time CF 编码复刻）
  - 守卫：全程无事后 .chunk()（A3 离线层）

不碰网络：ee/xee 边界全部以伪对象替身（fake xr.Dataset + 假 open_dataset 工厂）。
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import xarray as xr

from gis.emit import (
    ARRAY_PATH_ENV,
    MAX_DIRECT_PIXELS,
    _ARRAY_BLOCK_BUDGET_BYTES,
    _GEE_REQUEST_BYTE_LIMIT,
    _XEE_DTYPE_BYTES,
    _array_path_mode,
    _compute_array_chunked_to_ncdf,
    plan_chunks,
)
from gis.grid import Grid

from _helpers import make_spec


def _grid(width: int, height: int) -> Grid:
    return Grid(
        crs="EPSG:32650", scale=10.0, width=width, height=height,
        transform=(10.0, 0.0, 500000.0, 0.0, -10.0, 4000000.0),
    )


# ---------------------------------------------------------------------------
# plan_chunks 纯函数
# ---------------------------------------------------------------------------

class TestPlanChunks(unittest.TestCase):
    def test_budget_and_request_invariants(self):
        """任意输入下：驻留 ≤ 预算（全波段最坏）、请求侧 ≤ GEE 单请求上限。"""
        cases = [
            (8200, 8200, 1, 3), (860, 784, 1, 1), (860, 784, 3, 3),
            (1000, 1000, 24, 3), (50000, 50000, 1, 1), (1, 1, 1, 1),
            (3, 100000, 7, 2), (100000, 3, 5, 13), (20001, 19999, 11, 5),
        ]
        for w, h, n, b in cases:
            c = plan_chunks(w, h, n, b)
            self.assertGreaterEqual(min(c.values()), 1, (w, h, n, b))
            self.assertLessEqual(c["index"], max(n, 1))
            px = c["index"] * c["width"] * c["height"]
            self.assertLessEqual(
                px * _XEE_DTYPE_BYTES * b, _ARRAY_BLOCK_BUDGET_BYTES,
                f"驻留超预算: {w}x{h}x{n}x{b} -> {c}",
            )
            self.assertLessEqual(
                px * (_XEE_DTYPE_BYTES + 1), _GEE_REQUEST_BYTE_LIMIT,
                f"请求侧超限: {w}x{h}x{n}x{b} -> {c}",
            )

    def test_deterministic(self):
        args = (8200, 8200, 1, 3)
        self.assertEqual(plan_chunks(*args), plan_chunks(*args))

    def test_single_period_big_grid_shape(self):
        """82km×82km @10m（大网格 smoke 网格）的块形状按预算反解（钉死算法）。"""
        c = plan_chunks(8200, 8200, 1, 3)
        self.assertEqual(c, {"index": 1, "width": 1672, "height": 1672})

    def test_small_grid_single_block(self):
        """小网格（现状规模）强制分块时整网格一块。"""
        self.assertEqual(plan_chunks(860, 784, 1, 1),
                         {"index": 1, "width": 860, "height": 784})

    def test_timeseries_index_fills(self):
        """期维装满：3 期×860×784×3 波段整立方体进一块。"""
        self.assertEqual(plan_chunks(860, 784, 3, 3),
                         {"index": 3, "width": 860, "height": 784})

    def test_long_series_splits_time(self):
        """24 期装不进预算 → 期块收缩、空间保持整网格。"""
        c = plan_chunks(1000, 1000, 24, 3)
        self.assertEqual(c, {"index": 2, "width": 1000, "height": 1000})

    def test_blocks_cover_grid(self):
        """块步长能铺满整网格（含除不尽的边缘块）。"""
        for w, h, n, b in [(8200, 8200, 1, 3), (20001, 19999, 11, 5)]:
            c = plan_chunks(w, h, n, b)
            self.assertGreaterEqual(c["width"] * -(-w // c["width"]), w)
            self.assertGreaterEqual(c["height"] * -(-h // c["height"]), h)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            plan_chunks(0, 100)
        with self.assertRaises(ValueError):
            plan_chunks(100, 0)
        with self.assertRaises(ValueError):
            plan_chunks(100, 100, 1, 8, budget_bytes=8)  # 预算 < 一个像素×8波段


# ---------------------------------------------------------------------------
# 路径选择
# ---------------------------------------------------------------------------

class _Bands3:
    bands = ("B4", "B3", "B2")


class _Bands1:
    bands = ("B4",)


class TestArrayPathMode(unittest.TestCase):
    def test_threshold(self):
        """est = 宽×高×N期×波段 ≥ 64M → chunked，否则 direct；64M 边界归 chunked。"""
        small = _grid(860, 784)          # 67.4 万像素 ×3 波段 ≈ 2.0M
        big = _grid(8200, 8200)          # 67.2M 像素 ×3 波段 ≈ 201.7M
        self.assertEqual(_array_path_mode(_Bands3(), small, None), "direct")
        self.assertEqual(_array_path_mode(_Bands3(), big, None), "chunked")
        # 恰在阈值的边界（1 波段）：8000×8000×1 = 64,000,000 → chunked；差 1 → direct
        self.assertEqual(_array_path_mode(_Bands1(), _grid(8000, 8000), None), "chunked")
        self.assertEqual(_array_path_mode(_Bands1(), _grid(7999, 8000), None), "direct")
        # 波段数计入口径：4600×4600×3 ≈ 63.5M < 64M → direct
        self.assertEqual(_array_path_mode(_Bands3(), _grid(4600, 4600), None), "direct")

    def test_env_override(self):
        big = _grid(8200, 8200)
        small = _grid(860, 784)
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "direct"}):
            self.assertEqual(_array_path_mode(_Bands3(), big, None), "direct")
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "chunked"}):
            self.assertEqual(_array_path_mode(_Bands3(), small, None), "chunked")
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "  CHUNKED "}):
            self.assertEqual(_array_path_mode(_Bands3(), small, None), "chunked")

    def test_env_invalid_readable_error(self):
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "turbo"}):
            with self.assertRaises(ValueError) as ctx:
                _array_path_mode(_Bands3(), _grid(860, 784), None)
            self.assertIn(ARRAY_PATH_ENV, str(ctx.exception))

    def test_fingerprint_untouched(self):
        """运行时开关与分块参数不进 spec、不影响指纹（A6）。"""
        spec = make_spec()
        fp_before = spec.fingerprint()
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "chunked"}):
            plan_chunks(8200, 8200, 1, 3)
            self.assertEqual(spec.fingerprint(), fp_before)
        d = spec.to_dict()
        self.assertNotIn(ARRAY_PATH_ENV, d)
        self.assertNotIn("io_chunks", d)


# ---------------------------------------------------------------------------
# 伪 xee 数据集与打开工厂
# ---------------------------------------------------------------------------

_EE_OBJ = object()  # source.build_image/build_cube 的替身返回值（不可当路径打开）


def _make_fake_ee_ds(shape_2d, n_images=1, bands=("B4", "B3", "B2"),
                     datetime_time=False):
    """形似 xee 打开结果的惰性语义 Dataset（numpy 后端，isel/values/to_netcdf 可用）。"""
    w, h = shape_2d
    t = max(int(n_images), 1)
    if datetime_time:
        time = np.arange("2024-06-01", t, dtype="datetime64[M]").astype("datetime64[ns]")
    else:
        time = np.arange(t, dtype=np.int64)
    y = 4000000.0 - np.arange(h) * 10.0
    x = 500000.0 + np.arange(w) * 10.0
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    data_vars = {}
    for i, b in enumerate(bands):
        arr = ((yy + xx + i) % 7).astype(np.float32) + 0.5
        arr[(yy * w + xx + i) % 97 == 0] = np.nan   # 确定性掩膜点
        data_vars[b] = xr.DataArray(
            arr[None, :, :].repeat(t, axis=0), dims=("time", "y", "x"),
            attrs={"id": b, "crs": "EPSG:32650"},
        )
    ds = xr.Dataset(data_vars, coords={"time": time, "y": y, "x": x})
    for b in bands:
        ds[b].encoding = {"scale_factor": 10.0, "dtype": np.float32}
    return ds


class _OpenRecorder:
    """替换 xarray.open_dataset：ee 对象 → 伪数据集并记录参数；文件路径 → 透传真库。"""

    def __init__(self, datetime_time=False):
        self.calls = []
        self.datetime_time = datetime_time
        self._real = xr.open_dataset

    def __call__(self, obj, **kw):
        if isinstance(obj, (str, os.PathLike)):
            return self._real(obj, **kw)
        self.calls.append(kw)
        return _make_fake_ee_ds(
            kw["shape_2d"], n_images=kw.get("n_images", -1),
            datetime_time=self.datetime_time,
        )


class _EndToEndBase(unittest.TestCase):
    """公共脚手架：临时产物目录 + 网络边界替身。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.derived = Path(self._tmp.name)
        self.recorder = _OpenRecorder()
        patchers = [
            mock.patch("gis.geoenv.DERIVED_DIR", self.derived),
            mock.patch("gis.emit.compute_grid", return_value=_grid(860, 784)),
            mock.patch("xarray.open_dataset", self.recorder),
            mock.patch("gis.geoenv.init_ee", return_value=(mock.MagicMock(), {})),
            mock.patch("gis.source.build_image", return_value=_EE_OBJ),
            mock.patch("gis.source.build_cube", return_value=_EE_OBJ),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def result_to_values(self, result):
        with xr.open_dataset(Path(result["path"])) as ds:
            return {v: ds[v].values.copy() for v in ds.data_vars}, ds


class TestChunkedWriter(_EndToEndBase):
    def test_chunked_writes_readable_product(self):
        """分块路径落盘 .nc 可读回：像素/NaN/dims/attrs/scale_factor 复刻 direct 结构。"""
        from gis.emit import emit_array
        from gis.jobs import Job

        spec = make_spec()
        job = Job(id="t-chunk", kind="emit", spec=spec, exit="array")
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "chunked"}):
            result = emit_array(job)

        self.assertEqual(result["dims"], {"time": 1, "y": 784, "x": 860})
        self.assertEqual(result["vars"], ["B4", "B3", "B2"])
        # 打开参数：io_chunks 来自 plan_chunks（单期 3 波段整网格一块）
        self.assertEqual(
            self.recorder.calls[0].get("io_chunks"), plan_chunks(860, 784, 1, 3),
        )
        # 产物读回与伪 xee 数据逐像素一致（float32 原值，NaN 位置一致）
        import netCDF4 as nc

        with xr.open_dataset(result["path"]) as ds:
            self.assertEqual(list(ds.data_vars), ["B4", "B3", "B2"])
            self.assertEqual(ds["B4"].dtype, np.float32)
            self.assertEqual(dict(ds.sizes), {"time": 1, "y": 784, "x": 860})
            self.assertIn("scale_factor", ds["B4"].encoding)
            self.assertEqual(ds["B4"].encoding["scale_factor"], 10.0)
            self.assertEqual(ds["B4"].attrs.get("id"), "B4")
            expected = _make_fake_ee_ds((860, 784), n_images=1)
            for b in ("B4", "B3", "B2"):
                got = ds[b].values
                want = expected[b].values
                self.assertTrue(
                    np.array_equal(np.isnan(got), np.isnan(want)),
                    f"{b} NaN 位置不一致",
                )
                diff = np.abs(got[~np.isnan(got)] - want[~np.isnan(want)])
                self.assertEqual(float(diff.max()), 0.0)
        # 文件变量序与 direct（arr.to_netcdf 的 data_vars→coords 序）一致——
        # 消除两路径产物的布局着色歧义（修复轮 Verifier 风险①）
        with nc.Dataset(result["path"]) as f:
            self.assertEqual(
                list(f.variables), ["B4", "B3", "B2", "time", "y", "x"],
            )

    def test_no_posthoc_chunk_called(self):
        """A3 离线守卫：分块路径执行期间 xr.Dataset.chunk 被调用即失败。"""
        from gis.emit import emit_array
        from gis.jobs import Job

        def _boom(*a, **k):
            raise AssertionError("分块路径调用了事后 .chunk()（触发 xee select('*') 的禁路）")

        spec = make_spec()
        job = Job(id="t-guard", kind="emit", spec=spec, exit="array")
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "chunked"}):
            with mock.patch.object(xr.Dataset, "chunk", side_effect=_boom):
                result = emit_array(job)  # 不应抛 AssertionError
        self.assertTrue(Path(result["path"]).exists())

    def test_direct_vs_chunked_pixel_identity(self):
        """A5：同一 spec 强制走两条路径，产物逐像素一致（max|diff|=0、NaN 一致）。"""
        from gis.emit import emit_array
        from gis.jobs import Job

        spec = make_spec()
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "direct"}):
            r_direct = emit_array(Job(id="t-d", kind="emit", spec=spec, exit="array"))
            vals_direct, _ = self.result_to_values(r_direct)
        Path(r_direct["path"]).unlink()  # 清缓存，避免第二次命中

        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "chunked"}):
            r_chunked = emit_array(Job(id="t-c", kind="emit", spec=spec, exit="array"))
            vals_chunked, _ = self.result_to_values(r_chunked)

        self.assertEqual(r_direct["dims"], r_chunked["dims"])
        self.assertEqual(r_direct["vars"], r_chunked["vars"])
        self.assertEqual(r_direct["sample"], r_chunked["sample"])
        # 文件变量序一致（修复轮 Verifier 风险①：消除布局着色歧义）
        import netCDF4 as nc

        with nc.Dataset(r_direct["path"]) as fd, nc.Dataset(r_chunked["path"]) as fc:
            self.assertEqual(list(fd.variables), list(fc.variables))
        for b in r_direct["vars"]:
            a, c = vals_direct[b], vals_chunked[b]
            self.assertTrue(np.array_equal(np.isnan(a), np.isnan(c)), b)
            diff = np.abs(a[~np.isnan(a)] - c[~np.isnan(c)])
            self.assertEqual(float(diff.max()), 0.0, b)

    def test_timeseries_chunked_matches_direct(self):
        """C3 交互：时序 spec 两条路径一致，time 坐标 CF 编码往返无损。"""
        from gis.emit import emit_array
        from gis.jobs import Job

        spec = make_spec(
            time_step="month", time_range=("2024-06-01", "2024-08-31"),
        )
        self.recorder.datetime_time = True
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "direct"}):
            r_direct = emit_array(Job(id="ts-d", kind="emit", spec=spec, exit="array"))
            vals_direct, _ = self.result_to_values(r_direct)
        Path(r_direct["path"]).unlink()

        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "chunked"}):
            r_chunked = emit_array(Job(id="ts-c", kind="emit", spec=spec, exit="array"))
            vals_chunked, _ = self.result_to_values(r_chunked)

        n = r_direct["timeseries"]["n_periods"]
        self.assertEqual(r_chunked["timeseries"]["n_periods"], n)
        self.assertEqual(
            r_direct["timeseries"]["time_coords"],
            r_chunked["timeseries"]["time_coords"],
        )
        for b in r_direct["vars"]:
            a, c = vals_direct[b], vals_chunked[b]
            self.assertTrue(np.array_equal(np.isnan(a), np.isnan(c)), b)
            diff = np.abs(a[~np.isnan(a)] - c[~np.isnan(c)])
            self.assertEqual(float(diff.max()), 0.0, b)

    def test_bands_none_two_step_open(self):
        """bands=None：先探测波段数再按真实波段数重开（进驻留账）。

        直接调 _compute_array_chunked_to_ncdf：spec.bands=None 能过 validate
        但 fingerprint() 会崩（spec.py 既有潜伏问题，C6 范围外不修），绕开
        _output_path 用临时文件直测函数本体。
        """
        from gis.jobs import Job

        class _SpecNoBands:
            asset = "FAKE/ASSET"
            bands = None
            is_timeseries = False

        tmp = Path(self._tmp.name) / "probe.nc"
        job = Job(id="t-nobands", kind="emit", spec=None, exit="array")
        _compute_array_chunked_to_ncdf(job, _SpecNoBands(), _grid(860, 784), None, tmp)
        self.assertEqual(len(self.recorder.calls), 2)
        self.assertIsNone(self.recorder.calls[0].get("io_chunks"))
        self.assertEqual(
            self.recorder.calls[1].get("io_chunks"), plan_chunks(860, 784, 1, 3),
        )
        with xr.open_dataset(tmp) as ds:
            self.assertEqual(list(ds.data_vars), ["B4", "B3", "B2"])

    def test_small_grid_auto_stays_direct(self):
        """A1：小网格 + auto → 现状路径，open_dataset 调用不含 io_chunks 参数。"""
        from gis.emit import emit_array
        from gis.jobs import Job

        spec = make_spec()
        job = Job(id="t-auto", kind="emit", spec=spec, exit="array")
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "auto"}):
            result = emit_array(job)
        self.assertNotIn("io_chunks", self.recorder.calls[0])
        self.assertEqual(result["dims"]["y"], 784)

    def test_big_grid_auto_goes_chunked(self):
        """A2：大网格 + auto → 分块路径（阈值判定，非强制开关）。

        单测里把阈值降为 1000 让小伪网格判为"大网格"，避免真的造 8200×8200
        数据/产物（大网格块形状已由 test_single_period_big_grid_shape 钉死）。
        """
        from gis.emit import emit_array
        from gis.jobs import Job

        spec = make_spec()
        threshold_patch = mock.patch("gis.emit.MAX_DIRECT_PIXELS", 1000)
        threshold_patch.start()
        self.addCleanup(threshold_patch.stop)
        job = Job(id="t-big", kind="emit", spec=spec, exit="array")
        with mock.patch.dict(os.environ, {ARRAY_PATH_ENV: "auto"}):
            emit_array(job)
        self.assertEqual(
            self.recorder.calls[0].get("io_chunks"), plan_chunks(860, 784, 1, 3),
        )


if __name__ == "__main__":
    unittest.main()
