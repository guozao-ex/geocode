# 目标

C3（`p2-timeseries`，docs/README.md §9.2 台账 / §9.5）：为 `ArtifactSpec` 做**时序扩展**——
同一份 spec 能声明"多时相堆栈"（N 期），`emit_array` 输出**沿时间维堆栈的 NetCDF 立方体**
（dims ≈ `(time, y, x)`），`emit_file` 输出**逐期堆叠的多波段 GeoTIFF**（期×波段），
并由 .nc 转出 **CRF 多维栅格**（ArcGIS Pro 原生格式）。每期在该期窗口内塌缩，计算语义与
现状单期路径完全一致（filterDate → 云掩膜 → select → reducer，红线 4 保持）。

契约演进满足**指纹向后兼容**（红线 8）：旧 spec（不含新字段，取默认值）指纹不变，
既有缓存（P0 指纹 `c9243efd`）继续命中；新增字段全部显式决定指纹归属并同步 C1 守卫名单。
C1 移交的契约议题 **D5（nodata 是否应参与指纹）** 在本 change 结案。

# 范围

## Source coverage

来源边界 = 用户请求（2026-10-06 会话，C3 任务书）+ docs/README.md 中被指名的条目
（§9.2 C3 行、§9.5 时序立方体行、§3.3 指纹规则、§8 xee 坑、§11 红线）。README 为唯一事实源。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：用户请求·核心需求 1（spec 表达多时相，方案由 Shape 澄清） | complete | 时序字段设计：Q1 裁决 = time_step 节奏切片 + time_ranges 多段列表（互斥） | specs/p2-timeseries/spec.md 行为规格·时序字段 | A1, A5, A7 | covered | 用户已裁决（2026-10-06 batch） |
| S2：用户请求·核心需求 2（emit_array 输出沿时间维 NetCDF 堆栈） | complete | array 出口多维 NetCDF 行为 | spec.md 行为规格·array 出口（时序模式） | A1 | covered | 当前有效需求 |
| S3：用户请求·验收要点 1（N 期堆栈逐期与单期产物对齐） | complete | 逐期像素对齐判据（array 与 file 双出口） | spec.md 对齐场景 | A2, A3 | covered | 当前有效需求 |
| S4：用户请求·验收要点 2（旧 spec 指纹不变） | complete | 指纹向后兼容判据 | spec.md 指纹场景 | A5 | covered | 当前有效需求 |
| S5：用户请求·D5 议题（nodata 是否参与指纹，触碰指纹时结案） | complete | nodata 归属结论：维持排除（Q4 裁决） | spec.md 指纹场景 + Decisions | A6 | covered | C1 brief 移交议题，已结案 |
| S6：README §9.2 C3 行（时序扩展 → NetCDF/CRF；N 期对齐 + 旧指纹不变） | complete | 同 S1–S4；"CRF" 部分按 Q3 裁决纳入 | spec.md 全文 | A1–A5 | covered | 台账总览行，细化见 S7 |
| S7：README §9.5 时序立方体行（多时相 → NetCDF/CRF；扩展满足指纹向后兼容） | complete | 同 S6 | spec.md 全文 | A1–A5 | covered | 与 S6 同源，验收要点一致 |
| S8：README §3.3（指纹 = 决定输出全部因素的哈希 + PROCESSING_VERSION；向后兼容规则） | complete | 指纹规则约束 | spec.md 指纹场景 | A5, A6 | covered | 契约层约束 |
| S9：README §8 xee 坑 #6/#7（crs_transform 传 tuple；shape_2d=(width,height)；不事后 .chunk()） | complete | 实现约束（防转置、防 select('*')） | spec.md Constraints | A1 | covered | 已实测踩坑，直接继承 |
| S10：README §11 红线 1/2/3/4/6/7/8 | complete | 架构红线（一份计算图 / compute_grid 定网格 / 版本纪律 / 云掩膜次序 / 串行试点 / 分环境 / 指纹归属） | spec.md Constraints | A1–A8 | covered | 全程适用 |
| S11：用户请求·工作约定（回归命令、smoke 不回退、geo env、网络任务标注、验收复用 P0 缓存） | complete | 验证期望 | spec.md 回归场景 | A8 | covered | Verification expectations |

