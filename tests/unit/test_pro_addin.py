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


@unittest.skipUnless(ZIP_PATH.exists(), "add-in zip 未构建")
class DockpaneDamlTest(unittest.TestCase):
    """C11 A2/A3 补充：dockPane 声明（DAML dockPanes 容器）与开面板按钮。

    契约要点（ProGuide DockPanes + xsd）：dockPane 放专用 <dockPanes> 容器；
    className=VM（Contracts.DockPane）；<content>=视图（UserControl）；
    condition 已弃用不用。静态文本断言，代码基类由 dotnet 构建保证。
    """

    @classmethod
    def setUpClass(cls):
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(ZIP_PATH) as z:
            cls.xml = z.read("Config.daml")
        cls.ns = {"d": "http://schemas.esri.com/DADF/Registry"}
        cls.root = ET.fromstring(cls.xml)

    def _dockpane(self):
        dp = self.root.findall(".//d:dockPanes/d:dockPane", self.ns)
        self.assertEqual(len(dp), 1, f"dockPane 应恰有 1 个声明：{len(dp)}")
        return dp[0]

    def test_dockpane_declared_in_dockpanes_container(self):
        dp = self._dockpane()
        self.assertEqual(dp.get("id"), "GeoCodePro_Dockpane")
        self.assertEqual(dp.get("className"), "GeoCodePro.GeoCodeDockpaneViewModel")

    def test_dockpane_content_and_dock_attrs(self):
        dp = self._dockpane()
        content = dp.findall("d:content", self.ns)
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0].get("className"), "GeoCodePro.GeoCodeDockpaneView")
        self.assertIn(dp.get("dock"), {"top", "left", "right", "bottom", "float", "group"})
        self.assertTrue(dp.get("dockWith"), "dockWith 应指定首显停靠目标")
        self.assertNotIn("condition", dp.attrib, "condition 已弃用，dockpane 不应使用")

    def test_show_dockpane_button_declared(self):
        declared = [b for b in self.root.findall(".//d:button", self.ns) if b.get("id")]
        show = [b for b in declared if b.get("id") == "GeoCodePro_ShowDockpane"]
        self.assertEqual(len(show), 1, "功能区应有开面板按钮 GeoCodePro_ShowDockpane")
        self.assertEqual(show[0].get("className"), "GeoCodePro.ShowDockpaneButton")

    def test_show_dockpane_button_caption_carries_geocode(self):
        """A5：Alt+Q 命令搜索按 caption 建索引——caption 必须含 GeoCode。

        实测证据（C11 第一轮独立验收）：查询 "Status Panel" 能命中该按钮，
        查询 "GeoCode" 不能（id/tooltip 均不被索引）；故 caption 必须含 GeoCode。
        """
        declared = [b for b in self.root.findall(".//d:button", self.ns) if b.get("id")]
        show = [b for b in declared if b.get("id") == "GeoCodePro_ShowDockpane"]
        self.assertEqual(len(show), 1)
        caption = show[0].get("caption") or ""
        self.assertIn("GeoCode", caption, f"按钮 caption 必须含 GeoCode 才能被 Alt+Q 搜到：{caption!r}")

    def test_dockpane_not_in_controls_container(self):
        """xsd 约束：controls 容器不允许 dockPane 子元素（防回归到错误位置）。"""
        for controls in self.root.findall(".//d:controls", self.ns):
            self.assertEqual(controls.findall("d:dockPane", self.ns), [])

    def test_source_files_match_zip_daml(self):
        """zip 内 DAML 与仓库源码一致（打包未过期）。"""
        src = (ROOT / "Pro" / "Config.daml").read_bytes()
        self.assertEqual(src, self.xml)


