# Capability：verify-all —— 全量功能自动化验证入口

`tests/verify_all.py` 是 GeoCode 的统一全量功能验证入口：一条命令在本地完成全部可离线执行的功能检查，自动编排 daemon 生命周期，产出结构化报告与机器可读覆盖矩阵。既有检查资产（tests/unit、tests/smoke_*.py）行为零修改，本入口只做编排、生命周期管理与报告。

## 用法

```bash
# conda geo 环境，仓库根
python tests/verify_all.py
```

无必填参数；不提供 `--online` 开关（在线依赖检查一律 SKIP）。

## 检查计划

入口按静态的「网络依赖分类表」把检查项分为 RUN 与 SKIP 两层，分类依据写入检查项元数据：

> ⚠️ **c17 修订（2026-10-18）**：条件项的**层位由盘上/环境事实决定**，不再由静态表固定 ——
> 渲染两项在当代指纹缓存命中时自动入 RUN 层（缺失则 SKIP 且文案写实），ruff 项在 uv/ruff
> 可用时入 RUN 层（不可用则 SKIP + 安装提示）。见下方 RUN 层第 4/5 条与
> `docs/comet/specs/README.md` 的 supersession 台账。

### RUN（离线层，全部执行）

- `tests/unit`：`-m unittest discover -s tests/unit`，≥212 用例，覆盖契约（spec/指纹/grid/CRS）、presets、array_chunking、osm、export_jobstore、layout/overlay spec、pro_addin、preflight 端点探测等单元面；
- `tui-timeseries-probe`：时序 spec 驱动 TUI headless 渲染探针（复用 smoke_all 同款实现）；
- `daemon-endpoint-probe`：入口自带的新探针——对 127.0.0.1:6531 的 /mcp（initialize + tools/list）、/rpc（status）、/events（SSE hello）做本地端点级断言（仅本地回环，不发起外网请求）；
- `smoke_array_chunking --stage rescan-big`：已有大网格产物的离线重扫描；**前置条件**：产物 `data/derived/s2_chunking_big_smoke.<当前指纹>.nc` 存在；缺失时该项转 SKIP 并注明原因（与 map_renderers 缓存未命中同款语义），联网跑 `--stage big` 生成产物后自动转 RUN。
- `smoke-map-renderers-qgis` / `smoke-map-renderers-arcpy`（**c17 新增为条件项**）：**前置条件**：当代指纹的 P0 栅格缓存 `data/derived/s2_beijing_test.<当前指纹8位>.tif` 存在且 >4096 B（即 `_ensure_raster` 命中、离线可跑）；命中时两项进入 RUN 层并 PASS（实测量级 2026-10-18：经本入口运行时 qgis 约数秒、arcpy 数十秒；具体耗时随机器状态浮动——同一台机器上实测曾从 24 s 劣化到 120 s，且用改动前代码同时刻实测同样约 118 s，属 ArcGIS Pro 冷启/许可服务等环境因素，非本入口引入，故此处不写死具体数值），缺失时保持 SKIP 且文案写实（说明「当代缓存缺失，联网跑一次即可离线复跑」）。与 rescan-big 同款条件项语义与实现风格。
- `report-selfcheck`（**c21 新增为条件 RUN 项**）：入口写完报告后，以子进程运行
  `python tools/verify_facts_check.py logs/verify_all_report.json`，把它对**刚落盘的第 1 版报告**的
  事实一致性结论作为一条检查项写回报告。工具退出码 0 → PASS；1（有违规）或 2（输入错误）→ FAIL，
  失败摘要附违规条目（断言 id + 检查项名 + 断言文本）；`tools/verify_facts_check.py` 不存在时转
  SKIP + 提示（与 ruff 门禁同款风格，不 FAIL）。该项**必须最后执行**，见「报告」节的**两遍写法**。
