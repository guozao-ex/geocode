"""结构守卫：指纹字面量不得散落在代码里（唯一事实源是 tests/unit/_helpers.py）。

三类同源事故促成的这条守卫：

- **C10 A1**：`tests/smoke_array_chunking.py` 硬编码 PV2 金值 `c9243efd`，`PROCESSING_VERSION`
  bump 之后恒 FAIL，成了长期误报；
- **C13 发布面规范 3**：按指纹指名的缓存路径与期望值必须随时代取值，不得把某时代的常量
  当作跨时代判据；
- **2026-10-11**：`stage_rescan_big` 与 `verify_all` 双双写死 `9d517910`（PV2 时代值），
  而 C4 把 PV 2→3 之后产品已改名 `2965c18a` —— 结果 rescan-big 即使联网产出也永远转不成
  RUN，且离线基线看不出来。

守卫规则：扫描 `gis/`、`tests/`、`scripts/` 下**非 docstring** 的字符串常量，命中即失败：

1. 16 位完整指纹字面量（如 `b91c09c9c6451c16`）；
2. `<8位十六进制>.<产物后缀>` 形式的产物文件名（如 `s2_chunking_big_smoke.9d517910.nc`）。

唯一豁免是单一事实源 `tests/unit/_helpers.py`（金值登记表与时代推导都在那里）。
docstring 与注释不查 —— 它们是给人看的文档，允许讲历史沿革。
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN_ROOTS = ("gis", "tests", "scripts")
EXEMPT = {"tests/unit/_helpers.py"}
HEX16 = re.compile(r"\b[0-9a-f]{16}\b")
FILENAME = re.compile(r"[0-9a-f]{8}\.(?:nc|tif|tiff|crf|gpkg|qgz|png|json|lax)\b")


def _docstrings(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                out.add(doc)
    return out


def scan_source(src: str, rel: str = "<mem>") -> list[str]:
    """返回违规描述列表；docstring 与豁免文件不计。"""
    if rel in EXEMPT:
        return []
    tree = ast.parse(src)
    docs = _docstrings(tree)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value in docs:
            continue
        for pattern, label in ((HEX16, "16 位指纹"), (FILENAME, "指纹文件名")):
            m = pattern.search(node.value)
            if m:
                bad.append(f"{rel}:{node.lineno}: {label}字面量 {m.group(0)!r}")
    return bad


class FingerprintLiteralGuardTest(unittest.TestCase):
    """不变量：代码里不得出现指纹字面量，一律从 _helpers 取。"""

    def test_no_fingerprint_literals_in_code(self):
        offenders: list[str] = []
        for root in SCAN_ROOTS:
            for dirpath, dirs, files in os.walk(os.path.join(ROOT, root)):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    path = os.path.join(dirpath, fn)
                    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                    offenders += scan_source(
                        pathlib.Path(path).read_text(encoding="utf-8"), rel
                    )
        self.assertFalse(
            offenders,
            "硬编码指纹（请改从 tests/unit/_helpers.py 取；确属历史文档就写进 docstring/注释）：\n  "
            + "\n  ".join(offenders),
        )

    def test_guard_actually_detects(self):
        """破坏性自证：构造违规源码，扫描器必须报出来（防守卫空转）。

        字面量用显式拼接构造，好让本文件自身保持干净。
        """
        bad_src = (
            'P = "s2_beijing_test." "9d517910" ".tif"\n'
            'Q = "b91c09c9" "c6451c16"\n'
        )
        found = scan_source(bad_src, "synthetic.py")
        self.assertEqual(len(found), 2, found)

    def test_docstring_and_comment_are_exempt(self):
        """docstring 与注释允许讲历史值：文档要能说清沿革，不能逼着删。

        （本文件自己也不留指纹字面量：下面的值用显式拼接构造，否则守卫会把自己抓了。）
        """
        fp = "c9243efd" + "40318c85"
        old8 = fp[:8]
        src = (
            f'"""历史沿革：金值 {fp}，产物 s2_beijing_test.{old8}.tif。"""\n'
            f"# 注释同理：s2_chunking_big_smoke.{old8}.nc 是 PV2 时代的名字\n"
            "VALUE = 1\n"
        )
        self.assertEqual(scan_source(src, "doc.py"), [])


if __name__ == "__main__":
    unittest.main()
