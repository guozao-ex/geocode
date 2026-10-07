---
generated_from_state_version: 21
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 2
- 迭代: 3
- 验证器尝试次数: 2
- 完成时间: 2026-10-07T03:26:02.470Z
- 摘要: C6 emit_array 大网格分块独立验收 7/7 通过。核心证据均经本人独立复证：113 离线用例亲跑全绿（3.3s，Runtime 10:38 正式回执一致且实现文件 mtime 均早于该检查）；sha256 三方链亲算闭合（worktree P0 产物=主工作区金产物=stage1 direct 副本，均 db2a6296a3228e90…），direct 路径字节级不变；_compute_array_via_xee 本体零改动；plan_chunks 双上限纯函数离线钉死且与真实 io_chunks 一致；分块只经 open_dataset 进入、无事后 .chunk()（守卫单测 + 红线 6 串行实测：小网格双路径逐像素 max|diff|=0 → 大网格 8244×8253@10m est 204.1M px 25 块 778.77MB 落盘读回合格）；内存峰值两点实测不随网格增长（Δ150.5/227.1MB，像素差 101×）；分块参数不进 spec/指纹（PV2/PV3 双时代金指纹亲算吻合，缓存命中语义不变）；文件改动面 emit.py+新测试，daemon/jobs/TUI/source/grid 零 diff，emit_file/emit_map 64M 上限与既有报错未动。唯一发现为 brief/spec 的 PV=3 事实笔误（实测=2），builder 已披露，记入 risks 不影响判定。Verifier 未执行任何 GEE 实网操作（红线 6），网络证据全部以上一轮留档证据文件+日志核对闭合。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | specs/p2-array-chunking/spec.md | 小网格路径不变——按需触发（验收：A1）【离线；smoke 需网络，已标注】 est = `grid.width × grid.height × N期 × 波段` < `MAX_DIRECT_PIXELS`（64,000,000）时， `_compute_array_via_xee` 走现状代码路径：`xr.open_dataset` 调用**不含** `io_chunks` 参数，读取为现状 `ds.compute()` 全量驻留，落盘为现状 `arr.to_netcdf(tmp)` + `.part` 原子替换——连参数列表都不变，行为字节级一致。离线单测以 monkeypatch 断言 `open_dataset` 收到的调用参数（无 io_chunks）；现有 `tests/unit` 94 用例基线全绿； 现有 smoke（需网络项标注）不回退。运行时强制开关（见下）默认 `auto`，不影响该判定。 | 小网格（est<64M）auto 走现状 direct 路径：diff 核实 _compute_array_via_xee 本体零改动，direct 分支保持 ds.compute() 全量 + arr.to_netcdf(.part) + 原子替换；单测 test_small_grid_auto_stays_direct 断言 open_dataset 无 io_chunks 参数；tests/unit 113 用例本人亲跑全绿（3.3s）；P0 产物三方 sha256 本人亲算相等（worktree s2_beijing_test.c9243efd.nc = 主工作区金产物 = stage1 direct 副本，均 db2a6296a3228e90…，8,120,315B），direct 路径字节级不变成立。 |
| A2 | passed | specs/p2-array-chunking/spec.md | 大网格走分块路径（验收：A2）【离线】 est ≥ 64,000,000 时走分块路径：`open_dataset` 收到显式 `io_chunks`，其值由 **块尺寸纯函数** `plan_chunks(width, height, n_periods, n_bands)` 计算——确定性 （同输入同输出）、无 IO、无全局态，形状映射到 xee 的 `(index=期块, width=x块, height=y块)`；空间优先大块、期维装满剩余预算，块尺寸不必 整除网格（xee 自行处理边缘块）。读取按（期块×空间块）两级循环执行： lazy 打开 → 逐块 `isel(...).values` → 直写预分配 netCDF4 变量切片 → 每块后 `job.check_cancelled()` 并更新 `job.progress`。离线单测以 monkeypatch 断言 `open_dataset` 的 io_chunks 参数、循环块数与块形状均来自 `plan_chunks`。 运行时强制开关 `GEOCODE_ARRAY_PATH`（环境变量，默认 `auto`）：`direct` 强制现状 路径、`chunked` 强制分块路径（用于 A5 交叉验证）。它是测试钩子——不进 `ArtifactSpec`、不进指纹、不进 daemon/TUI 工具面；非法值报可读错误。 | plan_chunks 纯函数确定性/无 IO/无全局态（单测钉死 8200×8200×1×3 → {index:1,width:1672,height:1672}，内含请求侧硬校验断言）；_array_path_mode 阈值 est≥MAX_DIRECT_PIXELS→chunked（64M 边界归 chunked 有测试）；GEOCODE_ARRAY_PATH 强制 direct/chunked、非法值报可读 ValueError；分块路径经 _open_ee_dataset_lazy 在 open_dataset 时显式传 io_chunks，期×空间块循环 isel→values→netCDF4 预分配直写，每块 check_cancelled+progress（diff 核实）；单测断言 io_chunks==plan_chunks 输出、auto 大网格走 chunked、块步长铺满不整除网格；真实 GEE 大网格 8244×8253@10m 以 io_chunks={1,1672,1672} 25/25 块完成（big_smoke_log.txt）。 |
| A3 | passed | specs/p2-array-chunking/spec.md | 不触发 select('*')——守卫 + 串行实测（验收：A3）【守卫离线；实测需网络，已标注】 分块路径全程**不调用事后 `.chunk()`**：离线守卫单测 monkeypatch `xr.Dataset.chunk`（分块路径执行期间被调用即失败）并断言 io_chunks 只经 open_dataset 进入。红线 6 串行实测：先小网格任务强制 `chunked` 验证分块读取正确 （产物与 direct 路径一致，即 A5 的小网格先行），再跑大网格 smoke—— **82km×82km @10m ≈ 67.2M 像素、单期、3 波段（S2_SR_HARMONIZED，B4/B3/B2， reducer=median）**，`emit_array` 成功落盘 `.nc`、读回校验 dims/期数/坐标合格。 触发 `select('*')` 必然 `Invalid regular expression` 400 失败——smoke 成功即为 未触发的证据。 | 离线守卫 test_no_posthoc_chunk_called（monkeypatch xr.Dataset.chunk 被调用即失败）通过；diff 全文无事后 .chunk()，io_chunks 唯一入口为 open_dataset；红线 6 串行实测留档：小网格 chunked 试点成功（41.1s）→ 大网格 smoke 25/25 块完成落盘 778.77MB 并读回校验 dims/期数/坐标合格——触发通配符 select 必 400 Invalid regular expression，成功即未触发证据。 |
| A4 | passed | specs/p2-array-chunking/spec.md | 内存有界——预算上界与实测对照（验收：A4）【上界离线；实测需网络，已标注】 单块驻留字节 = 块像素 × 4B ≤ **32 MiB** 预算常量（≈8.39M 像素/块）；请求侧 = 块像素 × 5B ≤ 48 MB（GEE 单请求上限；32 MiB 预算下自动满足，`plan_chunks` 内保留断言防御预算上调）。离线单测对边界输入（单期/多期、极窄/极宽网格、 超阈值网格）断言 `plan_chunks` 输出满足两个上限且确定。读入阶段峰值上界 = 单块驻留 + 写缓冲（常数级）——大网格 smoke 实测读入阶段内存峰值（记录数值与 采样方式），对照公式上界（容差 ≤ 2×），并在验收报告留档。落盘为逐块增量写， 不整期/全量驻留（D4 裁决：两级分块直写 netCDF4）。 | 离线：TestPlanChunks 对 9 组边界输入断言块像素×波段×4B≤32MiB、×5B≤48MB 且确定；plan_chunks 内请求侧超限 AssertionError 防御；逐块增量直写、不整期/全量驻留（两级循环结构核实）。实测：大网格 psutil 0.2s 采样 peak 278.4MB（Δ227.1MB）留档，另补 2.0M px 第二数据点 Δ150.5MB（memory_constant_evidence.json，含常数分解）——像素差 101× 而峰值增量同带，峰值与网格尺寸无关成立（同规模 direct 全量驻留需约 815MB 数组）。 |
| A5 | passed | specs/p2-array-chunking/spec.md | 两条路径产物一致——交叉验证（验收：A5）【需网络，已标注】 同一 spec 经 `GEOCODE_ARRAY_PATH=direct` 与 `=chunked` 各跑一次 `emit_array` （小网格即可，成本等同两次小网格下载；chunked 侧同时覆盖 A3 的"分块读取正确" 先行验证），产物逐像素比对：NaN 位置一致、max\|diff\| = 0（两路径走同一计算语义 + computePixels float32，预期逐位一致），dims/vars/空间网格（crs/scale/shape 对齐 `compute_grid(spec)`）/time 坐标语义一致。分块路径产物可被 `xr.open_dataset` 读回，dtype 为 float32、掩膜像素为 NaN（与现状 `.nc` 语义一致）；结果 dict 字段 语义与现状一致（exit/path/size_mb/spec_fingerprint/grid/dims/vars/sample/ timeseries）。 | stage1_cross_validation_evidence.json（iteration 3 新变量序重跑，双腿缓存击穿冷下载 direct 25.2s / chunked 41.1s）：B4/B3/B2 max\|diff\|=0.0、NaN 9352 位置逐位一致、dims/vars/sample 一致、verdict PASS；双产物本体留档且文件变量序均为 B4,B3,B2,time,y,x（direct 序）；离线 test_direct_vs_chunked_pixel_identity 与时序用例全绿；emit_array 返回 dict 字段（exit/path/size_mb/spec_fingerprint/grid/dims/vars/sample/timeseries）与现状一致（diff 仅双路径共享化重构）。 |
| A6 | passed | specs/p2-array-chunking/spec.md | 指纹与缓存语义不变（验收：A6）【离线】 分块参数（阈值、预算、`plan_chunks` 输出、`GEOCODE_ARRAY_PATH`）不进 `ArtifactSpec`、不进指纹白名单——`tests/unit` 现有指纹守卫与金指纹 （PV=3 时代 `b91c09c9c6451c16`）不回退；`PROCESSING_VERSION` 保持 3 不 bump （本 change 不改像素输出；任务书"现值 2"为 C4 bump 前旧值，2026-10-07 按 README §3.3 核实为 3）。`.nc` 产物缓存命中语义不变：产物存在且 >4096 字节即复用， 与路径选择无关。 | git 核实 spec.py 零改动：分块参数/GEOCODE_ARRAY_PATH 不进 ArtifactSpec 与指纹白名单（test_fingerprint_untouched：开关前后指纹相等、to_dict 无相关键）；指纹守卫与金指纹含于 113 全绿；本人亲算双时代金值 PV2→c9243efd40318c85、PV3→b91c09c9c6451c16 均吻合；.nc 缓存命中（存在且>4096B 即复用）分支未动。注意：brief/spec 声称当前 PV=3 与实测不符（worktree 与主工作区均为 2，C4 的 bump 在未并线分支），builder 已在 known_limits 披露——change 零指纹变更对任一时代成立，详见 risks。 |
| A7 | passed | specs/p2-array-chunking/spec.md | 架构红线保持（验收：A7）【离线】 ee 对象只在 `source.py` 构建（红线 1）、网格由 `compute_grid(spec)` 唯一确定 （红线 2）——分块只发生在读取层，不改变计算图构建语义，现状单期/时序计算图 构建代码不动。文件改动集中在 `gis/emit.py` + `tests/unit/` 新文件，与 `p2-batch-export`（C5：daemon.py/jobs.py/导出新文件）零交叠；不碰 daemon/jobs/TUI；不给 emit_file/emit_map 的 64M 像素上限与既有报错（含 "批处理导出……待接"原文）做任何修改——>64M 的 file/map 超限处理归 C5 （进行中、尚未落地），本 change 不依赖 C5，emit_array 的 >64M 由本 change 分块路径自行解决（不加硬上限）。 | git status/diff 核实：改动仅 gis/emit.py + 新增 tests/unit/test_array_chunking.py + tests/smoke_array_chunking.py（红线 6 实测工具，brief 交付 5 载体）+ 本地件 geocode.json + docs/comet 正式产物；daemon/jobs/client/tui/source/grid 零 diff，与 C5 零交叠；emit_file/emit_map 的 MAX_DIRECT_PIXELS=64_000_000 与『批处理导出……待接』报错原文未动（行 341-348/415-419 核实）；ee 对象构建仍只经 source.build_image/build_cube，emit.py 内仅 init_ee/ee.Initialize（行 664/759，与 direct 既有模式同构）；网格仍由 compute_grid(spec) 唯一确定。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| tests/unit 全量离线基线（113 用例） | -m unittest discover -s tests/unit | . | passed | 0 | 4109 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- tests/unit 全量离线基线（含新变量序断言）: passed — 113 用例 2.96s 全绿
- 阶段1 留档重跑（新变量序，双腿冷下载）: passed — direct 25.2s / chunked 41.1s；max|diff|=0.0、NaN 一致；变量序 B4,B3,B2,time,y,x 两侧一致
- memory-constant 第二尺寸内存对照: passed — 2.0M px Δ150.5MB vs 204.1M px Δ227.1MB 同带；常数分解留档 memory_constant_evidence.json
- 大产物离线重扫描（沿用）: passed — B4 1.967 / B3 2.137 / B2 2.358、NaN 2.88%（stage2_big_smoke_evidence.json）
- 已知限制: 大网格 778MB 留档产物（s2_chunking_big_smoke.9d517910.nc）为变量序修复前写入（像素逐位不变，仅文件内变量布局不同）；对 A2/A3/A4 证据价值不受影响；如需新布局大产物可再跑一次大网格 smoke（~18 分钟/778MB）
- 已知限制: 峰值增量『与网格尺寸无关』现由两点实测支撑（2.0M px Δ150.5MB / 204.1M px Δ227.1MB）；两点均含会话/库常数，未做逐项内存剖析（分项数值见 memory_constant_evidence.json 分解）
- 已知限制: spec.py fingerprint() 对 bands=None 会 TypeError——既有潜伏问题（先于 C6），超出范围未修
- 已知限制: emit_array 缓存命中分支仍全量 load 产物（现状语义保留）——A4 约束的是 GEE 读入阶段
- 已知限制: _array_sample 对 (time,y,x) 返回 error dict——既有行为，两路径经同一函数保持一致
- 已知限制: Verifier 证据产物保留在 worktree data/derived（gitignored）：stage1_cross_validation_evidence.json、stage2_big_smoke_evidence.json、memory_constant_evidence.json、s2_chunking_pilot.c9243efd.evidence-direct.nc、s2_chunking_pilot.c9243efd.nc、s2_chunking_big_smoke.9d517910.nc、s2_beijing_test.c9243efd.nc、big_smoke_log.txt（含修正横幅）
- 已知限制: docs/README.md §9.2 C6 行状态更新随归档轮在主工作区就地修改（gitignored 不随提交）
- 已知限制: worktree 基线 PROCESSING_VERSION=2（C4 的 PV bump 在其未并线分支）——本 change 零指纹变更对任一时代都成立

