"""C15 A6：缓存清单 / 显式清理的离线用例（含「当代指纹产物不得被删」守卫）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gis import cache_manage as cm

SLUG = "demo_product"
FP_NEW = "aa11bb22"          # 当代
FP_OLD = "cc33dd44"          # 历史
FP_OLD2 = "ee55ff66"         # 历史（另一个后缀）
FP_UNKNOWN = "99887766"      # 未登记 slug


def _touch(root: Path, name: str, size: int = 10) -> Path:
    p = root / name
    p.write_bytes(b"x" * size)
    return p


class TestParseArtifactName(unittest.TestCase):
    def test_parses_fingerprinted_names(self):
        self.assertEqual(
            cm.parse_artifact_name(f"{SLUG}.{FP_NEW}.tif"),
            (SLUG, FP_NEW, "tif"),
        )
        self.assertEqual(
            cm.parse_artifact_name(f"c8_mini_dongcheng.{FP_OLD}.nc"),
            ("c8_mini_dongcheng", FP_OLD, "nc"),
        )

    def test_rejects_non_conforming_names(self):
        for bad in (
            "readme.md", "data.tif", f"{SLUG}.zzzzzzzz.tif",
            f"{SLUG}.{FP_NEW}.part", f"{SLUG}.{FP_NEW}.tif.part",
            f"{SLUG}.{FP_NEW[:6]}.tif", ".cache-index.json", "",
        ):
            self.assertIsNone(cm.parse_artifact_name(bad), bad)

    def test_slug_with_dots_keeps_last_hex_segment_as_fingerprint(self):
        self.assertEqual(
            cm.parse_artifact_name(f"a.b.{FP_NEW}.tif"), ("a.b", FP_NEW, "tif"),
        )


class TestScanClassifySummarize(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        _touch(self.root, f"{SLUG}.{FP_NEW}.tif", 100)
        _touch(self.root, f"{SLUG}.{FP_OLD}.tif", 200)
        _touch(self.root, "other_thing.tif", 1)                  # 不匹配 → 不进清单
        _touch(self.root, ".hidden.tif", 1)                      # 隐藏件 → 不进清单
        self.current = {SLUG: FP_NEW}

    def test_scan_ignores_unrelated_files(self):
        names = {e.path.name for e in cm.scan(self.root)}
        self.assertEqual(names, {f"{SLUG}.{FP_NEW}.tif", f"{SLUG}.{FP_OLD}.tif"})

    def test_classify_statuses(self):
        entries = cm.classify(cm.scan(self.root), self.current)
        status = {e.fingerprint: e.status for e in entries}
        self.assertEqual(status[FP_NEW], cm.STATUS_CURRENT)
        self.assertEqual(status[FP_OLD], cm.STATUS_HISTORICAL)

    def test_unknown_slug_is_protected_class(self):
        _touch(self.root, f"ghost.{FP_UNKNOWN}.nc", 50)
        entries = cm.classify(cm.scan(self.root), self.current)
        ghost = next(e for e in entries if e.slug == "ghost")
        self.assertEqual(ghost.status, cm.STATUS_UNKNOWN)

    def test_summary_splits_bytes_by_status(self):
        entries = cm.classify(cm.scan(self.root), self.current)
        summary = cm.summarize(entries)
        self.assertEqual(summary["count"][cm.STATUS_CURRENT], 1)
        self.assertEqual(summary["count"][cm.STATUS_HISTORICAL], 1)
        self.assertEqual(summary["bytes"][cm.STATUS_CURRENT], 100)
        self.assertEqual(summary["bytes"][cm.STATUS_HISTORICAL], 200)
        self.assertEqual(summary["total_bytes"], 300)

    def test_directory_artifact_counted(self):
        d = self.root / f"{SLUG}.{FP_OLD2}.crf"
        d.mkdir()
        (d / "a.bin").write_bytes(b"y" * 33)
        entries = cm.classify(cm.scan(self.root), self.current)
        crf = next(e for e in entries if e.ext == "crf")
        self.assertTrue(crf.is_dir)
        self.assertEqual(crf.size_bytes, 33)
        self.assertEqual(crf.status, cm.STATUS_HISTORICAL)


class TestIndex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_record_and_load_roundtrip(self):
        self.assertEqual(cm.load_index(self.root), {})
        cm.record_current(self.root, SLUG, FP_NEW + "c0ffee00")
        self.assertEqual(cm.load_index(self.root), {SLUG: FP_NEW})
        # 同样的当代指纹不重复写盘（内容稳定）
        first = cm.index_path(self.root).read_text(encoding="utf-8")
        cm.record_current(self.root, SLUG, FP_NEW)
        self.assertEqual(cm.index_path(self.root).read_text(encoding="utf-8"), first)

    def test_corrupt_index_is_treated_as_empty(self):
        cm.index_path(self.root).write_text("{ not json", encoding="utf-8")
        self.assertEqual(cm.load_index(self.root), {})

    def test_index_is_hidden_from_scan(self):
        cm.save_index(self.root, {SLUG: FP_NEW})
        self.assertEqual(cm.scan(self.root), [])


class TestPrune(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.current_path = _touch(self.root, f"{SLUG}.{FP_NEW}.tif", 100)
        self.hist_path = _touch(self.root, f"{SLUG}.{FP_OLD}.tif", 200)
        self.unknown_path = _touch(self.root, f"ghost.{FP_UNKNOWN}.nc", 300)
        self.current = {SLUG: FP_NEW}
        self.entries = cm.classify(cm.scan(self.root), self.current)

    def test_plan_prune_only_historical_by_default(self):
        plan = cm.plan_prune(self.entries)
        self.assertEqual({e.path.name for e in plan}, {self.hist_path.name})

    def test_current_is_never_in_plan_even_with_unknown(self):
        for include_unknown in (False, True):
            plan = cm.plan_prune(self.entries, include_unknown=include_unknown)
            self.assertNotIn(
                self.current_path.name, {e.path.name for e in plan},
                "当代指纹产物在任何参数组合下都不得进入清理计划",
            )

    def test_unknown_only_with_explicit_flag(self):
        plan = cm.plan_prune(self.entries, include_unknown=True)
        self.assertIn(self.unknown_path.name, {e.path.name for e in plan})

    def test_run_prune_requires_confirmation(self):
        plan = cm.plan_prune(self.entries)
        with self.assertRaises(RuntimeError):
            cm.run_prune(plan, confirm=False)
        self.assertTrue(self.hist_path.exists(), "未确认时不得删除任何文件")
        self.assertTrue(self.current_path.exists())

    def test_run_prune_deletes_historical_and_keeps_current(self):
        plan = cm.plan_prune(self.entries, include_unknown=True)
        result = cm.run_prune(plan, confirm=True)
        self.assertFalse(self.hist_path.exists())
        self.assertFalse(self.unknown_path.exists())
        self.assertTrue(self.current_path.exists())
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["freed_bytes"], 500)

    def test_run_prune_removes_pam_sidecar(self):
        aux = self.hist_path.with_name(self.hist_path.name + ".aux.xml")
        aux.write_text("<PAMDataset/>", encoding="utf-8")
        result = cm.run_prune(cm.plan_prune(self.entries), confirm=True)
        self.assertFalse(aux.exists())
        self.assertIn(str(aux), result["deleted"])

    def test_run_prune_removes_directory_artifacts(self):
        d = self.root / f"{SLUG}.{FP_OLD2}.crf"
        d.mkdir()
        (d / "f.bin").write_bytes(b"z" * 7)
        entries = cm.classify(cm.scan(self.root), self.current)
        plan = cm.plan_prune(entries)
        self.assertEqual(len(plan), 2)
        cm.run_prune(plan, confirm=True)
        self.assertFalse(d.exists())
        self.assertTrue(self.current_path.exists())


class TestCli(unittest.TestCase):
    """CLI 冒烟：list 分类 + prune 必须 --confirm（不真删当前产物）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.current_path = _touch(self.root, f"{SLUG}.{FP_NEW}.tif", 100)
        self.hist_path = _touch(self.root, f"{SLUG}.{FP_OLD}.tif", 200)
        cm.record_current(self.root, SLUG, FP_NEW)

    def _run(self, argv):
        import io
        import contextlib
        from scripts import prune_cache

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = prune_cache.main(argv)
        return code, buf.getvalue()

    def test_list_json_reports_statuses(self):
        code, out = self._run(["--data-dir", str(self.root), "list", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        statuses = {e["fingerprint"]: e["status"] for e in payload["entries"]}
        self.assertEqual(statuses[FP_NEW], cm.STATUS_CURRENT)
        self.assertEqual(statuses[FP_OLD], cm.STATUS_HISTORICAL)

    def test_prune_without_confirm_is_dry(self):
        code, out = self._run(["--data-dir", str(self.root), "prune"])
        self.assertEqual(code, 2)
        self.assertTrue(self.hist_path.exists())
        self.assertIn("--confirm", out)

    def test_prune_with_confirm_deletes_only_history(self):
        code, _ = self._run(["--data-dir", str(self.root), "prune", "--confirm"])
        self.assertEqual(code, 0)
        self.assertFalse(self.hist_path.exists())
        self.assertTrue(self.current_path.exists())

    def test_mark_current_roundtrip(self):
        code, _ = self._run(["--data-dir", str(self.root), "mark-current", f"x={FP_OLD}"])
        self.assertEqual(code, 0)
        self.assertEqual(cm.load_index(self.root).get("x"), FP_OLD)


if __name__ == "__main__":
    unittest.main()