## 交付内容

1. `gis/spec.py`：ArtifactSpec 新增 `time_step`（`day/week/month/year`，配合现有
   time_range 切出连续等宽 N 期）与 `time_ranges`（显式多段窗口列表，N=len，允许不等长），
   两字段互斥；共享的期窗口推导纯函数（月/年跨边界正确、N 上限保护）；校验、
   to_dict/from_dict 往返、两字段入指纹白名单（红线 8）。
2. `gis/source.py`：新增时序计算图构建（**只在 source.py 建 ee 对象**，红线 1）——每期
   窗口内复用与现状一致的语义：filterDate(期) → mask_clouds（select 之前，红线 4）→
   select(bands) → reducer → toFloat → 缩放 → clip → setDefaultProjection；每期设置
   `system:time_start`（期起点）与 `system:index`（期标识）。现状单期路径（不含新字段）
   字节级不动。
3. `gis/emit.py`：
   - `emit_array` 时序模式：xee 打开多维集合（crs_transform 传 tuple、shape_2d=(w,h)、
     不 `.chunk()`），落盘 `.nc`（time,y,x）；结果 dict 报告期数、期窗口与 time 坐标。
   - `emit_file` 时序模式：期集合 `toBands()` 成单张多波段 ee.Image（波段名 = 期标识_波段），
     复用现有 getDownloadURL 直下路径落盘 `.tif`（N×B 波段）；像素上限检查按 N×B 放大。
   - `emit_map` 对时序 spec 报可读 SpecError（提示当前出口不支持时序）。
4. CRF：geo env GDAL 3.13.3 与 rasterio 内置 GDAL **均无 CRF 驱动**（2026-10-06 实测），
   故走 arcpy 桥——`.nc` → arcgispro-py3 `CopyRaster` → `.crf` 多维栅格（沿用 C2 的
   subprocess + 文件交换模式，不违红线 7）。
5. `tests/unit/`：期窗口推导（月/年跨边界、N 上限、互斥）、时序校验、序列化往返、指纹守卫
   名单同步 + 金指纹回归（P0 参数 spec → `c9243efd40318c85`）等离线用例；全量保持全绿。
6. `docs/README.md`：§9.2 台账 C3 状态、§3.1/§3.3 契约段落补时序字段说明（随归档轮提交）。

# 非目标

- 不做 emit_array 大网格分块（xee `io_chunks` 是 C6；本 change 不事后 `.chunk()`）。
- 不新增数据集预设（C4）；不碰批处理导出与 jobs 持久化（C5）。
- 时序模式下 map 出口的多期渲染/动画不做（map 对时序 spec 直接报可读错误）。
- 不改 daemon/TUI 的 MCP 工具面——新字段经 spec JSON 透传即可（TUI 仅展示字段，已确认不受影响）。

# 验收示例

### Scenario: 时序立方体 emit_array（验收：A1）【需网络，已标注】

以 P0 样本参数（S2_SR_HARMONIZED、北京 AOI、EPSG:32650、10m、B4/B3/B2、reducer=median）
构造时序 spec：time_range=("2024-06-01","2024-08-31") + time_step="month"（N=3 期月度窗口）。
`emit_array` 成功产出 `.nc`：含时间维（N=3）与波段变量（time,y,x）；time 坐标为各期窗口
起点（datetime）；结果 dict 报告期数与期窗口。立方体网格与 compute_grid(spec) 一致
（crs/scale/shape 同单期）。

### Scenario: N 期堆栈逐期对齐——array（验收：A2）【需网络，已标注】