- `ruff-check`（**c17 新增为可选 RUN 项**）：执行 `uvx --offline ruff@0.17.0 check`（`ruff.toml` 门禁，零安装）；uv/ruff 可用且缓存就绪时为 RUN 项，零告警 PASS、有告警 FAIL（退出码语义生效）；uv 或 ruff 不可用（含 uv 缓存冷）时转 SKIP + 安装提示（不 FAIL）。**必须带 `--offline`**：uvx 默认会为冷缓存下载 ruff，与「新增 RUN 项不得引入外网请求」相冲突。

### SKIP（本轮在线依赖层，标记并注明原因）

- `smoke_emit`、`smoke_three_exits`：array 出口真实拉取 GEE 像素；
- `smoke_presets`：GEE 真实值复算；
- `smoke_timeseries`：GEE 拉取 8 次；
- `smoke_osm`：Overpass API（经 geocode.json 代理）及首轮栅格建源；
- `smoke_tui`：其 action_describe 段走 /rpc gee.describe → ee.data.getAsset()（GEE REST，需网络+认证）；TUI 渲染面已由 tui-timeseries-probe 离线覆盖；
- `smoke_map_renderers`（qgis/arcpy）：当代 PV 下 `_ensure_raster` 缓存未命中时需联网生成，命中后可离线复跑。

> ⚠️ **c17 修订（2026-10-18）**：上一条 SKIP 语义已被收窄 —— `smoke_map_renderers`（qgis/arcpy）
> **仅在当代缓存缺失时**保持在 SKIP 层；缓存命中时按条件项**自动升入 RUN 层**（见 RUN 层第 4 条）。
> SKIP 行位、原因与单独复跑方式仍按本节口径保留，不做删除。原文保留不删，见
> `docs/comet/specs/README.md` 台账。

SKIP 项在报告中保留行位，状态 `SKIP`，注明原因与单独复跑方式；不发起任何网络请求。

> ⚠️ **c17 补充（2026-10-18）**：SKIP 文案必须与盘上/环境事实逐条一致 ——
> 缓存/前置产物**存在**时不得出现「不存在 / 未命中」字样；产物**缺失**时不得出现「已命中」字样；
> 产物实际在主工作区盘上时不得断言「不在主工作区」。`summary.skipped` 必须等于
> checks 中 `status == "skip"` 的条数。

## daemon 生命周期

入口自动检测 6531 端口：无 daemon 则启动（独立进程、用完即停、日志落 logs/），8 秒内未监听则该相关检查项判 FAIL；已有 daemon 则复用。结束时仅停止由入口自行启动的 daemon。

TUI 与 daemon 的功能覆盖映射：TUI 渲染面由 tui-timeseries-probe 承担；daemon 的 /mcp /rpc /events 由 daemon-endpoint-probe 承担；smoke_tui 因 describe 段的网络依赖归 SKIP 层，在覆盖矩阵中如实显示。

## 报告

- 控制台：逐检查项 `[PASS/FAIL/SKIP] 名称 耗时`，末尾汇总（RUN 通过数/失败数/SKIP 数）与覆盖矩阵摘要；
- JSON 报告落盘 `logs/verify_all_report.json`：每检查项含 `name / module / layer(run|skip) / status(pass|fail|skip) / duration_s / log_path / skip_reason / fail_summary`（失败项附 stdout/stderr 尾部摘要），顶层含 `started_at / finished_at / overall` 与覆盖矩阵；
- （c21）**两遍写法**：`main()` 先组装并写出第 1 版报告，再运行 `report-selfcheck`，把其结论插回
  `checks`、重算 `summary` 与 `coverage_matrix`，然后**整体重写**报告；最终报告仍是唯一事实源，
  不产生额外中间文件。
- （c21）**自指说明**：`report-selfcheck` 读到的是**第 1 版**快照（不含它自身）；最终报告里含有该项，
  但对该报告单独复跑 `tools/verify_facts_check.py` 仍应退出 0 —— 工具的 G1–G4 独立核对
  `summary` 与 `checks` 的吻合，不受「多了一条检查项」影响。
