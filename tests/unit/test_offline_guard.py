"""离线守卫（A1 的机器证据）：被测模块与测试代码不得导入 ee / 网络库。

用 AST 扫描：
- gis/spec.py、gis/grid.py、gis/crs_rules.py（被测契约层）
- tests/unit/ 下全部测试文件与共享 helper（_helpers.py）

导入（顶层模块名）命中禁用名单即失败。

注：`import gis.spec` 会执行 gis 包 __init__，传递导入 emit 等模块。
实测（独立 Verifier 验收，2026-10-06）：ee 是 geoenv.py 函数内的延迟导入，
测试导入链**不会加载 ee**；传递链中唯一的网络相关引用是
emit → urllib.request —— 测试导入链**仅发生 import、不触发网络调用**
（urlopen 位于 emit._download 函数体内，仅下载路径才执行）。本守卫约束
被测模块与测试代码自身；__init__ 传递链不在 C1 范围，不构成网络访问。

pyproj 是允许导入：D7/D10 授权其用于 CRS 元数据查询（读 EPSG 名称校验
中央经线），且它是 compute_grid 生产实现的既有依赖。
"""

import ast
import pathlib
import unittest

BANNED = {
    "ee", "earthengine_api",
    "requests", "httpx", "aiohttp", "urllib3",
    "urllib", "http", "socket", "ftplib", "smtplib",
}

ROOT = pathlib.Path(__file__).resolve().parents[2]  # 仓库根 D:/DEV/geocode
TARGETS = [
    ROOT / "gis" / "spec.py",
    ROOT / "gis" / "grid.py",
    ROOT / "gis" / "crs_rules.py",
] + sorted((ROOT / "tests" / "unit").glob("*.py"))  # 含 _helpers.py 与本文件


def imported_top_level_names(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


class OfflineGuardTest(unittest.TestCase):
    def test_no_banned_imports_in_contract_layer_and_tests(self):
        offenders = {}
        for f in TARGETS:
            bad = imported_top_level_names(f) & BANNED
            if bad:
                offenders[str(f.relative_to(ROOT))] = sorted(bad)
        self.assertFalse(
            offenders,
            f"违反离线约束：发现 ee / 网络库导入：{offenders}",
        )


if __name__ == "__main__":
    unittest.main()
