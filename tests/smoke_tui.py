import asyncio, json, re, pathlib
from textual.widgets import Static, DataTable
from gis.tui import GeoCodeTUI

# 期望的 GEE 项目从配置读 —— 真实 id 只存在于本地 geocode.json，不入库
PROJECT = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "geocode.json").read_text(encoding="utf-8-sig")
)["gee"]["project"]

OUT = pathlib.Path("logs/_tui_check.txt")
lines = []
def say(s=""): lines.append(str(s))

def txt(w):
    return re.sub(r'\[/?[^\]]*\]', '', str(w.render()))

async def main():
    app = GeoCodeTUI()
    async with app.run_test(size=(118, 42)) as pilot:
        await pilot.pause(); await asyncio.sleep(3.0); await pilot.pause()
        checks = []
        d = txt(app.query_one("#st-daemon", Static))
        checks.append(("守护进程面板", "运行中" in d, d.strip()))
        g = txt(app.query_one("#st-gee", Static))
        checks.append(("GEE 状态行", PROJECT in g, g.strip()))
        e = txt(app.query_one("#st-env", Static))
        checks.append(("环境行", "GDAL 3.13.3" in e, e.strip()))
        t = txt(app.query_one("#st-tasks", Static))
        checks.append(("任务汇总行", "共" in t, t.strip()))
        n_before = app.query_one("#jobs", DataTable).row_count
        checks.append(("任务表有历史", n_before > 0, f"{n_before} 行"))

        app.action_describe()
        await asyncio.sleep(11); await pilot.pause(); app.tick(); await pilot.pause()

        sb = txt(app.query_one("#spec-body", Static))
        checks.append(("spec 被填充", "COPERNICUS" in sb, sb.replace("\n", " | ")[:160]))
        n_after = app.query_one("#jobs", DataTable).row_count
        checks.append(("产生新任务", n_after > n_before, f"{n_before} → {n_after}"))

        say("=" * 78)
        for name, ok, detail in checks:
            say(f"  {'PASS' if ok else 'FAIL'}  {name:14s} {detail}")
        say("=" * 78)
        say(f"  通过 {sum(1 for _, o, _ in checks if o)}/{len(checks)}")
        say("")
        say("全部日志行：")
        for ln in lines[:0]: pass

asyncio.run(main())
OUT.write_text("\n".join(lines), encoding="utf-8")
