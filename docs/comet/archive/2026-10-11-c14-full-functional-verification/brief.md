# Outcome

为 GeoCode 建立**全量功能自动化验证**：一条命令跑完项目全部功能面的既有检查（离线单测 + smoke 套件 + 服务层探针），自动处理 daemon 生命周期，产出结构化验证报告（JSON + 控制台摘要），并以退出码表达总体结论。功能覆盖以 README.md 与 docs/README.md 声明的功能面为准，验证报告必须给出「功能模块 → 检查项」覆盖矩阵，杜绝静默漏测。

交付物：可复用统一验证入口 `tests/verify_all.py`，并实际跑通一轮留档。本轮验证**完全不碰网络**：依赖网络的检查一律标记 SKIP 并注明原因，不留 --online 开关。

# Scope

- 验证对象：仓库 `gis/` 包全部功能面（README.md 声明），分层如下：
  - 契约层：ArtifactSpec / 指纹 / compute_grid / CRS 规则；
  - 三出口：emit_file（GeoTIFF/COG）、emit_array（xarray）、emit_map（.qgz/.png，QGIS 与 arcpy 渲染器）；
  - 扩展：presets、batch export、array chunking、timeseries、OSM/Overpass；
  - 服务层：daemon（6531，/mcp + /rpc + /events，9 个 MCP 工具）、Client、TUI；
  - 桌面端：arcpy bridge（headless 出版）、ArcGIS Pro add-in 探测（端点级）、preflight；
- 现有资产：`tests/unit`（16 文件、212 用例、离线 ~5s，受 test_offline_guard 禁网约束）；`tests/smoke_*.py` 9 个（smoke_all.py 现只编排其中 4 个 + 渲染器双跑 + TUI 探针）；
- 交付物（已确认）：统一验证入口 `tests/verify_all.py`（编排 unit + 全部 smoke + daemon 生命周期 + 覆盖矩阵 + JSON 报告），并实际跑通一轮留档；
- 在线依赖检查（需真实 GEE 像素/认证，或前置产物/缓存缺失需联网生成的）本轮一律 SKIP 并注明原因，入口不提供 --online 开关；离线可用的检查（tests/unit、tui-timeseries-probe、daemon-endpoint-probe，及 rescan-big 在前置产物存在时）全部执行；
- 现有 smoke 与 unit 的行为零修改，只做编排（smoke_all 未纳入的 4 个 smoke 由新入口纳入编排）；
- 报告内容：每检查项（名称 / 所属模块 / 层 / 状态 / 耗时 / 日志路径 / 失败摘要），总体结论 + 覆盖矩阵。

## Source coverage

无外部来源文档；功能面清单以仓库内 README.md、docs/README.md（§1–§5、§12 命令速查）为调查依据，非用户指定覆盖边界，不触发逐条登记。

## 目录结构

### 新建

- `tests/verify_all.py`：统一全量验证入口（编排 + daemon 生命周期 + daemon-endpoint-probe + 覆盖矩阵 + JSON 报告）；
- `logs/verify_all_report.json`：运行产物（运行时生成，logs/ 已被忽略不入库）。

### 修改

- 无（现有 9 个 smoke 与 tests/unit 行为零修改）。

### 删除

- 无。

### 明确不建

- 不建 CI 配置、不建 pytest 框架层、不建 Markdown 报告生成器、不建 --online 开关；
- 不修改 gis/ 包任何模块。

# Non-goals

- 不做性能基准测试、覆盖率统计工具接入；
- 不搭建 CI 流水线（本地命令行验证为准）；
- 不新增产品功能、不修改三出口/daemon/TUI 任何行为；
- 不重写现有 smoke 与 unit 的断言逻辑；
- 不做跨平台适配（仅本机 Windows + conda geo 环境）。

# Acceptance examples

