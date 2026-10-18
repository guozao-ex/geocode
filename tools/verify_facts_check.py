"""报告措辞 vs 盘上事实的机械检查（离线、只读）。

背景
----
c17 把 verify_all 的承诺立成「报告与事实一致」，并给每条检查项加了 probe 字段记录层位判据
（cache_probe / tool_probe），但这条承诺没有机械防线：报告里某条措辞与盘上事实脱节时，
只有人翻报告才会发现。c17 当时用一次性脚本人工核对，跑完即散落、不可复用。
本工具把那套核对产品化：读 logs/verify_all_report.json + 盘上事实，逐条断言。

用法
----
::

    python tools/verify_facts_check.py [报告] [--facts-root 目录] [--json]

报告默认 logs/verify_all_report.json（相对当前工作目录）。

事实根（去哪里核对盘上事实）三级回落：
1. --facts-root 显式指定；
2. 从报告 checks[].log_path 反推报告生成根（形如 <root>/logs/verify_all/<name>.log）；
3. 回落到当前工作目录。
再用 git rev-parse --git-common-dir 从事实根推出「主工作区根」（worktree -> main），
专门核对「不在主工作区」类断言 —— c17 的原始 bug 正是报告在 worktree 里生成、
却断言某产物不在主工作区，而该产物其实在主工作区盘上。

断言清单
--------
全局（G1-G4，报告内部计数自洽）：

- G1: summary.run 等于 layer == "run" 的条数
- G2: summary.skipped 等于 status == "skip" 的条数
- G3: summary.passed 等于 status == "pass" 的条数
- G4: summary.failed 等于 status == "fail" 的条数

逐项（P1-P7）：

- P1: probe 字段存在且类型合法（null / cache_probe / tool_probe），且带齐该类型的必需字段
- P2: layer 取值只能是 "run" 或 "skip"
- P3: layer == "run" 的项必须有真实 status（pass/fail）与大于 0 的耗时
- P4: layer == "skip" 的项 status 必须为 "skip" 且耗时必须为 0
- P5: cache_probe 的措辞与盘上事实一致 —— 前置产物在盘时 skip_reason 不得声称
      「不存在 / 未命中 / 缺失」；产物缺失时不得声称「已命中 / 在盘」
- P6: 断言「不在主工作区」的 skip_reason，若其点名的产物确实存在于主工作区盘上即为违规
- P7: cache_probe.hit 与层位自洽（命中应在 RUN 层，未命中不应在 RUN 层）

退出码
------
0 全通过 / 1 有违规 / 2 用法或输入错误（报告不存在、非 JSON、schema 不符、缺必需字段、
--facts-root 不是目录等）。输入错误只打印可读消息，不抛裸 traceback。

本工具全程只读：只读 logs/ 与 data/，不写、不删、不改任何盘上产物。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPORT_SCHEMA = "geocode.verify-all.report.v1"
CHECK_SCHEMA = "geocode.verify-facts-check.v1"

# probe 类型的必需字段（与 tests/verify_all.py 写出的字段一致）。
PROBE_REQUIRED_FIELDS = {
    "cache_probe": ("path", "exists", "size_bytes", "min_bytes", "hit"),
    "tool_probe": ("cmd", "ok"),
}

# 措辞判定：命中类词汇用负向后顾排除「未命中 / 不命中 / 未在盘 / 不在盘」等否定形态。
_MISSING_TOKENS = ("不存在", "未命中", "未在盘", "缺失", "不在主工作区")
_HIT_RE = re.compile(r"(?<![未不])命中|(?<![未不])在盘")
_MAIN_ABSENT_TOKENS = ("不在主工作区", "未在主工作区", "主工作区不存在")
_PATH_TOKEN_RE = re.compile(r"data/[A-Za-z0-9._/-]+")


class InputError(Exception):
    """用法或输入错误：调用方按退出码 2 处理。"""


def _configure_stdio() -> None:
    """把标准流切到 UTF-8，避免中文在 Windows 控制台里乱码或被替换。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def load_report(path_text: str) -> dict:
    """读取并校验报告；任何不满足约定结构的情况都抛 InputError。"""
    path = Path(path_text)
    if not path.is_file():
        raise InputError(f"报告不存在：{path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InputError(f"报告不是合法 UTF-8 文本：{path}（{exc}）") from exc
    except OSError as exc:
        raise InputError(f"报告无法读取：{path}（{exc}）") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(
            f"报告不是合法 JSON：{path}（{exc.msg}，第 {exc.lineno} 行第 {exc.colno} 列）"
        ) from exc
    if not isinstance(data, dict):
        raise InputError(f"报告顶层必须是 JSON 对象：{path}")
    schema = data.get("schema")
    if schema != REPORT_SCHEMA:
        raise InputError(f"报告 schema 不符：期望 {REPORT_SCHEMA!r}，实际 {schema!r}（{path}）")
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise InputError(f"报告缺 checks 数组：{path}")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise InputError(f"报告 checks[{index}] 不是 JSON 对象：{path}")
        name = check.get("name")
        if not isinstance(name, str) or not name:
            raise InputError(f"报告 checks[{index}] 缺合法 name：{path}")
        if name in seen:
            raise InputError(f"报告内检查项重名：{name!r}（{path}）")
        seen.add(name)
    if not isinstance(data.get("summary"), dict):
        raise InputError(f"报告缺 summary 对象：{path}")
    return data


def infer_generation_root(report: dict) -> tuple[Path | None, str]:
    """从 checks[].log_path 反推报告生成根；形态为 <root>/logs/verify_all/<name>.log。"""
    candidates: list[Path] = []
    for check in report["checks"]:
        log_path = check.get("log_path")
        if not isinstance(log_path, str) or not log_path:
            continue
        parts = Path(log_path).parts
        for index in range(len(parts) - 1):
            if parts[index] == "logs" and parts[index + 1] == "verify_all":
                candidates.append(Path(*parts[:index]))
                break
    distinct = sorted({str(item) for item in candidates})
    if len(distinct) == 1:
        return Path(distinct[0]), "由报告 checks[].log_path 反推"
    if len(distinct) > 1:
        return None, f"报告内 log_path 指向多个根（{distinct}），无法反推"
    return None, "报告内没有可用的 log_path"


def resolve_facts_root(report: dict, explicit: str | None) -> tuple[Path, str]:
    """确定事实根：显式参数 -> 报告反推 -> 当前工作目录。"""
    if explicit:
        root = Path(explicit)
        if not root.is_dir():
            raise InputError(f"--facts-root 不是已存在的目录：{root}")
        return root.resolve(), "由 --facts-root 显式指定"
    inferred, source = infer_generation_root(report)
    if inferred is not None:
        return inferred.resolve(), source
    return Path.cwd().resolve(), f"回落到当前工作目录（{source}）"


def resolve_main_root(facts_root: Path) -> tuple[Path, str]:
    """用 git --git-common-dir 从事实根推出主工作区根（worktree -> main）。"""
    for extra in (["--path-format=absolute"], []):
        args = ["git", "-C", str(facts_root), "rev-parse", *extra, "--git-common-dir"]
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return facts_root, "git 不可用，主工作区根 = 事实根"
        if proc.returncode == 0 and (proc.stdout or "").strip():
            common_dir = Path((proc.stdout or "").strip())
            if common_dir.name == ".git":
                return common_dir.parent.resolve(), "由 git rev-parse --git-common-dir 解析"
            return facts_root, "git-common-dir 形态未知，主工作区根 = 事实根"
    return facts_root, "不在 git 仓库内或 git 调用失败，主工作区根 = 事实根"


def _claims_missing(reason: str) -> str | None:
    for token in _MISSING_TOKENS:
        if token in reason:
            return token
    return None


def _claims_hit(reason: str) -> str | None:
    found = _HIT_RE.search(reason)
    return found.group(0) if found else None


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_report(report: dict, facts_root: Path, main_root: Path) -> list:
    """逐条断言，返回违规列表。"""
    violations: list = []
    checks = report["checks"]
    summary = report["summary"]

    def add(assertion_id: str, check_name, assertion: str, message: str, evidence=None) -> None:
        violations.append({
            "id": assertion_id,
            "check": check_name,
            "assertion": assertion,
            "message": message,
            "evidence": evidence or {},
        })

    # ---- 全局：报告内部计数自洽（G1-G4）----
    counters = (
        ("G1", "run", lambda c: c.get("layer") == "run", 'layer == "run"'),
        ("G2", "skipped", lambda c: c.get("status") == "skip", 'status == "skip"'),
        ("G3", "passed", lambda c: c.get("status") == "pass", 'status == "pass"'),
        ("G4", "failed", lambda c: c.get("status") == "fail", 'status == "fail"'),
    )
    for assertion_id, key, predicate, expr in counters:
        reported = summary.get(key)
        expected = sum(1 for check in checks if predicate(check))
        if reported != expected:
            add(
                assertion_id,
                None,
                f"summary.{key} 等于 {expr} 的条数",
                f"summary.{key} = {reported!r}，而报告中 {expr} 的条数 = {expected}",
                {"summary_key": key, "reported": reported, "expected": expected},
            )

    # ---- 逐项（P1-P7）----
    for check in checks:
        name = check["name"]
        layer = check.get("layer")
        status = check.get("status")
        duration = check.get("duration_s")
        probe = check.get("probe")
        reason = check.get("skip_reason") if isinstance(check.get("skip_reason"), str) else ""

        # P1 probe 字段存在且类型合法（c17 起每条检查项都写 probe，可能为 null）
        if "probe" not in check:
            add("P1", name, "probe 字段存在且类型合法（cache_probe / tool_probe / null）",
                "检查项缺 probe 字段（c17 之前的旧报告 schema？）", {"check_keys": sorted(check)})
        elif probe is not None:
            if not isinstance(probe, dict):
                add("P1", name, "probe 字段存在且类型合法（cache_probe / tool_probe / null）",
                    f"probe 不是 JSON 对象，而是 {type(probe).__name__}", {"probe": probe})
            else:
                kind = probe.get("kind")
                required = PROBE_REQUIRED_FIELDS.get(kind)
                if required is None:
                    add("P1", name, "probe 字段存在且类型合法（cache_probe / tool_probe / null）",
                        f"probe.kind 非法：{kind!r}（只允许 cache_probe / tool_probe）", {"probe": probe})
                else:
                    missing = [field for field in required if field not in probe]
                    if missing:
                        add("P1", name, "probe 字段存在且类型合法（cache_probe / tool_probe / null）",
                            f"probe（{kind}）缺必需字段：{missing}", {"probe": probe})

        # P2 layer 取值合法
        if layer not in ("run", "skip"):
            add("P2", name, 'layer 取值合法（"run" 或 "skip"）',
                f"layer = {layer!r}", {"layer": layer})

        # P3 / P4 层位与状态、耗时一致
        if layer == "run":
            if status not in ("pass", "fail"):
                add("P3", name, 'layer == "run" 的项必须有真实 status（pass/fail）',
                    f"status = {status!r}", {"status": status})
            if not _is_number(duration) or duration <= 0:
                add("P3", name, 'layer == "run" 的项耗时必须大于 0',
                    f"duration_s = {duration!r}", {"duration_s": duration})
        elif layer == "skip":
            if status != "skip":
                add("P4", name, 'layer == "skip" 的项 status 必须为 "skip"',
                    f"status = {status!r}", {"status": status})
            if duration != 0:
                add("P4", name, 'layer == "skip" 的项耗时必须为 0',
                    f"duration_s = {duration!r}", {"duration_s": duration})

        # P5 / P7 只对 cache_probe 生效
        if isinstance(probe, dict) and probe.get("kind") == "cache_probe":
            relative = probe.get("path")
            min_bytes = probe.get("min_bytes")
            if not _is_number(min_bytes):
                min_bytes = 0
            target = (facts_root / relative) if isinstance(relative, str) else None
            disk_exists = bool(target is not None and target.is_file())
            disk_size = target.stat().st_size if (target is not None and disk_exists) else 0
            hit_now = disk_exists and disk_size > min_bytes

            hit_claim = _claims_hit(reason)
            missing_claim = _claims_missing(reason)
            if hit_now and missing_claim:
                add("P5", name, "cache_probe 措辞与盘上事实一致",
                    f"前置产物在盘（{relative}：{disk_size} B > 阈值 {min_bytes} B），"
                    f"但 skip_reason 出现「{missing_claim}」",
                    {"probe_path": relative, "disk_exists": disk_exists,
                     "disk_size_bytes": disk_size, "min_bytes": min_bytes, "skip_reason": reason})
            if (not hit_now) and hit_claim:
                add("P5", name, "cache_probe 措辞与盘上事实一致",
                    f"前置产物缺失（{relative}：exists={disk_exists}，size={disk_size} B，"
                    f"阈值 {min_bytes} B），但 skip_reason 出现「{hit_claim}」",
                    {"probe_path": relative, "disk_exists": disk_exists,
                     "disk_size_bytes": disk_size, "min_bytes": min_bytes, "skip_reason": reason})

            recorded_hit = probe.get("hit")
            if recorded_hit is True and layer != "run":
                add("P7", name, "cache_probe.hit 与层位自洽（命中应在 RUN 层）",
                    f"probe.hit = True，但 layer = {layer!r}", {"layer": layer, "probe": probe})
            if recorded_hit is False and layer == "run":
                add("P7", name, "cache_probe.hit 与层位自洽（未命中不应在 RUN 层）",
                    f"probe.hit = False，但 layer = {layer!r}", {"layer": layer, "probe": probe})

        # P6 「不在主工作区」断言 vs 主工作区盘上事实
        if reason and any(token in reason for token in _MAIN_ABSENT_TOKENS):
            for token in _PATH_TOKEN_RE.findall(reason):
                candidate = main_root / token
                if candidate.is_file():
                    add("P6", name, "「不在主工作区」断言与主工作区盘上事实一致",
                        f"skip_reason 断言 {token} 不在主工作区，但该文件确实存在：{candidate}",
                        {"path": str(candidate), "skip_reason": reason})
                    break

    return violations


def render_text(report_path: str, facts_root: Path, facts_source: str, main_root: Path,
                main_source: str, violations: list, check_count: int) -> str:
    lines = [
        f"报告：{report_path}",
        f"事实根：{facts_root}（{facts_source}）",
        f"主工作区根：{main_root}（{main_source}）",
    ]
    if not violations:
        lines.append(f"全部通过：{check_count} 个检查项在 G1-G4 / P1-P7 上零违规。")
        lines.append("退出码 0")
        return "\n".join(lines)
    lines.append(f"发现违规：{len(violations)} 条（覆盖 {check_count} 个检查项）")
    for item in violations:
        scope = item["check"] if item["check"] else "（全局）"
        lines.append(f"  [{item['id']}] {scope} :: {item['assertion']}")
        lines.append(f"        {item['message']}")
    lines.append("退出码 1")
    return "\n".join(lines)


def _report_input_error(message: str, as_json: bool) -> None:
    print(f"verify_facts_check.py: 输入错误：{message}", file=sys.stderr)
    if as_json:
        print(json.dumps({"schema": CHECK_SCHEMA, "ok": False, "error": message},
                         ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        prog="verify_facts_check.py",
        description="报告措辞与盘上事实的机械检查（离线、只读）。",
    )
    parser.add_argument("report", nargs="?", default="logs/verify_all_report.json",
                        help="报告路径（默认 logs/verify_all_report.json）")
    parser.add_argument("--facts-root", default=None,
                        help="核对盘上事实所用的根目录；缺省时从报告 log_path 反推")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结构化结果")
    args = parser.parse_args(argv)
    try:
        report = load_report(args.report)
        facts_root, facts_source = resolve_facts_root(report, args.facts_root)
        main_root, main_source = resolve_main_root(facts_root)
        violations = check_report(report, facts_root, main_root)
    except InputError as exc:
        _report_input_error(str(exc), args.json)
        return 2
    except Exception as exc:
        _report_input_error(f"未预期的内部错误：{type(exc).__name__}: {exc}", args.json)
        return 2

    result = {
        "schema": CHECK_SCHEMA,
        "ok": not violations,
        "report": args.report,
        "facts_root": str(facts_root),
        "facts_root_source": facts_source,
        "main_root": str(main_root),
        "main_root_source": main_source,
        "checks": len(report["checks"]),
        "violations": violations,
        "violation_count": len(violations),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(args.report, facts_root, facts_source, main_root, main_source,
                          violations, len(report["checks"])))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
