# Capability：p2-timeseries —— 时序立方体（多时相堆栈 → NetCDF / 堆叠 GeoTIFF / CRF）

## 定位

`ArtifactSpec` 的时序扩展：同一份 spec 声明 N 期时间窗口，每期在窗口内按现状单期语义
塌缩（filterDate → 云掩膜 → select → reducer → toFloat → 缩放 → clip →
setDefaultProjection），期与期沿时间维堆叠。三个物化出口的时序行为：

- `emit_array` → 沿时间维堆栈的 NetCDF（time,y,x）
- `emit_file` → 期×波段堆叠的多波段 GeoTIFF
- `emit_map` → 明确拒绝（可读报错），多期渲染留待后续 change

契约演进满足指纹向后兼容（docs/README.md §3.3、§11 红线 8）：新字段缺省的旧 spec
指纹不变，既有缓存继续命中。ee 计算图仍只在 `source.py` 构建（红线 1），网格仍由
`compute_grid(spec)` 唯一确定（红线 2）。

## 行为规格

### Scenario: 时序立方体 emit_array（验收：A1）【需网络，已标注】

时序 spec（P0 样本参数：S2_SR_HARMONIZED、北京 AOI、EPSG:32650、10m、B4/B3/B2、
reducer=median，time_range=("2024-06-01","2024-08-31") + time_step="month"，N=3）经
`emit_array` 落盘 `.nc`：数据集含时间维（N=3）与每波段一个变量，变量 dims =
`(time, y, x)`；time 坐标为各期窗口起点（datetime 语义）；空间网格与
`compute_grid(spec)` 一致（crs/scale/shape 同单期）。xee 打开纪律：`crs_transform` 传
tuple、`shape_2d=(grid.width, grid.height)`、不做事后 `.chunk()`（大网格分块属 C6）。
结果 dict 报告期数、期窗口与 time 坐标。文件名沿用 `{slug}.{指纹8位}.nc` 约定。

### Scenario: N 期堆栈逐期对齐——array（验收：A2）【需网络，已标注】

对每一期 i 构造单期 spec（不含时序字段，time_range=第 i 期窗口，其余参数相同），各跑
一次 `emit_array` 得单期 `.nc`。立方体第 i 期切片与该单期产物逐像素比对：有效掩膜逐期
一致，且 max|diff| ≤ `ALIGN_TOLERANCE = 0.5`（两者走同一计算语义 + computePixels，
预期逐位一致；若出现非零差，须在验收报告中解释来源）。3 期全部达标。

### Scenario: N 期堆栈逐期对齐——file（验收：A3）【需网络，已标注】

时序 spec 经 `emit_file`：期集合在 `source.py` 内 `toBands()` 成单张多波段 ee.Image
（每期设置 `system:index` = 期起点 YYYYMMDD，波段名 = `{YYYYMMDD}_{波段}`），复用现有
getDownloadURL 直下路径落盘 `.tif`，含 N×B=9 个波段且波段描述与波段名一致；空间网格
与 `compute_grid(spec)` 一致；像素上限检查按 N×B 放大（时序模式 est =
width×height×N×B）。对每期 i 的单期 spec 各跑一次 `emit_file` 得单期 `.tif`；堆栈
第 i 期对应波段与单期 `.tif` 波段逐像素比对：max|diff| ≤ 0.5（int32 量化容差）且
nodata 掩膜一致。3 期全部达标。堆叠与单期 `.tif` 的掩膜/填充约定保持一致：
GEE 直下 GEO_TIFF 为 float64、掩膜像素填充 0、头部 nodata=0.0（三者自洽，实测
9352 个 0 像素与 .nc 的 9352 个 NaN 一一对应）；"有效像素恰为 0 不可与掩膜区分"
是 GEE 导出格式固有限制，以踩坑记录文档化，不改写头部。

**实现注记（C10 正文订正，2026-10-08）**：本场景的实现走 Constraints 授权的**逐期拉取 + 本地
合并**路径（落点 `gis/emit.py::_download_stack_to`：逐期 `getDownloadURL` 下 `.tif` 后按网格
本地堆叠），**而非**上文「期集合在 `source.py` 内 `toBands()` 成单张多波段 ee.Image → 复用
getDownloadURL 直下」的字面描述——实测 `toBands()` 单请求 9 波段 54,613,440B 超 GEE
50,331,648B 上限被 400 拒，逐期请求与单期同限（`gis/source.py` 内保留该实测记录）。产物形态与
对齐判据完全不变：单张 N×B=9 波段、期前缀命名、空间网格同 `compute_grid(spec)`、逐期 vs 单期
`max|diff| ≤ 0.5` 且掩膜一致。

### Scenario: CRF 多维栅格（验收：A4）【转换离线，依赖 A1 产物】

A1 的 `.nc` 经 arcpy 桥（arcgispro-py3 `CopyRaster`，subprocess + 文件交换，红线 7）
转出 `.crf` 多维栅格，落盘 `data/derived/`，命名 `{slug}.{指纹8位}.crf`；读回验证期数
=3、变量/波段数与 `.nc` 一致（arcpy 或 GDAL 多维 API 读回均可，注明方式）。背景：geo
env 与 rasterio 的 GDAL 3.13.3 均无 CRF 驱动（2026-10-06 实测），CRF 写出必须走
arcgispro-py3。

