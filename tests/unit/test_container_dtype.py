"""C18 容器 dtype 契约：解析 / 守卫 / 落容器 的离线用例。

覆盖 brief 的 A1（两出口容器一致）、A2 + A10（守卫与 collapse 提升）、A9（序列化红线 8）、
A6（旧产物容器归一）的离线部分。全部用临时目录与内存数组，不触网（`test_offline_guard` 约束）。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gis.container import (                                    # noqa: E402
    assert_product_container,
    cast_to_container,
    guard_container_capacity,
    read_bounded_sample,
    resolve_container,
    rewrite_geotiff_container,
)
from gis.spec import (                                         # noqa: E402
    DEFAULT_CONTAINER_DTYPE,
    INTEGER_CONTAINER_DTYPES,
    ArtifactSpec,
    SpecError,
)

from tests.unit._helpers import make_spec                        # noqa: E402


class ContainerContractTest(unittest.TestCase):
    """契约层：默认值、取值校验与序列化（A9）。"""

    def test_default_container_is_float32(self):
        self.assertEqual(DEFAULT_CONTAINER_DTYPE, "float32")
        self.assertEqual(make_spec().container_dtype, "float32")
        self.assertEqual(resolve_container(make_spec()), "float32")

    def test_unknown_container_rejected(self):
        with self.assertRaises(SpecError):
            make_spec(container_dtype="float16").validate()

    def test_float_dtype_with_integer_container_rejected(self):
        """自相矛盾声明静态拦下（S2 反射率误用整数容器的第一种形态）。"""
        with self.assertRaises(SpecError):
            make_spec(dtype="float32", container_dtype="uint16").validate()
        # 量纲与容器一致的组合放行（整数数据 + 整数容器不在本 change 支持面内，
        # 由 resolve_container 在出口层拒绝，见下一类）
        make_spec(dtype="uint16", container_dtype="float64").validate()

    def test_nan_nodata_rejected(self):
        """`nodata=nan` 与整数容器互斥；契约层拒绝 NaN 声明（无数据语义由出口层统一写 NaN）。"""
        with self.assertRaises(SpecError):
            make_spec(nodata=float("nan")).validate()

    def test_serialization_omits_default_container(self):
        """红线 8：缺省即缺席；显式非默认才落键；两者指纹逐字节相同。"""
        base = make_spec()
        self.assertNotIn("container_dtype", base.to_dict())
        declared = base.with_(container_dtype="float64")
        self.assertEqual(declared.to_dict()["container_dtype"], "float64")
        self.assertEqual(declared.fingerprint(), base.fingerprint())
        # 往返不丢
        self.assertEqual(ArtifactSpec.from_dict(declared.to_dict()).container_dtype, "float64")
        self.assertEqual(
            ArtifactSpec.from_dict(base.to_dict()).container_dtype, DEFAULT_CONTAINER_DTYPE
        )

    def test_integer_containers_rejected_at_resolve(self):
        """整数容器一律拒绝：NaN 掩膜语义装不进整数容器（附条件 2 的拒绝侧）。"""
        for bad in INTEGER_CONTAINER_DTYPES:
            with self.subTest(container=bad):
                spec = make_spec(dtype="uint16", container_dtype=bad)
                with self.assertRaises(SpecError) as ctx:
                    resolve_container(spec)
                self.assertIn("NaN", str(ctx.exception))


class DimensionGuardTest(unittest.TestCase):
    """量纲守卫：破坏性自证（A2）。"""

    def test_fractional_data_rejected_for_integer_container(self):
        """**破坏性自证**：0–1 小数 + 整数容器必须被拦下（不是恰好通过）。"""
        import numpy as np

        arr = np.array([[0.0695, 0.0, 1.0], [0.5, np.nan, 0.25]], dtype="float64")
        with self.assertRaises(SpecError) as ctx:
            guard_container_capacity(arr, "uint16", context="s2_truecolor.tif:")
        msg = str(ctx.exception)
        self.assertIn("uint16", msg)
        self.assertIn("静默数据损坏", msg)
        self.assertIn("0.0695", msg)          # 报出首个越界样值，便于定位

    def test_fractional_data_passes_float_containers(self):
        """同一份数据 + 浮点容器必须放行（守卫不得误伤正常路径）。"""
        import numpy as np

        arr = np.array([[0.0695, 0.0, 1.0]], dtype="float64")
        for ok in ("float32", "float64"):
            with self.subTest(container=ok):
                guard_container_capacity(arr, ok, context="s2_truecolor.tif:")

    def test_integer_data_passes_integer_container(self):
        """整数数据 + 整数容器不丢小数（本轮虽在出口层拒绝，守卫判据本身要正确）。"""
        import numpy as np

        guard_container_capacity(np.array([[1, 2, 3]], dtype="int32"), "uint16")

    def test_cast_only_changes_container(self):
        """容器实施只 astype，不改数值（float64 → float32 的容差在 1e-6 内）。"""
        import numpy as np

        arr = np.linspace(0.0, 1.0, 1001, dtype="float64").reshape(1, -1)
        out = cast_to_container(arr, "float32")
        self.assertEqual(out.dtype, np.dtype("float32"))
        self.assertLessEqual(float(np.max(np.abs(out.astype("float64") - arr))), 1e-6)


class ProductContainerTest(unittest.TestCase):
    """产物侧：GeoTIFF/NetCDF 容器归一与核验（A6 的离线部分）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_tif(self, path: Path, dtype: str, nodata=None) -> None:
        import numpy as np
        import rasterio
        from rasterio.transform import Affine

        data = np.linspace(0.0, 1.0, 12, dtype="float64").reshape(3, 4)
        with rasterio.open(
            path, "w", driver="GTiff", width=4, height=3, count=1, dtype=dtype,
            crs="EPSG:4326", transform=Affine(0.001, 0.0, 116.3, 0.0, -0.001, 40.0),
            nodata=nodata,
        ) as ds:
            ds.write(data.astype(dtype), 1)

    def test_rewrite_geotiff_container_floats(self):
        """float64 → float32 就地归一：容器变、数值域不变（容差 ≤ 1e-6）。"""
        import numpy as np
        import rasterio

        p = self.tmp / "legacy.tif"
        self._write_tif(p, "float64")
        spec = make_spec(container_dtype="float32")
        self.assertTrue(assert_product_container(p, spec))       # 先证偏差存在

        info = rewrite_geotiff_container(p, "float32")

        self.assertTrue(info["changed"])
        self.assertEqual(info["from"], "float64")
        self.assertEqual(info["to"], "float32")
        self.assertEqual(assert_product_container(p, spec), [])   # 归一后一致
        with rasterio.open(p) as ds:
            self.assertEqual(list(ds.dtypes), ["float32"])
            vals = ds.read(1)
        self.assertLessEqual(float(np.max(np.abs(vals.astype("float64") - np.linspace(0.0, 1.0, 12).reshape(3, 4)))), 1e-6)

    def test_rewrite_is_noop_when_container_matches(self):
        """容器已一致 ⇒ 不重写（不制造无谓的字节变化）。"""
        p = self.tmp / "current.tif"
        self._write_tif(p, "float32")
        before = p.stat().st_mtime_ns
        info = rewrite_geotiff_container(p, "float32")
        self.assertFalse(info["changed"])
        self.assertEqual(p.stat().st_mtime_ns, before)

    def test_rewrite_bounds_memory_and_keeps_nodata(self):
        import rasterio

        p = self.tmp / "nan_nodata.tif"
        self._write_tif(p, "float64", nodata=float("nan"))
        rewrite_geotiff_container(p, "float32")
        with rasterio.open(p) as ds:
            self.assertEqual(list(ds.dtypes), ["float32"])
            self.assertTrue(ds.nodata != ds.nodata)              # NaN 声明保留

    def test_ncdf_written_with_contract_container(self):
        """A1 的 NetCDF 侧：落盘容器 = 契约（离线覆盖 `_write_ncdf_with_container`）。

        不跑 GEE：直接给一份 float64 数据集，验证写出的 NetCDF 变量容器是契约值，
        且数值域在 1e-6 内不变（容器只改表示精度）。
        """
        import numpy as np
        import xarray as xr

        from gis.emit import _write_ncdf_with_container

        spec = make_spec(container_dtype="float32")
        y = xr.Dataset(
            {"B4": (("y", "x"), np.linspace(0.0, 1.0, 12, dtype="float64").reshape(3, 4))}
        )
        out = self.tmp / "product.nc"
        _write_ncdf_with_container(y, out, spec)

        with xr.open_dataset(out) as ds:
            self.assertEqual(str(ds["B4"].dtype), "float32")
            got = ds["B4"].values.astype("float64")
        want = np.linspace(0.0, 1.0, 12).reshape(3, 4)
        self.assertLessEqual(float(np.max(np.abs(got - want))), 1e-6)
        self.assertEqual(assert_product_container(out, spec), [])

    def test_read_bounded_sample_is_windowed(self):
        """采样只读一窗口：1200 万像素级的产物也不会因守卫整份入内存。"""
        p = self.tmp / "sample.tif"
        self._write_tif(p, "float64")
        block = read_bounded_sample(p, block_rows=2)
        self.assertEqual(block.shape, (1, 2, 4))


if __name__ == "__main__":
    unittest.main()
