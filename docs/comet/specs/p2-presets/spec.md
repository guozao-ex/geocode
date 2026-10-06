# 数据集预设表（dataset presets）

`gis/source.py` 的 `DEFAULT_ASSETS` 是「GEE 资产 → 常用约定」的查表：agent 用 `defaults_for(asset)`
即可拿到可用的 scale / 波段 / dtype / 渲染建议，无需每次查目录。本规格描述该能力在 C4
（`p2-presets`）交付后的**完整行为**。

C4 在既有 8 条预设之上新增 **5 条**（S1 两条、Landsat 8+9 合并一条、ERA5-Land 一条、
WorldCover 一条），并扩展 `AssetPreset` 契约与渲染链路以支撑分类栅格与 SAR。

**2026-10-06 范围变更（用户验收轮补充）**：一并修复既有 `LANDSAT/LC08|LC09/C02/T1_L2`
缺 `-0.2` offset 的遗留问题。这是有意的像素输出变更 ⇒ `PROCESSING_VERSION` 2 → 3，
全部指纹更新、原金指纹作废。除这两条的缩放口径外，其余既有预设的字段值与计算语义不变。

## Requirement: 预设契约（AssetPreset）

`AssetPreset` 为 frozen dataclass。既有字段语义不变；C4 新增字段**一律带默认值**，缺省时既有预设的
行为与像素输出逐字节不变。

| 字段 | 默认 | 语义 |
| --- | --- | --- |
| `asset` / `label` / `scale` / `bands` / `dtype` / `nodata` / `rgb` / `index_expr` / `cloud_mask` / `reflectance_scale` | 现状 | 语义不变（`cloud_mask` 仍取 `scl` / `qa_pixel` / `None`） |
| `merge_assets: tuple[str, ...] \| None` | `None` | 合成预设：`asset` 为本地键，真正要合并的 GEE 集合列在此处 |
| `band_transforms: dict[str, tuple[float, float]] \| None` | `None` | 逐波段 `(scale, offset)`，在 `toFloat()` 之后、`clip` 之前施加 |
| `polarizations: tuple[str, ...] \| None` | `None` | 该资产可能出现为**波段**的极化名集合（S1：VV/VH/HH/HV） |
| `instrument_mode: str \| None` | `None` | 需按 GEE 属性等值过滤的成像模式（S1：`IW`） |
| `categorical: bool` | `False` | 分类栅格语义（类码而非物理量） |
| `class_values` / `class_palette` / `class_names` | `None` | 类值、类色（十六进制，无 `#`）、类名，三者等长 |
| `default_reducer: str \| None` | `None` | 集合模式下 `spec.reducer` 缺省时的归约算子建议 |
| `collection_only: bool` | `False` | 该资产是 ImageCollection，不能走 `ee.Image(asset)` 单景分支 |
| `single_image_asset: bool` | `False` | 集合内仅 1 景，整体塌缩是安全且确定的 |

约束：`categorical=True` 时必须给出等长的 `class_values` / `class_palette`（`class_names` 可选）；
`merge_assets` 非空时 `collection_only` 必须为真；`polarizations` 与 `instrument_mode` 只用于集合过滤。

## Requirement: 新增预设条目

5 条新增条目的字段值（`label` 为中文说明，供 TUI / `describe_asset` 展示）：

1. `COPERNICUS/S1_GRD` —— Sentinel-1 GRD 后向散射（dB，IW）：
   `scale=10`、`bands=("VV","VH")`、`dtype="float32"`、`rgb=("VV","VH","VV")`、
   `cloud_mask=None`、`polarizations=("VV","VH","HH","HV")`、`instrument_mode="IW"`、`collection_only=True`。
2. `COPERNICUS/S1_GRD_FLOAT` —— Sentinel-1 GRD 后向散射（线性，IW）：
   字段同上，仅 `asset` 与 `label` 不同（线性量纲）。
3. `LANDSAT/LC08+LC09/C02/T1_L2` —— Landsat 8+9 Collection 2 L2 地表反射率（合并）：
   `scale=30`、`bands=("SR_B2","SR_B3","SR_B4","SR_B5","SR_B6","SR_B7")`、`dtype="uint16"`、
   `rgb=("SR_B4","SR_B3","SR_B2")`、`cloud_mask="qa_pixel"`、
   `merge_assets=("LANDSAT/LC08/C02/T1_L2","LANDSAT/LC09/C02/T1_L2")`、
   `band_transforms={SR_B2..SR_B7: (0.0000275, -0.2)}`、`collection_only=True`。
   该 `asset` 是**本地合成键**，不是 GEE 资产：`describe_asset` 对它不得发起 `getAsset`。
