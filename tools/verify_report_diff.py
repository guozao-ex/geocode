"""两份 verify_all 报告的漂移对比工具（离线、只读）。

背景
----
tests/verify_all.py 每次运行把结果写成 logs/verify_all_report.json
（schema geocode.verify-all.report.v1）。两次运行之间「哪些检查项从 RUN 掉回 SKIP、
耗时是否异常漂移、probe 判据是否翻转」此前只能人工翻报告，本工具把它机械化。

用法
----
::

    python tools/verify_report_diff.py <当前报告> <基线报告> [选项]

    --json                 以 JSON 输出结构化差异（供自动化消费）
    --duration-ratio 2.0   耗时漂移的倍数阈值（默认 2.0）
    --duration-abs-s 5.0   耗时漂移的绝对阈值（秒，默认 5.0）

覆盖的差异类别：检查项集合增删、层位变化（run <-> skip）、状态变化（pass/fail/skip）、
summary 计数变化（run/passed/failed/skipped）、耗时漂移、probe 判据变化。

耗时漂移判据：同一检查项同时满足 max/min >= --duration-ratio 与 |delta| > --duration-abs-s
才算漂移（默认「2 倍」且「绝对差超过 5 秒」）。arcpy 项耗时受并发影响极大（实测 24-28 s，
与其他重任务并发时可涨到 117 s+），「且」语义可压掉小基数放大（例如 0.1 s -> 0.3 s）的误报。

退出码
------
0 无漂移 / 1 有漂移 / 2 用法或输入错误（报告不存在、非 JSON、schema 不符、缺必需字段、
同一报告内检查项重名、阈值非法等）。输入错误只打印可读消息，不抛裸 traceback。

本工具全程只读：不写、不删、不改任何盘上产物。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPORT_SCHEMA = "geocode.verify-all.report.v1"
DIFF_SCHEMA = "geocode.verify-report-diff.v1"

# summary 中参与计数比对的键（与 tests/verify_all.py 写出的 summary 一致）。
SUMMARY_KEYS = ("run", "passed", "failed", "skipped")

# probe 的「判据字段」：只有这些字段变化才算判据变化。
# size_bytes 是测量值（缓存被重建就会变），不构成判据变化，故不列入。
PROBE_JUDGEMENT_FIELDS = {
    "cache_probe": ("path", "exists", "min_bytes", "hit"),
    "tool_probe": ("cmd", "uvx", "ok"),
}


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


def load_report(path_text: str, label: str) -> dict:
    """读取并校验一份报告；任何不满足约定结构的情况都抛 InputError。"""
    path = Path(path_text)
    if not path.is_file():
        raise InputError(f"{label}报告不存在：{path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InputError(f"{label}报告不是合法 UTF-8 文本：{path}（{exc}）") from exc
    except OSError as exc:
        raise InputError(f"{label}报告无法读取：{path}（{exc}）") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(
            f"{label}报告不是合法 JSON：{path}（{exc.msg}，第 {exc.lineno} 行第 {exc.colno} 列）"
        ) from exc
    if not isinstance(data, dict):
        raise InputError(f"{label}报告顶层必须是 JSON 对象：{path}")
    schema = data.get("schema")
    if schema != REPORT_SCHEMA:
        raise InputError(
            f"{label}报告 schema 不符：期望 {REPORT_SCHEMA!r}，实际 {schema!r}（{path}）"
        )
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise InputError(f"{label}报告缺 checks 数组：{path}")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise InputError(f"{label}报告 checks[{index}] 不是 JSON 对象：{path}")
        name = check.get("name")
        if not isinstance(name, str) or not name:
            raise InputError(f"{label}报告 checks[{index}] 缺合法 name：{path}")
        if name in seen:
            raise InputError(f"{label}报告内检查项重名：{name!r}（{path}）")
        seen.add(name)
    if not isinstance(data.get("summary"), dict):
        raise InputError(f"{label}报告缺 summary 对象：{path}")
    return data


def _index_checks(report: dict) -> dict:
    return {check["name"]: check for check in report["checks"]}


def _probe_changes(name: str, previous, current) -> list:
    """比较同一检查项的 probe；只在判据字段变化时产出条目。"""
    if not isinstance(previous, dict):
        previous = None
    if not isinstance(current, dict):
        current = None
    if previous is None and current is None:
        return []
    previous_kind = previous.get("kind") if previous else None
    current_kind = current.get("kind") if current else None
    if previous_kind != current_kind:
        return [{"name": name, "field": "kind", "from": previous_kind, "to": current_kind}]
    fields = PROBE_JUDGEMENT_FIELDS.get(current_kind)
    if fields is None:
        if previous == current:
            return []
        return [{"name": name, "field": "raw", "from": previous, "to": current}]
    changes = []
    for field in fields:
        before, after = previous.get(field), current.get(field)
        if before != after:
            changes.append({"name": name, "field": field, "from": before, "to": after})
    return changes


def _duration_drift(name: str, previous: dict, current: dict, ratio_threshold: float, abs_threshold: float):
    """耗时漂移：倍数与绝对差需同时越阈；非正/非数值耗时不做比值。"""
    before = previous.get("duration_s")
    after = current.get("duration_s")
    for value in (before, after):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
    if before <= 0 or after <= 0:
        return None
    delta = float(after) - float(before)
    if abs(delta) <= abs_threshold:
        return None
    ratio = max(before, after) / min(before, after)
    if ratio < ratio_threshold:
        return None
    return {
        "name": name,
        "from_s": round(float(before), 3),
        "to_s": round(float(after), 3),
        "delta_s": round(delta, 3),
        "ratio": round(ratio, 3),
        "direction": "slower" if delta > 0 else "faster",
    }


def build_diff(current_report: dict, baseline_report: dict, ratio_threshold: float, abs_threshold: float) -> dict:
    current_checks = _index_checks(current_report)
    baseline_checks = _index_checks(baseline_report)

    added = sorted(set(current_checks) - set(baseline_checks))
    removed = sorted(set(baseline_checks) - set(current_checks))
    layer_changes: list = []
    status_changes: list = []
    probe_changes: list = []
    duration_drifts: list = []

    for name in sorted(set(current_checks) & set(baseline_checks)):
        current, baseline = current_checks[name], baseline_checks[name]
        if current.get("layer") != baseline.get("layer"):
            layer_changes.append({"name": name, "from": baseline.get("layer"), "to": current.get("layer")})
        if current.get("status") != baseline.get("status"):
            status_changes.append({"name": name, "from": baseline.get("status"), "to": current.get("status")})
        probe_changes.extend(_probe_changes(name, baseline.get("probe"), current.get("probe")))
        drift = _duration_drift(name, baseline, current, ratio_threshold, abs_threshold)
        if drift is not None:
            duration_drifts.append(drift)

    summary_changes = []
    for key in SUMMARY_KEYS:
        before = baseline_report["summary"].get(key)
        after = current_report["summary"].get(key)
        if before != after:
            summary_changes.append({"key": key, "from": before, "to": after})

    categories = {
        "checks_added": added,
        "checks_removed": removed,
        "layer_changes": layer_changes,
        "status_changes": status_changes,
        "summary_changes": summary_changes,
        "duration_drifts": duration_drifts,
        "probe_changes": probe_changes,
    }
    counts = {key: len(value) for key, value in categories.items()}
    drift = any(counts.values())
    return {
        "schema": DIFF_SCHEMA,
        "ok": not drift,
        "current": {
            "path": None,
            "started_at": current_report.get("started_at"),
            "overall": current_report.get("overall"),
            "summary": current_report["summary"],
        },
        "baseline": {
            "path": None,
            "started_at": baseline_report.get("started_at"),
            "overall": baseline_report.get("overall"),
            "summary": baseline_report["summary"],
        },
        "duration_thresholds": {"ratio": ratio_threshold, "abs_s": abs_threshold},
        "drift": drift,
        "counts": counts,
        "categories": categories,
    }


def _format_probe_item(item: dict) -> str:
    before = json.dumps(item["from"], ensure_ascii=False)
    after = json.dumps(item["to"], ensure_ascii=False)
    return f"  {item['name']}: {item['field']} {before} -> {after}"


def render_text(diff: dict) -> str:
    thresholds = diff["duration_thresholds"]
    lines = [
        f"当前报告：{diff['current']['path']}",
        f"基线报告：{diff['baseline']['path']}",
        f"耗时漂移阈值：倍数 >= {thresholds['ratio']} 且 绝对差 > {thresholds['abs_s']}s",
    ]
    counts = diff["counts"]
    if not diff["drift"]:
        lines.append("无漂移：检查项集合、层位、状态、summary 计数、耗时与 probe 判据完全一致。")
        lines.append("退出码 0")
        return "\n".join(lines)

    categories = diff["categories"]
    total = sum(counts.values())
    breakdown = "、".join(f"{key}={value}" for key, value in counts.items())
    lines.append(f"发现漂移：共 {total} 处（{breakdown}）")

    if categories["checks_added"]:
        lines.append(f"[检查项新增] {len(categories['checks_added'])} 项")
        lines.extend(f"  + {name}" for name in categories["checks_added"])
    if categories["checks_removed"]:
        lines.append(f"[检查项消失] {len(categories['checks_removed'])} 项")
        lines.extend(f"  - {name}" for name in categories["checks_removed"])
    if categories["layer_changes"]:
        lines.append(f"[层位变化] {len(categories['layer_changes'])} 项")
        lines.extend(f"  {item['name']}: {item['from']} -> {item['to']}" for item in categories["layer_changes"])
    if categories["status_changes"]:
        lines.append(f"[状态变化] {len(categories['status_changes'])} 项")
        lines.extend(f"  {item['name']}: {item['from']} -> {item['to']}" for item in categories["status_changes"])
    if categories["summary_changes"]:
        lines.append(f"[summary 计数变化] {len(categories['summary_changes'])} 项")
        lines.extend(f"  {item['key']}: {item['from']} -> {item['to']}" for item in categories["summary_changes"])
    if categories["duration_drifts"]:
        lines.append(f"[耗时漂移] {len(categories['duration_drifts'])} 项")
        lines.extend(
            "  {name}: {from_s}s -> {to_s}s（{direction}，{ratio}x，delta {delta_s}s）".format(**item)
            for item in categories["duration_drifts"]
        )
    if categories["probe_changes"]:
        lines.append(f"[probe 判据变化] {len(categories['probe_changes'])} 项")
        lines.extend(_format_probe_item(item) for item in categories["probe_changes"])
    lines.append("退出码 1")
    return "\n".join(lines)


def _report_input_error(message: str, as_json: bool) -> None:
    print(f"verify_report_diff.py: 输入错误：{message}", file=sys.stderr)
    if as_json:
        print(json.dumps({"schema": DIFF_SCHEMA, "ok": False, "error": message}, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        prog="verify_report_diff.py",
        description="对比两份 verify_all 报告的漂移（离线、只读）。",
    )
    parser.add_argument("current", help="当前报告路径，如 logs/verify_all_report.json")
    parser.add_argument("baseline", help="基线报告路径，如 logs/verify_all_report.c14-baseline.json")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结构化差异")
    parser.add_argument("--duration-ratio", type=float, default=2.0, help="耗时漂移倍数阈值（默认 2.0）")
    parser.add_argument("--duration-abs-s", type=float, default=5.0, help="耗时漂移绝对阈值，秒（默认 5.0）")
    args = parser.parse_args(argv)
    try:
        if args.duration_ratio <= 0:
            raise InputError(f"--duration-ratio 必须 > 0，实际 {args.duration_ratio}")
        if args.duration_abs_s < 0:
            raise InputError(f"--duration-abs-s 必须 >= 0，实际 {args.duration_abs_s}")
        current_report = load_report(args.current, "当前")
        baseline_report = load_report(args.baseline, "基线")
        diff = build_diff(current_report, baseline_report, args.duration_ratio, args.duration_abs_s)
    except InputError as exc:
        _report_input_error(str(exc), args.json)
        return 2
    except Exception as exc:
        _report_input_error(f"未预期的内部错误：{type(exc).__name__}: {exc}", args.json)
        return 2

    diff["current"]["path"] = str(Path(args.current))
    diff["baseline"]["path"] = str(Path(args.baseline))
    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print(render_text(diff))
    return 1 if diff["drift"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