- 覆盖矩阵：README 功能面模块（契约、三出口、presets、batch、chunking、timeseries、OSM、daemon/MCP/RPC/events、TUI、arcpy bridge、add-in 探测、preflight、client）逐模块列出映射的检查项及状态；无任何检查项映射的模块显式标 `uncovered`。
- （c17）条件项与可选项的状态同样进入 JSON 报告与覆盖矩阵；条件成立的真实耗时要落 `duration_s`，SKIP 项耗时保持 0。
- （c17）每条检查项新增 `probe` 字段，记录层位判据：条件项为 `{"kind": "cache_probe", "path", "exists", "size_bytes", "min_bytes", "hit"}`，ruff 项为 `{"kind": "tool_probe", "cmd", "uvx", "ok"}`；固定 RUN/SKIP 项为 `null`。报告读者可据此直接核对「为什么这一项是 RUN 还是 SKIP」。
- （c21）`probe` 形态补充：`report-selfcheck`（c21 新增的条件项）为
  `{"kind": "tool_probe", "cmd", "path", "ok"}`（`ok` = 自查工具文件是否存在，对应其 RUN/SKIP 层位）；
  `smoke-array-chunking-rescan-big`（c17 时漏了判据的条件项）同渲染两项改用 `cache_probe`，但其产品
  没有额外体积门槛（`min_bytes` 记 0）；该两项的层位判据与 `probe.hit` 同源 —— 均为「产物存在且非空」
  （0 字节视为不可用，SKIP 文案如实写「存在但为空」）。

## 退出码

任一 RUN 项 FAIL → 1；否则（全部 PASS 或 SKIP）→ 0。

> ⚠️ **c21 补充（2026-10-18）**：`report-selfcheck` 作为条件 RUN 项参与同一退出码语义 ——
> 它在 RUN 层且报 FAIL（报告与盘上事实不一致，或工具自身返回输入错误 2）时，进程退出码为 1；
> 它因工具缺失转 SKIP 时不影响退出码。
>
> ⚠️ **c17 补充（2026-10-18）**：`ruff-check` 作为可选 RUN 项参与同一退出码语义 ——
> 它在 RUN 层且报 FAIL 时，进程退出码为 1；它转 SKIP 时不影响退出码（与其它 SKIP 项一致）。

> **c17 编号说明（2026-10-18）**：验收集编号连续且 brief 与 spec **互不重叠** ——
> brief 占 **A1–A9**（A1–A5 为条件项/措辞/发布面/ruff/回归，A6–A9 为渲染失败语义收紧四项），
> 本 spec 的 14 个场景占 **A10–A23**。
> 其中 A10–A16 为 C14（`2026-10-11-c14-full-functional-verification`）归档时编号 A1–A7 的同一批场景，
> 按「编号须对应本 change 验收集」的发布面规范（C13 规 2）整体重排；
> 对应关系：A10←A1、A11←A2、A12←A3、A13←A4、A14←A5、A15←A6、A16←A7。
> A17–A19 为 c17 第一批新增场景（条件项/措辞/ruff），A20–A23 为第二批新增场景（渲染失败语义收紧）。
> **各场景正文逐字未改**，仅标题内的引用编号重排（该形态修正与 C13 自身 spec 的 A13–A24 自纠同类，
> 登记于 `docs/comet/specs/README.md` 的「就地订正」表）。

### Scenario: 全量验证一条命令跑通（验收：A8）

哥哥在仓库根执行 `python tests/verify_all.py`，入口自动起停 daemon，无需任何手工前置步骤；RUN 层全部执行，SKIP 层保持跳过；结束后打印汇总并按退出码语义返回。

> ⚠️ **c17 修订（2026-10-18）**：本条在 C14 归档时的验收编号为 A1；在 c17 中编号改为 **A10**
> （brief 的验收示例占用 A1–A9）。语义不变：一条命令跑通的总纲。原文保留不删。

### Scenario: 覆盖矩阵防漏测（验收：A9）

报告中的覆盖矩阵覆盖 README 全部功能面模块；每个模块至少映射一项实际检查项（RUN 或 SKIP），无法映射的模块显式标 `uncovered` 而非静默缺失。

### Scenario: 离线层零网络通过（验收：A10）