4. `ECMWF/ERA5_LAND/DAILY_AGGR` —— ERA5-Land 逐日聚合（9 km，陆地）：
   `scale=11132`、`bands=("temperature_2m","total_precipitation_sum","u_component_of_wind_10m","v_component_of_wind_10m")`、
   `dtype="float32"`、`band_transforms={"temperature_2m": (1.0, -273.15), "total_precipitation_sum": (1000.0, 0.0)}`、
   `default_reducer="mean"`、`collection_only=True`（`surface_pressure` 等其余波段保持原生单位）。
5. `ESA/WorldCover/v200` —— ESA WorldCover v200 10 m 土地覆盖（2021）：
   `scale=10`、`bands=("Map",)`、`dtype="uint8"`、`rgb=None`、`cloud_mask=None`、`categorical=True`、
   `class_values=(10,20,30,40,50,60,70,80,90,95,100)`、
   `class_palette=("006400","ffbb22","ffff4c","f096ff","fa0000","b4b4b4","f0f0f0","0064c8","0096a0","00cf75","fae6a0")`、
   `class_names=("Tree cover","Shrubland","Grassland","Cropland","Built-up","Bare / sparse vegetation","Snow and ice","Permanent water bodies","Herbaceous wetland","Mangroves","Moss and lichen")`、
   `default_reducer="mode"`、`collection_only=True`、`single_image_asset=True`。

类值/类色/类名与 GEE 资产属性 `Map_class_values` / `Map_class_palette` / `Map_class_names`
（2026-10-06 实测）及官方目录 Class Table 一致。

## Requirement: `defaults_for()` 的派生行为

有预设时零网络往返（现状保持）；返回 dict 增补：

- `reducer`：仅当 `single_image_asset=True` 时输出 `default_reducer`（WorldCover → `"mode"`）。
  其余预设不输出 reducer —— 避免"有 reducer 无 time_range"把整个历史集合卷进一次归约。
- `dtype`：分类预设用 `preset.dtype`（WorldCover → `"uint8"`）；其余沿用现状的 `"float32"`。
- `render`：分类预设输出 `{"bands": None, "palette": [...], "class_values": [...], "stretch": "none"}`；
  其余沿用现状 `{"bands": rgb, "stretch": "stddev"}`。

## Requirement: 计算图行为（红线 1 —— ee 对象只在本模块构建）

`build_image` / `build_collection` / `build_cube` 的共存语义以 C3 为准；本 change 只新增：

1. **集合来源**：`preset.merge_assets` 非空时，集合是各资产 `ee.ImageCollection(...)` 的 `merge()`
   结果；否则仍是 `ee.ImageCollection(spec.asset)`。云掩膜、时间/空间过滤、`select`、归约、
   缩放、`clip` 的**次序与现状一致**（红线 4：云掩膜在 `select()` 之前）。
2. **极化过滤**（S1）：集合按 `spec.bands ∩ preset.polarizations` 逐项
   `ee.Filter.listContains("transmitterReceiverPolarisation", p)` 过滤；`preset.instrument_mode`
   非空时追加 `ee.Filter.eq("instrumentMode", mode)`。过滤后集合为空时抛出 `SpecError`，
   消息指出请求的波段、区域与"该地区可能使用另一组极化"，**不得**静默产出空产物。
3. **逐波段变换**：在 `toFloat()` 之后、`clip` 之前，对 `bands ∩ preset.band_transforms` 的波段施加
   `img.multiply(scale).add(offset)`；未列出的波段保持原值。`preset.reflectance_scale`（既有机制）
   语义不变，与 `band_transforms` 同时存在时二者都按各自波段生效（既有预设不设 `band_transforms`）。
4. **分类语义**：`categorical=True` 的预设没有云掩膜与数值缩放；归约算子取
   `spec.reducer or preset.default_reducer or "median"`（WorldCover → `mode`），保证输出仍是精确类码。
5. **单景分支保护**：`preset.collection_only=True` 且 spec 未进入集合模式时，
   - `single_image_asset=True`（WorldCover）→ 用 `ee.ImageCollection(asset).mosaic()`（单景，确定性）；
   - 否则抛 `SpecError`，指出"该资产是 ImageCollection，请设置 time_range（+ reducer）"，
     替代 GEE 的 `Asset ... is not an Image`。
   既有预设未设该标记，行为与错误信息**不变**。

