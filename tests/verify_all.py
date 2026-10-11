"""C14 全量功能自动化验证入口（verify-all capability）。

一条命令跑完全部可离线执行的功能检查：
    1. tests-unit                    —— tests/unit 全量离线单测（禁网守卫约束下的 212 用例级）；
    2. smoke-tui                     —— daemon + TUI headless（复用既有 smoke）；
    3. tui-timeseries-probe          —— 时序 spec 驱动 TUI headless 渲染（复用 smoke_all 实现）；
    4. smoke-array-chunking-rescan-big —— 已有大网格产物离线重扫描（既有 smoke 的离线 stage）；
    5. daemon-endpoint-probe         —— 本入口新探针：/mcp initialize+tools/list、/rpc status、
                                        /events SSE hello，仅访问 127.0.0.1，不发起外网请求。

在线依赖检查（需真实 GEE 像素/认证，或当代 PV 缓存未命中需联网生成）一律 SKIP 并注明原因
与单独复跑方式；本入口不提供 --online 开关。

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
    if big_artifact.exists():
        checks.append(C("smoke-array-chunking-rescan-big", "array chunking"))
    else:
        checks.append(skip_check(
            Check("smoke-array-chunking-rescan-big", "array chunking", "skip"),
            f"前置产物缺失：C6 大网格产物 data/derived/{big_name} "
            "不在主工作区（worktree 时代产物，未入库）；chunking 单元面已由 tests-unit 的 "
            "test_array_chunking 离线覆盖；单独复跑：联网环境先 PYTHONPATH=. python "
            "tests/smoke_array_chunking.py --stage big 生成产物，之后本项自动转 RUN"))

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
    p0_tif = _era_product_name("p0", "tif") or "s2_beijing_test.<指纹8位>.tif"
    # SKIP 文案必须写实：缓存已在盘时不得再声称「未命中」
    if (ROOT / "data" / "derived" / p0_tif).exists():
        cache_note = (f"缓存已命中（data/derived/{p0_tif} 在盘），本项可离线复跑；"
                      "本入口 RUN 层按 C14 验收范围维持 tests-unit / tui-timeseries-probe / "
                      "daemon-endpoint-probe（＋前置产物存在时的 rescan-big），渲染面未入层。"
                      "单独复跑：PYTHONPATH=. python tests/smoke_map_renderers.py qgis|arcpy")
    else:
        cache_note = (f"当代 PV 下 _ensure_raster 缓存未命中（data/derived/{p0_tif} 不存在），"
                      "直接跑会走联网路径生成缓存；联网跑通一次后可离线复跑。"
                      "渲染 spec 结构面已由 tests-unit 的 test_layout_spec/test_overlay_spec 离线覆盖")
    checks.append(skip_check(Check("smoke-map-renderers-qgis", "三出口 emit_map（.qgz/.png 渲染）", "skip"),
                             cache_note, note="QGIS 渲染器"))
    checks.append(skip_check(Check("smoke-map-renderers-arcpy", "三出口 emit_map（.qgz/.png 渲染）", "skip"),
                             cache_note, note="arcpy 渲染器 / arcpy bridge 出版链路"))
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

    # 汇总 + 覆盖矩阵
    failed = [c for c in checks if c.layer == "run" and c.status == "fail"]
    overall = "fail" if failed else "pass"
    summary = {
        "run": sum(1 for c in checks if c.layer == "run"),
        "passed": sum(1 for c in checks if c.status == "pass"),
        "failed": len(failed),
        "skipped": sum(1 for c in checks if c.status == "skip"),
    }

    coverage: dict[str, list[dict]] = {}
    uncovered: list[str] = []
    for module, names in MATRIX.items():
        rows = [{"check": n, "status": by_name[n].status if n in by_name else "missing"} for n in names]
        coverage[module] = rows
        if not names or all(r["status"] in ("missing",) for r in rows):
            uncovered.append(module)

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

    # JSON 报告
    finished = datetime.now(timezone.utc)
    report = {
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
                "fail_summary": c.fail_summary,
            }
            for c in checks
        ],
        "coverage_matrix": coverage,
        "uncovered_modules": uncovered,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
