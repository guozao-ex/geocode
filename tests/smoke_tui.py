import asyncio
import json
import pathlib
import re
import sys

from textual.widgets import DataTable, Static

from gis.tui import GeoCodeTUI

# 报告含中文与 PASS/FAIL 字样：转 UTF-8 输出，避免 GBK 控制台/重定向下写崩
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
        # 不断言「有历史」（全新 daemon 必为 0），改为断言两个视图自洽：
        # 任务表行数 == 汇总行「共 N」的 N（守护进程只持久化 export 类任务，
        # emit 等内存任务重启即空——断言大于 0 会让本脚本在干净环境下误报）
        m_n = re.search(r"共\s*(\d+)", t)
        summary_n = int(m_n.group(1)) if m_n else -1
        checks.append(("任务表与汇总行一致", n_before == summary_n,
                       f"表 {n_before} 行 / 汇总行 共 {summary_n}"))

        app.action_describe()
        await asyncio.sleep(11); await pilot.pause(); app.tick(); await pilot.pause()

        sb = txt(app.query_one("#spec-body", Static))
        checks.append(("spec 被填充", "COPERNICUS" in sb, sb.replace("\n", " | ")[:160]))
        n_after = app.query_one("#jobs", DataTable).row_count
        # describe 走同步 RPC（gee.describe），按设计不产生任务行：
        #   client.py describe_asset → daemon /rpc act_gee_describe 直调 source.describe_asset
        # 旧断言「产生新任务」（n_after > n_before）与该设计不符，
        # 2026-10-06 C3 修复轮改为断言同步语义本身（任务数不变 + spec 已更新）。
        checks.append(("describe 同步语义（不产生任务行）", n_after == n_before,
                       f"{n_before} → {n_after}（describe 不入队）"))

        say("=" * 78)
        for name, ok, detail in checks:
            say(f"  {'PASS' if ok else 'FAIL'}  {name:14s} {detail}")
        say("=" * 78)
        say(f"  通过 {sum(1 for _, o, _ in checks if o)}/{len(checks)}")
        say("")
        say("全部日志行：")
        for ln in lines[:0]: pass
    # 返回失败数：由 __main__ 转成退出码（此前无论成败都返回 0，单独复跑会看不出失败）
    return sum(1 for _, o, _ in checks if not o)

failed = asyncio.run(main())
report = "\n".join(lines)
OUT.write_text(report, encoding="utf-8")

# 同时打到 stdout：开发文档里给出的「单独复跑」命令就是本脚本，只落盘会让人以为它没干活
print(report)
print(f"（同一份日志已落盘：{OUT}）")
sys.exit(1 if failed else 0)