## Requirement: 地图与可视化（分类栅格精确配色）

1. `RenderSpec` 新增 `class_values: tuple[float, ...] | None`：与 `palette` 等长配对，表示
   「精确类值 → 颜色」；含校验（等长、类值唯一）与 `to_dict`/`from_dict` 往返。
   `render` 不参与 `ArtifactSpec.fingerprint()`（现状保持），红线 8 不受影响。
2. `write_visual_rgb` / `_render_png`：当 `render.class_values` 与 `render.palette` 同时给出时，
   按类值**精确匹配**取色（非类值 → `nodata_color`，缺省为黑），**绕过** `_stretch` 与固定 viridis；
   两个函数走同一套映射，保证「图与文件一致」。其余情形（含全部既有预设）行为不变。
3. `qgis_bridge`：已烘焙的 8 位 RGB 栅格（`is_byte_rgb`）一律走多波段无拉伸渲染，**不得**被
   palette 分支二次着色；单波段分类源按 `Exact` 色带 + 类值精确渲染。既有预设产物不变。
4. `arcpy_bridge` 消费同一份烘焙 RGB，无需改动。

## Requirement: 既有 Landsat 预设的缩放修正（2026-10-06 范围变更）

C4 立项时把「既有 `LANDSAT/LC08|LC09/C02/T1_L2` 缺 `-0.2` offset」记为遗留问题；用户在验收轮
补充范围，要求本次一并修复：

- 两条既有预设的 `SR_B2..SR_B7` 缩放口径改为官方 `DN × 2.75e-05 + (-0.2)`（用
  `band_transforms` 表达，与合并预设同一张表）；
- 这是**有意的像素输出变更** ⇒ `PROCESSING_VERSION` 2 → 3（红线 3）；
- 全部 spec 指纹随之更新；原金指纹 `c9243efd40318c85` 作废，测试改锚 bump 后重算的新值；
- 既有 Landsat 缓存产物失效，下次运行按新指纹重新生成（`data/derived/` 下旧文件成为孤儿，属预期）；
- 除这两条的缩放口径外，既有 8 条预设的字段值与计算语义不变。

## Requirement: 既有预设语义与版本纪律

- 8 条既有预设中，除 LC08/LC09 的缩放口径（上一条）外，字段值与计算语义逐个不变：
  `COPERNICUS/S2_SR_HARMONIZED`、`COPERNICUS/S2_HARMONIZED`、`MODIS/061/MOD13Q1`、
  `MODIS/061/MOD11A2`、`COPERNICUS/DEM/GLO30`、`JRC/GSW1_4/GlobalSurfaceWater` 的像素输出不变；
- `PROCESSING_VERSION` 为 `3`，且离线用例断言该值（版本纪律可回归）；
- 对未受影响的既有 spec，其指纹**变化面仅来自 `PROCESSING_VERSION` 这一项**：把 payload 里的
  版本号替换回 `2` 后，这些 spec 的哈希必须等于原有语义下的值（即实现没有夹带其他变更）；
- `ArtifactSpec` 字段集与指纹白名单/排除名单不变（红线 8 的守卫测试继续成立）。

## Requirement: 文档

`docs/README.md` 是本仓库的**本地开发文档**（被 `.gitignore` 的 `/docs/*` 忽略，不进版本库，
只存在于主工作区）。按最终状态更新：§9.2 台账 C4 行状态、§2.2 与 §9.5 的预设数量（8 → 13）、
§11 红线 4 的 SAR 豁免说明、新增预设的语义要点（S1 dB/线性、Landsat 合并键、ERA5 单位换算、
WorldCover 分类配色）、`PROCESSING_VERSION` 2 → 3 的变更记录；并**删除**原「既有 LC08/LC09
缺 offset」的遗留记录（本次已修）。

## 约束（Constraints）

- 红线：1（ee 只在 source.py）、2（网格由 `compute_grid()` 定）、3（像素输出变更必须
  `PROCESSING_VERSION += 1` —— 本次因修正既有 Landsat 缩放而 2 → 3）、4（云掩膜在 `select()`
  之前）、6（新流程先串行试点 1 个样本）、8（新增 spec 字段不得改变旧 spec 指纹 —— 本次 bump
  是有意的例外，须在测试与文档中留痕）。
- 红线 4 的**SAR 豁免**：该红线约束"有掩膜时的施加次序"。SAR 预设 `cloud_mask=None`，计算图中
  不存在掩膜步骤，故无次序约束；豁免仅限此类无云掩膜数据集，并须在预设注释与 README 写明。
