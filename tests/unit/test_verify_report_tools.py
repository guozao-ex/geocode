"""tools/ 两个报告核查工具的离线用例（unittest，零网络）。

覆盖：
- verify_report_diff.py：无漂移 / 层位翻转 / 耗时漂移（含「且」语义与阈值覆盖）/
  probe 判据翻转 / 检查项增删 / summary 计数变化 / 损坏输入退出码 2 / --json 结构；
- verify_facts_check.py：全对时零违规 / 计数不一致 / 措辞与盘上事实相反 /
  「不在主工作区」断言 / probe 缺失与非法的 / 层位与耗时不一致 / probe.hit 与层位不自洽 /
  损坏输入退出码 2 / --json 结构；
- tools/*.py 的 AST 级禁网断言（既有 tests/unit/test_offline_guard.py 的扫描名单不含
  tools/，且该文件属本 change 的禁止修改面，故这把守卫落在本文件里）。

风格与 tests/unit 既有用例一致：只读文件、只用标准库、不导入 socket/http/urllib，
故不破坏既有离线守卫。
"""

import ast
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# c22 #2：工具文件缺失时不要让整个 tests/unit 因 import 失败而整片红 ——
# 只有两个工具都在盘上时才 import，并在功能用例上加 skipIf；工具齐全时行为与原来完全一致。
TOOL_FILES = {
    "verify_facts_check": TOOLS_DIR / "verify_facts_check.py",
    "verify_report_diff": TOOLS_DIR / "verify_report_diff.py",
}
MISSING_TOOLS = sorted(name for name, path in TOOL_FILES.items() if not path.is_file())

if not MISSING_TOOLS:
    from tools import verify_facts_check, verify_report_diff  # noqa: E402  (需先落 sys.path)

_TOOLS_SKIP_REASON = f"tools/ 缺 {MISSING_TOOLS}：相关用例归 SKIP（c22）"

REPORT_SCHEMA = "geocode.verify-all.report.v1"

# 与 tests/unit/test_offline_guard.py 的 BANNED 同口径（此处独立定义，避免耦合到别的测试模块）。
BANNED_IMPORTS = {
    "ee", "earthengine_api",
    "requests", "httpx", "aiohttp", "urllib3",
    "urllib", "http", "socket", "ftplib", "smtplib",
}


def _check(name, layer="run", status="pass", duration=1.0, skip_reason=None, probe=None,
           include_probe=True, module="m"):
    item = {
        "name": name,
        "module": module,
        "layer": layer,
        "status": status,
        "duration_s": duration,
        "log_path": None,
        "skip_reason": skip_reason,
        "note": None,
        "fail_summary": None,
    }
    if include_probe:
        item["probe"] = probe
    return item


def _report(checks, summary=None):
    if summary is None:
        summary = {
            "run": sum(1 for c in checks if c.get("layer") == "run"),
            "passed": sum(1 for c in checks if c.get("status") == "pass"),
            "failed": sum(1 for c in checks if c.get("status") == "fail"),
            "skipped": sum(1 for c in checks if c.get("status") == "skip"),
        }
    return {
        "schema": REPORT_SCHEMA,
        "started_at": "2026-10-18T00:00:00+00:00",
        "finished_at": "2026-10-18T00:00:10+00:00",
        "overall": "pass",
        "summary": summary,
        "network_allowlist": ["127.0.0.1"],
        "checks": checks,
        "coverage_matrix": {},
        "uncovered_modules": [],
    }


