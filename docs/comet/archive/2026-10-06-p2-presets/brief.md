# 目标

C4（`p2-presets`，docs/README.md §9.2 Change 台账 C4 行 / §9.5「更多预设」行）：为
`gis/source.py` 的 `DEFAULT_ASSETS` 预设表**新增 4 个数据集预设**——Sentinel-1 GRD（SAR）、
Landsat 8/9 Collection 2 Level 2 SR、ERA5(-Land)、ESA WorldCover v200。

**2026-10-06 需求变更（用户在验收轮补充范围）**：一并**修复遗留问题**——既有
`LANDSAT/LC08/C02/T1_L2` 与 `LANDSAT/LC09/C02/T1_L2` 两条预设缺官方辐射缩放 offset `-0.2`；
并更新 `docs/README.md`。该修复改变既有像素输出，按红线 3 必须 `PROCESSING_VERSION += 1`
（2 → 3），全部 spec 指纹随之更新（原金指纹 `c9243efd40318c85` 作废，由新值取代），
既有 Landsat 缓存产物失效并在下次运行时按新指纹重新生成——以上变化已由用户明确接受。

验收口径（按台账 + 上述变更）：**每个新预设走通三出口 smoke**（emit_file / emit_array /
emit_map）；**既有预设的语义不回退**——除有意修正的 LC08/LC09 缩放口径外，其余预设的
计算语义与字段不变，且版本纪律（bump + 变更面记录）正确执行；**现有 smoke（emit /
three_exits / tui / map_renderers）不回退**；离线单测基线在 worktree 内全绿。

既有 8 个预设：`COPERNICUS/S2_SR_HARMONIZED`、`COPERNICUS/S2_HARMONIZED`、
`LANDSAT/LC09/C02/T1_L2`、`LANDSAT/LC08/C02/T1_L2`、`MODIS/061/MOD13Q1`、
`MODIS/061/MOD11A2`、`COPERNICUS/DEM/GLO30`、`JRC/GSW1_4/GlobalSurfaceWater`。

本 change 在独立 worktree（`comet/p2-presets`，基线 `0cc8b25` = C2 归档后）内推进，与进行中的
C3 `p2-timeseries` 并行；两边都改 `gis/source.py`，归档集成时按仓库实际内容解决冲突。

# 范围

## Source coverage

覆盖边界 = 用户请求（2026-10-06 会话，C4 任务书：4 个预设 + worktree 隔离 + 三条验收要点 +
4 组待裁决语义差异 + 约束）+ **验收轮补充（修遗留 offset + 更新 README）** +
docs/README.md 中被指名的条目（§9.2 C4 行、§9.5「更多预设」行、§3.3 指纹规则、§11 红线、
§2.2 代码地图、§12 命令速查）。README 为需求事实源，台账之外不做。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：用户请求·目标（4 个数据集预设，都落在 `gis/source.py` 预设表内） | complete | 4 个数据集的口径与落点（裁决后展开为 5 条预设条目） | specs/p2-presets/spec.md 行为规格·预设表 | A1–A4 | covered | Q1–Q4 已裁决 |
| S2：用户请求·验收要点 1（每个新预设走通三出口 smoke） | complete | 三出口产物形态判据 | spec.md 三出口场景 | A1–A4 | covered | 与台账验收口径一致 |
| S3：用户请求·验收要点 2（既有 8 预设与既有 spec 指纹不回退） | complete | **已被 S13 取代**：修正 LC08/LC09 缩放口径后不再要求旧指纹不变，改为"语义不回退 + 版本纪律正确" | spec.md 版本纪律场景 | A5 | superseded | 由 S13 替代（用户 2026-10-06 验收轮补充范围） |
| S4：用户请求·验收要点 3（现有 smoke 不回退） | complete | emit / three_exits / tui / map_renderers 四条 smoke 判据 | spec.md 回归场景 | A7 | covered | 当前有效需求 |
| S5：用户请求·已知语义差异 4 组（WorldCover 分类 / S1 SAR / Landsat 缩放 / ERA5 档位） | complete | 逐项裁决结论 Q1–Q4 | spec.md 各预设行为规格 | A1–A4 | covered | 用户已逐项裁决（2026-10-06 batch） |
| S6：用户请求·约束（ee 只建在 source.py、红线以 §11 为准、与 C3 交叠） | complete | 约束与不变量 | spec.md Constraints | A1–A8 | covered | 用户指定；PROCESSING_VERSION 条款由 S13 更新 |
| S7：README §9.2 C4 行（`p2-presets`：S1 / Landsat 8-9 SR / ERA5 / WorldCover 预设；每个预设走通三出口 smoke） | complete | 台账总览行（同 S1/S2） | spec.md 全文 | A1–A4 | covered | 台账行，细化见 S8 |
| S8：README §9.5「更多预设」行（当前 8 个；补 S1、Landsat 8/9 SR、ERA5、WorldCover） | complete | 基线预设数 8 与新增清单 | spec.md 预设表 | A1–A4 | covered | 与 S7 同源 |
| S9：README §11 红线 1 / 3 / 4 / 6 / 8 | complete | 架构红线（ee 归属、版本纪律、掩膜次序、串行试点、指纹归属） | spec.md Constraints | A1–A8 | covered | 红线 4 的 SAR 豁免由 Q2 裁决；红线 3 由 S13 触发 |
| S10：README §3.3 指纹规则 + 「指纹向后兼容」段 | complete | 指纹 = 白名单哈希 + PROCESSING_VERSION；新增字段缺席不参与哈希 | spec.md 版本纪律场景 | A5 | covered | 本次 bump 为有意的例外，须记录 |
| S11：README §2.2 代码地图（"source.py … 8 个数据集预设"） | complete | 基线预设数（背景） | — | — | background | 事实描述，随 README 更新为 13 |
| S12：README §12 命令速查（smoke 跑法、geo env 解释器） | complete | 验证执行方式 | spec.md 回归场景 | A6, A7 | covered | 验证期望 |
| S13：**用户请求·验收轮补充（2026-10-06）**：修复遗留（LC08/LC09 缺 offset）+ 更新 README；接受由此产生的 PROCESSING_VERSION bump 与指纹更新 | complete | 既有 Landsat 缩放修正、版本纪律、README 四处更新 | spec.md 预设表 + 版本纪律 + 文档 Requirement | A2, A5, A8 | covered | 取代 S3 的"旧指纹不变"要求 |

