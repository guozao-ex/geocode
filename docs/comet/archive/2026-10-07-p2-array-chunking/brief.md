# 目标

C6（`p2-array-chunking`，docs/README.md §9.2 台账 C6 行 / §9.5 `emit_array` 分块行）：
`emit_array` **大网格分块**——大网格在 `xr.open_dataset(..., engine='ee')` 时通过 xee 的
`io_chunks` 参数按块读取（**不**事后 `.chunk()`），读取与 `.nc` 拼装阶段**内存有界**
（读入阶段峰值可测量、有明确上限公式）；**按需触发**，小网格（现状规模，如 860×784 实测）
路径与产物完全不变。

分块是**运行时决策**不是产品行为：触发阈值与块参数不进 `ArtifactSpec`、不进指纹，
`.nc` 指纹缓存的命中语义不受影响。

事实基线（2026-10-07 源码核实，xee 0.1.2 安装包）：

- xee 0.1.2 后端 `open_dataset` **原生支持 `io_chunks`**（映射到 store 分块）——
  **无需升级 xee/xarray**，用户要求的升级回归前提不触发。
- `io_chunks`/默认 auto_chunks 只控制**单次网络请求大小**（默认 48 MB 请求预算）；
  `ds.compute()` 时 xee 在 `_raw_indexing_method` 中线程池拉全部块后 `np.block()`
  一次性拼装**全量数组**——内存峰值 = 全网格数组，随网格线性增长。即：现状缺的不是
  请求分块（已有），是**读取与落盘的内存有界**。
- xee 数组 dtype 固定 float32（4 B/像素/波段/期）→ 内存账可精确计算。
- `emit_array` 现状**无**像素上限（`MAX_DIRECT_PIXELS = 64_000_000` 只约束
  `emit_file`）；本 change 不加上限、只加有界内存。

# 范围

## Source coverage

来源边界 = 用户请求（2026-10-07 会话，C6 任务书）+ docs/README.md 被指名条目
（§9.2 C6 行、§9.5 emit_array 分块行）及其必要依赖（§8.2 xee 坑、§11 红线 1/2/3/6/8、
§3.3 指纹规则）；§9.2 C5 行仅作范围边界背景。README 为唯一事实源（gitignore 本地件，
只存在于主工作区）。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：用户请求·目标（emit_array 大网格分块；`_compute_array_via_xee` 现状整网格直接 compute 仅适用小网格；open_dataset 时按块读取；emit.py:545 结论注释变成代码） | complete | 分块路径行为：io_chunks 在 open_dataset 时传入，读取/落盘内存有界 | spec.md 行为规格·分块路径 | A2, A3, A4 | covered | 当前有效需求 |
| S2：用户请求·按需触发（小网格行为完全不变：tests/unit 基线全绿、smoke 不回退） | complete | 路径选择行为：阈值以下现状路径字节级不动 | spec.md 行为规格·路径选择 | A1 | covered | 当前有效需求 |
| S3：用户请求·验收要点（大网格不触发 `select('*')`、内存有界：峰值可测量、有明确上限） | complete | select('*') 禁令 + 内存上界公式与实测 | spec.md 行为规格·分块路径 + 验证 | A3, A4 | covered | 当前有效需求 |
| S4：用户请求·验收要点（分块路径与直接路径产物数值一致：同一 spec 能强制走两条路径交叉验证） | complete | 双路径像素一致性判据 + 强制路径测试钩子 | spec.md 一致性场景 | A5 | covered | 当前有效需求 |
| S5：用户请求·验收要点（分块参数不进 ArtifactSpec；指纹不变；.nc 指纹缓存命中语义不受影响） | complete | 指纹/缓存不变性判据 | spec.md 指纹场景 | A6 | covered | 当前有效需求 |
| S6：README §9.2 C6 行（xee io_chunks 大网格分块；按需触发；大网格不触发 select('*')、内存有界） | complete | 同 S1–S3 | spec.md 全文 | A1–A4 | covered | 台账总览行，细化见 S7 |
| S7：README §9.5 emit_array 分块行（大网格走 io_chunks；不要事后 .chunk()，会触发 select('*')；按需触发） | complete | 同 S6；.chunk() 禁令继承 | spec.md Constraints | A2, A3 | covered | 与 S6 同源，验收要点一致 |
| S8：README §9.2 C5 行（>64M 像素 AOI 走 Export.toCloudStorage 批处理导出） | complete | 范围边界：64M 上限归 C5 承接，本 change 不动 emit_file/emit_map 上限 | —（非目标） | — | background | 边界背景，不做实现 |
| S9：README §8.2 xee 坑 #6/#7（crs_transform 传 tuple；shape_2d=(width,height)）+ §8.1 #4（select('*') Invalid regex）+ #5（GeoTIFF Int32 vs .nc float32） | complete | 实现约束（防转置、防通配符 select、.nc 为像素真值来源） | spec.md Constraints | A3, A5 | covered | 已实测踩坑，直接继承 |
| S10：README §11 红线 1/2（ee 对象只在 source.py；网格由 compute_grid() 定）、红线 6（串行试点）、红线 8（指纹向后兼容） | complete | 架构红线全程适用 | spec.md Constraints | A6, A7 | covered | 全程适用 |
| S11：README §3.3 指纹与缓存（指纹 = 全因素哈希 + PROCESSING_VERSION；任何改变像素输出的改动必须 +1） | complete | 本 change 不改像素输出 → 不 bump PV | spec.md 指纹场景 | A6 | covered | 契约层约束 |
| S12：用户请求·红线 6 串行试点（先小任务验证分块读取正确，再 >64M 像素大网格 smoke，成本可控） | complete | 验证顺序：离线 → 小任务 → 大网格 smoke | spec.md 验证期望 | A3 | covered | Verification expectations |