def _cache_probe(path, exists=True, size_bytes=1024, min_bytes=4096, hit=False):
    return {
        "kind": "cache_probe",
        "path": path,
        "exists": exists,
        "size_bytes": size_bytes,
        "min_bytes": min_bytes,
        "hit": hit,
    }


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _invoke(module, argv):
    """调用工具的 main()，捕获 stdout/stderr，返回 (退出码, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(argv)
    return code, out.getvalue(), err.getvalue()


@unittest.skipIf(MISSING_TOOLS, _TOOLS_SKIP_REASON)
class ReportDiffToolTest(unittest.TestCase):
    """verify_report_diff.py：漂移检测与退出码语义。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self, current, baseline, *extra):
        current_path = _write(self.tmp / "current.json", current)
        baseline_path = _write(self.tmp / "baseline.json", baseline)
        argv = [str(current_path), str(baseline_path), *extra]
        return _invoke(verify_report_diff, argv)

    def test_identical_reports_report_no_drift(self):
        report = _report([_check("a"), _check("b", "skip", "skip", 0.0)])
        code, out, err = self._run(report, report)
        self.assertEqual(code, 0, err)
        self.assertIn("无漂移", out)

    def test_layer_flip_is_detected(self):
        baseline = _report([_check("render", "skip", "skip", 0.0, skip_reason="缓存缺失")])
        current = _report([_check("render", "run", "pass", 4.0)])
        code, out, err = self._run(current, baseline, "--json")
        self.assertEqual(code, 1, err)
        payload = json.loads(out)
        self.assertTrue(payload["drift"])
        self.assertFalse(payload["ok"])
        self.assertEqual(
            payload["categories"]["layer_changes"],
            [{"name": "render", "from": "skip", "to": "run"}],
        )
        self.assertEqual(payload["categories"]["status_changes"],
                         [{"name": "render", "from": "skip", "to": "pass"}])

    def test_duration_doubling_is_detected(self):
        baseline = _report([_check("tests-unit", duration=18.6)])
        current = _report([_check("tests-unit", duration=45.0)])
        code, out, err = self._run(current, baseline, "--json")
        self.assertEqual(code, 1, err)
        drifts = json.loads(out)["categories"]["duration_drifts"]
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0]["name"], "tests-unit")
        self.assertEqual(drifts[0]["direction"], "slower")
        self.assertGreaterEqual(drifts[0]["ratio"], 2.0)

    def test_duration_drift_requires_both_ratio_and_absolute_delta(self):
        # 0.1s -> 0.3s：倍数 3x 但绝对差只有 0.2s，按「且」语义不算漂移。
        baseline = _report([_check("tiny", duration=0.1)])
        current = _report([_check("tiny", duration=0.3)])
        code, out, err = self._run(current, baseline)
        self.assertEqual(code, 0, err)
        self.assertIn("无漂移", out)

    def test_duration_drift_thresholds_are_configurable(self):
        baseline = _report([_check("tiny", duration=0.1)])
        current = _report([_check("tiny", duration=0.3)])
        code, out, err = self._run(current, baseline, "--duration-abs-s", "0.1", "--json")
        self.assertEqual(code, 1, err)
        payload = json.loads(out)
        self.assertEqual(payload["duration_thresholds"], {"ratio": 2.0, "abs_s": 0.1})
        self.assertEqual(len(payload["categories"]["duration_drifts"]), 1)

    def test_illegal_duration_threshold_exits_2(self):
        report = _report([_check("a")])
        code, out, err = self._run(report, report, "--duration-ratio", "0")
        self.assertEqual(code, 2)
        self.assertIn("--duration-ratio", err)

    def test_probe_hit_flip_is_detected(self):
        probe_hit = _cache_probe("data/derived/p0_cache.tif", exists=True, size_bytes=9000, hit=True)
        probe_miss = _cache_probe("data/derived/p0_cache.tif", exists=False, size_bytes=0, hit=False)
        baseline = _report([_check("render", "run", "pass", 4.0, probe=probe_hit)])
        current = _report([_check("render", "skip", "skip", 0.0, skip_reason="缓存缺失", probe=probe_miss)])
        code, out, err = self._run(current, baseline, "--json")
        self.assertEqual(code, 1, err)
        changes = json.loads(out)["categories"]["probe_changes"]
        fields = {(item["field"], item["from"], item["to"]) for item in changes}
        self.assertIn(("hit", True, False), fields)
        self.assertIn(("exists", True, False), fields)

    def test_probe_size_change_is_not_a_judgement_change(self):
        baseline = _report([_check("render", probe=_cache_probe("data/x.tif", size_bytes=9000, hit=True))])
        current = _report([_check("render", probe=_cache_probe("data/x.tif", size_bytes=9500, hit=True))])
        code, out, err = self._run(current, baseline, "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["categories"]["probe_changes"], [])

    def test_check_added_and_removed_are_detected(self):
        baseline = _report([_check("keep"), _check("gone")])
        current = _report([_check("keep"), _check("fresh")])
        code, out, err = self._run(current, baseline, "--json")
        self.assertEqual(code, 1, err)
        categories = json.loads(out)["categories"]
        self.assertEqual(categories["checks_added"], ["fresh"])
        self.assertEqual(categories["checks_removed"], ["gone"])

    def test_summary_count_change_is_detected(self):
        baseline = _report([_check("a")], summary={"run": 1, "passed": 1, "failed": 0, "skipped": 0})
        current = _report([_check("a")], summary={"run": 1, "passed": 0, "failed": 1, "skipped": 0})
        code, out, err = self._run(current, baseline, "--json")
        self.assertEqual(code, 1, err)
        changes = json.loads(out)["categories"]["summary_changes"]
        self.assertEqual({item["key"] for item in changes}, {"passed", "failed"})

    def test_missing_report_exits_2(self):
        current = _write(self.tmp / "current.json", _report([_check("a")]))
        argv = [str(current), str(self.tmp / "nope.json")]
        code, _out, err = _invoke(verify_report_diff, argv)
        self.assertEqual(code, 2)
        self.assertIn("不存在", err)

    def test_invalid_json_exits_2(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        good = _write(self.tmp / "good.json", _report([_check("a")]))
        code, _out, err = _invoke(verify_report_diff, [str(bad), str(good)])
        self.assertEqual(code, 2)
        self.assertIn("不是合法 JSON", err)

    def test_schema_mismatch_exits_2(self):
        other = _report([_check("a")])
        other["schema"] = "geocode.verify-all.report.v0"
        code, _out, err = self._run(other, _report([_check("a")]))
        self.assertEqual(code, 2)
        self.assertIn("schema 不符", err)

    def test_missing_summary_exits_2(self):
        broken = _report([_check("a")])
        del broken["summary"]
        code, _out, err = self._run(broken, _report([_check("a")]))
        self.assertEqual(code, 2)
        self.assertIn("summary", err)

    def test_duplicate_check_name_exits_2(self):
        dup = _report([_check("a"), _check("a")])
        code, _out, err = self._run(dup, _report([_check("a")]))
        self.assertEqual(code, 2)
        self.assertIn("重名", err)

    def test_input_error_json_mode_still_emits_machine_readable_object(self):
        argv = [str(self.tmp / "nope.json"), str(self.tmp / "nope2.json"), "--json"]
        code, out, _err = _invoke(verify_report_diff, argv)
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)


@unittest.skipIf(MISSING_TOOLS, _TOOLS_SKIP_REASON)
class FactsCheckAssertionTest(unittest.TestCase):
    """verify_facts_check.py 的断言层（直接调 check_report，事实根可控）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _assertions(self, report, facts_root=None, main_root=None):
        root = pathlib.Path(facts_root) if facts_root else self.tmp
        violations = verify_facts_check.check_report(report, root, main_root or root)
        return [(item["id"], item["check"]) for item in violations]

    def _product(self, relative, size=9000):
        target = self.tmp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"0" * size)
        return target

    def test_consistent_report_has_zero_violations(self):
        self._product("data/derived/p0_cache.tif")
        probe = _cache_probe("data/derived/p0_cache.tif", exists=True, size_bytes=9000, hit=True)
        report = _report([
            _check("render", "run", "pass", 4.0, probe=probe),
            _check("net", "skip", "skip", 0.0, skip_reason="需要真实 GEE 像素（网络 + GEE 认证）",
                   probe=None, module="三出口"),
        ])
        self.assertEqual(self._assertions(report), [])

    def test_summary_count_mismatch_is_reported(self):
        report = _report(
            [_check("a"), _check("b", "skip", "skip", 0.0)],
            summary={"run": 2, "passed": 2, "failed": 0, "skipped": 0},
        )
        ids = self._assertions(report)
        self.assertIn(("G1", None), ids)  # summary.run 与实际 run 条数不符
        self.assertIn(("G2", None), ids)  # summary.skipped 与实际 skip 条数不符

    def test_wording_claims_missing_while_product_is_on_disk(self):
        self._product("data/derived/p0_cache.tif")
        probe = _cache_probe("data/derived/p0_cache.tif", exists=True, size_bytes=9000, hit=True)
        report = _report([
            _check("render", "skip", "skip", 0.0,
                   skip_reason="当代指纹缓存 data/derived/p0_cache.tif 不存在，未命中",
                   probe=probe),
        ])
        self.assertIn(("P5", "render"), self._assertions(report))

    def test_wording_claims_hit_while_product_is_absent(self):
        probe = _cache_probe("data/derived/stale_cache.tif", exists=False, size_bytes=0, hit=False)
        report = _report([
            _check("render", "skip", "skip", 0.0,
                   skip_reason="缓存已命中（data/derived/stale_cache.tif 在盘），本项可离线复跑",
                   probe=probe),
        ])
        self.assertIn(("P5", "render"), self._assertions(report))

    def test_negative_hit_wording_is_not_a_false_positive(self):
        # 产物确实缺失时，「未命中」是写实话术，不得被判为「声称命中」。
        probe = _cache_probe("data/derived/stale_cache.tif", exists=False, size_bytes=0, hit=False)
        report = _report([
            _check("render", "skip", "skip", 0.0,
                   skip_reason="当代指纹缓存 data/derived/stale_cache.tif 不存在，未命中",
                   probe=probe),
        ])
        self.assertEqual(self._assertions(report), [])

    def test_main_workspace_claim_violation(self):
        self._product("data/derived/big_smoke.nc")
        report = _report([
            _check("rescan-big", "skip", "skip", 0.0,
                   skip_reason="前置产物缺失：C6 大网格产物 data/derived/big_smoke.nc 不在主工作区",
                   probe=None),
        ])
        self.assertIn(("P6", "rescan-big"), self._assertions(report))

    def test_main_workspace_claim_is_fine_when_product_really_absent(self):
        report = _report([
            _check("rescan-big", "skip", "skip", 0.0,
                   skip_reason="前置产物缺失：C6 大网格产物 data/derived/big_smoke.nc 不在主工作区",
                   probe=None),
        ])
        self.assertEqual(self._assertions(report), [])

    def test_missing_probe_key_is_reported(self):
        report = _report([_check("a", probe=None, include_probe=False)])
        self.assertIn(("P1", "a"), self._assertions(report))

    def test_explicit_null_probe_is_legal(self):
        report = _report([_check("a", probe=None, include_probe=True)])
        self.assertEqual(self._assertions(report), [])

    def test_illegal_probe_kind_is_reported(self):
        report = _report([_check("a", probe={"kind": "network_probe"})])
        self.assertIn(("P1", "a"), self._assertions(report))

    def test_cache_probe_missing_required_fields_is_reported(self):
        report = _report([_check("a", probe={"kind": "cache_probe", "path": "data/x.tif"})])
        self.assertIn(("P1", "a"), self._assertions(report))

    def test_run_layer_needs_real_status_and_positive_duration(self):
        report = _report([_check("a", "run", "skip", 0.0)])
        ids = self._assertions(report)
        self.assertIn(("P3", "a"), ids)
        self.assertNotIn(("P4", "a"), ids)  # layer=run 时不走 P4

    def test_skip_layer_must_have_zero_duration(self):
        report = _report([_check("a", "skip", "skip", 3.2)])
        self.assertIn(("P4", "a"), self._assertions(report))

    def test_illegal_layer_value_is_reported(self):
        report = _report([_check("a", layer="maybe")])
        self.assertIn(("P2", "a"), self._assertions(report))

    def test_probe_hit_but_skip_layer_is_reported(self):
        probe = _cache_probe("data/derived/x.tif", exists=True, size_bytes=9000, hit=True)
        report = _report([
            _check("render", "skip", "skip", 0.0, skip_reason="缓存已命中，未入本入口 RUN 层", probe=probe),
        ])
        self.assertIn(("P7", "render"), self._assertions(report))

    def test_probe_miss_but_run_layer_is_reported(self):
        probe = _cache_probe("data/derived/x.tif", exists=False, size_bytes=0, hit=False)
        report = _report([_check("render", "run", "pass", 4.0, probe=probe)])
        self.assertIn(("P7", "render"), self._assertions(report))


@unittest.skipIf(MISSING_TOOLS, _TOOLS_SKIP_REASON)
class FactsCheckCliTest(unittest.TestCase):
    """verify_facts_check.py 的入口层：退出码、事实根回落与 --json 结构。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _consistent_report(self):
        logs = self.tmp / "logs" / "verify_all"
        logs.mkdir(parents=True, exist_ok=True)
        probe = _cache_probe("data/derived/p0_cache.tif", exists=True, size_bytes=9000, hit=True)
        checks = [
            _check("tests-unit", "run", "pass", 18.6, probe=None, include_probe=True),
            _check("render", "run", "pass", 4.0, probe=probe),
        ]
        checks[0]["log_path"] = str(logs / "tests-unit.log")
        checks[1]["log_path"] = str(logs / "render.log")
        return _report(checks)

    def test_consistent_report_exits_0_and_reports_facts_root(self):
        report = self._consistent_report()
        path = _write(self.tmp / "report.json", report)
        code, out, err = _invoke(verify_facts_check, [str(path)])
        self.assertEqual(code, 0, err)
        self.assertIn("全部通过", out)
        self.assertIn("事实根", out)

    def test_violation_exits_1_and_names_check_and_assertion(self):
        report = self._consistent_report()
        # 报告生成时产物缺失（probe.hit=False、SKIP 落层）；此后产物出现在盘上，措辞随之失效。
        report["checks"][1]["probe"] = _cache_probe("data/derived/p0_cache.tif",
                                                    exists=False, size_bytes=0, hit=False)
        report["checks"][1]["layer"] = "skip"
        report["checks"][1]["status"] = "skip"
        report["checks"][1]["duration_s"] = 0.0
        report["checks"][1]["skip_reason"] = "当代指纹缓存 data/derived/p0_cache.tif 不存在，未命中"
        report["summary"] = {"run": 1, "passed": 1, "failed": 0, "skipped": 1}
        product = self.tmp / "data" / "derived" / "p0_cache.tif"
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_bytes(b"0" * 9000)
        path = _write(self.tmp / "report.json", report)
        code, out, err = _invoke(verify_facts_check, [str(path), "--json"])
        self.assertEqual(code, 1, err)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["violation_count"], len(payload["violations"]))
        hit = [v for v in payload["violations"] if v["id"] == "P5" and v["check"] == "render"]
        self.assertTrue(hit, payload["violations"])
        self.assertIn("措辞", hit[0]["assertion"])
        self.assertIn("data/derived/p0_cache.tif", hit[0]["message"])

    def test_explicit_facts_root_is_respected(self):
        report = self._consistent_report()
        report["checks"][1]["probe"] = _cache_probe("data/derived/p0_cache.tif",
                                                    exists=False, size_bytes=0, hit=False)
        report["checks"][1]["skip_reason"] = "缓存缺失：data/derived/p0_cache.tif 不存在"
        report["checks"][1]["layer"] = "skip"
        report["checks"][1]["status"] = "skip"
        report["checks"][1]["duration_s"] = 0.0
        report["summary"] = {"run": 1, "passed": 1, "failed": 0, "skipped": 1}
        path = _write(self.tmp / "report.json", report)
        # 事实根下确有该产物 -> 报告声称「不存在」应转红
        product = self.tmp / "data" / "derived" / "p0_cache.tif"
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_bytes(b"0" * 9000)
        code, _out, err = _invoke(verify_facts_check, [str(path), "--facts-root", str(self.tmp)])
        self.assertEqual(code, 1, err)

    def test_missing_report_exits_2(self):
        code, _out, err = _invoke(verify_facts_check, [str(self.tmp / "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("不存在", err)

    def test_invalid_json_exits_2(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        code, _out, err = _invoke(verify_facts_check, [str(bad)])
        self.assertEqual(code, 2)
        self.assertIn("不是合法 JSON", err)

    def test_missing_checks_field_exits_2(self):
        broken = self._consistent_report()
        del broken["checks"]
        path = _write(self.tmp / "report.json", broken)
        code, _out, err = _invoke(verify_facts_check, [str(path)])
        self.assertEqual(code, 2)
        self.assertIn("checks", err)

    def test_facts_root_not_a_directory_exits_2(self):
        path = _write(self.tmp / "report.json", self._consistent_report())
        argv = [str(path), "--facts-root", str(self.tmp / "nope-dir")]
        code, _out, err = _invoke(verify_facts_check, argv)
        self.assertEqual(code, 2)
        self.assertIn("--facts-root", err)

    def test_input_error_json_mode_emits_machine_readable_object(self):
        argv = [str(self.tmp / "nope.json"), "--json"]
        code, out, _err = _invoke(verify_facts_check, argv)
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)


@unittest.skipIf(not sorted(TOOLS_DIR.glob("*.py")), "tools/ 下没有 .py —— 无从扫描")
class ToolsOfflineGuardTest(unittest.TestCase):
    """tools/*.py 不得导入网络/GEE 库（AST 扫描，与 test_offline_guard.py 同口径）。"""

    def test_tools_have_no_banned_imports(self):
        modules = sorted(TOOLS_DIR.glob("*.py"))
        self.assertTrue(modules, f"{TOOLS_DIR} 下没有 .py —— tools/ 缺失")
        offenders = {}
        for path in modules:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names.add(node.module.split(".")[0])
            bad = names & BANNED_IMPORTS
            if bad:
                offenders[path.name] = sorted(bad)
        self.assertFalse(offenders, f"tools/ 出现 ee / 网络库导入：{offenders}")


if __name__ == "__main__":
    unittest.main()