对 A1 的每一期 i，构造单期 spec（不含时序字段，time_range=第 i 期窗口，其余参数相同），
各跑一次 `emit_array` 得单期 `.nc`。立方体第 i 期切片与单期产物逐像素比对：有效掩膜
逐期一致，且 max|diff| ≤ ALIGN_TOLERANCE=0.5（两者走同一计算语义 + computePixels，
预期逐位一致；若出现非零差，须在报告中解释来源）。3 期全部达标。

### Scenario: N 期堆栈逐期对齐——file（验收：A3）【需网络，已标注】

同一时序 spec 走 `emit_file`：落盘 `.tif` 含 N×B=9 个波段（期×波段，波段描述含期标识与
波段名），网格对齐。对每期 i 的单期 spec 各跑一次 `emit_file` 得单期 `.tif`；堆栈第 i 期
对应波段与单期 `.tif` 波段逐像素比对：max|diff| ≤ ALIGN_TOLERANCE=0.5（int32 量化容差）
且 nodata 掩膜一致。3 期全部达标。堆叠与单期 `.tif` 的掩膜/填充约定保持一致：
GEE 直下 GEO_TIFF 为 float64、掩膜像素填充 0、头部 nodata=0.0（三者自洽，实测 9352 个
0 像素与 .nc 的 9352 个 NaN 一一对应）；"有效像素恰为 0 不可与掩膜区分"是 GEE 导出
格式固有限制，以踩坑记录文档化（不改写头部——改任何其他填充值都会破坏掩膜语义）。

### Scenario: CRF 多维栅格（验收：A4）【转换离线，依赖 A1 的 .nc 产物】

A1 的 `.nc` 经 arcpy 桥转出 `.crf` 多维栅格，落盘 data/derived/；读回验证期数=3、
变量/波段数与 `.nc` 一致（arcpy 或 GDAL 多维 API 读回均可，注明所用读回方式）。
背景：geo env 与 rasterio 的 GDAL 3.13.3 均无 CRF 驱动（实测），CRF 写出必须走
arcgispro-py3。

### Scenario: 旧 spec 指纹不变（验收：A5）【离线】

时序字段缺省（默认值）的 spec，指纹与不含该字段的旧 spec 完全一致；以 P0 参数构造的
spec 指纹金值断言仍为 `c9243efd40318c85`（锚定 data/derived/ 既有缓存）。设置了
time_step 或 time_ranges 的 spec 指纹必然改变（新字段在白名单）。

### Scenario: 指纹守卫名单同步（验收：A6）【离线】

红线 8 守卫：`tests/unit/test_spec_fingerprint.py` 的 FINGERPRINT_FIELDS 纳入
time_step 与 time_ranges；dataclass 字段全集仍被白名单∪排除名单覆盖；D5 结案结论
（nodata 维持排除，2026-10-06 C3 裁决）写入守卫注释与 spec.md 存档，nodata 现状归属不变。

### Scenario: spec 校验与序列化（验收：A7）【离线】

时序字段校验：time_step 与 time_ranges 同时设置报互斥错误；非法步长值报错（消息列出
可选项）；time_step 缺 time_range 报错；time_ranges 条目 (起>止) 报错；期数 N 推导规则
正确（含月末/年末跨边界、N 上限保护报错）；to_dict/from_dict 往返保真；map 出口对
时序 spec 报可读 SpecError（说明原因与出路）。

### Scenario: 回归基线不回退（验收：A8）【离线单测 + 本机 smoke】

geo env 下 `python -m unittest discover -s tests/unit` 全绿（断网可跑）；现有
smoke_emit / smoke_three_exits / smoke_map_renderers 行为零修改且不回退；smoke_tui
修正一处与 P0 以来同步 RPC 设计不符的过时断言（2026-10-06 修复轮，用户指示）：
describe 走 `gee.describe` 同步端点、不入任务队列（client.py:103 → daemon.py:180，
事实已核），『产生新任务』断言改为『describe 不产生任务行（同步语义）且 spec 面板
被默认值填充』，其余行为不变。现有 4 个 smoke 由 tests/smoke_all.py（daemon 生命周期
包装，用后即停）作为可重复检查运行。