- A1: 在仓库根用 geo 环境 python 执行 `python tests/verify_all.py`，无需任何手工前置步骤（daemon 自动检测/启动/停止），全部检查自动执行，任一失败时进程退出码非 0，全部通过（含 SKIP）时为 0。
- A2: 报告含覆盖矩阵：README 声明的每个功能模块（契约、三出口、presets、batch、chunking、timeseries、OSM、daemon/MCP/RPC/events、TUI、arcpy bridge、add-in 探测、preflight、client）至少映射到一项实际执行的检查项（RUN 或 SKIP）；未覆盖模块在矩阵中显式标 uncovered，不允许静默缺失。
- A3: 离线层全自动：tests/unit 全量（≥212 用例）、tui-timeseries-probe、daemon-endpoint-probe 全部通过（smoke-array-chunking --stage rescan-big 在前置产物存在时执行），全程不发起外网请求（仅 127.0.0.1 本地回环）。
- A4: 在线依赖检查（smoke_emit、smoke_three_exits、smoke_presets、smoke_timeseries、smoke_osm 的 Overpass/栅格建源、smoke_map_renderers 当代缓存未命中时、smoke_tui 的 describe 段走 GEE REST、smoke-array-chunking-rescan-big 前置产物缺失时）标记 SKIP 并注明原因与单独复跑方式，全程不发起任何网络请求，入口无 --online 开关。
- A5: JSON 报告落盘 logs/ 下，含每检查项名称/模块/层/状态/耗时/日志路径，失败项含 stdout/stderr 摘要；控制台输出等价摘要表。
- A6: 现有 9 个 smoke 与 tests/unit 行为零修改（新入口只做编排与新探针）。
- A7: 不真实启动 ArcGIS Pro UI；add-in/arcpy 面由 tests/unit 断言（test_pro_addin、test_preflight_pro_endpoint 等）覆盖并在矩阵中体现。

# Constraints and invariants

- tests/unit 受 test_offline_guard AST 禁网约束（禁 import ee/requests/socket 等），新入口不得破坏该守卫；
- 验证入口运行于 conda geo 环境（python 3.12），daemon 端口 6531，复用 smoke_all 的生命周期模式（用完即停、独立进程）；
- geocode.json 为 skip-worktree 本地件，含真实 GEE project id，验证依赖其存在但不入库、不外泄内容；
- `tests/unit` 离线守卫只约束 tests/unit 目录；`tests/verify_all.py` 位于 tests/ 根，允许使用本地 HTTP 探针（仅 127.0.0.1，不发起外网请求）。

# Decisions

- D1（Q1）：交付物为可复用验证入口 `tests/verify_all.py` 并跑通留档；不采用「仅跑现有资产」——哥哥明确要以后一条命令随时全量回归。
- D2（Q2）：本轮完全不碰网络；在线依赖检查一律 SKIP + 原因，不留 --online 开关（哥哥选 C）。
- D3（Q3）：报告 = 控制台摘要 + JSON 落盘；不产出 Markdown 报告（可后续按需加）。
- D4（Q4）：不真实启动 ArcGIS Pro UI；add-in/arcpy 面由 unit 断言 + 端点级探测覆盖（哥哥选 A）。
- D5（Build 期事实修正，2026-10-11）：实测发现 ① smoke_tui 的 action_describe 段走 /rpc gee.describe → ee.data.getAsset()（GEE REST，需网络+认证，C3 验收时联网跑过、非离线安全）；② smoke-array-chunking --stage rescan-big 的前置产物 data/derived/s2_chunking_big_smoke.9d517910.nc 不在主工作区（C6 worktree 时代产物，未入库）。二者按 SKIP+原因+单独复跑方式处理，与 smoke_map_renderers 缓存未命中同款语义；TUI 渲染面与 chunking 单元面分别由 tui-timeseries-probe、tests-unit 离线覆盖。A3/A4 文字同步更新。

# Open questions

（无：Q1–Q4 已由哥哥 2026-10-11 批量答复确认，结论见 Decisions D1–D4。）