## 交付内容

1. `gis/source.py`：新增 5 条 `AssetPreset` 条目 + 支撑机制（**ee 对象仍只在本模块构建**，红线 1）：
   - `merge_assets` 多资产合并（Landsat 8+9 合并预设）；
   - `band_transforms` 逐波段 `(scale, offset)`（ERA5 单位换算；Landsat 的 SR 缩放）；
   - `polarizations` + `instrument_mode`：按 `spec.bands` 推导极化过滤（S1）+ 空集可读报错；
   - `categorical`/`class_values`/`class_palette`/`class_names` 分类语义（WorldCover）；
   - `default_reducer`（WorldCover=mode、ERA5=mean）、`collection_only` 与 `single_image_asset`
     单景保护；
   - `defaults_for()` 随预设返回 dtype / reducer / render（含类色表）；
   - **修正既有 `LANDSAT/LC08/C02/T1_L2` 与 `LANDSAT/LC09/C02/T1_L2`：补官方 offset `-0.2`**
     （改用 `band_transforms`，scaling = `DN * 2.75e-05 - 0.2`），与合并预设口径一致。
2. `gis/spec.py`：`RenderSpec.class_values`（与 `palette` 等长配对，精确类值 → 颜色）；
   **`PROCESSING_VERSION` 2 → 3**（红线 3：修正既有 Landsat 像素输出的直接后果）。
3. `gis/emit.py`：`write_visual_rgb` / `_render_png` 支持按类值精确映射的调色板烘焙
   （现状单波段固定 viridis、忽略 `RenderSpec.palette`）。
4. `gis/qgis_bridge.py`：已烘焙 8 位 RGB 一律走多波段零拉伸（原先分类栅格会被 palette 分支
   二次着色），单波段分类源按 `Exact` 类值渲染。
5. `tests/unit/`：预设表结构断言（5 条新预设 + 既有 8 条字段快照，其中 LC08/LC09 的缩放口径
   按本次变更显式更新）、纯函数（极化过滤、逐波段变换、类表配对）、`RenderSpec.class_values`
   往返、**新金指纹回归**（bump 后重算的 P0 指纹）。
6. `tests/smoke_presets.py`：5 条新预设 × 三出口 smoke（含独立 GEE 复算量纲校验）。
7. `docs/README.md`（**主工作区的本地文档**，被 `.gitignore` 的 `/docs/*` 忽略、不进版本库）：
   §9.2 台账 C4 行状态、§2.2 与 §9.5 的预设数量 8 → 13、§11 红线 4 的 SAR 豁免说明、
   新增预设语义说明与 PROCESSING_VERSION 2 → 3 的变更记录；**删除**原「既有 LC08/LC09 缺
   offset」遗留记录（已修）。

