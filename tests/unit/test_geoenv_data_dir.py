"""C15 A5：产物根 `paths.data_dir` 覆盖的离线用例（未设时行为逐字节不变）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gis import geoenv


class TestDataRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.cfg = self.tmp / "geocode.json"
        self._patch = mock.patch.object(geoenv, "CONFIG_PATH", self.cfg)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _write_cfg(self, payload: dict) -> None:
        self.cfg.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_default_is_repo_data_dir(self):
        # 配置文件不存在 → 缺省仓库 data/
        self.assertFalse(self.cfg.exists())
        self.assertEqual(geoenv.data_root(), geoenv.DATA_DIR)

    def test_empty_data_dir_keeps_default(self):
        self._write_cfg({"paths": {"data_dir": ""}})
        self.assertEqual(geoenv.data_root(), geoenv.DATA_DIR)

    def test_explicit_absolute_dir(self):
        target = self.tmp / "research_out"
        self._write_cfg({"paths": {"data_dir": str(target)}})
        self.assertEqual(geoenv.data_root(), target)

    def test_relative_dir_resolves_against_repo_root(self):
        self._write_cfg({"paths": {"data_dir": "work/products"}})
        self.assertEqual(geoenv.data_root(), geoenv.ROOT / "work" / "products")

    def test_broken_config_falls_back_to_default(self):
        self.cfg.write_text("{ not json", encoding="utf-8")
        self.assertEqual(geoenv.data_root(), geoenv.DATA_DIR)

    def test_three_kinds_land_under_configured_root(self):
        target = self.tmp / "out"
        self._write_cfg({"paths": {"data_dir": str(target)}})
        for kind in geoenv.DATA_KINDS:
            p = geoenv.data_path(kind, "x.tif")
            self.assertEqual(p, target / kind / "x.tif")
            self.assertTrue(p.parent.is_dir(), "三出口子目录必须自动创建")
        # 嵌套路径同样自动建目录
        nested = geoenv.data_path("derived", "sub", "y.nc")
        self.assertEqual(nested, target / "derived" / "sub" / "y.nc")
        self.assertTrue(nested.parent.is_dir())

    def test_unset_behavior_matches_history(self):
        p = geoenv.data_path("derived", "legacy.tif")
        self.assertEqual(p, geoenv.DATA_DIR / "derived" / "legacy.tif")
        self.assertEqual(geoenv.data_path("deliver"), geoenv.DELIVER_DIR)

    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            geoenv.data_path("nowhere", "x")

    def test_describe_exposes_data_root(self):
        target = self.tmp / "out2"
        self._write_cfg({"paths": {"data_dir": str(target)}})
        with mock.patch.object(geoenv, "gdal_bin", return_value=None), \
                mock.patch.object(geoenv, "gee_credentials_path",
                                  return_value=self.tmp / "cred"):
            self.assertEqual(geoenv.describe()["data_root"], str(target))


if __name__ == "__main__":
    unittest.main()
