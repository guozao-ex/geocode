"""
终端界面。管理守护进程、看状态、盯任务、编 spec。

设计原则：
1. **守护进程不在也能用** —— 显示"未运行"并提供启动入口，而不是报错退出。
2. **轮询而非 SSE** —— 2 秒一次的状态刷新对这个量级足够，
   换来的是断线自愈（SSE 断流要处理重连，复杂度不划算）。
3. **所有写操作都走守护进程** —— TUI 自己不跑 GEE，避免两套状态。

启动：
    python -m gis.tui
键位见界面底部。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from .client import Client, DaemonError
from . import geoenv

REFRESH_S = 2.0


# ---------------------------------------------------------------------------
# 小组件
# ---------------------------------------------------------------------------

class StatusLine(Static):
    """一行「灯 + 标签 + 值」。"""

    def __init__(self, label: str, id: str | None = None) -> None:
        super().__init__(id=id)
        self._label = label

    def update_state(self, ok: bool | None, value: str, detail: str = "") -> None:
        lamp = {True: "[green]●[/]", False: "[red]●[/]", None: "[yellow]○[/]"}[ok]
        tail = f"  [dim]{detail}[/]" if detail else ""
        self.update(f"{lamp} [b]{self._label:<8}[/] {value}{tail}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class GeoCodeTUI(App):
    CSS = """
    Screen { layout: vertical; }
    #status-box {
        height: auto; padding: 0 1; border: round $primary;
        margin: 0 1;
    }
    #jobs-box { height: 1fr; margin: 0 1; }
    #spec-box { height: auto; max-height: 14; padding: 0 1; border: round $secondary; margin: 0 1; }
    #log-box { height: 12; margin: 0 1; }
    .row { height: auto; }
    Button { min-width: 18; margin: 0 1 1 1; }
    #hint { color: $text-muted; padding: 0 2; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("r", "refresh", "刷新"),
        Binding("s", "submit", "提交任务"),
        Binding("d", "toggle_daemon", "启停守护"),
        Binding("c", "cancel", "取消选中任务"),
        Binding("a", "cancel_all", "取消全部"),
        Binding("e", "describe", "探测资产"),
        Binding("escape", "quit", "退出"),
    ]

    TITLE = "GeoCode Console"

    def __init__(self, host: str = "127.0.0.1", port: int = 6531) -> None:
        super().__init__()
        self.client = Client(host, port)
        self.port = port
        self._daemon_pid: int | None = None
        self._last_job_count = -1
        self._seen_jobs: set[str] = set()
        self._auto_descried: set[str] = set()

    # --- 布局 -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll():
            with Vertical(id="status-box"):
                yield Static("[b]运行状态[/]", classes="row")
                yield Static(id="st-daemon")
                yield Static(id="st-gee")
                yield Static(id="st-net")
                yield Static(id="st-env")
                yield Static(id="st-tasks")
            with Horizontal(classes="row"):
                yield Button("刷新 (r)", id="btn-refresh", variant="default")
                yield Button("提交任务 (s)", id="btn-submit", variant="primary")
                yield Button("探测资产 (e)", id="btn-describe", variant="default")
                yield Button("取消选中 (c)", id="btn-cancel", variant="warning")
                yield Button("启停守护 (d)", id="btn-daemon", variant="success")
            yield Static(id="hint", classes="row")
            with Vertical(id="jobs-box"):
                yield DataTable(id="jobs", zebra_stripes=True, cursor_type="row")
            with Vertical(id="spec-box"):
                yield Static("[b]当前 ArtifactSpec[/]", classes="row")
                yield Static(id="spec-body")
            with Vertical(id="log-box"):
                yield RichLog(id="log", highlight=True, markup=True, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#jobs", DataTable)
        t.add_columns("ID", "类型", "出口", "状态", "进度", "阶段", "耗时", "说明")
        self.log_msg("[b]GeoCode Console[/] 启动")
        self.tick()
        self.set_interval(REFRESH_S, self.tick)

    # --- 日志 -------------------------------------------------------------

    def log_msg(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.query_one("#log", RichLog).write(f"[dim]{ts}[/] {msg}")

    # --- 主循环 -----------------------------------------------------------

    def tick(self) -> None:
        self.check_daemon()
        self.refresh_jobs()

    def check_daemon(self) -> None:
        alive = self.client.alive()
        self.query_one("#st-daemon", Static).update(
            ("[green]●[/] [b]守护进程[/] 运行中  "
             f"[dim]127.0.0.1:{self.port}[/]")
            if alive else
            ("[red]●[/] [b]守护进程[/] [red]未运行[/]  "
             "[dim]按 d 启动，或 python -m gis.daemon[/]")
        )
        for wid in ("#st-gee", "#st-net", "#st-env", "#st-tasks"):
            self.query_one(wid, Static).update("[dim]─[/]")
        self.query_one("#spec-body", Static).update("[dim]（守护进程未运行）[/]")
        if not alive:
            return

        try:
            st = self.client.status()
        except DaemonError as e:
            self.query_one("#st-daemon", Static).update(f"[red]●[/] 守护进程通信失败：{e}")
            return

        # GEE
        g = st.get("gee_local", {})
        if g.get("ok"):
            self.query_one("#st-gee", Static).update(
                f"[green]●[/] [b]GEE     [/] 就绪  [dim]项目 {g['value'].get('project')}[/]")
        else:
            self.query_one("#st-gee", Static).update(
                f"[red]●[/] [b]GEE     [/] [red]{g.get('code')}[/]")

        # 包 / GDAL
        env = st.get("env", {})
        pk = env.get("packages", {})
        gd = env.get("gdal", {}).get("value", {}) or {}
        n_req = len((pk.get("value") or {}).get("required") or {})
        self.query_one("#st-env", Static).update(
            f"[green]●[/] [b]环境     [/] {geoenv.env_name()} env · GDAL {gd.get('version','?')} · {n_req} 个必需包"
        )

        # 任务
        jo = st.get("jobs", {})
        active = len(jo.get("active") or [])
        by = jo.get("by_status") or {}
        self.query_one("#st-tasks", Static).update(
            f"{'[yellow]●[/]' if active else '[green]●[/]'} [b]任务     [/] "
            f"共 {jo.get('total',0)} · 进行中 [b]{active}[/] · "
            f"[dim]" + " ".join(f"{k}={v}" for k, v in by.items()) + "[/]"
        )

        # Spec
        spec = st.get("spec")
        self.query_one("#spec-body", Static).update(self._fmt_spec(spec))

    def _fmt_spec(self, spec: dict | None) -> str:
        if not spec:
            return "[dim]（未设置。用 e 探测资产后会自动生成一份）[/]"
        rows = [
            ("id", spec.get("id")),
            ("asset", spec.get("asset")),
            ("crs", spec.get("crs")),
            ("scale", spec.get("scale")),
            ("bands", ",".join(spec.get("bands") or [])),
            ("time", " → ".join(spec.get("time_range") or []) or None),
            ("reducer", spec.get("reducer")),
            ("dtype", spec.get("dtype")),
            ("aoi", "[green]有[/]" if spec.get("aoi") else "[red]无[/]"),
            ("指纹", spec.get("fingerprint")),
        ]
        return "\n".join(
            f"  [dim]{k:<8}[/] {v if v is not None else '[dim]─[/]'}" for k, v in rows
        )

    def refresh_jobs(self) -> None:
        if not self.client.alive():
            return
        try:
            data = self.client.jobs(limit=60)
        except DaemonError:
            return
        jobs = data.get("jobs") or []

        t = self.query_one("#jobs", DataTable)
        cur = t.cursor_row
        t.clear()
        for j in jobs:
            color = {
                "done": "green", "failed": "red", "cancelled": "yellow",
                "running": "cyan", "queued": "dim",
            }.get(j["status"], "white")
            t.add_row(
                j["id"],
                j["kind"],
                j["exit"] or "─",
                f"[{color}]{j['status']}[/]",
                f"{j['pct']:5.1f}%",
                (j["phase"] or "─")[:14],
                f"{j['elapsed']:.0f}s",
                (j["message"] or j["error"] or "")[:46].replace("\n", " "),
                key=j["id"],
            )
        if jobs:
            try:
                t.move_cursor(row=min(cur, len(jobs) - 1))
            except Exception:
                pass

        # 新任务 / 状态变化写进日志
        for j in jobs:
            if j["id"] not in self._seen_jobs:
                self._seen_jobs.add(j["id"])
                if j["status"] in ("done", "failed", "cancelled"):
                    self.log_msg(f"{j['id']} {j['status']} {j.get('message') or ''}")
                else:
                    self.log_msg(f"[b]{j['id']}[/] 已提交 · {j['kind']}/{j['exit'] or '-'}")
            if j["status"] in ("done", "failed") and j["id"] not in getattr(self, "_reported", set()):
                if not hasattr(self, "_reported"):
                    self._reported: set[str] = set()
                if j["id"] in self._reported:
                    continue
                self._reported.add(j["id"])
                if j["status"] == "done":
                    self.log_msg(f"[green]✓[/] {j['id']} 完成 {j.get('message') or ''}")
                else:
                    self.log_msg(f"[red]✗[/] {j['id']} 失败")

    # --- 动作 -------------------------------------------------------------

    def action_refresh(self) -> None:
        self.tick()
        self.log_msg("已刷新")

    def action_submit(self) -> None:
        self.do_submit()

    @work(thread=True, exclusive=True)
    def do_submit(self) -> None:
        if not self.client.alive():
            self.call_from_thread(self.log_msg, "[red]守护进程未运行[/]")
            return
        try:
            cur = self.client.spec().get("spec")
        except DaemonError as e:
            self.call_from_thread(self.log_msg, f"[red]{e}[/]")
            return
        if not cur:
            self.call_from_thread(self.log_msg, "[yellow]还没有 spec —— 先按 e 探测一个资产[/]")
            return
        for ex in ("file", "array", "map"):
            try:
                r = self.client.submit(kind="emit", exit=ex)
                self.call_from_thread(self.log_msg, f"提交 {ex} 出口 → {r['job_id']}")
            except DaemonError as e:
                self.call_from_thread(self.log_msg, f"[yellow]{ex} 出口跳过：{str(e)[:120]}[/]")

    def action_describe(self) -> None:
        self.do_describe()

    @work(thread=True, exclusive=True)
    def do_describe(self) -> None:
        if not self.client.alive():
            self.call_from_thread(self.log_msg, "[red]守护进程未运行[/]")
            return
        # 用第一个已知资产做演示；有 spec 就用它的
        asset = None
        try:
            s = self.client.spec().get("spec")
            asset = (s or {}).get("asset")
        except DaemonError:
            pass
        if not asset:
            try:
                asset = self.client.status()["assets_known"][0]
            except Exception:
                asset = "COPERNICUS/S2_SR_HARMONIZED"

        self.call_from_thread(self.log_msg, f"探测 {asset} …")
        try:
            d = self.client.describe_asset(asset)
        except DaemonError as e:
            self.call_from_thread(self.log_msg, f"[red]探测失败：{str(e)[:200]}[/]")
            return

        bands = [b["name"] for b in d.get("bands", []) if not b["name"].startswith("...")]
        preset = d.get("preset") or {}
        self.call_from_thread(
            self.log_msg,
            f"[green]✓[/] {d['type']} · {len(bands)} 波段 · "
            f"时间 {d.get('date_range') or '未知'} · 预设 {preset.get('label') or '无'}",
        )
        # 顺手把 spec 填成合理默认值
        try:
            self.client.set_spec({
                "id": asset.split("/")[-1].lower(),
                "asset": asset,
                "bands": preset.get("bands") or bands[:4],
                "scale": preset.get("scale") or 10,
                "dtype": "float32",
            })
            self.call_from_thread(self.log_msg, "已生成默认 spec")
        except DaemonError as e:
            self.call_from_thread(self.log_msg, f"[yellow]写 spec 失败：{e}[/]")
        self.call_from_thread(self.tick)

    def action_cancel(self) -> None:
        jid = self._selected_job()
        if not jid:
            self.log_msg("[yellow]没有选中任务[/]")
            return
        try:
            self.client.cancel(jid)
            self.log_msg(f"已请求取消 {jid}")
        except DaemonError as e:
            self.log_msg(f"[red]{e}[/]")

    def action_cancel_all(self) -> None:
        if not self.client.alive():
            return
        try:
            r = self.client.cancel_all()
            self.log_msg(f"已请求取消 {r.get('cancelled', 0)} 个任务")
        except DaemonError as e:
            self.log_msg(f"[red]{e}[/]")

    def action_toggle_daemon(self) -> None:
        if self.client.alive():
            self.log_msg("[yellow]守护进程在跑。要停请到它的窗口按 Ctrl-C[/]")
            return
        self.do_start_daemon()

    @work(thread=True, exclusive=True)
    def do_start_daemon(self) -> None:
        py = sys.executable
        self.call_from_thread(self.log_msg, f"启动守护进程 {py} -m gis.daemon …")
        try:
            subprocess.Popen(
                [py, "-X", "utf8", "-m", "gis.daemon"],
                cwd=str(geoenv.ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
        except Exception as e:
            self.call_from_thread(self.log_msg, f"[red]启动失败：{e}[/]")
            return
        for _ in range(20):
            time.sleep(0.5)
            if self.client.alive():
                self.call_from_thread(self.log_msg, "[green]✓[/] 守护进程已就绪")
                self.call_from_thread(self.tick)
                return
        self.call_from_thread(self.log_msg, "[red]启动后 10 秒内没起来，检查 logs/daemon.err[/]")

    def _selected_job(self) -> str | None:
        t = self.query_one("#jobs", DataTable)
        try:
            row = t.coordinate_to_cell_key(t.cursor_coordinate).row_key
            return row.value if row else None
        except Exception:
            return None

    # --- 事件 -------------------------------------------------------------

    @on(Button.Pressed)
    def on_button(self, ev: Button.Pressed) -> None:
        {"btn-refresh": self.action_refresh,
         "btn-submit": self.action_submit,
         "btn-describe": self.action_describe,
         "btn-cancel": self.action_cancel,
         "btn-daemon": self.action_toggle_daemon,
         }.get(ev.button.id or "", lambda: None)()


def main() -> int:
    cfg = geoenv.load_config()["server"]
    app = GeoCodeTUI(host=cfg["host"], port=int(cfg["port"]))
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
