# Capability：p2-array-chunking —— emit_array 大网格分块（xee io_chunks，内存有界）

## 定位

`emit_array` 的**运行时**分块能力：大网格（阈值及以上）在 `xr.open_dataset(...,
engine='ee')` 时通过 xee 0.1.2 的 `io_chunks` 参数按块读取，读取与 `.nc` 拼装阶段
**内存有界**——读入阶段峰值 = 单块驻留（≤ 32 MiB 常数，与网格尺寸无关），可测量、
有明确上限公式。小网格（阈值以下）现状代码路径**字节级不动**。

分块是运行时决策不是产品行为：阈值与块参数不进 `ArtifactSpec`、不进指纹，
`.nc` 指纹缓存的命中语义不变。xee 数组固定 float32（本地驻留 4 B/像素；GEE 请求侧
按 (4+1) B 计费掩膜字节、单请求上限 48 MB），内存账据此精确计算。

事实基线（2026-10-07 源码核实）：xee 0.1.2 后端 `open_dataset` 原生支持 `io_chunks`
（映射到 store 分块），**无需升级 xee/xarray**；`io_chunks` 只控制单次网络请求大小，
`ds.compute()` 时 xee 以 `np.block()` 一次性拼装全量数组——因此内存有界必须由
**读取循环 + 增量落盘**自行实现（本 change 的核心工作）。禁止事后 `.chunk()`
（实测触发 xee 内部 `select('*')`，被 GEE 拒绝：Invalid regular expression，
gis/emit.py:545 结论注释升级为代码守卫）。

## 行为规格

### Scenario: 小网格路径不变——按需触发（验收：A1）【离线；smoke 需网络，已标注】

est = `grid.width × grid.height × N期 × 波段` < `MAX_DIRECT_PIXELS`（64,000,000）时，
`_compute_array_via_xee` 走现状代码路径：`xr.open_dataset` 调用**不含** `io_chunks`
参数，读取为现状 `ds.compute()` 全量驻留，落盘为现状 `arr.to_netcdf(tmp)` +
`.part` 原子替换——连参数列表都不变，行为字节级一致。离线单测以 monkeypatch 断言
`open_dataset` 收到的调用参数（无 io_chunks）；现有 `tests/unit` 94 用例基线全绿；
现有 smoke（需网络项标注）不回退。运行时强制开关（见下）默认 `auto`，不影响该判定。

### Scenario: 大网格走分块路径（验收：A2）【离线】

est ≥ 64,000,000 时走分块路径：`open_dataset` 收到显式 `io_chunks`，其值由
**块尺寸纯函数** `plan_chunks(width, height, n_periods, n_bands)` 计算——确定性
（同输入同输出）、无 IO、无全局态，形状映射到 xee 的
`(index=期块, width=x块, height=y块)`；空间优先大块、期维装满剩余预算，块尺寸不必
整除网格（xee 自行处理边缘块）。读取按（期块×空间块）两级循环执行：
lazy 打开 → 逐块 `isel(...).values` → 直写预分配 netCDF4 变量切片 → 每块后
`job.check_cancelled()` 并更新 `job.progress`。离线单测以 monkeypatch 断言
`open_dataset` 的 io_chunks 参数、循环块数与块形状均来自 `plan_chunks`。

运行时强制开关 `GEOCODE_ARRAY_PATH`（环境变量，默认 `auto`）：`direct` 强制现状
路径、`chunked` 强制分块路径（用于 A5 交叉验证）。它是测试钩子——不进
`ArtifactSpec`、不进指纹、不进 daemon/TUI 工具面；非法值报可读错误。

### Scenario: 不触发 select('*')——守卫 + 串行实测（验收：A3）【守卫离线；实测需网络，已标注】

分块路径全程**不调用事后 `.chunk()`**：离线守卫单测 monkeypatch
`xr.Dataset.chunk`（分块路径执行期间被调用即失败）并断言 io_chunks 只经
open_dataset 进入。红线 6 串行实测：先小网格任务强制 `chunked` 验证分块读取正确
（产物与 direct 路径一致，即 A5 的小网格先行），再跑大网格 smoke——
**82km×82km @10m ≈ 67.2M 像素、单期、3 波段（S2_SR_HARMONIZED，B4/B3/B2，
reducer=median）**，`emit_array` 成功落盘 `.nc`、读回校验 dims/期数/坐标合格。
触发 `select('*')` 必然 `Invalid regular expression` 400 失败——smoke 成功即为
未触发的证据。

### Scenario: 内存有界——预算上界与实测对照（验收：A4）【上界离线；实测需网络，已标注】

