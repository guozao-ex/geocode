"""C15 分块下载：切块计划 / 边界定位 / nodata 归一 / 重试判定的离线用例。

全部离线：不导入 ee / urllib / socket（见 test_offline_guard.py 的 BANNED 名单），
栅格用例只用 rasterio 读写本地临时文件。
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio

from gis.export_chunks import (
    BYTES_PER_PIXEL_BAND,
    MASK_BAND_BYTES_PER_BAND,
    MAX_DOWNLOAD_BYTES,
    apply_masks_to_values,
    bytes_per_pixel_band,
    chunk_request_bytes,
    coerce_nan,
    coerce_nan_stack,
    collapse_mask_bands,
    is_retryable_error,
    locate_actual_window,
    mask_band_name,
    normalize_nodata_to_nan,
    plan_download_chunks,
    window_bounds,
    write_chunk_array,
)
from gis.grid import Grid


def _grid(w=860, h=784, scale=10.0, xmin=500_000.0, ymax=4_000_000.0) -> Grid:
    return Grid(
        crs="EPSG:32650", scale=scale, width=w, height=h,
        transform=(scale, 0.0, xmin, 0.0, -scale, ymax),
    )


def _covers(windows, width, height) -> np.ndarray:
    """把窗口画成计数图：恰好 1 = 覆盖且不重叠。"""
    counts = np.zeros((height, width), dtype=np.int32)
    for w in windows:
        counts[w["y"]:w["y"] + w["height"], w["x"]:w["x"] + w["width"]] += 1
    return counts


class TestPlanDownloadChunks(unittest.TestCase):
    def test_small_grid_is_single_chunk(self):
        win = plan_download_chunks(860, 784, 3)
        self.assertEqual(win, [{"x": 0, "y": 0, "width": 860, "height": 784}])

    def test_square_plan_covers_and_fits(self):
        win = plan_download_chunks(17000, 9000, 3, bytes_per_pixel_band=9)
        counts = _covers(win, 17000, 9000)
        self.assertTrue((counts == 1).all())
        for w in win:
            self.assertLessEqual(chunk_request_bytes(w, 3, bytes_per_pixel_band=9),
                                 MAX_DOWNLOAD_BYTES)

    def test_covers_grid_exactly_once(self):
        win = plan_download_chunks(860, 784, 1, max_bytes=500_000)
        self.assertGreater(len(win), 1)
        counts = _covers(win, 860, 784)
        self.assertTrue((counts == 1).all(), "窗口必须恰好覆盖整幅网格一次")

    def test_every_chunk_within_budget(self):
        budget = 700_000
        for bands in (1, 3, 4):
            for win in plan_download_chunks(1234, 987, bands, max_bytes=budget):
                self.assertLessEqual(
                    chunk_request_bytes(win, bands), budget,
                    f"分片越限：{win} × {bands} 波段",
                )

    def test_margin_counted_in_budget(self):
        win = plan_download_chunks(2000, 500, 1, max_bytes=600_000)[0]
        raw = win["width"] * win["height"] * BYTES_PER_PIXEL_BAND
        with_margin = chunk_request_bytes(win, 1)
        self.assertGreater(with_margin, raw)
        self.assertEqual(
            raw, win["width"] * win["height"] * BYTES_PER_PIXEL_BAND,
        )
        self.assertLessEqual(with_margin, 600_000)

    def test_prefers_square_blocks(self):
        """方形块：横长矩形会被 4326 region 的“鼓包”放大（实测 1.9 倍），不允许整行切。"""
        win = plan_download_chunks(17000, 9000, 3, bytes_per_pixel_band=9)
        w0, h0 = win[0]["width"], win[0]["height"]
        self.assertLess(max(w0 / h0, h0 / w0), 2.0, f"块长宽比失衡：{w0}×{h0}")
        self.assertLess(w0, 17000, "不应把整行作为一块（会撞 4326 bbox 鼓包）")

    def test_wide_grid_splits_columns(self):
        win = plan_download_chunks(5000, 40, 1, max_bytes=20_000)
        self.assertTrue(any(w["width"] < 5000 for w in win))
        counts = _covers(win, 5000, 40)
        self.assertTrue((counts == 1).all())

    def test_deterministic(self):
        a = plan_download_chunks(860, 784, 3, max_bytes=250_000)
        b = plan_download_chunks(860, 784, 3, max_bytes=250_000)
        self.assertEqual(a, b)

    def test_default_budget_is_gee_limit(self):
        win = plan_download_chunks(860, 784, 3)
        self.assertLessEqual(chunk_request_bytes(win[0], 3), MAX_DOWNLOAD_BYTES)

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            plan_download_chunks(0, 10)
        with self.assertRaises(ValueError):
            plan_download_chunks(10, -1)
        with self.assertRaises(ValueError):
            plan_download_chunks(10, 10, 1, max_bytes=0)
        with self.assertRaises(ValueError):
            # 连 1 像素 + 余量都装不下
            plan_download_chunks(10, 10, 1, max_bytes=5)
        with self.assertRaises(ValueError):
            plan_download_chunks(10, 10, 1, bytes_per_pixel_band=0)

    def test_margin_zero_still_covers(self):
        win = plan_download_chunks(300, 200, 1, max_bytes=100_000, margin_pixels=0)
        counts = _covers(win, 300, 200)
        self.assertTrue((counts == 1).all())


class TestWindowBoundsAndLocate(unittest.TestCase):
    def test_window_bounds_exact(self):
        g = _grid()
        win = {"x": 5, "y": 3, "width": 20, "height": 10}
        self.assertEqual(
            window_bounds(g, win),
            (500_050.0, 3_999_870.0, 500_250.0, 3_999_970.0),
        )

    def test_locate_with_margin(self):
        """GEE 多回 1 像素边界余量：按实际 transform 定位并裁掉。"""
        g = _grid()
        win = {"x": 5, "y": 3, "width": 20, "height": 10}
        # 实际栅格比目标窗口每边多 1 像素（c/f 各外移 1 像素）
        actual_transform = (10.0, 0.0, 500_040.0, 0.0, -10.0, 3_999_980.0)
        loc = locate_actual_window(g, win, transform=actual_transform, size=(22, 12))
        self.assertEqual(loc, (1, 1, 20, 10))

    def test_locate_exact_fit(self):
        g = _grid()
        win = {"x": 5, "y": 3, "width": 20, "height": 10}
        transform = (10.0, 0.0, 500_050.0, 0.0, -10.0, 3_999_970.0)
        self.assertEqual(
            locate_actual_window(g, win, transform=transform, size=(20, 10)),
            (0, 0, 20, 10),
        )

    def test_locate_rejects_half_pixel_shift(self):
        g = _grid()
        win = {"x": 5, "y": 3, "width": 20, "height": 10}
        transform = (10.0, 0.0, 500_053.0, 0.0, -10.0, 3_999_970.0)
        self.assertIsNone(
            locate_actual_window(g, win, transform=transform, size=(20, 10))
        )

    def test_locate_rejects_short_coverage(self):
        g = _grid()
        win = {"x": 5, "y": 3, "width": 20, "height": 10}
        transform = (10.0, 0.0, 499_960.0, 0.0, -10.0, 3_999_980.0)
        self.assertIsNone(
            locate_actual_window(g, win, transform=transform, size=(20, 12))
        )

    def test_locate_rejects_rotated_and_other_scale(self):
        g = _grid()
        win = {"x": 0, "y": 0, "width": 10, "height": 10}
        rotated = (10.0, 1.0, 500_000.0, 0.0, -10.0, 4_000_000.0)
        self.assertIsNone(locate_actual_window(g, win, transform=rotated, size=(10, 10)))
        other_scale = (20.0, 0.0, 500_000.0, 0.0, -20.0, 4_000_000.0)
        self.assertIsNone(
            locate_actual_window(g, win, transform=other_scale, size=(10, 10))
        )


class TestBillingBytesPerBand(unittest.TestCase):
    """GEE 的计费口径实测：输出 dtype 字节 + 1 B mask（C15 A1 的 A1 实测值）。"""

    def test_known_precisions(self):
        self.assertEqual(bytes_per_pixel_band("float"), 5)      # 旧口径：float32
        self.assertEqual(bytes_per_pixel_band("double"), 9)     # S2 真彩色实际精度
        self.assertEqual(bytes_per_pixel_band("uint16"), 3)
        self.assertEqual(bytes_per_pixel_band("byte"), 2)
        self.assertEqual(bytes_per_pixel_band("  DOUBLE  "), 9)

    def test_unknown_falls_back_to_worst_case(self):
        self.assertEqual(bytes_per_pixel_band(None), 9)
        self.assertEqual(bytes_per_pixel_band(""), 9)
        self.assertEqual(bytes_per_pixel_band("mystery"), 9)

    def test_budget_shrinks_with_cost(self):
        """同一预算下，double 波段的单请求像素数必须小于 float32。"""
        px_f32 = plan_download_chunks(5000, 5000, 3, bytes_per_pixel_band=5)[0]
        px_f64 = plan_download_chunks(5000, 5000, 3, bytes_per_pixel_band=9)[0]
        self.assertGreater(px_f32["width"] * px_f32["height"],
                           px_f64["width"] * px_f64["height"])
        self.assertLessEqual(chunk_request_bytes(px_f64, 3, bytes_per_pixel_band=9),
                             MAX_DOWNLOAD_BYTES)


class TestCoerceNan(unittest.TestCase):
    def test_float_keeps_dtype_and_replaces_invalid(self):
        a = np.array([[1.0, -np.inf], [np.nan, 3.0]], dtype=np.float32)
        out = coerce_nan(a)
        self.assertEqual(out.dtype, np.float32)
        self.assertTrue(np.isnan(out[0, 1]) and np.isnan(out[1, 0]))
        self.assertEqual(out[0, 0], 1.0)
        self.assertTrue(np.isneginf(a[0, 1]), "不得就地修改入参数组")

    def test_src_nodata_value_becomes_nan(self):
        a = np.array([[0.0, 5.0]], dtype=np.float64)
        out = coerce_nan(a, 0.0)
        self.assertTrue(np.isnan(out[0, 0]))
        self.assertEqual(out[0, 1], 5.0)

    def test_integer_promoted_to_float32(self):
        a = np.array([[7, 0]], dtype=np.uint16)
        out = coerce_nan(a, None)
        self.assertEqual(out.dtype, np.float32)
        self.assertEqual(out[0, 0], 7.0)


class TestCoerceNanStack(unittest.TestCase):
    """多波段整文件级哨兵判据（C15 A1 实测事故的离线复现）。

    事故（2026-10-13 真实尺度）：GEO_TIFF 的 nodata=0.0（float64）是**整文件级**的，
    掩膜像素全波段都写 0；单波段判据把 B2 真值恰为 0 的 7 个像素误抹成 NaN，
    与 array 出口的掩膜比对失败。EE 权威采样确认这 7 个像素掩膜=1、真值=0。
    """

    def test_all_bands_sentinel_becomes_nan(self):
        s = np.array([[[0.0, 1.0]], [[0.0, 2.0]], [[0.0, 3.0]]], dtype=np.float64)
        out = coerce_nan_stack(s, 0.0)
        self.assertTrue(np.isnan(out).all(axis=0)[0, 0])
        self.assertEqual(list(out[:, 0, 1]), [1.0, 2.0, 3.0])
        self.assertFalse(np.isnan(s).any(), "不得就地修改入参")

    def test_single_band_sentinel_keeps_real_zero(self):
        """只有一个波段是哨兵 → 该像素有效，真值 0 必须保留（事故本体）。"""
        s = np.array([[[0.0159]], [[0.0251]], [[0.0]]], dtype=np.float64)
        out = coerce_nan_stack(s, 0.0)
        self.assertFalse(np.isnan(out).any(), "全波段哨兵才判无效")
        self.assertEqual(out[2, 0, 0], 0.0)

    def test_non_finite_is_per_band(self):
        s = np.array([[[np.nan]], [[np.inf]], [[2.5]]], dtype=np.float32)
        out = coerce_nan_stack(s, 0.0)
        self.assertTrue(np.isnan(out[0, 0, 0]) and np.isnan(out[1, 0, 0]))
        self.assertEqual(out[2, 0, 0], np.float32(2.5),
                         "非有限不牵连其他波段")

    def test_integer_stack_promoted(self):
        s = np.array([[[0, 7]], [[0, 8]]], dtype=np.uint16)
        out = coerce_nan_stack(s, 0)
        self.assertEqual(out.dtype, np.float32)
        self.assertTrue(np.isnan(out[0, 0, 0]) and np.isnan(out[1, 0, 0]))
        self.assertEqual(out[0, 0, 1], np.float32(7.0))

    def test_requires_three_dim(self):
        with self.assertRaises(ValueError):
            coerce_nan_stack(np.zeros((4, 5)), 0.0)


class TestMaskBands(unittest.TestCase):
    """C15 A1 追加：下载带逐波段掩膜带 → 真值 0 与哨兵 0 分开（单波段也准）。

    GEO_TIFF 的 nodata 是文件级的（float32 -inf / float64 0.0），单波段 float64
    产物无法靠哨兵区分「真值 0」与「无数据」；唯一可靠来源是 GEE 掩膜本身。
    """

    def test_mask_band_name_is_valid_ee_identifier(self):
        self.assertEqual(mask_band_name("B2"), "mask_B2")
        self.assertTrue(mask_band_name("B2")[0].isalpha(),
                        "EE 波段名不能以下划线开头（实测 __m_B2 被拒）")

    def test_mask_budget_included(self):
        """掩膜带计入预算：同一上限下分母变大 → 单请求像素数变小。"""
        plain = plan_download_chunks(5000, 5000, 3, bytes_per_pixel_band=9)[0]
        masked = plan_download_chunks(
            5000, 5000, 3,
            bytes_per_pixel_band=9 + MASK_BAND_BYTES_PER_BAND)[0]
        self.assertLess(masked["width"] * masked["height"],
                        plain["width"] * plain["height"])

    def test_apply_masks_keeps_real_zero(self):
        """掩膜=1 的真值 0 必须保留；掩膜=0 / NaN 掩膜 → NaN。"""
        vals = np.array([[[0.0159, 0.0, 5.0, 7.0]]], dtype=np.float64)
        masks = np.array([[[1.0, 1.0, 0.0, np.nan]]], dtype=np.float64)
        out = apply_masks_to_values(vals, masks)
        self.assertEqual(out[0, 0, 0], 0.0159)
        self.assertEqual(out[0, 0, 1], 0.0, "真值 0 不得抹掉（事故本体）")
        self.assertTrue(np.isnan(out[0, 0, 2]), "掩膜 0 → NaN")
        self.assertTrue(np.isnan(out[0, 0, 3]), "掩膜 NaN → NaN")
        self.assertFalse(np.isnan(vals).any(), "不得就地修改入参")

    def test_collapse_drops_mask_bands(self):
        """2n 波段下载件 → n 波段产物：掩膜→NaN、丢掩膜带、nodata=nan、无 .part 残留。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dl.tif"
            vals = np.array(
                [[[0.0159, 0.0, 1.0]], [[2.0, 2.0, 2.0]]], dtype=np.float64)
            masks = np.array(
                [[[1.0, 1.0, 0.0]], [[1.0, 1.0, 1.0]]], dtype=np.float64)
            with rasterio.open(
                p, "w", driver="GTiff", width=3, height=1, count=4,
                dtype="float64", crs="EPSG:32650",
                transform=(10.0, 0.0, 500_000.0, 0.0, -10.0, 4_000_000.0),
                nodata=0.0,
            ) as ds:
                ds.write(vals[0], 1)
                ds.write(vals[1], 2)
                ds.write(masks[0], 3)
                ds.write(masks[1], 4)
            info = collapse_mask_bands(p, 2)
            self.assertEqual(info["bands"], 2)
            with rasterio.open(p) as ds:
                self.assertEqual(ds.count, 2)
                self.assertTrue(math.isnan(ds.nodata))
                arr = ds.read()
            self.assertEqual(arr[0, 0, 1], 0.0, "掩膜=1 的真值 0 保留")
            self.assertTrue(np.isnan(arr[0, 0, 2]), "掩膜=0 → NaN")
            self.assertEqual(arr[1, 0, 0], 2.0)
            self.assertFalse(any(x.name.endswith(".part")
                                 for x in Path(tmp).iterdir()))

    def test_collapse_promotes_integer_value_band(self):
        """c18 附条件 2：整数 value band 必须提升为 float32 —— 否则 nodata=nan 越界硬失败。

        c15 记录在案的缺陷路径：`profile.update(nodata=nan)` 配上 int32 容器，rasterio
        直接抛 "nodata value, nan, is beyond the valid range of its data type, int32"。
        本用例是**破坏性自证**：先证明该组合在旧实现下必失败，再证明现在被提升且结果正确。
        """
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dl_int.tif"
            vals = np.array([[3, 0, 5]], dtype=np.int32)
            masks = np.array([[1, 1, 0]], dtype=np.int32)
            with rasterio.open(
                p, "w", driver="GTiff", width=3, height=1, count=2,
                dtype="int32", crs="EPSG:32650",
                transform=(10.0, 0.0, 500_000.0, 0.0, -10.0, 4_000_000.0),
                nodata=-9999,
            ) as ds:
                ds.write(vals, 1)
                ds.write(masks, 2)
            info = collapse_mask_bands(p, 1)
            self.assertEqual(info["dtype"], "int32")
            self.assertEqual(info["out_dtype"], "float32", "整数容器必须提升为 float32")
            with rasterio.open(p) as ds:
                self.assertEqual(ds.count, 1)
                self.assertEqual(list(ds.dtypes), ["float32"])
                self.assertTrue(math.isnan(ds.nodata))
                arr = ds.read(1)
            self.assertEqual(arr[0, 0], 3.0, "掩膜=1 的整数值保留")
            self.assertTrue(np.isnan(arr[0, 2]), "掩膜=0 → NaN（整数容器装不下，故提升）")
            self.assertFalse(any(x.name.endswith(".part")
                                 for x in Path(tmp).iterdir()))

    def test_collapse_rejects_wrong_band_count(self):
        """波段数不符要报错，不得静默退回哨兵猜测。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.tif"
            with rasterio.open(
                p, "w", driver="GTiff", width=2, height=1, count=2,
                dtype="float64", crs="EPSG:32650",
                transform=(10.0, 0.0, 500_000.0, 0.0, -10.0, 4_000_000.0),
            ) as ds:
                ds.write(np.ones((2, 1, 2), dtype=np.float64))
            with self.assertRaises(ValueError):
                collapse_mask_bands(p, 2)


class TestNodataNormalization(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, name: str, *, dtype, nodata, nodata_value):
        p = self.root / name
        data = np.array([[1.0, nodata_value], [3.5, 4.0]], dtype=dtype)
        with rasterio.open(
            p, "w", driver="GTiff", width=2, height=2, count=1,
            dtype=np.dtype(dtype).name, crs="EPSG:32650",
            transform=(10.0, 0.0, 500_000.0, 0.0, -10.0, 4_000_000.0),
            nodata=nodata,
        ) as ds:
            ds.write(data, 1)
        return p

    def test_neg_inf_rewritten_to_nan(self):
        p = self._write("a.tif", dtype=np.float32, nodata=float("-inf"),
                        nodata_value=float("-inf"))
        info = normalize_nodata_to_nan(p)
        self.assertTrue(info["changed"])
        with rasterio.open(p) as ds:
            self.assertTrue(math.isnan(ds.nodata))
            arr = ds.read(1)
        self.assertTrue(np.isnan(arr[0, 1]))
        self.assertEqual(arr[0, 0], np.float32(1.0))
        # 幂等：已是 NaN 语义则短路
        self.assertFalse(normalize_nodata_to_nan(p)["changed"])

    def test_integer_sentinel_promoted(self):
        p = self._write("b.tif", dtype=np.uint16, nodata=0, nodata_value=0)
        info = normalize_nodata_to_nan(p)
        self.assertTrue(info["changed"])
        self.assertEqual(info["out_dtype"], "float32")
        with rasterio.open(p) as ds:
            self.assertEqual(ds.dtypes[0], "float32")
            self.assertTrue(math.isnan(ds.nodata))
            arr = ds.read(1)
        self.assertTrue(np.isnan(arr[0, 1]))
        self.assertEqual(arr[0, 0], np.float32(1.0))

    def test_no_part_left_behind(self):
        p = self._write("c.tif", dtype=np.float32, nodata=0.0, nodata_value=0.0)
        normalize_nodata_to_nan(p)
        self.assertFalse(any(x.name.endswith(".part") for x in self.root.iterdir()))

    def test_multiband_sentinel_needs_all_bands(self):
        """多波段：全波段哨兵才判无数据；单波段哨兵（真值 0）保留 —— A1 事故的回归用例。"""
        p = self.root / "multi.tif"
        data = np.zeros((3, 2, 3), dtype=np.float64)
        data[:, 0, 0] = [0.0, 0.0, 0.0]        # 掩膜像素：全波段哨兵
        data[:, 0, 1] = [0.0159, 0.0251, 0.0]  # 有效像素：B2 真值恰为 0
        data[:, 1, 0] = [1.0, 2.0, 3.0]
        data[:, 1, 1] = [np.nan, 5.0, 6.0]     # 仅 B4 非有限
        with rasterio.open(
            p, "w", driver="GTiff", width=3, height=2, count=3,
            dtype="float64", crs="EPSG:32650",
            transform=(10.0, 0.0, 500_000.0, 0.0, -10.0, 4_000_000.0),
            nodata=0.0,
        ) as ds:
            ds.write(data)
        info = normalize_nodata_to_nan(p)
        self.assertTrue(info["changed"])
        with rasterio.open(p) as ds:
            self.assertTrue(math.isnan(ds.nodata))
            arr = ds.read()
        self.assertTrue(np.isnan(arr[:, 0, 0]).all(), "全波段哨兵 → 全 NaN")
        self.assertFalse(np.isnan(arr[:, 0, 1]).any(), "真值 0 必须保留")
        self.assertEqual(arr[2, 0, 1], 0.0)
        self.assertTrue(np.isnan(arr[0, 1, 1]) and arr[1, 1, 1] == 5.0,
                        "非有限只影响本波段")

    def test_write_chunk_array_places_window(self):
        p = self.root / "probe.tif"
        with rasterio.open(
            p, "w", driver="GTiff", width=4, height=4, count=1,
            dtype="float32", nodata=float("nan"),
            transform=(1.0, 0.0, 0.0, 0.0, -1.0, 4.0),
        ) as dst:
            block = np.full((2, 2), 9.0, dtype=np.float32)
            write_chunk_array(dst, {"x": 1, "y": 2, "width": 2, "height": 2}, block)
        with rasterio.open(p) as ds:
            arr = ds.read(1)
        self.assertTrue(np.isnan(arr[:2, :]).all() and np.isnan(arr[2:, 0]).all())
        self.assertEqual(arr[2, 1], 9.0)


class TestRetryClassification(unittest.TestCase):
    def _exc(self, name: str, msg: str = "", **attrs):
        cls = type(name, (Exception,), {})
        e = cls(msg)
        for k, v in attrs.items():
            setattr(e, k, v)
        return e

    def test_remote_disconnected_is_retryable(self):
        self.assertTrue(is_retryable_error(self._exc("RemoteDisconnected", "closed")))

    def test_timeout_is_retryable(self):
        self.assertTrue(is_retryable_error(TimeoutError("timed out")))
        self.assertTrue(is_retryable_error(self._exc("ReadTimeout", "read timed out")))

    def test_http_5xx_retryable_4xx_not(self):
        self.assertTrue(is_retryable_error(self._exc("HTTPError", "boom", code=503)))
        self.assertTrue(is_retryable_error(self._exc("HTTPError", "limited", code=429)))
        self.assertFalse(is_retryable_error(self._exc("HTTPError", "nope", code=404)))
        self.assertFalse(is_retryable_error(self._exc("HTTPError", "denied", code=403)))

    def test_url_error_reason_chain(self):
        e = self._exc("URLError", "urlopen error")
        e.reason = self._exc("ConnectionResetError", "reset by peer")
        self.assertTrue(is_retryable_error(e))

    def test_gee_volume_limit_is_not_retryable(self):
        e = self._exc(
            "EEException",
            "Total request size (91916930 bytes) must be less than or equal to 50331648 bytes",
        )
        self.assertFalse(is_retryable_error(e))

    def test_gee_band_not_found_is_not_retryable(self):
        self.assertFalse(is_retryable_error(
            self._exc("EEException", "Image has no band named B4")
        ))

    def test_transient_server_text_is_retryable(self):
        self.assertTrue(is_retryable_error(self._exc("EEException", "Internal error")))
        self.assertTrue(is_retryable_error(
            self._exc("EEException", "Server returned HTTP code: 503")
        ))

    def test_generic_error_not_retryable(self):
        self.assertFalse(is_retryable_error(ValueError("spec 不合法")))
        self.assertFalse(is_retryable_error(None))


if __name__ == "__main__":
    unittest.main()