tests/unit 全量用例、tui-timeseries-probe、daemon-endpoint-probe（及前置产物存在时的 rescan-big）执行通过；全程对外网请求为零（仅本地回环 127.0.0.1 访问）。

> ⚠️ **c17 修订（2026-10-18）**：本条 RUN 层构成已被扩展 —— 当代缓存命中时，
> `smoke-map-renderers-qgis` / `-arcpy` 亦在 RUN 层执行并通过；ruff 项以
> `uvx --offline` 执行（零外网请求）。「全程对外网请求为零」的口径不变，
> 仍是本场景的硬断言。原文保留不删，修订依据见 `docs/comet/specs/README.md`。

> ⚠️ **c22 修订（2026-10-18，用户裁决口径）**：上一条 c17 注记称「全程对外网请求为零」的口径不变、
> 仍是硬断言 —— 经实测该表述**不成立**：当代缓存命中时 `smoke-map-renderers-arcpy` 会拉起
> `arcgispro-py3` 子进程，后者在渲染期间回连 Esri 许可/basemap 服务（观测到 443/80 出站约 12 s+；
> `smoke-map-renderers-qgis` 一侧未观测到外连）。故本场景断言**收窄为「入口自身发起的对外请求为零」**：
> 覆盖 python 主进程、入口自带的 daemon 探针与既有 smoke/单测（仅访问 127.0.0.1 且探针显式禁代理）；
> **arcpy / QGIS 渲染子进程属第三方运行时（ArcGIS Pro / QGIS），其厂商回连不计入本断言** ——
> 它们是「离线可跑」（不依赖网络即可产出）而非「零外网」。原文与 c17 注记均保留不删。

### Scenario: 在线依赖项显式跳过（验收：A11）

smoke_emit、smoke_three_exits、smoke_presets、smoke_timeseries、smoke_osm、smoke_tui、smoke_map_renderers（缓存未命中时）、smoke-array-chunking-rescan-big（前置产物缺失时）被标记 SKIP，报告中可见原因与单独复跑方式；入口不提供 --online 开关。

> ⚠️ **c17 修订（2026-10-18）**：本条的 SKIP 集合已收窄 ——
> `smoke_map_renderers`（qgis/arcpy）与 `smoke-array-chunking-rescan-big` 改为**条件项**：
> 前置产物存在时**不得**出现在 SKIP 集合中（自动入 RUN 层），缺失时才 SKIP 且文案写实。
> 「入口不提供 --online 开关」不变。原文保留不删，见 `docs/comet/specs/README.md` 台账。

### Scenario: JSON 报告可机读（验收：A12）

`logs/verify_all_report.json` 落盘且字段完整（名称/模块/层/状态/耗时/日志路径，失败项含输出摘要）；控制台摘要与 JSON 内容一致。

### Scenario: 既有资产行为零修改（验收：A13）

tests/ 下 **10 个** smoke（含 `smoke_all.py` 汇总器）与 tests/unit 的既有代码在本 change 中不被修改（git diff 为空）；入口仅编排运行。

> **c22 就地订正（2026-10-18）**：原句写「9 个 smoke」—— C14 立此条时盘上确为 9 个，其后
> `tests/smoke_all.py`（汇总器）入库成为第 10 个，计数随之失准。断言本体（既有 smoke 与
> tests/unit 零修改）不受影响；此处只订正计数并注明沿革，登记于
> `docs/comet/specs/README.md` 的「就地订正」表。

> ⚠️ **c22 范围说明（2026-10-18）**：本条约束的是「入口**编排**既有资产、而不改写它们的行为」。
> c22 为修一处测试健壮性问题（工具文件缺失时整个 tests/unit 因硬 import 整片红）**修改了
> `tests/unit/test_verify_report_tools.py` 的 import 形态与 skip 语义** —— 不改其中任何一条断言。
> 故本场景对 c22 的判读是：10 个 smoke 全部零 diff、tests/unit 除该模块外零 diff，且该模块的
> 41 条断言在工具齐备时行为与改动前完全一致（实测 41 例 OK）。

### Scenario: 不真实启动 ArcGIS Pro（验收：A14）