## 交付内容

1. `gis/emit.py`：`_compute_array_via_xee` 增加运行时路径选择——阈值以下**现状代码路径
   字节级不动**（连 io_chunks 参数都不传）；阈值以上走分块路径：`open_dataset` 传入
   `io_chunks`（由块尺寸纯函数计算），读取循环与 `.nc` 写入按 Q4 裁决的粒度增量进行，
   内存上界明确。保留现有失败诊断路径（逐期影像数诊断）与取消检查。
2. 块尺寸计算纯函数（放 `gis/emit.py`，无 IO 无全局态）：内存账按 xee float32
   （驻留 4 B/像素，GEE 请求侧按 (dtype+1) B 计费掩膜字节）；形状策略与预算常量按
   Q2 裁决确定；常量写在代码里，不进 spec、不进指纹。
3. 运行时强制路径开关（环境变量测试钩子）：同一 spec 可强制走直接路径或分块路径，
   支撑 A5 交叉验证；不进 spec、不进指纹、不影响 daemon/TUI 工具面。
4. `tests/unit/` 新增离线用例：纯函数（预算上界、形状边界）、路径选择
   （monkeypatch 断言 open_dataset 收到/未收到 io_chunks、全程无事后 `.chunk()`）、
   指纹不变回归；现有 94 用例基线保持全绿。
5. 网络实测（红线 6 串行）：小任务分块读取正确性 → >64M 像素单期大网格 smoke，
   记录读入阶段峰值；不回退现有 smoke。

# 非目标

- 不动 `emit_file` / `emit_map` 及其 `MAX_DIRECT_PIXELS = 64_000_000` 上限与既有
  报错（含"批处理导出……待接"原文）。>64M 的 file/map 超限处理归 **C5** 负责
  （`p2-batch-export`，进行中、尚未归档/落地）——**本 change 不依赖 C5**，C5 落地前
  超大请求维持现状报错引导（放大 scale / 缩小 AOI）；`p2-batch-export` 在独立
  worktree 并行推进，本 change 与其零文件交叠：不改 daemon.py / jobs.py / 导出新文件。
- 不碰 daemon / jobs / TUI。
- 不升级 xee / xarray（xee 0.1.2 已原生支持 io_chunks，2026-10-07 源码核实）。
- 不新增数据集预设；不做 CRF / map 出口改动；不改 source.py 的计算图构建语义。
- 分块参数不进 ArtifactSpec（不新增任何 spec 字段）。
- 不给 emit_array 新增像素数上限（只加内存有界；硬上限归 C5 的批处理导出）。

# 验收示例

### Scenario: 小网格路径不变——按需触发（验收：A1）【离线；smoke 需网络，已标注】

est = `grid.width × grid.height × N期 × 波段` < `MAX_DIRECT_PIXELS`（64,000,000）时，
`_compute_array_via_xee` 走现状代码路径：`xr.open_dataset` 调用**不含** `io_chunks`
参数，读取为现状 `ds.compute()` 全量驻留，落盘为现状 `arr.to_netcdf(tmp)` + `.part`
原子替换——连参数列表都不变，行为字节级一致。离线单测以 monkeypatch 断言
`open_dataset` 收到的调用参数（无 io_chunks）；现有 `tests/unit` 94 用例基线全绿；
现有 smoke（需网络项标注）不回退。强制开关默认 `auto`，不影响该判定。