## 阻塞项

_无。_

## 风险与跳过的工作

- brief/spec 事实笔误：声称 PROCESSING_VERSION 当前=3，实测 worktree 与主工作区基线均为 2（C4 的 PV 2→3 在未并线分支）；金指纹守卫按时代登记表双值兼容（PV2→c9243efd40318c85、PV3→b91c09c9c6451c16 本人亲算均吻合），change 零指纹变更对任一时代成立；不影响本判定，归档时 README 台账表述需以实测为准。
- A4 的写缓冲无精确定义：大网格峰值 Δ227.1MB（psutil 0.2s 采样）与单块 32MiB+写缓冲的字面 ≤2× 对照依赖常数分解解释（解释器/库导入/会话/运行时，memory_constant_evidence.json 留档）；实质判据（峰值不随网格增长）由两点实测闭合（2.0M px Δ150.5MB vs 204.1M px Δ227.1MB 同带）。
- 大网格留档产物 s2_chunking_big_smoke.9d517910.nc（778MB）为变量序修复前写入（像素逐位不变）；A3/A4 统计证据以离线重扫描 stage2_big_smoke_evidence.json 为准（big_smoke_log.txt 已附修正横幅）。
- emit_array 缓存命中分支仍全量 load 产物（现状语义保留；A4 约束面为 GEE 读入阶段，非缓存读回）。
- tests/smoke_array_chunking.py 位于 tests/ 而非 spec A7 文字所述 tests/unit/ 新文件——属 brief 交付 5 红线 6 网络实测的合理载体，builder 已如实申报，非红线偏离。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-06T17:14:59.813Z |
| 2 | 1 | 1 | blocked | A5 | C6 emit_array 大网格分块的实现本体经独立核验成立：_compute_array_via_xee 零改动、io_chunks 仅经 open_dataset 进入、全程无事后 .chunk()、plan_chunks 双上限纯函数、两级分块直写 netCDF4；离线 113/113 绿（本人实跑 2.795s + Runtime 构建期回执 2.785s）；真实 GEE 大网格 smoke（8244×8253@10m est 204.1M px）产物经我离线复算指纹/网格/块计划逐项吻合、结构核验确认出自分块写入器，内存峰值 Δ227.1MB 为数据量 0.28 倍常数级。唯一缺口：A5 的真实 GEE 双路径逐像素比对无留痕（阶段1产物按设计删除、无日志），任务包指定的 P0 sha256 对比经变量序取证属 direct 路径证据而非 A5 证据——按'证据不足须重跑方可判定则标 blocked'的纪律判 blocked；补证成本低（一次小网格双路径留档重跑），不涉及昂贵大网格任务重跑。总判定 blocked 与 A5=blocked 一致，其余 6 项 passed。 | 2026-10-06T18:59:37.375Z |
| 2 | 1 | 1 | recovery | — | Observed implementation write before tests/smoke_array_chunking.py | 2026-10-06T19:03:08.242Z |
| 2 | 2 | 1 | pass | — | C6 iteration 2 修复轮验收通过（pass，7/7）。上轮唯一缺口 A5 已由真实 GEE 双路径留档重跑补齐并经本人独立复算闭合：双产物逐像素 bitwise 一致（max\|diff\|=0.0、NaN 9352 一致）、sha256 链三件相等（evidence 副本=worktree P0=主工作区金产物 db2a6296…）。上轮指出的 smoke max 逐块覆盖缺陷确认已修复（min(mn,b_min)/max(mx,b_max) 累积写法），离线重扫描统计本人对 778MB 大产物全量重扫逐位复现（B4 max 1.9672000408172607、NaN 1,957,133/2.88%）。『产品代码零改动』声明属实：emit.py diff 与上轮审查结构一致、_compute_array_via_xee 本体零改动，tests/unit 113/113 本人实跑（2.781s）与 Runtime 本轮正式回执（2.750s OK）双确认。spec.py/daemon/jobs/client/tui/source/grid 零 diff，双时代金指纹（PV2 c9243efd / PV3 b91c09c9）本人实算吻合，架构红线保持。 | 2026-10-06T19:25:05.408Z |
| 2 | 2 | 1 | recovery | — | 用户裁决：先修复验收风险再接受结果。两项风险——① 分块写入器 netCDF 变量序（time,y,x,B4,B3,B2）与 direct（B4,B3,B2,time,y,x）不一致导致逐字节比对着色歧义：改分块写入器变量创建顺序为波段在前、坐标在后，与 direct 完全对齐，并加离线单测钉死变量序；② 内存峰值 Δ227.1MB『与网格尺寸无关』只有单尺寸实测：新增 --stage memory-constant 小网格（860×784，2M px）分块内存对照实验（含常数分解：导入/库基线 vs 运行峰值），留档第二数据点。顺带给 big_smoke_log.txt 追加修正横幅（max 列为缺陷期数值，以 stage2_big_smoke_evidence.json 为准）。不改像素输出、不进指纹、验收标准不变。 | 2026-10-07T02:28:52.744Z |
| 2 | 3 | 1 | execution-error | — | 原 Verifier 子代理随属主会话终止而丢失：启动回执已确认（confirmed），但 20+ 分钟无结果提交（同类任务正常完成窗口 9-14 分钟），属主会话已由用户关闭并将工作移交本会话。按协议登记执行丢失，请求重新派发。 | 2026-10-07T02:57:47.587Z |
| 2 | 3 | 2 | pass | — | C6 emit_array 大网格分块独立验收 7/7 通过。核心证据均经本人独立复证：113 离线用例亲跑全绿（3.3s，Runtime 10:38 正式回执一致且实现文件 mtime 均早于该检查）；sha256 三方链亲算闭合（worktree P0 产物=主工作区金产物=stage1 direct 副本，均 db2a6296a3228e90…），direct 路径字节级不变；_compute_array_via_xee 本体零改动；plan_chunks 双上限纯函数离线钉死且与真实 io_chunks 一致；分块只经 open_dataset 进入、无事后 .chunk()（守卫单测 + 红线 6 串行实测：小网格双路径逐像素 max\|diff\|=0 → 大网格 8244×8253@10m est 204.1M px 25 块 778.77MB 落盘读回合格）；内存峰值两点实测不随网格增长（Δ150.5/227.1MB，像素差 101×）；分块参数不进 spec/指纹（PV2/PV3 双时代金指纹亲算吻合，缓存命中语义不变）；文件改动面 emit.py+新测试，daemon/jobs/TUI/source/grid 零 diff，emit_file/emit_map 64M 上限与既有报错未动。唯一发现为 brief/spec 的 PV=3 事实笔误（实测=2），builder 已披露，记入 risks 不影响判定。Verifier 未执行任何 GEE 实网操作（红线 6），网络证据全部以上一轮留档证据文件+日志核对闭合。 | 2026-10-07T03:26:02.470Z |



