# -*- coding: utf-8 -*-
"""C9 p1b-arcgis-addin 离线单测：打包结构（A2）+ preflight 探测项（A8）。

全部离线：zip 结构读本地构建产物；preflight 探测用 mock 路径与关阒端口，
不做网络依赖（6530 监听探测用本机 socket connect_ex，零字节）。
"""

import tempfile
from unittest import mock
import unittest
import zipfile
from pathlib import Path

from gis import preflight

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "Pro" / "GeoCodePro.addin.zip"


@unittest.skipUnless(ZIP_PATH.exists(), "add-in zip 未构建（先跑 scripts/package_pro_addin.py build）")
class PackageStructureTest(unittest.TestCase):
    """A2：zip 根 Config.daml + Install/*.dll 标准布局。"""

    def test_zip_layout_config_daml_at_root(self):
        with zipfile.ZipFile(ZIP_PATH) as z:
            names = z.namelist()
        self.assertIn("Config.daml", names)

    def test_zip_layout_install_dlls(self):
        with zipfile.ZipFile(ZIP_PATH) as z:
            names = z.namelist()
            install_dlls = [n for n in names if n.startswith("Install/") and n.endswith(".dll")]
        self.assertGreaterEqual(len(install_dlls), 1, f"Install 目录应含程序集：{names}")

    def test_zip_no_stray_top_level_entries(self):
        with zipfile.ZipFile(ZIP_PATH) as z:
            names = z.namelist()
        top = {n.split("/")[0] for n in names}
        self.assertLessEqual(top, {"Config.daml", "Install"},
                             f"zip 根只允许 Config.daml 与 Install/：{top}")


@unittest.skipUnless(ZIP_PATH.exists(), "add-in zip 未构建")
class DamlValidityTest(unittest.TestCase):
    """A3：Config.daml 可解析、模块/按钮声明齐全。"""

    def test_daml_parses_and_declarations(self):
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(ZIP_PATH) as z:
            xml = z.read("Config.daml")
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "{http://schemas.esri.com/DADF/Registry}ArcGIS")
        ns = {"d": "http://schemas.esri.com/DADF/Registry"}
        modules = root.findall(".//d:insertModule", ns)
        self.assertEqual(len(modules), 1)
        module = modules[0]
        self.assertEqual(module.get("autoLoad"), "true")
        buttons = root.findall(".//d:button", ns)
        # 至少一个工具按钮（排除 group 内的 refID 引用：只看带 id 的声明）
        declared = [b for b in buttons if b.get("id")]
        self.assertGreaterEqual(len(declared), 1)
        self.assertEqual(module.get("className"), "GeoCodePro.GeoCodeModule")


class ProAddinPreflightTest(unittest.TestCase):
    """A8：preflight 探测项（Pro 安装 / add-in 部署 / 端口监听），mock 路径离线可测。"""

    def test_all_good_with_mock_addin_dir(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "fake.esriAddInX").write_bytes(b"zip")
            r = preflight.check_pro_addin(addin_dir=d, port=6530)
        v = r.value
        # installed 依赖本机真实 Pro 安装（已核实存在）；deployed 用 mock 目录
        self.assertTrue(v["deployed"])
        self.assertEqual(v["addin_files"], ["fake.esriAddInX"])
        self.assertEqual(v["port"], 6530)
        self.assertIsInstance(v["listening"], bool)
        if v["installed"] and v["listening"]:
            self.assertTrue(r.ok)

    def test_legacy_esriaddin_still_counts_deployed(self):
        """旧扩展名 .esriAddIn 也算部署（兼容探测），但 Pro 3.7 实际不识别——README 已记录。"""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "legacy.esriAddIn").write_bytes(b"zip")
            r = preflight.check_pro_addin(addin_dir=d, port=6530)
        self.assertTrue(r.value["deployed"])

    def test_not_deployed_when_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            r = preflight.check_pro_addin(addin_dir=Path(td), port=6530)
        self.assertFalse(r.ok)
        self.assertIn(r.code, {"pro-addin-not-deployed", "pro-mcp-not-listening", "pro-not-installed"})
        if not r.value["deployed"]:
            self.assertEqual(r.code, "pro-addin-not-deployed")
            self.assertIn("package_pro_addin", r.reason)

    def test_deploy_false_reason_is_actionable(self):
        with tempfile.TemporaryDirectory() as td:
            r = preflight.check_pro_addin(addin_dir=Path(td), port=6530)
        self.assertTrue(r.reason.startswith("症状："), "失败码必须配可执行 reason")

    def test_port_override_from_env(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
                "os.environ", {"GEOCODE_PRO_PORT": "6999"}):
            r = preflight.check_pro_addin(addin_dir=Path(td), port=None)
        self.assertEqual(r.value["port"], 6999)

    def test_probe_all_contains_pro_addin(self):
        res = preflight.probe_all()
        self.assertIn("pro_addin", res)


if __name__ == "__main__":
    unittest.main()