### Scenario: 旧 spec 指纹不变（验收：A5）【离线】

`time_step`/`time_ranges` 缺省（None）的 spec，指纹与不含该字段的旧 spec 完全一致；
以 P0 参数构造的 spec 指纹金值断言仍为 `c9243efd40318c85`（锚定 data/derived/ 既有缓存
产物）。设置了 `time_step` 或 `time_ranges` 的 spec 指纹必然改变（新字段在白名单）。
`PROCESSING_VERSION` 保持 2 不 bump——不含新字段的 spec 走的代码路径与产物逐位不变，
时序差异由新指纹字段承载（红线 3）。

### Scenario: 指纹守卫名单同步（验收：A6）【离线】

红线 8 守卫同步：`tests/unit/test_spec_fingerprint.py` 的 `FINGERPRINT_FIELDS` 纳入
`time_step` 与 `time_ranges`；dataclass 字段全集仍被 白名单∪排除名单 覆盖，未决定归属的
新字段会被守卫拦截。D5 结案（2026-10-06 C3 用户裁决）：`nodata` **维持排除**——调查
依据为 spec.nodata 在计算与出口全链路零消费（仅出现在序列化与元信息报告），不影响像素
值；结论写入守卫注释与本 Spec 存档，nodata 现状归属不变。

### Scenario: spec 校验与序列化（验收：A7）【离线】

`ArtifactSpec` 新增两个互斥时序字段：

- `time_step: "day" | "week" | "month" | "year" | None`——节奏切片模式：以
  `time_range[0]` 为起点，第 i 期窗口 = `[t0 + i·step, t0 + (i+1)·step)`；期起点 < t1
  的期全部生成（N 由 起止÷步长 确定性推导）；最后一期窗口终点可越过 `time_range[1]`
  至多一个步长（保证末段覆盖完整）。月/年步进用年月加法，日超过当月天数时钳制到月末；
  日/周步进用 timedelta。
- `time_ranges: tuple[tuple[str, str], ...] | None`——显式多段模式：N = len(time_ranges)，
  期 i 窗口 = 条目 i 原样使用；允许不等长窗口，不禁止间隔或重叠（显式列表即契约）。

校验（SpecError 消息写清怎么修）：`time_step` 取值必须是四个步长之一（消息列出可选项）；
`time_step` 设置时必须提供 `time_range`；`time_ranges` 每个条目必须是 (起, 止) 且
起 ≤ 止；两字段同时设置报互斥错误；期数 N > `MAX_TIME_PERIODS`（=120）报错（提示
缩短范围或加大步长）。任一字段设置即进入时序模式（`is_collection` 为真）。
`to_dict`/`from_dict` 对两字段往返保真（None/元组/列表语义不丢）。
`emit_map` 对时序 spec（任一时序字段非 None）报可读 SpecError：说明 map 出口暂不支持
时序，并给出生路（单期 spec 或等待后续 change）；不静默塌缩、不产出歧义产物。

### Scenario: 回归基线不回退（验收：A8）【离线单测 + 本机 smoke】

geo env 下 `python -m unittest discover -s tests/unit` 全绿（断网可跑）；现有
smoke_emit / smoke_three_exits / smoke_map_renderers 行为零修改且不回退；smoke_tui
修正一处与 P0 以来同步 RPC 设计不符的过时断言（2026-10-06 修复轮，用户指示）：
describe 走 `gee.describe` 同步端点、不入任务队列（client.py:103 → daemon.py:180，
事实已核），『产生新任务』断言改为『describe 不产生任务行（同步语义）且 spec 面板
被默认值填充』，其余行为不变。现有 4 个 smoke 由 tests/smoke_all.py（daemon 生命周期
包装，用后即停）作为可重复检查运行。

## Constraints

- 红线 1：时序 ee 计算图只能在 `source.py` 构建，三出口不得自建 ee 对象；每期窗口内
  复用与现状单期一致的算子序列，云掩膜在 select() 之前（红线 4）。
- 红线 2：网格由 `compute_grid(spec)` 唯一确定，时序不改变网格语义。
- 红线 3：`PROCESSING_VERSION` 保持 2（理由见「旧 spec 指纹不变」场景）。
- 红线 6：串行试点，验收样本 N=3 小样本先行。
- 红线 7：CRF 转换只做文件交换（喂 .nc、收 .crf），不在 arcgispro-py3 安装 GEE 栈。
- 红线 8：新增字段显式入指纹白名单，守卫名单同步，旧 spec 指纹回归断言。
- xee 纪律：`crs_transform` 传 tuple；`shape_2d=(width, height)`；不事后 `.chunk()`。
- GEE 直下 GeoTIFF 的掩膜/填充约定：float64、掩膜像素填充 0、头部 nodata=0.0（三者
  自洽）；不做头部改写——"有效像素恰为 0 不可与掩膜区分"是 GEE 导出格式固有限制，
  以文档化收口。
- 实现路径允许回退：服务端多维集合优先；若 xee 0.1.2 对 ImageCollection 的支持有实测
  障碍，允许逐期经 `source.build_image` 拉取后本地堆叠/toBands 等价实现（仍满足红线 1，
  验收判据不变）。
- 网络任务标注：A1/A2/A3 需 GEE 网络（共 8 次拉取：立方体 array/file 各 1 + 单期对照
  各 3）；A4 转换本身离线；其余验收全部离线。