单块驻留字节 = 块像素 × 4B ≤ **32 MiB** 预算常量（≈8.39M 像素/块）；请求侧
= 块像素 × 5B ≤ 48 MB（GEE 单请求上限；32 MiB 预算下自动满足，`plan_chunks`
内保留断言防御预算上调）。离线单测对边界输入（单期/多期、极窄/极宽网格、
超阈值网格）断言 `plan_chunks` 输出满足两个上限且确定。读入阶段峰值上界 =
单块驻留 + 写缓冲（常数级）——大网格 smoke 实测读入阶段内存峰值（记录数值与
采样方式），对照公式上界（容差 ≤ 2×），并在验收报告留档。落盘为逐块增量写，
不整期/全量驻留（D4 裁决：两级分块直写 netCDF4）。

### Scenario: 两条路径产物一致——交叉验证（验收：A5）【需网络，已标注】

同一 spec 经 `GEOCODE_ARRAY_PATH=direct` 与 `=chunked` 各跑一次 `emit_array`
（小网格即可，成本等同两次小网格下载；chunked 侧同时覆盖 A3 的"分块读取正确"
先行验证），产物逐像素比对：NaN 位置一致、max|diff| = 0（两路径走同一计算语义 +
computePixels float32，预期逐位一致），dims/vars/空间网格（crs/scale/shape 对齐
`compute_grid(spec)`）/time 坐标语义一致。分块路径产物可被 `xr.open_dataset`
读回，dtype 为 float32、掩膜像素为 NaN（与现状 `.nc` 语义一致）；结果 dict 字段
语义与现状一致（exit/path/size_mb/spec_fingerprint/grid/dims/vars/sample/
timeseries）。

### Scenario: 指纹与缓存语义不变（验收：A6）【离线】

分块参数（阈值、预算、`plan_chunks` 输出、`GEOCODE_ARRAY_PATH`）不进
`ArtifactSpec`、不进指纹白名单——`tests/unit` 现有指纹守卫与金指纹
（PV=3 时代 `b91c09c9c6451c16`）不回退；`PROCESSING_VERSION` 保持 3 不 bump
（本 change 不改像素输出；任务书"现值 2"为 C4 bump 前旧值，2026-10-07 按
README §3.3 核实为 3）。`.nc` 产物缓存命中语义不变：产物存在且 >4096 字节即复用，
与路径选择无关。

### Scenario: 架构红线保持（验收：A7）【离线】

ee 对象只在 `source.py` 构建（红线 1）、网格由 `compute_grid(spec)` 唯一确定
（红线 2）——分块只发生在读取层，不改变计算图构建语义，现状单期/时序计算图
构建代码不动。文件改动集中在 `gis/emit.py` + `tests/unit/` 新文件，与
`p2-batch-export`（C5：daemon.py/jobs.py/导出新文件）零交叠；不碰
daemon/jobs/TUI；不给 emit_file/emit_map 的 64M 像素上限与既有报错（含
"批处理导出……待接"原文）做任何修改——>64M 的 file/map 超限处理归 C5
（进行中、尚未落地），本 change 不依赖 C5，emit_array 的 >64M 由本 change
分块路径自行解决（不加硬上限）。

## Constraints

- 禁止事后 `.chunk()`（emit.py:545 结论 + README §9.5）；分块只经 open_dataset
  时的 `io_chunks` 进入。
- xee 打开纪律继承（README §8.2 #6/#7）：`crs_transform` 传 tuple、
  `shape_2d=(grid.width, grid.height)`（(x,y) 序，传反在正方形网格静默错）。
- `.nc` 是像素真值来源（README §8.1 #5/#18）：分块直写需保持 float32 + NaN 掩膜
  语义与 CF time 编码，产物可被 `xr.open_dataset` 读回且语义与现状一致。
- 红线 6：串行试点（离线单测 → 小网格 chunked 验证 → 大网格 smoke），不并行放大。
- worktree 跑 GEE 前复制主工作区本地 `geocode.json`（skip-worktree 本地件）；
  并行会话 daemon 端口 6531 冲突——client 类 smoke 需备用端口。
- 失败诊断保留：现状 `xee 拉取失败` 报错（含逐期影像数诊断）在分块路径同样可得。

## 验证期望

- 离线基线：`PYTHONPATH=. C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest
  discover -s tests/unit`（worktree 根运行）——现有 94 用例 + 新增用例，秒级、不碰网络。
- 网络项（验收时标注【需网络】）：smoke 不回退；A5 双路径交叉验证；
  A3/A4 大网格 smoke（82km×82km @10m 单期，红线 6 串行：先小后大）。