### Scenario: 大网格走分块路径（验收：A2）【离线】

est ≥ 64,000,000 时走分块路径：`open_dataset` 收到显式 `io_chunks`，其值由块尺寸
纯函数 `plan_chunks(width, height, n_periods, n_bands)` 计算——确定性、无 IO、无全局态，
形状映射到 xee 的 `(index=期块, width=x块, height=y块)`；空间优先大块、期维装满剩余
预算，块尺寸不必整除网格。读取按（期块×空间块）两级循环：lazy 打开 → 逐块
`isel(...).values` → 直写预分配 netCDF4 变量切片 → 每块 `job.check_cancelled()` 并更新
进度。离线单测以 monkeypatch 断言 io_chunks 参数、循环块数与块形状均来自
`plan_chunks`。强制开关 `GEOCODE_ARRAY_PATH`（默认 auto；direct/chunked 强制，
非法值可读报错）是测试钩子，不进 spec/指纹/daemon 工具面。

### Scenario: 不触发 select('*')——守卫 + 串行实测（验收：A3）【守卫离线；实测需网络，已标注】

分块路径全程不调用事后 `.chunk()`：离线守卫单测 monkeypatch `xr.Dataset.chunk`
（执行期间被调用即失败）并断言 io_chunks 只经 open_dataset 进入。红线 6 串行实测：
先小网格任务强制 `chunked` 验证分块读取正确，再跑大网格 smoke——**82km×82km @10m
≈ 67.2M 像素、单期、3 波段（S2_SR_HARMONIZED，B4/B3/B2，reducer=median）**，
`emit_array` 成功落盘 `.nc`、读回校验合格。触发 `select('*')` 必然
`Invalid regular expression` 400 失败——smoke 成功即为未触发的证据。

### Scenario: 内存有界——预算上界与实测对照（验收：A4）【上界离线；实测需网络，已标注】

单块驻留字节 = 块像素 × 4B ≤ **32 MiB** 预算常量（≈8.39M 像素/块）；请求侧 =
块像素 × 5B ≤ 48 MB（GEE 单请求上限；32 MiB 预算下自动满足，`plan_chunks` 内保留
断言防御预算上调）。离线单测对边界输入（单期/多期、极窄/极宽网格、超阈值网格）
断言输出满足两个上限且确定。读入阶段峰值上界 = 单块驻留 + 写缓冲（常数级）——
大网格 smoke 实测读入阶段内存峰值（记录数值与采样方式），对照公式上界（容差 ≤ 2×）
留档。落盘逐块增量写，不整期/全量驻留。

### Scenario: 两条路径产物一致——交叉验证（验收：A5）【需网络，已标注】

同一 spec 经 `GEOCODE_ARRAY_PATH=direct` 与 `=chunked` 各跑一次 `emit_array`
（小网格即可，成本等同两次小网格下载），产物逐像素比对：NaN 位置一致、
max|diff| = 0（两路径同一计算语义 + computePixels float32，预期逐位一致），
dims/vars/空间网格（对齐 compute_grid(spec)）/time 坐标语义一致。分块路径产物可被
`xr.open_dataset` 读回，dtype float32、掩膜像素 NaN（与现状 `.nc` 语义一致）；
结果 dict 字段语义与现状一致。

### Scenario: 指纹与缓存语义不变（验收：A6）【离线】

分块参数（阈值、预算、`plan_chunks` 输出、`GEOCODE_ARRAY_PATH`）不进
`ArtifactSpec`、不进指纹白名单——现有指纹守卫与金指纹（PV=3 时代
`b91c09c9c6451c16`）不回退；`PROCESSING_VERSION` 保持 3 不 bump（本 change 不改
像素输出；任务书"现值 2"为 C4 bump 前旧值，2026-10-07 按 README §3.3 核实为 3）。
`.nc` 产物缓存命中语义不变：存在且 >4096 字节即复用，与路径选择无关。

### Scenario: 架构红线保持（验收：A7）【离线】