# 非目标

- 不做台账之外的事：C5（批处理导出 + jobs 持久化）、C6（array 分块）、C7（skill 知识）、
  C8（OSM）、C9（add-in）一律不碰。
- **除 LC08/LC09 的辐射缩放口径外，不改既有 8 预设的字段与计算语义**：S2 / MODIS / DEM / GSW
  的像素输出不变（其指纹变化仅来自 `PROCESSING_VERSION` 这一项）。
- **不在出口层按 `spec.dtype` 强制写盘 dtype**：实测 GEO_TIFF 容器 dtype 由导出路径决定
  （S2 声明 uint16、产物 float64；WorldCover 声明 uint8、产物 float32），改它会影响全部既有
  产物的形态，属独立 change（已记录）。
- 不在本 change 修 `tests/smoke_tui.py` 的『产生新任务』断言（经基线 A/B 证明为既有问题：
  describe 走同步 `/rpc`，不产生任务行）。
- 不做 S1 的自定义地形校正 / 斑噪滤波 / 入射角归一化（GEE 目录已是 S1TBX 处理结果）。
- 不做 WorldCover 的多年份（v100+v200）合并与分类后处理。
- 不新增第三方依赖；不改 daemon / TUI 的 MCP 工具面。

# 约束与不变量

- 红线（docs/README.md §11）：1（ee 只建在 source.py）、2（网格由 `compute_grid()` 定）、
  3（改变像素输出的改动必须 `PROCESSING_VERSION += 1`）、4（云掩膜必须在 `select()` 之前）、
  6（新流程先串行试点 1 个样本）、8（新增 spec 字段不得改变旧 spec 指纹）。
- **版本纪律（本次变更的核心）**：修正既有 Landsat 缩放 ⇒ `PROCESSING_VERSION` 2 → 3；
  全部 spec 指纹更新；原金指纹 `c9243efd40318c85` 作废，测试锚定 bump 后的新值；
  既有 Landsat 缓存产物失效（下次运行按新指纹重新生成）。变更面必须可追溯（测试 + README）。
- 新预设一律"新增条目"：除上述有意的 Landsat 修正外，不影响任何既有预设的像素输出。
- `AssetPreset` 新增字段一律带默认值：对未使用它们的既有预设，行为逐字节不变。
- 单位换算与辐射缩放属于**计算图**（改变像素值），只在 `source.py` 施加；`render` 层不承担数值变换。
- 工作区纪律：代码改动只落在本 change 的 worktree（`D:\DEV\geocode\.worktrees\p2-presets`）；
  `docs/README.md` 是主工作区的本地文档（非版本控制文件），仅在用户明确要求下就地更新，
  不触碰主工作区里 C3 的未提交代码改动。

# 事实核查（2026-10-06，GEE 实测 + 官方目录）