全量验证全程不启动 ArcGIS Pro UI 进程；add-in/arcpy 面的验证由 tests/unit 断言（test_pro_addin、test_preflight_pro_endpoint）承担，并在覆盖矩阵中体现为 add-in 探测/arcpy bridge 模块的检查项。

> ⚠️ **c17 补充（2026-10-18）**：`smoke-map-renderers-arcpy` 进入 RUN 层后，本场景约束不变且
> 已实测复核 —— arcpy 出图经 `arcgispro-py3` 解释器的**子进程**完成（`arcpy.mp.CreateArcGISProject`），
> 2026-10-18 缓存命中的一轮 `tasklist` 核对**无** `ArcGISPro.exe` 进程；本入口仍不含任何启动 Pro UI 的调用。

### Scenario: 条件项按盘上事实自动升降（验收：A15）

当代指纹的 P0 栅格缓存存在时，`smoke-map-renderers-qgis` 与 `smoke-map-renderers-arcpy` 在报告中为 `layer=run / status=pass` 并附真实耗时；缓存缺失时两项为 `layer=skip / status=skip`，文案写明「当代缓存缺失，联网跑一次即可离线复跑」，不得出现「已命中」字样。`smoke-array-chunking-rescan-big` 同款语义保持一致。

### Scenario: SKIP 文案与盘上事实逐条一致（验收：A16）

报告中每条 SKIP 的措辞与盘上/环境事实一致：产物存在时不含「不存在 / 未命中」，产物缺失时不含「已命中」，产物在主工作区盘上时不含「不在主工作区」；`summary.skipped` 等于 `status == "skip"` 的条数，且与各条件项的实际前置条件吻合。

### Scenario: ruff 以可选 RUN 项接入（验收：A17）

uv/ruff 可用时，入口以 `uvx --offline ruff@0.17.0 check` 执行 ruff 门禁并计分：零告警为 PASS、有告警为 FAIL（进程退出码 1）；uv 或 ruff 不可用（含 uv 缓存冷、`--offline` 无法解析）时该项为 SKIP 并给出安装/预热提示，不判 FAIL；两种条件下入口均不发起外网请求。

### Scenario: 渲染局部失败必须判失败（验收：A18）

构造「`.qgz` 生成失败但 `.png` 渲染成功」的条件时，`emit_map` 必须判失败：抛错、`job.error` 非空、
不返回成功结果，失败消息包含 qgz 一侧的真实原因；对应 `smoke_map_renderers.py qgis` 退出码非 0。

> ⚠️ **c17 修订（2026-10-18，用户裁决「全量修复风险」）**：本条推翻原实现口径 ——
> `gis/emit.py` 原 `branch_failed` 判据为「`qgz_error` **且** `png_error`」，
> 即两者都失败才算失败；已实测复现「qgz 失败 + png 成功 ⇒ 整体判成功」。

### Scenario: 布局失败不再被吞（验收：A19）

QGIS 侧返回 `layout_error` 非空时，`emit_map` 判失败并把该错误写入失败消息/结果；
不得出现「报告里对布局失败毫无痕迹」。无 `layout_error` 的正常路径仍返回 `.qgz`。

> ⚠️ **c17 修订（2026-10-18）**：`gis/qgis_bridge.py` 一直产出 `layout_error`，
> 但 `gis/emit.py` 只读 `layout` 键、丢弃该错误；已实测复现结果中无任何痕迹。

### Scenario: arcpy 产物齐备性核验（验收：A20）

`write_aprx` 返回成功但**缺 `spec.layout.formats` 所要求的任一导出**时，`emit_map` 判失败而非
静默成功；`.aprx` 恒为预期产物。正常情况下 formats（默认 `("pdf","png")`）齐备仍 PASS；
`formats=("pdf",)` 这类**只要求单一格式的合法配置必须 PASS**；`layout=None`（nolayout，
只出 map-only `.aprx`、无任何导出）**不**算失败。

> ⚠️ **c17 新增（2026-10-18）**：原实现仅在 `res.get(key)` 为真时登记产物，缺键不报错。
> 该条与上两条共同确立「预期产物缺一即失败」的统一口径。