ee 对象只在 `source.py` 构建（红线 1）、网格由 `compute_grid(spec)` 唯一确定
（红线 2）——分块只发生在读取层，不改变计算图构建语义，现状单期/时序计算图构建
代码不动。文件改动集中在 `gis/emit.py` + `tests/unit/` 新文件，与
`p2-batch-export`（C5：daemon.py/jobs.py/导出新文件）零交叠；不碰 daemon/jobs/TUI；
不给 emit_file/emit_map 的 64M 像素上限做任何修改。

# 约束与不变量

- 红线 1/2：ee 对象只在 source.py 构建；网格由 compute_grid() 定——分块只发生在
  读取层，不改变计算图构建。
- 红线 3：PROCESSING_VERSION **不 bump**（本 change 不改像素输出；当前值 = 3——
  任务书写的"现值 2"为 C4 bump 前旧值，2026-10-07 按 README §3.3 核实为 3）。
- 红线 6：串行试点——离线单测 → 小任务分块读取验证 → >64M 大网格 smoke，逐级放大。
- 红线 8 / §3.3：指纹向后兼容，本 change 零指纹变更。
- 禁止事后 `.chunk()`（emit.py:545 结论注释 + README §9.5）：分块只经
  open_dataset 时的 `io_chunks` 进入。
- 与 C5（`p2-batch-export`）并行：不 select/resume 该 change、不写其 worktree；
  文件改动集中在 `gis/emit.py` + `tests/unit/` 新文件。
- worktree 跑 GEE 需先复制主工作区本地 `geocode.json`（skip-worktree 本地件，
  worktree 检出的是模板）。
- 并行会话 daemon 端口 6531 冲突：client 类 smoke 需备用端口（项目记忆教训）。

# 决定

Q1–Q4 已由用户逐项裁决（2026-10-07 batch，四项均采纳推荐项）：

- **D1（Q1）触发阈值 = 像素数 ≥ 64M**：est = 宽×高×N期×波段 ≥ `MAX_DIRECT_PIXELS`
  （64,000,000）→ 分块路径；阈值以下现状代码路径字节级不动（连 io_chunks 参数都不传）。
  与 emit_file 既有护栏同口径，两出口语义一致。
- **D2（Q2）块尺寸 = 预算驱动纯函数**：`plan_chunks(宽, 高, N期, 波段)` →
  `(index, width, height)`；单块驻留字节 = 块像素×4B（xee float32）≤ **32 MiB** 预算
  常量（≈8.39M 像素/块），空间优先大块、期维装满剩余预算；并校验请求侧
  = 块像素×5B（GEE 掩膜字节计费）≤ 48MB 单请求上限（32MiB 预算下自动满足，
  校验防御预算上调）。常量写死在 emit.py，不进 spec、不进指纹。
- **D3（Q3）select('*') 证明 = 组合双层**：离线守卫单测（monkeypatch
  `xr.Dataset.chunk`，被调用即失败；断言 open_dataset 收到/未收到 io_chunks）
  + 红线 6 网络串行实测（触发必 400，成功即证据）。
- **D4（Q4）.nc 拼装 = 期×空间两级分块直写**：lazy 打开（io_chunks 生效）→
  逐（期块×空间块）isel→values→ 直写预分配 netCDF4 变量切片；内存上界 =
  单块 ≤ 32MiB（常数，与网格尺寸无关）；时序与单期统一同一写入器；需自写
  CF time 编码等写入层。不采用逐期整期驻留（单期大网格无空间分块收益）、
  不赌 dask 流式路径（与"事后 .chunk() 触发 select('*')"实测结论同走
  xarray chunk 路径，风险未知）。

# 验收预期

- 离线基线：`PYTHONPATH=. C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest
  discover -s tests/unit`（worktree 根运行）——现有 94 用例 0.3s 全绿（2026-10-07
  实测），新增用例并入；秒级完成、不碰网络。
- 网络项（需网络，验收时标注）：smoke_emit 不回退；分块小任务试点；
  >64M 像素大网格 smoke（红线 6 串行：先小后大）。
- 大网格 smoke 规格修正：任务书示例"约 10km×10km @10m"实为 1000×1000 = **1M 像素**，
  不满足 ">64M 像素"目标——定稿 **82km×82km @10m ≈ 67.2M 像素、单期、3 波段**
  （S2 原生 10m，GEE computePixels 下载量 ≈ 67.2M×3×4B ≈ 805 MB，成本可控）。
- 两条路径交叉验证（A5）在真实 GEE 上对小网格执行（强制开关切换路径，成本等同
  两次小网格下载）。