| # | 事实 | 证据 |
| --- | --- | --- |
| F1 | `COPERNICUS/S1_GRD` 为 ImageCollection，值已转 **dB**；预处理链 = Sentinel-1 Toolbox 的 thermal noise removal + radiometric calibration + **terrain correction**（已地形校正/正射） | GEE 官方目录页原文；波段 HH/HV/VV/VH（dB）+ angle（deg），分辨率 10/25/40 m |
| F2 | S1 极化组合随景变化（VV、HH、VV+VH、HH+HV）；不加过滤时 `select(['HH','HV'])` 会**静默产出空结果**而不是报错 | 实测：北京 2024-06~09 共 14 景（全部 VV+VH）；HH+HV 过滤后 0 景，不过滤 `select` 后 `reduceRegion` 返回 `{}` |
| F3 | `COPERNICUS/S1_GRD_FLOAT` 是该产品家族的线性版本（同源、同重访） | GEE 目录；实测同一景 `system:index` 一致 |
| F4 | `LANDSAT/LC08\|LC09/C02/T1_L2` 光学 SR 波段缩放 = `DN * 2.75e-05 + (-0.2)`；热红外 `ST_B10` = `DN * 0.00341802 + 149.0` | GEE 官方目录页 Bands 表（Scale 2.75e-05 / Offset -0.2） |
| F5 | 修正前：既有 LC08/LC09 预设只做 `reflectance_scale=0.0000275`，缺 `-0.2`，输出反射率偏高约 +0.2（实测 `SR_B4` DN≈10975 → 无 offset 0.302 / 有 offset 0.102） | 实测 + 代码；**本次变更即修正此遗留** |
| F6 | LC08 与 LC09 是 C02 L2 同源产品，缩放系数一致；两者重访互补（各自 16 天，合起来约 8 天） | GEE 目录（两个集合的 Bands 表相同） |
| F7 | `ECMWF/ERA5_LAND/HOURLY`：11132 m，逐小时 1 景，50 个变量；累积量每日 0 点重置，EE 另给 19 个 `_hourly` 差值波段 | GEE 官方目录页；实测 2024-06-01 一天 = 24 景 |
| F8 | `ECMWF/ERA5_LAND/DAILY_AGGR`：逐日 1 景，含 `_sum` / `_min` / `_max` 变体 | 实测 2024-06 共 30 景；波段名如 `temperature_2m`、`total_precipitation_sum` |
| F9 | `ECMWF/ERA5/HOURLY` 与 `ECMWF/ERA5/DAILY` 是全球 0.25°（约 31 km，含海洋）产品；ERA5-Land 是 9 km 陆地产品 | GEE 目录 + 实测 |
| F10 | ERA5-Land 单位：温度 **K**、降水 **m**、气压 **Pa** | 实测 2024-06-15 12:00 北京：`temperature_2m`=299.39、`total_precipitation`=2.79e-6、`surface_pressure`=99579 |
| F11 | `ESA/WorldCover/v200` 是 **ImageCollection**（`size()=1`，`ee.Image()` 报 "is not an Image"），波段 `Map`；类值 {10..100}，资产属性自带 `Map_class_values` / `Map_class_palette`（11 色）/ `Map_class_names` | 实测 `ee.data.getAsset` + `toDictionary()`；目录页 Class Table 同值 |
| F12 | WorldCover 是分类栅格：`mode()` 归约后仍为**精确类码**；`mean` 会产生 15 这类不存在的类 | 实测北京 `frequencyHistogram` = {10,20,30,40,50,60,80,90}，无插值值 |
| F13 | 现状 `write_visual_rgb` 单波段走固定 viridis 色带，**忽略** `RenderSpec.palette`；`qgis_bridge` 的 palette 分支按 min/max 连续插值，且会把已烘焙的 RGB 再着色一次 | 代码：`gis/emit.py:_apply_colormap`、`gis/qgis_bridge.py` 渲染分支 |
| F14 | `COPERNICUS/DEM/GLO30` 也是 ImageCollection（26076 景）且已被 GEE 标记 deprecated | 实测 `ee.Image()` 报 "is not an image" + DeprecationWarning。台账之外的既有问题，只记录不修 |
| F15 | 产物**容器 dtype** 不由 `spec.dtype` 决定：两次对照下载（uint8 / float32 声明）容器都是 float32；既有 S2 产物（声明 uint16）为 float64 | 实测对照下载 + rioxarray 读回 |

# 决策（Shape 逐项裁决）

- **Q1 = A｜WorldCover 走 `mode` + 离散配色**（2026-10-06 batch）：`mode` 归约、不做辐射缩放、
  `dtype=uint8` 声明；emit_map 按类值精确配色（`RenderSpec.class_values` → `write_visual_rgb`
  精确映射资产自带 11 色 → `qgis_bridge` 精确类渲染）。
- **Q2 = B｜S1 出两个预设（dB + 线性）**：`COPERNICUS/S1_GRD` 与 `S1_GRD_FLOAT`；
  均按 `spec.bands` 推导极化过滤 + `instrument_mode="IW"`；`cloud_mask=None` ⇒ 无掩膜步骤 ⇒
  红线 4 在该路径无从适用（SAR 豁免，写入预设注释与 README）；地形校正不重做。
- **Q3 = A｜新增 L8+L9 合并预设，既有 LC08/LC09 当时不动**（2026-10-06 batch）。
- **Q4 = A｜ERA5-Land 逐日 + 单位换算**：`ECMWF/ERA5_LAND/DAILY_AGGR`；温度 K→°C、降水 m→mm；
  默认归约 `mean`。
- **D5（2026-10-06 验收轮，用户补充范围）｜修遗留 + 更新 README，并接受版本 bump**：
  给既有 `LANDSAT/LC08|LC09/C02/T1_L2` 补官方 offset `-0.2`；由此 `PROCESSING_VERSION` 2 → 3、
  全部指纹更新、原金指纹作废（测试改锚新值）、既有 Landsat 缓存失效；README 按最终状态更新。
  该项**取代** Q3 中"既有两预设缺 offset 记为遗留、另立 change"的部分。

# 验收示例

### Scenario: Sentinel-1 预设三出口（验收：A1）【需网络，已标注】