class DockpaneStatusSourceTest(unittest.TestCase):
    """A6：状态区数据来源与刷新（源码级静态断言：C# 无法在离线单测里执行）。

    实测证据（C11 第一轮独立验收）：面板运行态计数恒为 0（无 UI 线程计时器）、
    端口写死 6530（GEOCODE_PRO_PORT 覆盖不显示）——本类把这两条判据钉成回归防线。
    """

    def _read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_status_port_read_from_host_not_hardcoded(self):
        """端口须读 McpServerHost.Port，不得出现 6530 字面量。"""
        src = self._read("Pro/GeoCodeDockpaneViewModel.cs")
        self.assertIn("host.Port", src)
        self.assertNotIn('"6530', src, "状态文本不得写死 6530（须随 GEOCODE_PRO_PORT 覆盖变化）")
        self.assertNotIn("6530 服务", src, "状态标题须由实际端口格式化生成")

    def test_status_refresh_uses_ui_thread_timer(self):
        """面板可见期间须由 UI 线程计时器周期刷新（DispatcherTimer）。"""
        src = self._read("Pro/GeoCodeDockpaneView.xaml.cs")
        self.assertIn("DispatcherTimer", src)
        self.assertIn("_statusTimer.Start()", src)
        self.assertIn("_statusTimer.Stop()", src)
        self.assertIn("IsVisibleChanged", src, "面板隐藏时应停表（仅可见期间刷新）")
        self.assertIn("Interval = TimeSpan.FromSeconds", src)


    def test_csproj_declares_reproducible_build(self):
        """A3（风险 1/3）：交付 DLL 须跨路径可复现，且不与本地调试符号冲突。

        实测：多路（工作区 + 不同路径长度/有无 .git 的副本）重建得到同一 sha256；
        关符号之所以必要，是因为 PDB GUID / CodeView 调试目录会随构建路径变化；
        符号只在 Release 关掉，其他配置保留 portable 供本地调试。
        """
        src = self._read("Pro/GeoCodePro.csproj")
        self.assertIn("<Deterministic>true</Deterministic>", src)
        self.assertIn("<IncludeSourceRevisionInInformationalVersion>false</IncludeSourceRevisionInInformationalVersion>", src)
        self.assertIn("<PathMap>", src)
        self.assertIn("<DebugType Condition=\"'$(Configuration)' == 'Release'\">none</DebugType>", src)
        self.assertIn("<DebugSymbols Condition=\"'$(Configuration)' == 'Release'\">false</DebugSymbols>", src)
        self.assertIn("<DebugType Condition=\"'$(Configuration)' != 'Release'\">portable</DebugType>", src)
        self.assertNotIn("<DebugType>none</DebugType>", src, "不得无条件关符号（会连带取消本地调试符号）")

    def test_status_counters_cover_both_execution_paths(self):
        """A6（风险 5）：面板按钮执行工具也须让计数增长——HTTP 请求与工具执行分列展示。

        面板与 HTTP 两条路径都经 ResultRegistry.Record 汇合，故计数在那里累加；
        McpServerHost.Requests 仍只数 HTTP 请求，两者互补、互不冒充。
        """
        vm = self._read("Pro/GeoCodeDockpaneViewModel.cs")
        self.assertIn("ResultRegistry.ToolCalls", vm)
        self.assertIn("HTTP 请求", vm)
        self.assertIn("工具执行", vm)
        reg = self._read("Pro/ResultRegistry.cs")
        self.assertIn("Interlocked.Increment(ref _toolCalls)", reg)
        self.assertIn("public static long ToolCalls", reg)


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
        # C12：就绪判定以「端点是不是本 add-in」为准（listening 降为诊断字段）
        self.assertIsInstance(v["endpoint_alive"], bool)
        if v["installed"] and v["endpoint_alive"]:
            self.assertTrue(r.ok)
        if v["listening"] and not v["endpoint_alive"]:
            self.assertFalse(r.ok, "端口有监听但非本 add-in 端点时不得报就绪")

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

    def test_addin_endpoint_identity_contract(self):
        """C12（A7/A14）：端点探测基准 = add-in GET / 的 name 字段。

        preflight 靠 `name == "geocode-pro"` 判定「这是本 add-in 的端点」；
        add-in 側一旦改名/删字段，本断言立即失败，提示同步更新探测基准。
        """
        self.assertEqual(preflight.PRO_ENDPOINT_NAME, "geocode-pro")
        src = (ROOT / "Pro" / "McpServerHost.cs").read_text(encoding="utf-8")
        self.assertIn('["name"] = "geocode-pro"', src,
                      "add-in 的 GET / info 必须仍声明 name=geocode-pro（C12 探测基准）")

    def test_probe_all_contains_pro_addin(self):
        res = preflight.probe_all()
        self.assertIn("pro_addin", res)


if __name__ == "__main__":
    unittest.main()