### Scenario: 收紧失败语义不回归既有资产（验收：A21）

`tests/unit` 全量仍全绿、`uvx ruff@0.17.0 check` 零告警；`tests/smoke_three_exits.py` 与
`tests/smoke_osm.py` 中读取 `qgz_error`/`overlay_errors` 的代码**未被修改**且判错语义不受影响；
`tests/verify_all.py` 仍一条命令跑通，缓存命中态渲染两项 PASS 且成功产物哈希不漂移。

> ⚠️ **c22 判据澄清（2026-10-18）**：末句「成功产物哈希不漂移」的**判据是「生产路径零 diff」**，
> 不是「产出文件逐字节可复现」—— 实测 `.aprx` / `.layout.pdf` 内嵌生成时间戳，跨轮哈希必然不同；
> `.png` / `.qgz` / `.rgb8.tif` 在同等输入下稳定。故本场景核对的是「渲染链路与产物集合未变、
> 稳定产物跨轮一致」，`.aprx` / `.layout.pdf` 以存在性 + 结构/内容要素为准。原文保留不删。

> **跨 capability 说明（2026-10-18）**：`emit_map` 的失败判定实现位于 `gis/emit.py`，
> 其 capability 归属为 `p1a-arcpy-bridge`（该 spec 定义了 `emit_map` 的 renderer 纪律与产物面）。
> 本 change 对「局部失败/布局失败/导出缺失」的收紧只直接影响 **verify-all 的 PASS 可信度**，
> 因此验收与场景登记在本 spec；`p1a-arcpy-bridge` 的既有条款未被删除或改写。
> **用户 2026-10-18 选 (a)**：`p1a-arcpy-bridge` 的 spec 与归档副本**只追加一条 `> ⚠️` 注记**
> 指向本次收紧（原文零删除、双副本逐字节一致、README 台账登记），**不改动**其 Scenario、
> Scenario 编号与既有验收；`emit_map` 的 renderer 纪律与产物面条款本身不变。

### Scenario: 报告自查接入 RUN 层（验收：A22）

入口一次运行结束时，报告中含一条 `report-selfcheck`（`layer=run`、`status=pass`），控制台有对应行；
它核对的是同一轮写出的报告，且该项自身也出现在最终报告的 `checks` 与覆盖矩阵里。

### Scenario: 报告自查失败即入口失败（验收：A23）

人为制造「报告与盘上事实不一致」（例如把某条 `skip_reason` 改成与盘上相反的说法）时，
`report-selfcheck` 判 FAIL、进程退出码为 1，且报告里给出可读的失败摘要（含违规的断言 id、
检查项名与断言文本）；其余 RUN 项的判定与覆盖矩阵仍如实写入，报告仍是完整合法 JSON。

### Scenario: 两遍写法下报告自洽（验收：A24）

最终报告的 `summary`（run/passed/failed/skipped）与 `coverage_matrix` 都计入 `report-selfcheck`，
且与 `checks` 逐项吻合；对最终报告单独复跑
`python tools/verify_facts_check.py logs/verify_all_report.json` 退出码为 0、零违规。

### Scenario: 缺少自查工具时归 SKIP（验收：A25）

`tools/verify_facts_check.py` 不存在时，`report-selfcheck` 为 `layer=skip / status=skip` 并给出提示，
不判 FAIL、不影响进程退出码；入口的其余行为不变。

> **c21 编号说明（2026-10-18）**：本次修订按 C13 发布面规范 2（「编号用该 change 的验收集编号」）
> 把原有 14 个场景的标题内引用从 c17 的 **A10–A23** 整体前移为 **A8–A21**（c21 的 brief 占 A1–A7），
> 新增 4 个场景为 **A22–A25**。**各场景正文逐字未改**，仅标题内编号重排；上方 c17 的编号说明
> 与历史映射（A10←C14 A1 … A16←C14 A7）**原文保留不删**。本项登记于
> `docs/comet/specs/README.md` 的「就地订正」表。