用两条 S1 预设（`COPERNICUS/S1_GRD`、`COPERNICUS/S1_GRD_FLOAT`）各派生 spec
（北京 AOI、`time_range=2024-06-01~09-01`、`reducer=median`）跑三出口：`emit_file` 得 GeoTIFF、
`emit_array` 得 NetCDF、`emit_map` 得工程+图；三产物网格与指纹一致；极化过滤后景数 > 0；
dB 预设数值在 -50~1 dB 量纲、线性预设在正数量纲；无云掩膜步骤不报错；请求该区域不存在的
极化时报可读 `SpecError`（含该区域实际极化）而不是静默空产物。

### Scenario: Landsat 8/9 预设三出口与缩放修正（验收：A2）【需网络，已标注】

(a) `LANDSAT/LC08+LC09/C02/T1_L2` 派生 spec（北京 AOI、2024 夏、`reducer="median"`）走通三出口；
波段 `SR_B2..SR_B7` 的产物均值逐波段等于 `2.75e-05 × GEE 原始均值 − 0.2`（独立复算）；
集合同时含 LC08 与 LC09 的景。
(b) **修正后的既有预设**：`LANDSAT/LC08/C02/T1_L2` 与 `LANDSAT/LC09/C02/T1_L2` 的产物同样落在
`DN × 2.75e-05 − 0.2` 量纲（修正前偏高约 +0.2）；两条预设的 `band_transforms` 与合并预设一致。

### Scenario: ERA5-Land 预设三出口（验收：A3）【需网络，已标注】

`ECMWF/ERA5_LAND/DAILY_AGGR` 派生 spec（北京 AOI、`time_range=2024-06`、`reducer=mean`）
走通三出口；`temperature_2m` 为摄氏量纲、`total_precipitation_sum` 以 mm 计（独立复算对上）。

### Scenario: WorldCover 预设三出口（验收：A4）【需网络，已标注】

`ESA/WorldCover/v200` 派生 spec（北京 AOI）走通三出口；栅格值为精确类码
（⊆ {10,20,30,40,50,60,70,80,90,95,100}，无 mean 产生的插值值）；`preset`/`defaults_for` 的
`dtype` 为 `uint8`；`emit_map` 的预览图与产物使用资产自带 11 色 palette 的精确类映射
（非 viridis 拉伸）。

### Scenario: 版本纪律与既有预设语义（验收：A5）

`PROCESSING_VERSION` 由 2 变为 3，且变更理由（修正既有 Landsat 缩放）可追溯；
修正前后指纹的差异面**仅**来自版本号这一项（对未受影响的预设：S2/MODIS/DEM/GSW 的
参与指纹字段取值不变）；测试锚定 bump 后重算的 P0 指纹并由离线用例断言；
原金指纹 `c9243efd40318c85` 已作废并在文档中记录。

### Scenario: 离线单测基线全绿（验收：A6）

在 worktree 内、断网条件下跑 `tests/unit` 全量用例，全部通过，用时秒级。

### Scenario: 现有 smoke 不回退（验收：A7）【需网络 / 需 daemon，已标注】

`tests/smoke_emit.py`、`tests/smoke_three_exits.py`、`tests/smoke_tui.py`、
`tests/smoke_map_renderers.py` 四条 smoke 的结果与 C2 基线一致（其中 smoke_tui 的
『产生新任务』项在未改动的 C2 基线上同样失败，属既有问题；其余全绿）。

### Scenario: 文档更新（验收：A8）

`docs/README.md`（主工作区本地文档）已按最终状态更新：§9.2 台账 C4 行、§2.2 与 §9.5 的预设
数量 8 → 13、§11 红线 4 的 SAR 豁免说明、新增预设语义与 `PROCESSING_VERSION` 2 → 3 的
变更记录；原「LC08/LC09 缺 offset」遗留记录已删除。

# 验证期望

- 离线单测（断网、秒级）：`PYTHONPATH=<worktree> <geo env python> -m unittest discover -s tests/unit -t tests/unit`
- 新 smoke（需网络）：`PYTHONPATH=<worktree> <geo env python> tests/smoke_presets.py`
- 既有 smoke：`tests/smoke_emit.py`、`tests/smoke_three_exits.py`、`tests/smoke_map_renderers.py`、
  `tests/smoke_tui.py`（后三条需守护进程；注意 6531 被并行会话占用，可用备用端口 + 端口重定向
  包装脚本）。
- 解释器：`C:\ProgramData\miniforge3\envs\geo\python.exe`（默认 `python` 无 `ee`）。
- 网络任务逐个串行试点（红线 6）。
