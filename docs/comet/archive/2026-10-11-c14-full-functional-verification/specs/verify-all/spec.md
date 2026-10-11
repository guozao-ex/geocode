# verify-all — 全量功能自动化验证入口

`tests/verify_all.py` 是 GeoCode 的统一全量功能验证入口：一条命令在本地完成全部可离线执行的功能检查，自动编排 daemon 生命周期，产出结构化报告与机器可读覆盖矩阵。既有检查资产（tests/unit、tests/smoke_*.py）行为零修改，本入口只做编排、生命周期管理与报告。

## 用法

```bash
# conda geo 环境，仓库根
python tests/verify_all.py
```

无必填参数；不提供 `--online` 开关（在线依赖检查一律 SKIP）。

## 检查计划

入口按静态的「网络依赖分类表」把检查项分为 RUN 与 SKIP 两层，分类依据写入检查项元数据：

### RUN（离线层，全部执行）

- `tests/unit`：`-m unittest discover -s tests/unit`，≥212 用例，覆盖契约（spec/指纹/grid/CRS）、presets、array_chunking、osm、export_jobstore、layout/overlay spec、pro_addin、preflight 端点探测等单元面；
- `tui-timeseries-probe`：时序 spec 驱动 TUI headless 渲染探针（复用 smoke_all 同款实现）；
- `daemon-endpoint-probe`：入口自带的新探针——对 127.0.0.1:6531 的 /mcp（initialize + tools/list）、/rpc（status）、/events（SSE hello）做本地端点级断言（仅本地回环，不发起外网请求）；
- `smoke_array_chunking --stage rescan-big`：已有大网格产物的离线重扫描；**前置条件**：产物 `data/derived/s2_chunking_big_smoke.<当前指纹>.nc` 存在；缺失时该项转 SKIP 并注明原因（与 map_renderers 缓存未命中同款语义），联网跑 `--stage big` 生成产物后自动转 RUN。

### SKIP（本轮在线依赖层，标记并注明原因）

- `smoke_emit`、`smoke_three_exits`：array 出口真实拉取 GEE 像素；
- `smoke_presets`：GEE 真实值复算；
- `smoke_timeseries`：GEE 拉取 8 次；
- `smoke_osm`：Overpass API（经 geocode.json 代理）及首轮栅格建源；
- `smoke_tui`：其 action_describe 段走 /rpc gee.describe → ee.data.getAsset()（GEE REST，需网络+认证）；TUI 渲染面已由 tui-timeseries-probe 离线覆盖；
- `smoke_map_renderers`（qgis/arcpy）：当代 PV 下 `_ensure_raster` 缓存未命中时需联网生成，命中后可离线复跑。

SKIP 项在报告中保留行位，状态 `SKIP`，注明原因与单独复跑方式；不发起任何网络请求。

## daemon 生命周期

入口自动检测 6531 端口：无 daemon 则启动（独立进程、用完即停、日志落 logs/），8 秒内未监听则该相关检查项判 FAIL；已有 daemon 则复用。结束时仅停止由入口自行启动的 daemon。

TUI 与 daemon 的功能覆盖映射：TUI 渲染面由 tui-timeseries-probe 承担；daemon 的 /mcp /rpc /events 由 daemon-endpoint-probe 承担；smoke_tui 因 describe 段的网络依赖归 SKIP 层，在覆盖矩阵中如实显示。

## 报告

- 控制台：逐检查项 `[PASS/FAIL/SKIP] 名称 耗时`，末尾汇总（RUN 通过数/失败数/SKIP 数）与覆盖矩阵摘要；
- JSON 报告落盘 `logs/verify_all_report.json`：每检查项含 `name / module / layer(run|skip) / status(pass|fail|skip) / duration_s / log_path / skip_reason / fail_summary`（失败项附 stdout/stderr 尾部摘要），顶层含 `started_at / finished_at / overall` 与覆盖矩阵；
- 覆盖矩阵：README 功能面模块（契约、三出口、presets、batch、chunking、timeseries、OSM、daemon/MCP/RPC/events、TUI、arcpy bridge、add-in 探测、preflight、client）逐模块列出映射的检查项及状态；无任何检查项映射的模块显式标 `uncovered`。

## 退出码

任一 RUN 项 FAIL → 1；否则（全部 PASS 或 SKIP）→ 0。

## Scenario: 全量验证一条命令跑通

哥哥在仓库根执行 `python tests/verify_all.py`，入口自动起停 daemon，无需任何手工前置步骤；RUN 层全部执行，SKIP 层保持跳过；结束后打印汇总并按退出码语义返回。
验收：A1

## Scenario: 覆盖矩阵防漏测

报告中的覆盖矩阵覆盖 README 全部功能面模块；每个模块至少映射一项实际检查项（RUN 或 SKIP），无法映射的模块显式标 `uncovered` 而非静默缺失。
验收：A2

## Scenario: 离线层零网络通过

tests/unit 全量用例、tui-timeseries-probe、daemon-endpoint-probe（及前置产物存在时的 rescan-big）执行通过；全程对外网请求为零（仅本地回环 127.0.0.1 访问）。
验收：A3

## Scenario: 在线依赖项显式跳过

smoke_emit、smoke_three_exits、smoke_presets、smoke_timeseries、smoke_osm、smoke_tui、smoke_map_renderers（缓存未命中时）、smoke-array-chunking-rescan-big（前置产物缺失时）被标记 SKIP，报告中可见原因与单独复跑方式；入口不提供 --online 开关。
验收：A4

## Scenario: JSON 报告可机读

`logs/verify_all_report.json` 落盘且字段完整（名称/模块/层/状态/耗时/日志路径，失败项含输出摘要）；控制台摘要与 JSON 内容一致。
验收：A5

## Scenario: 既有资产行为零修改

tests/ 下 9 个 smoke 与 tests/unit 的既有代码在本 change 中不被修改（git diff 为空）；入口仅编排运行。
验收：A6

## Scenario: 不真实启动 ArcGIS Pro

全量验证全程不启动 ArcGIS Pro UI 进程；add-in/arcpy 面的验证由 tests/unit 断言（test_pro_addin、test_preflight_pro_endpoint）承担，并在覆盖矩阵中体现为 add-in 探测/arcpy bridge 模块的检查项。
验收：A7
