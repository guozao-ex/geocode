"""
C3 修复轮新增：现有 smoke 的守护进程生命周期包装（A8 的可重复证据面）。

背景：smoke_emit / smoke_three_exits / smoke_map_renderers / smoke_tui 都通过
Client→daemon 工作，单独跑需要先手动起 daemon。本脚本负责：
    1. 检测 6531 端口：没有 daemon 就起一个（用完即停，独立进程无自启）；
    2. 依次运行四个既有 smoke（子进程，PYTHONPATH=仓库根，行为零修改）；
    3. TUI 时序探针：用时序 spec 驱动 TUI headless 渲染（验证新字段不破坏展示面）；
    4. 汇总退出码（任一失败 → 1）。

用法（geo env，仓库根）：
    C:/ProgramData/miniforge3/envs/geo/python.exe tests/smoke_all.py

⚠️ smoke_emit / smoke_three_exits 的 array 出口会真实拉取 GEE 像素（需网络）；
   其余步骤离线（map_renderers 命中 _ensure_raster 缓存）。
"""

import io
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PORT = 6531


def daemon_alive() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start_daemon() -> subprocess.Popen:
    log = open(ROOT / "logs" / "smoke_all_daemon.log", "ab")
    proc = subprocess.Popen(
        [PY, "-m", "gis.daemon"], cwd=str(ROOT), stdout=log, stderr=log,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    for _ in range(40):
        if daemon_alive():
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("daemon 8 秒内未监听 6531，见 logs/smoke_all_daemon.log")


def run(name: str, args: list[str]) -> bool:
    env = dict(os.environ, PYTHONPATH=str(ROOT), IO_ENCODING="utf-8")
    t0 = time.time()
    proc = subprocess.run(
        [PY, *args], cwd=str(ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600,
    )
    dt = time.time() - t0
    ok = proc.returncode == 0
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {dt:.1f}s")
    if not ok:
        tail = (proc.stdout or "")[-1200:] + "\n----stderr----\n" + (proc.stderr or "")[-1200:]
        print("     " + tail.replace("\n", "\n     "))
    return ok


def tui_timeseries_probe() -> bool:
    """
    TUI 时序展示探针（风险 11 的闭环）：给 daemon 设一个 time_step spec，
    headless 驱动 TUI，断言：任务/spec 面板正常渲染、新字段不引发异常、
    spec 面板仍显示 time_range 行（时序 spec 的 time_range 是切片范围）。
    """
    script = r'''
import asyncio, json, sys
sys.path.insert(0, ".")
from gis.client import Client
from gis.tui import GeoCodeTUI
from textual.widgets import Static

c = Client()
prev = c.spec().get("spec") or {}
c.set_spec({
    "id": "s2_ts_probe", "asset": "COPERNICUS/S2_SR_HARMONIZED",
    "bands": ["B4", "B3", "B2"], "scale": 10, "crs": "EPSG:32650",
    "dtype": "uint16", "time_range": ["2024-06-01", "2024-08-31"],
    "time_step": "month", "reducer": "median",
    "aoi": {"type": "Polygon", "coordinates": [[[116.30, 39.95], [116.40, 39.95],
            [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]]},
})
try:
    async def main():
        app = GeoCodeTUI()
        async with app.run_test(size=(118, 42)) as pilot:
            await pilot.pause(); await asyncio.sleep(2.0); await pilot.pause()
            checks = []
            body = str(app.query_one("#spec-body", Static).render())
            checks.append(("spec 面板渲染", "s2_ts_probe" in body))
            checks.append(("time_range 行在", "2024-06" in body))
            jobs = app.query_one("#jobs").row_count if hasattr(app.query_one("#jobs"), "row_count") else -1
            checks.append(("任务表可读", jobs >= 0))
            for name, ok in checks:
                print(("PASS" if ok else "FAIL"), name)
            sys.exit(0 if all(ok for _, ok in checks) else 1)
    asyncio.run(main())
finally:
    if prev:
        try:
            c.set_spec(prev)
        except Exception:
            pass
'''
    probe = ROOT / "logs" / "_tui_ts_probe_inline.py"
    probe.write_text(script, encoding="utf-8")
    try:
        return run("tui-timeseries-probe（headless）", [str(probe)])
    finally:
        probe.unlink(missing_ok=True)


def main() -> int:
    print("== smoke_all：现有 smoke 全量回归（A8 可重复证据面）==")
    owned = None
    try:
        if daemon_alive():
            print("  daemon 已在运行（复用）")
        else:
            print("  启动 daemon …")
            owned = start_daemon()
            print("  daemon 就绪")

        results = [
            run("smoke_emit", ["tests/smoke_emit.py"]),
            run("smoke_three_exits", ["tests/smoke_three_exits.py"]),
            run("smoke_map_renderers qgis", ["tests/smoke_map_renderers.py", "qgis"]),
            run("smoke_map_renderers arcpy", ["tests/smoke_map_renderers.py", "arcpy"]),
            run("smoke_tui", ["tests/smoke_tui.py"]),
            tui_timeseries_probe(),
        ]
    finally:
        if owned is not None:
            owned.terminate()
            try:
                owned.wait(timeout=10)
            except Exception:
                owned.kill()
            print("  临时 daemon 已停止")

    ok = all(results)
    print(f"\n== smoke_all {'全部通过' if ok else '存在失败'}（{sum(results)}/{len(results)}）==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