## 结论

C6 emit_array 大网格分块独立验收 7/7 通过。核心证据均经本人独立复证：113 离线用例亲跑全绿（3.3s，Runtime 10:38 正式回执一致且实现文件 mtime 均早于该检查）；sha256 三方链亲算闭合（worktree P0 产物=主工作区金产物=stage1 direct 副本，均 db2a6296a3228e90…），direct 路径字节级不变；_compute_array_via_xee 本体零改动；plan_chunks 双上限纯函数离线钉死且与真实 io_chunks 一致；分块只经 open_dataset 进入、无事后 .chunk()（守卫单测 + 红线 6 串行实测：小网格双路径逐像素 max|diff|=0 → 大网格 8244×8253@10m est 204.1M px 25 块 778.77MB 落盘读回合格）；内存峰值两点实测不随网格增长（Δ150.5/227.1MB，像素差 101×）；分块参数不进 spec/指纹（PV2/PV3 双时代金指纹亲算吻合，缓存命中语义不变）；文件改动面 emit.py+新测试，daemon/jobs/TUI/source/grid 零 diff，emit_file/emit_map 64M 上限与既有报错未动。唯一发现为 brief/spec 的 PV=3 事实笔误（实测=2），builder 已披露，记入 risks 不影响判定。Verifier 未执行任何 GEE 实网操作（红线 6），网络证据全部以上一轮留档证据文件+日志核对闭合。
