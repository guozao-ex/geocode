"""全量功能自动化验证入口（verify-all capability；C14 建立，c17 改为证据感知）。

一条命令跑完全部可离线执行的功能检查：
    1. tests-unit                    —— tests/unit 全量离线单测（禁网守卫约束下的 212 用例级）；
    2. smoke-tui                     —— daemon + TUI headless（复用既有 smoke）；
    3. tui-timeseries-probe          —— 时序 spec 驱动 TUI headless 渲染（复用 smoke_all 实现）；
    4. smoke-array-chunking-rescan-big —— 已有大网格产物离线重扫描（既有 smoke 的离线 stage）；
    5. daemon-endpoint-probe         —— 本入口新探针：/mcp initialize+tools/list、/rpc status、
                                        /events SSE hello，仅访问 127.0.0.1，不发起外网请求；
    6. smoke-map-renderers-qgis/-arcpy —— 条件项：当代指纹的 P0 栅格缓存存在（离线可跑）时入
                                        RUN 层，缺失时 SKIP 且文案写实；
    7. ruff-check                    —— 可选 RUN 项：uv/ruff 可用时跑 ruff 门禁并计分，
                                        不可用（含 uv 缓存冷）时 SKIP + 安装提示，不 FAIL；
    8. report-selfcheck              —— 条件 RUN 项（c21）：写完报告后对**刚落盘**的报告跑一次
                                        事实一致性自查（tools/verify_facts_check.py），把结论作为
                                        一条检查项写进同一份报告；工具缺失时 SKIP + 提示，不 FAIL。

c17 的目标是「报告与事实一致」：层位由盘上事实决定，SKIP 文案不得与盘上/环境事实相悖。
条件项与可选项一律**先探条件、再定层位**，并在报告里写清判据（cache_probe / tool_probe）。

c21 起入口**自身保证**这条承诺：main() 采用**两遍写法** —— 先落一份不含自查项的报告，再用它跑
自查，把结论插回 checks 后整体重写。最终报告因此同时是「被查对象」与「结论载体」；自查读到的
是**第 1 版**快照（不含自身），故对最终报告单独复跑 tools/verify_facts_check.py 仍应退出 0。

在线依赖检查（需真实 GEE 像素/认证）一律 SKIP 并注明原因与单独复跑方式；
本入口不提供 --online 开关。

产出：
    - 控制台：逐检查项 [PASS/FAIL/SKIP] + 汇总 + 覆盖矩阵；
    - logs/verify_all_report.json：结构化报告（含 coverage_matrix）；
    - logs/verify_all/<check>.log：RUN 项完整 stdout/stderr。

退出码：任一 RUN 项 FAIL → 1；否则 0。

用法（geo env，仓库根）：
    C:/ProgramData/miniforge3/envs/geo/python.exe tests/verify_all.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# UTF-8 输出包装；模块级引用保活，避免 smoke_all 再包一层时旧 wrapper 被 GC 后关掉底层 buffer
_utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_utf8_stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.stdout = _utf8_stdout
sys.stderr = _utf8_stderr

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PORT = 6531
LOGS = ROOT / "logs"
RUN_LOGS = LOGS / "verify_all"
REPORT_PATH = LOGS / "verify_all_report.json"

# README 声明的 9 个 MCP 工具（daemon-endpoint-probe 断言 tools/list 覆盖它们）
MCP_TOOL_NAMES = {
    "gee_status", "gee_describe", "spec_defaults", "spec_get", "spec_set",
    "job_submit", "job_list", "job_get", "job_cancel",
}

FAIL_TAIL = 1200  # 失败摘要截断长度，与 smoke_all 同口径

# 缓存命中判据，与 gis/emit.py::_ensure_raster 完全一致（exists() 且 size > 4096）
CACHE_MIN_BYTES = 4096

# ruff 门禁（可选 RUN 项，c17 / Q2=a）。版本钉死在 ruff.toml 用法注释里，两处必须一致。
RUFF_SPEC = "ruff@0.17.0"
RUFF_CMD = ["uvx", "--offline", RUFF_SPEC, "check"]
RUFF_INSTALL_HINT = (
    "安装/预热：uv tool install ruff==0.17.0，或先联网跑一次 uvx ruff@0.17.0 预热缓存；"
    "手工复跑：uvx ruff@0.17.0 check"
)


# ---------------------------------------------------------------------------
# 前置产物的当代文件名（单一事实源：tests/unit/_helpers.py）
#
# 指纹进产物名（<slug>.<指纹8位>.<ext>），PROCESSING_VERSION bump 就会改名；这里
# 统一从 _helpers 推导，**不硬编码某个时代的常量**。C6 曾把大网格产物名写死为
# 9d517910（PV2 时代值），C4 bump 2→3 后本入口的 rescan-big 恒判「产物不存在」；
# 2026-10-11 在线层补跑时发现并纠正（与 C13 发布面规范 3 同一类陷阱）。
# ---------------------------------------------------------------------------

def _era_product_name(kind: str, ext: str) -> str | None:
    """按当代 PV 推出产物文件名；推导失败返回 None（调用侧退化为不含文件名的文案）。"""
    try:
        if str(ROOT) not in sys.path:
            # 本脚本以 `python tests/verify_all.py` 运行：sys.path[0] 是 tests/，ROOT 不在其中
            sys.path.insert(0, str(ROOT))
        from tests.unit._helpers import big_chunk_product_name, p0_product_name

        return big_chunk_product_name(ext) if kind == "big_chunk" else p0_product_name(ext)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# daemon 生命周期（与 smoke_all 同款模式：检测 6531，没有就起一个，用完即停）
# ---------------------------------------------------------------------------

def daemon_alive() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start_daemon() -> subprocess.Popen:
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    # Popen 会为子进程复制句柄，父进程这边可立即关：守护进程日志照旧写进同一文件
    with open(RUN_LOGS / "daemon.log", "ab") as log:
        proc = subprocess.Popen(
            [PY, "-m", "gis.daemon"], cwd=str(ROOT), stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    for _ in range(40):
        if daemon_alive():
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("daemon 8 秒内未监听 6531，见 logs/verify_all/daemon.log")


# ---------------------------------------------------------------------------
# 检查项模型与执行
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    module: str
    layer: str                    # run | skip
    status: str = "pending"       # pass | fail | skip
    duration_s: float = 0.0
    log_path: str | None = None
    skip_reason: str | None = None
    fail_summary: str | None = None
    note: str | None = None
    # c17：条件项判定依据（写进报告，便于核对「层位为何是 run/skip」）
    probe: dict | None = None


def run_cmd(check: Check, args: list[str], timeout: int = 900) -> Check:
    """子进程执行一个既有检查，全程捕获、日志落盘、退出码定 PASS/FAIL。"""
    t0 = time.time()
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    log_path = RUN_LOGS / f"{check.name}.log"
    # 子进程 stdout 重定向为管道后仍按 locale encoding 写出（Windows 默认 cp936）；
    # 这里统一强制 UTF-8，与下面的 encoding="utf-8" 解码侧对齐。
    # （历史上写作 IO_ENCODING —— 不是 Python 认的变量名，等于没设。）
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(
            [PY, *args], cwd=str(ROOT), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        ok = proc.returncode == 0
        out, err = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        ok = False
        out = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        err += f"\n[verify_all] 超时 {timeout}s"
    log_path.write_text(f"--- cmd ---\n{PY} {' '.join(args)}\n\n--- stdout ---\n{out}\n\n--- stderr ---\n{err}",
                        encoding="utf-8")
    check.duration_s = round(time.time() - t0, 1)
    check.status = "pass" if ok else "fail"
    check.log_path = str(log_path)
    if not ok:
        check.fail_summary = out[-FAIL_TAIL:] + "\n----stderr----\n" + err[-FAIL_TAIL:]
    return check


def skip_check(check: Check, reason: str, note: str | None = None) -> Check:
    check.status = "skip"
    check.skip_reason = reason
    check.note = note
    return check


# ---------------------------------------------------------------------------
# daemon-endpoint-probe（新探针：仅 127.0.0.1，不走系统代理）
# ---------------------------------------------------------------------------

def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post_json(path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with _opener().open(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def daemon_endpoint_probe(check: Check) -> Check:
    """对 127.0.0.1:6531 的 /mcp、/rpc、/events 做端点级断言（离线）。"""
    t0 = time.time()
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    log_path = RUN_LOGS / f"{check.name}.log"
    lines: list[str] = []
    failures: list[str] = []

    def assert_(label: str, cond: bool, detail: str = "") -> None:
        lines.append(f"{'PASS' if cond else 'FAIL'} {label}" + (f" —— {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(label)

    try:
        # /mcp initialize
        code, body = _post_json("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                         "params": {"protocolVersion": "2024-11-05"}})
        srv = (body.get("result") or {}).get("serverInfo") or {}
        assert_("mcp initialize: HTTP 200", code == 200, f"code={code}")
        assert_("mcp initialize: serverInfo.name 非空", bool(srv.get("name")), json.dumps(body, ensure_ascii=False)[:300])
        assert_("mcp initialize: protocolVersion 非空", bool((body.get("result") or {}).get("protocolVersion")
                                                    or srv.get("version")))

        # /mcp tools/list：README 的 9 个工具一个不少
        code, body = _post_json("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = [t.get("name") for t in ((body.get("result") or {}).get("tools") or [])]
        assert_("mcp tools/list: HTTP 200", code == 200, f"code={code}")
        assert_("mcp tools/list: 工具数 >= 9", len(tools) >= 9, f"got {len(tools)}: {tools}")
        missing = MCP_TOOL_NAMES - set(tools)
        assert_("mcp tools/list: README 9 工具齐全", not missing, f"missing={sorted(missing)}")

        # /rpc status（network=False，离线安全）
        code, body = _post_json("/rpc", {"jsonrpc": "2.0", "id": 7, "method": "status", "params": {"network": False}})
        assert_("rpc status: HTTP 200", code == 200, f"code={code}")
        assert_("rpc status: ok=true 且 result 为对象", body.get("ok") is True and isinstance(body.get("result"), dict),
                json.dumps(body, ensure_ascii=False)[:300])

        # /events SSE：200 + text/event-stream + 立即 hello
        # 注意：SSE 流不会 EOF，read(n) 会等满 n 字节直到超时；用 read1 只取已到达字节
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
        try:
            conn.request("GET", "/events")
            resp = conn.getresponse()
            ctype = resp.getheader("Content-Type") or ""
            chunk = resp.read1(2048)
            assert_("events SSE: HTTP 200", resp.status == 200, f"status={resp.status}")
            assert_("events SSE: content-type 是 text/event-stream", "text/event-stream" in ctype, ctype)
            assert_("events SSE: 首帧含 hello 事件", b"hello" in chunk, chunk[:200].decode("utf-8", errors="replace"))
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 —— 探针自身的连接异常按 FAIL 记录，不炸整个入口
        failures.append(f"endpoint-probe exception: {type(e).__name__}: {e}")
        lines.append(f"FAIL endpoint-probe exception —— {type(e).__name__}: {e}")

    check.duration_s = round(time.time() - t0, 1)
    check.status = "pass" if not failures else "fail"
    check.log_path = str(log_path)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if failures:
        check.fail_summary = "\n".join(lines[-FAIL_TAIL:])
    return check


def tui_timeseries_probe(check: Check) -> Check:
    """复用 smoke_all.tui_timeseries_probe 的既有实现（行为零修改），捕获其控制台输出。"""
    import smoke_all as _sa  # sys.path[0] = tests/；模块级仅做 stdout UTF-8 包装

    t0 = time.time()
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    log_path = RUN_LOGS / f"{check.name}.log"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = _sa.tui_timeseries_probe()
    out = buf.getvalue()
    log_path.write_text(out, encoding="utf-8")
    check.duration_s = round(time.time() - t0, 1)
    check.status = "pass" if ok else "fail"
    check.log_path = str(log_path)
    if not ok:
        check.fail_summary = out[-FAIL_TAIL:]
    return check


# ---------------------------------------------------------------------------
# ruff 门禁（可选 RUN 项，c17）
#
# 定位纪律：用 uvx --offline，**绝不让 uvx 去下载**。uvx 默认会为冷缓存拉取 ruff 包，
# 那是外网请求；--offline 在缓存缺失时直接失败，正好等价于「工具不可用」→ SKIP + 安装提示。
# ---------------------------------------------------------------------------

def _probe_ruff() -> tuple[dict, str | None]:
    """探测 ruff 能否在**零网络**前提下执行；返回 (probe, 不可用原因 or None)。"""
    probe: dict = {"kind": "tool_probe", "cmd": " ".join(RUFF_CMD), "uvx": None, "ok": False}
    uvx = shutil.which("uvx")
    probe["uvx"] = uvx
    if not uvx:
        return probe, ("未检测到 uvx（uv 工具链）：ruff 门禁为可选 RUN 项，缺失时不判失败。"
                       + RUFF_INSTALL_HINT)
    try:
        proc = subprocess.run([uvx, "--offline", RUFF_SPEC, "--version"], cwd=str(ROOT),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
    except Exception as e:  # noqa: BLE001 —— 探测失败按「不可用」处理，不影响其它检查项
        return probe, f"uvx 探测异常（{type(e).__name__}: {e}）" + "；" + RUFF_INSTALL_HINT
    if proc.returncode == 0:
        probe["ok"] = True
        probe["version"] = (proc.stdout or "").strip().splitlines()[-1:] or [""]
        return probe, None
    tail = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
    detail = tail[-1] if tail else f"退出码 {proc.returncode}"
    return probe, (f"uv 缓存中无 {RUFF_SPEC}（离线无法解析：{detail}）。" + RUFF_INSTALL_HINT)


def build_ruff_check() -> Check:
    """条件项：ruff 可用则 RUN（计分），否则 SKIP + 安装提示（不 FAIL）。"""
    check = Check("ruff-check", "静态检查（ruff 门禁）", "run",
                  note="ruff.toml：E9 / F / B / RUF012 / SIM115；uvx --offline 调用，零外网请求")
    probe, unavailable = _probe_ruff()
    check.probe = probe
    if unavailable:
        check.layer = "skip"
        return skip_check(check, unavailable)
    return check


def run_ruff(check: Check) -> Check:
    """执行 ruff 检查（已确认离线可用），零告警 PASS、有告警 FAIL。"""
    t0 = time.time()
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    log_path = RUN_LOGS / f"{check.name}.log"
    ok, out, err = False, "", ""
    try:
        proc = subprocess.run(RUFF_CMD, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
        ok = proc.returncode == 0
        out, err = proc.stdout or "", proc.stderr or ""
    except Exception as e:  # noqa: BLE001 —— 执行异常按 FAIL 记录（不炸整个入口）
        err = f"{type(e).__name__}: {e}"
    log_path.write_text(f"--- cmd ---\n{' '.join(RUFF_CMD)}\n\n--- stdout ---\n{out}\n\n"
                        f"--- stderr ---\n{err}", encoding="utf-8")
    check.duration_s = round(time.time() - t0, 1)
    check.status = "pass" if ok else "fail"
    check.log_path = str(log_path)
    if not ok:
        check.fail_summary = (out[-FAIL_TAIL:] + "\n----stderr----\n" + err[-FAIL_TAIL:])
    return check


# ---------------------------------------------------------------------------
# c21 报告自查（两遍写法）与汇总辅助
# ---------------------------------------------------------------------------

SELFCHECK_TOOL = ROOT / "tools" / "verify_facts_check.py"
SELFCHECK_MODULE = "报告一致性"


def run_report_selfcheck(check: Check, report_path: Path) -> Check:
    """对**刚落盘**的报告跑一次事实一致性自查（tools/verify_facts_check.py）。

    工具缺失时归 SKIP + 提示（与 ruff 门禁同款，不 FAIL）。工具退出码 0 → PASS；
    1（报告与盘上事实不一致）或 2（输入错误）→ FAIL，失败摘要附前若干行报告正文。
    """
    check.probe = {"kind": "tool_probe", "cmd": f"{PY} tools/verify_facts_check.py",
                   "path": "tools/verify_facts_check.py", "ok": SELFCHECK_TOOL.is_file()}
    if not SELFCHECK_TOOL.is_file():
        check.layer = "skip"
        check.status = "skip"
        check.skip_reason = (
            "缺 tools/verify_facts_check.py：报告自查为可选 RUN 项，缺失时不判失败。"
            "恢复：使用含 tools/ 的版本，或 git checkout <commit> -- tools/")
        return check

    t0 = time.time()
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    log_path = RUN_LOGS / f"{check.name}.log"
    cmd = [PY, str(SELFCHECK_TOOL), str(report_path)]
    code, out, err = None, "", ""
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
        code, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception as e:  # noqa: BLE001 —— 执行异常按 FAIL 记录（不炸整个入口）
        err = f"{type(e).__name__}: {e}"
    check.duration_s = round(time.time() - t0, 1)
    check.log_path = str(log_path)
    log_path.write_text(f"--- cmd ---\n{' '.join(cmd)}\n\n--- stdout ---\n{out}\n\n"
                        f"--- stderr ---\n{err}", encoding="utf-8")
    check.status = "pass" if code == 0 else "fail"
    if code != 0:
        head = "\n".join(out.strip().splitlines()[:24])
        tail = f"\n----stderr----\n{err[-FAIL_TAIL:]}" if err.strip() else ""
        check.fail_summary = (head + tail)[-FAIL_TAIL:]
    return check


def summarize(checks: list[Check]) -> tuple[dict, list[Check]]:
    """汇总计数与失败项（c21 抽出：两遍写法需要算两次）。"""
    failed = [c for c in checks if c.layer == "run" and c.status == "fail"]
    summary = {
        "run": sum(1 for c in checks if c.layer == "run"),
        "passed": sum(1 for c in checks if c.status == "pass"),
        "failed": len(failed),
        "skipped": sum(1 for c in checks if c.status == "skip"),
    }
    return summary, failed


def build_coverage(checks: list[Check]) -> tuple[dict, list[str]]:
    """覆盖矩阵与未覆盖模块（c21 抽出：两遍写法需要算两次）。"""
    by_name = {c.name: c for c in checks}
    coverage: dict[str, list[dict]] = {}
    uncovered: list[str] = []
    for module, names in MATRIX.items():
        rows = [{"check": n, "status": by_name[n].status if n in by_name else "missing"} for n in names]
        coverage[module] = rows
        if not names or all(r["status"] in ("missing",) for r in rows):
            uncovered.append(module)
    return coverage, uncovered


def build_report(started, finished, overall, summary, checks, coverage, uncovered) -> dict:
    """组装 JSON 报告 dict（c21 抽出：两遍写法共用同一组装逻辑）。"""
    return {
        "schema": "geocode.verify-all.report.v1",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "overall": overall,
        "summary": summary,
        "network_allowlist": ["127.0.0.1"],  # 本轮 RUN 层唯一允许访问的主机
        "checks": [
            {
                "name": c.name, "module": c.module, "layer": c.layer, "status": c.status,
                "duration_s": c.duration_s, "log_path": c.log_path,
                "skip_reason": c.skip_reason, "note": c.note,
                "fail_summary": c.fail_summary, "probe": c.probe,
            }
            for c in checks
        ],
        "coverage_matrix": coverage,
        "uncovered_modules": uncovered,
    }


# ---------------------------------------------------------------------------
# 覆盖矩阵（README 功能面 → 检查项）
# ---------------------------------------------------------------------------

MATRIX: dict[str, list[str]] = {
    "契约层（ArtifactSpec/指纹/grid/CRS）": ["tests-unit"],
    "三出口 emit_file（GeoTIFF/COG）": ["smoke-three-exits", "smoke-emit"],
    "三出口 emit_array（xarray/NetCDF）": ["smoke-array-chunking-rescan-big", "smoke-presets", "smoke-timeseries"],
    "三出口 emit_map（.qgz/.png 渲染）": ["smoke-map-renderers-qgis", "smoke-map-renderers-arcpy", "tests-unit"],
    "presets": ["tests-unit", "smoke-presets"],
    "batch export": ["tests-unit"],
    "array chunking": ["tests-unit", "smoke-array-chunking-rescan-big"],
    "timeseries": ["tests-unit", "tui-timeseries-probe", "smoke-timeseries"],
    "OSM/Overpass": ["tests-unit", "smoke-osm"],
    "daemon（/mcp /rpc /events）": ["daemon-endpoint-probe", "smoke-tui"],
    "TUI": ["smoke-tui", "tui-timeseries-probe"],
    "client": ["smoke-tui", "daemon-endpoint-probe"],
    "arcpy bridge（headless 出版）": ["smoke-map-renderers-arcpy"],
    "add-in 探测（端点级）": ["tests-unit"],
    "preflight": ["tests-unit"],
    "静态检查（ruff 门禁）": ["ruff-check"],
    "报告一致性": ["report-selfcheck"],
}


# ---------------------------------------------------------------------------
# 检查计划
# ---------------------------------------------------------------------------

def build_checks() -> list[Check]:
    checks: list[Check] = []

    def C(name: str, module: str) -> Check:
        return Check(name=name, module=module, layer="run")

    # RUN 层（离线）
    checks.append(C("tests-unit", "契约层（ArtifactSpec/指纹/grid/CRS）"))
    checks.append(C("tui-timeseries-probe", "timeseries"))
    checks.append(C("daemon-endpoint-probe", "daemon（/mcp /rpc /events）"))

    # rescan-big：前置产物存在才 RUN，缺失则 SKIP（与 map_renderers 缓存未命中同款语义）
    big_name = _era_product_name("big_chunk", "nc") or "s2_chunking_big_smoke.<指纹8位>.nc"
    big_artifact = ROOT / "data" / "derived" / big_name
    big_size = big_artifact.stat().st_size if big_artifact.exists() else 0
    # c21：条件项必须带层位判据（verify-all spec 报告节：条件项为 cache_probe）。此前本项 probe 为
    # null，使 tools/verify_facts_check.py 的 P5/P7 无法覆盖它的措辞（实测把 skip_reason 改写成
    # 「已命中」工具仍判绿）。判定语义不变 —— 产物存在即 RUN；min_bytes=0 表示本项无额外体积门槛，
    # 故 hit 与层位始终自洽（P7），size_bytes 仍如实记录以便读者判断产物是否被截断。
    probe_big = {"kind": "cache_probe", "path": f"data/derived/{big_name}",
                 "exists": big_artifact.exists(), "size_bytes": big_size,
                 "min_bytes": 0, "hit": big_size > 0}
    if big_artifact.exists():
        big_check = C("smoke-array-chunking-rescan-big", "array chunking")
        big_check.probe = probe_big
        checks.append(big_check)
    else:
        # 措辞纪律（c17 / A2）：只陈述「本次执行根下缺失」，不断言别处有无 ——
        # 该产物曾确实存在于主工作区盘上，旧文案「不在主工作区」与事实相悖。
        big_check = skip_check(
            Check("smoke-array-chunking-rescan-big", "array chunking", "skip"),
            f"前置产物缺失：本次执行根下无 data/derived/{big_name}"
            f"（查找路径 {big_artifact}）；产物未入库、按需生成，"
            "chunking 单元面已由 tests-unit 的 test_array_chunking 离线覆盖；"
            "单独复跑：联网环境先 PYTHONPATH=. python tests/smoke_array_chunking.py --stage big "
            "生成产物，之后本项自动转 RUN")
        big_check.probe = probe_big
        checks.append(big_check)

    checks.append(skip_check(
        Check("smoke-tui", "TUI", "skip"),
        "smoke_tui 的 action_describe 段走 /rpc gee.describe → ee.data.getAsset()"
        "（GEE REST，需网络 + 认证，非离线安全）；TUI 渲染面已由 tui-timeseries-probe "
        "离线覆盖；单独复跑：联网环境 PYTHONPATH=. python tests/smoke_tui.py"))

    # SKIP 层（在线依赖，注明原因与单独复跑方式）
    net_gee = "需要真实 GEE 像素（网络 + GEE 认证）；单独复跑：联网环境 PYTHONPATH=. python tests/{file}"
    checks.append(skip_check(Check("smoke-emit", "三出口 emit_file（GeoTIFF/COG）", "skip"),
                             net_gee.format(file="smoke_emit.py"),
                             note="emit_file/emit_array 真实像素链路"))
    checks.append(skip_check(Check("smoke-three-exits", "三出口 emit_file（GeoTIFF/COG）", "skip"),
                             net_gee.format(file="smoke_three_exits.py"),
                             note="三出口逐像素一致性（含 array 出口真拉像素）"))
    checks.append(skip_check(Check("smoke-presets", "presets", "skip"),
                             net_gee.format(file="smoke_presets.py"),
                             note="预设量纲用 GEE 原始值独立复算"))
    checks.append(skip_check(Check("smoke-timeseries", "timeseries", "skip"),
                             net_gee.format(file="smoke_timeseries.py"),
                             note="立方体 emit_array/emit_file 需 GEE 拉取 8 次"))
    checks.append(skip_check(Check("smoke-osm", "OSM/Overpass", "skip"),
                             "Overpass API 需网络（经 geocode.json 代理），首轮栅格建源经 GEE；"
                             "单元面已由 tests-unit 的 test_osm/test_aoi 离线覆盖；"
                             "单独复跑：联网环境 PYTHONPATH=. python tests/smoke_osm.py <cmd>"))
    # --- 渲染两项：条件项（c17）—— 与 rescan-big 同款语义：前置产物存在即自动升 RUN ---
    # 判据与实现对齐 gis/emit.py::_ensure_raster：目标文件存在且 > 4096 B 即复用（离线命中）；
    # 否则会走联网路径现场生成。故「离线可跑」⇔ 缓存文件在盘且体积达标。
    p0_tif = _era_product_name("p0", "tif") or "s2_beijing_test.<指纹8位>.tif"
    p0_path = ROOT / "data" / "derived" / p0_tif
    p0_size = p0_path.stat().st_size if p0_path.exists() else 0
    cache_hit = p0_size > CACHE_MIN_BYTES
    probe_render = {"kind": "cache_probe", "path": f"data/derived/{p0_tif}",
                    "exists": p0_path.exists(), "size_bytes": p0_size,
                    "min_bytes": CACHE_MIN_BYTES, "hit": cache_hit}
    for renderer, note in (("qgis", "QGIS 渲染器"), ("arcpy", "arcpy 渲染器 / arcpy bridge 出版链路")):
        name = f"smoke-map-renderers-{renderer}"
        if cache_hit:
            c = C(name, "三出口 emit_map（.qgz/.png 渲染）")
            c.note = f"{note}；缓存命中（data/derived/{p0_tif} 在盘且 >4096 B），离线执行"
            c.probe = probe_render
            checks.append(c)
        else:
            reason = (f"当代指纹缓存缺失：data/derived/{p0_tif} "
                      + ("不存在" if not p0_path.exists() else f"过小（{p0_size} B ≤ {CACHE_MIN_BYTES} B）")
                      + "，_ensure_raster 会走联网路径现场生成；联网跑一次后本项自动转 RUN。"
                      "渲染 spec 结构面已由 tests-unit 的 test_layout_spec/test_overlay_spec 离线覆盖；"
                      "单独复跑：联网环境 PYTHONPATH=. python tests/smoke_map_renderers.py " + renderer)
            c = skip_check(Check(name, "三出口 emit_map（.qgz/.png 渲染）", "skip"), reason, note=note)
            c.probe = probe_render
            checks.append(c)

    # --- ruff 门禁：可选 RUN 项（c17，Q2=a）---
    # 关键：必须带 --offline —— uvx 默认会为冷缓存**下载** ruff，与「新增 RUN 项不得引入外网
    # 请求」红线冲突。冷缓存/无 uv 时 --offline 会失败，按「工具不可用」归 SKIP + 安装提示。
    checks.append(build_ruff_check())
    return checks


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    started = datetime.now(timezone.utc)
    print("== verify_all：全量功能自动化验证（离线层 RUN / 在线依赖层 SKIP）==")
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    checks = build_checks()
    by_name = {c.name: c for c in checks}

    # 1) 离线单测（无需 daemon）
    run_cmd(by_name["tests-unit"], ["-m", "unittest", "discover", "-s", "tests/unit"], timeout=600)

    # 2) daemon 窗口：TUI 探针 / 端点探针（smoke-tui 已按网络依赖归 SKIP，不在此窗口）
    owned = None
    try:
        if daemon_alive():
            print("  daemon 已在运行（复用，结束时不停止外部 daemon）")
        else:
            print("  启动 daemon …")
            owned = start_daemon()
            print("  daemon 就绪")
        tui_timeseries_probe(by_name["tui-timeseries-probe"])
        daemon_endpoint_probe(by_name["daemon-endpoint-probe"])
    finally:
        if owned is not None:
            owned.terminate()
            try:
                owned.wait(timeout=10)
            except Exception:
                owned.kill()
            print("  临时 daemon 已停止")

    # 3) 离线重扫描（无需 daemon；仅在前置产物存在时已在 checks 里置为 RUN）
    if by_name["smoke-array-chunking-rescan-big"].layer == "run":
        run_cmd(by_name["smoke-array-chunking-rescan-big"],
                ["tests/smoke_array_chunking.py", "--stage", "rescan-big"], timeout=600)

    # 4) 渲染两项（条件项：仅缓存命中时入 RUN 层；离线、无需 daemon）
    for renderer in ("qgis", "arcpy"):
        name = f"smoke-map-renderers-{renderer}"
        if by_name[name].layer == "run":
            run_cmd(by_name[name], ["tests/smoke_map_renderers.py", renderer], timeout=900)

    # 5) ruff 门禁（可选 RUN 项；_probe_ruff 已确认离线可用才为 RUN）
    if by_name["ruff-check"].layer == "run":
        run_ruff(by_name["ruff-check"])

    # 汇总 + 覆盖矩阵（第一遍）
    summary, failed = summarize(checks)
    coverage, uncovered = build_coverage(checks)
    overall = "fail" if failed else "pass"

    # c21 两遍写法（第一遍）：先落一份**不含自查项**的报告，供自查读取 ——
    # 自查读到的正是它将要评述的那份快照（不含自身），自指问题由此解除。
    REPORT_PATH.write_text(json.dumps(
        build_report(started, datetime.now(timezone.utc), overall, summary, checks, coverage, uncovered),
        ensure_ascii=False, indent=2), encoding="utf-8")

    # c21 报告自查（条件 RUN 项；工具缺失时该项自身转 SKIP）：把结论插回 checks 后重算第二遍
    checks.append(run_report_selfcheck(
        Check(name="report-selfcheck", module=SELFCHECK_MODULE, layer="run"), REPORT_PATH))
    summary, failed = summarize(checks)
    coverage, uncovered = build_coverage(checks)
    overall = "fail" if failed else "pass"

    # 控制台输出
    for c in checks:
        tag = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c.status]
        line = f"  [{tag}] {c.name}  {c.duration_s:.1f}s  <{c.module}>"
        if c.status == "skip":
            line += f"  原因: {c.skip_reason}"
        print(line)
    print(f"\n== 汇总：RUN {summary['run']}（PASS {summary['passed']} / FAIL {summary['failed']}）"
          f" · SKIP {summary['skipped']} ==")
    if failed:
        for c in failed:
            print(f"  [FAIL] {c.name} —— 日志: {c.log_path}")
            if c.fail_summary:
                print("     " + c.fail_summary.replace("\n", "\n     ")[:FAIL_TAIL])
    print("\n== 覆盖矩阵（功能模块 → 检查项状态）==")
    for module, rows in coverage.items():
        cells = ", ".join(f"{r['check']}={r['status']}" for r in rows)
        print(f"  {module}: {cells}")
    if uncovered:
        print(f"  [uncovered] {'、'.join(uncovered)}")
    print(f"\n== verify_all {'全部通过（含 SKIP）' if overall == 'pass' else '存在失败'}"
          f" · 报告: {REPORT_PATH} ==")

    # JSON 报告（第二遍：含自查项，整体覆盖第一版；最终报告是唯一事实源）
    REPORT_PATH.write_text(json.dumps(
        build_report(started, datetime.now(timezone.utc), overall, summary, checks, coverage, uncovered),
        ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