- 不新增第三方依赖；不触碰 daemon / TUI 的工具面。
- `tests/unit` 必须保持离线（不 import `ee`、不发网络请求）且秒级完成。
- 出口层**不**按 `spec.dtype` 强制写盘 dtype（容器 dtype 由 GEE 导出路径决定，见 brief F15）；
  该能力属独立 change。

## 场景（Scenario）

### Scenario: S1 预设三出口（验收：A1）

对两条 S1 预设各派生 spec（北京 AOI、`time_range=("2024-06-01","2024-09-01")`、`reducer="median"`）
并跑三出口：`emit_file` 产出 GeoTIFF、`emit_array` 产出 NetCDF、`emit_map` 产出工程与图；
三者 `spec_fingerprint` 相同、网格相同；极化过滤后集合非空；`S1_GRD` 像元值落在 dB 量纲
（约 -50~1），`S1_GRD_FLOAT` 落在正数量纲；请求该区域不存在的极化时抛可读 `SpecError`
（消息含该区域实际出现的极化），不得静默产出空产物。

### Scenario: Landsat 8+9 合并预设与既有预设修正（验收：A2）

(a) `LANDSAT/LC08+LC09/C02/T1_L2` 派生 spec（北京 AOI、2024 夏、`reducer="median"`）跑通三出口；
产物均值为 `2.75e-05 × GEE 原始均值 − 0.2`（独立复算逐波段对上）；集合含 LC08 与 LC09。
(b) 修正后的既有 `LANDSAT/LC08/C02/T1_L2` 与 `LANDSAT/LC09/C02/T1_L2` 产物同样落在
`DN × 2.75e-05 − 0.2` 量纲（修正前偏高约 +0.2），其 `band_transforms` 与合并预设一致。

### Scenario: ERA5-Land 逐日预设三出口（验收：A3）

`ECMWF/ERA5_LAND/DAILY_AGGR` 派生 spec（北京 AOI、`time_range=("2024-06-01","2024-07-01")`、
`reducer="mean"`）跑通三出口；`temperature_2m` 为摄氏量纲（北京 6 月约 15~35，而非 288~308）；
`total_precipitation_sum` 以 mm 计（而非 m）；两者与独立复算一致。

### Scenario: WorldCover 预设三出口（验收：A4）

`ESA/WorldCover/v200` 派生 spec（北京 AOI）跑通三出口；栅格值为精确类码
（⊆ {10,20,30,40,50,60,70,80,90,95,100}，无 mean 产生的插值值）；`preset` 与 `defaults_for`
的 `dtype` 声明为 `uint8`；`emit_map` 的预览图与产物使用资产自带 11 色 palette 的精确类映射
（非 viridis 拉伸）。

### Scenario: 版本纪律与既有预设语义（验收：A5）

`PROCESSING_VERSION` 为 `3` 且变更理由可追溯；对 6 条未受影响的既有预设，指纹的变化面**仅**
来自版本号（把版本号替换回 2 后哈希与本 change 之前一致）；`ArtifactSpec` 字段集与指纹
白名单/排除名单不变；离线用例锚定 bump 后重算的 P0 指纹，原金指纹 `c9243efd40318c85`
已在文档中标注作废。

### Scenario: 离线单测基线全绿（验收：A6）

在 worktree 内断网运行 `tests/unit` 全量用例，全部通过且秒级完成；`tests/unit` 不 import `ee`、
不发起网络请求。

### Scenario: 现有 smoke 不回退（验收：A7）

`tests/smoke_emit.py`、`tests/smoke_three_exits.py`、`tests/smoke_map_renderers.py`、
`tests/smoke_tui.py` 四条 smoke 全部跑通，产物形态（网格 / 波段数 / 量纲 / 三个出口一致性）
与 C2 基线一致；指纹因本次 `PROCESSING_VERSION` bump 按设计变为新值、产物按新指纹重新生成
（这是 A5 记录的有意版本变更，不是回退）；其中 `smoke_tui` 的『产生新任务』项在未改动的
C2 基线上同样失败（既有问题，非本 change 引入）。

### Scenario: 文档更新（验收：A8）

主工作区的 `docs/README.md`（本地文档，非版本控制文件）已按最终状态更新：§9.2 台账 C4 行、
§2.2 与 §9.5 的预设数量 8 → 13、§11 红线 4 的 SAR 豁免说明、新增预设语义与
`PROCESSING_VERSION` 2 → 3 的变更记录；原「LC08/LC09 缺 offset」遗留记录已删除。