# Constraints and invariants

- 红线 1：时序 ee 计算图只能在 `source.py` 构建，三出口不得自建 ee 对象。
- 红线 2：网格仍由 `compute_grid(spec)` 唯一确定；时序不改变网格语义。
- 红线 3：**PROCESSING_VERSION 保持 2 不 bump**——不含新字段的 spec 走的代码路径与
  产物逐位不变（bump 会改变所有旧指纹，直接违反本 change 的 A5）；时序差异由新指纹
  字段承载。
- 红线 4：每期窗口内云掩膜仍在 select() 之前。
- 红线 6：串行试点——验收用 N=3 小样本先行，成功率优先。
- 红线 7：CRF 转换走 arcgispro-py3 时只做**文件交换**（喂 .nc、收 .crf），
  不在 arcgispro-py3 安装 GEE 栈。
- 红线 8：新增字段显式入指纹白名单 + 守卫名单同步 + 旧 spec 指纹回归断言。
- xee 纪律：`crs_transform` 传 tuple；`shape_2d=(grid.width, grid.height)`；不事后
  `.chunk()`（会触发 select('*')）。
- 实现路径允许回退：服务端多维集合优先，若 xee 0.1.2 对 ImageCollection 的支持有实测
  障碍，允许逐期经 `source.build_image` 拉取后本地 concat / toBands 等价实现
  （仍满足红线 1，验收判据不变）。

# Decisions

- D1（Q1，2026-10-06 用户裁决）：时序表达**两者都做**——`time_step` 节奏切片为主
  （N 由 起止÷步长 推导），`time_ranges` 显式多段为辅（不等长窗口），两字段互斥。
- D2（Q2，用户裁决）：出口范围 **array + file 都支持**；emit_file 出期×波段堆叠
  GeoTIFF；map 出口对时序 spec 报可读 SpecError（拒绝而非静默塌缩）。
- D3（Q3，用户裁决）：**NetCDF + CRF 都做**；CRF 写出经 arcpy 桥
  （GDAL 路线实测不可用：geo env / rasterio 的 GDAL 3.13.3 均无 CRF 驱动）。
- D4（Q4，用户裁决）：D5 结案——`nodata` **维持指纹排除**。调查依据：spec.nodata 在
  计算与出口全链路零消费（grep 证据：仅 spec.py 序列化与 emit.py 元信息报告引用），
  不影响像素值；移入白名单会无谓改变设值 spec 的历史指纹。结论存入守卫注释与 spec.md。
- D5：验收样本固定为 P0 AOI + 2024-06/07/08 逐月 N=3 + B4/B3/B2；单期对照与立方体均为
  新指纹（需网络，见各场景标注），P0 缓存 `c9243efd` 以金指纹断言离线复用（不重复下载）。
- D6：PROCESSING_VERSION 不 bump（理由见 Constraints 红线 3 条）。
- D7（2026-10-06 修复轮，用户指示"先修复残余风险"）：修正 smoke_tui『产生新任务』过时
  断言为同步 RPC 设计语义——原 A8"不修改既有 smoke 的行为"承诺相应放宽为"除该过时
  断言修正外零修改"。
- D8（2026-10-06 修复轮）：nodata=0.0 头部经事实核查为 GEE 自洽约定（float64 + 掩膜
  填充 0 + 头部 0.0），处置=文档化（README 踩坑记录新增条目），不改写头部。

# Verification expectations

- 离线：`C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit`
  全绿（断网可跑，C1 基线延续）。
- 网络（已在 A1/A2/A3 标注，共 8 次 GEE 拉取）：立方体 emit_array 1 + 立方体 emit_file 1
  + 单期对照 emit_array 3 + 单期对照 emit_file 3；GEE 项目 round-gasket-480009-t4，
  代理配置在 geocode.json。CRF 转换（A4）离线，依赖 A1 产物。
- 现有 smoke 不回退（A8）；实现轮每轮跑离线单测回归。
