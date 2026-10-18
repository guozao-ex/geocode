# Capability：container-dtype —— 产物容器 dtype 契约（声明可控、两出口一致、量纲守卫）

GeoCode 的产物容器 dtype 在 c18 之前**不由 `ArtifactSpec` 决定**，而由 GEE 导出路径决定：
声明 `uint16` 的 S2 样本实落 GeoTIFF `float64`（P0 产物 `s2_beijing_test.b91c09c9.tif`，
860×784 / 3 波段），声明 `uint8` 的 WorldCover 实落 `float32`；NetCDF 侧（xee）统一按
`float32` 落盘。同一份数据、同一网格，两个出口的字节占用差 2–3 倍，声明值与实际值不符 ——
下游（论文附件、ArcGIS/QGIS 工程、后续栅格代数）无法按声明预期规划存储与精度。

本 capability 把"落盘容器"从**副产物**提升为**显式契约**：`ArtifactSpec.container_dtype`
（默认 `"float32"`）声明该 spec 的落盘容器，GeoTIFF 与 NetCDF 两个出口按同一契约落盘；
同时把 `spec.dtype` 的语义收敛为**数据语义提示**（当前不影响落盘）。

## 语义分工

- `spec.dtype` = **数据语义提示**（当前不影响落盘）。保留该字段与取值域不变，只收敛注释与文档口径。
- `spec.container_dtype` = **落盘容器契约**。默认 `"float32"`；缺省即默认值。
  取值域与 `dtype` 相同的 7 个：`uint8` / `int16` / `uint16` / `int32` / `float32` / `float64`；
  默认取 `float32` 的依据是与 NetCDF/xee 侧既有落盘一致（未声明时等价于历史 NetCDF 行为）。

## 指纹与缓存

容器 dtype **不进指纹**（与 `render` / `layout` / `overlays` 同类：不改变物理像素值），
因此**不 bump `PROCESSING_VERSION`**，旧 spec 的指纹与缓存键原样保留。

序列化按红线 8（指纹归属显式化）处理：`to_dict()` 仅在 `container_dtype != "float32"` 时写入该键；
`from_dict()` 缺省即 `float32`；`fingerprint()` 的 payload 完全不含该键。

**由此产生的已知边界（显式处置，不默认无视）**：盘上的"旧容器"产物与"新契约"产物共用同一指纹，
指纹分不出二者。处置方式为**缓存命中时即时归一**（沿用 C15 `normalize_nodata_to_nan` 的
同目录 `.part` + 原子替换先例），不删除既有缓存、不另造基线。本 capability 不采用"作废旧缓存 +
重生成"的路线。

## 落盘路径

`emit_file`（GeoTIFF）与 `emit_array`（NetCDF）的**全部写盘路径**都按 `container_dtype` 落容器：

| 出口 | 写盘路径 | 落容器位置 |
|---|---|---|
| `emit_file` | 直写（单次 `getDownloadURL`） | 下载件掩膜折叠后的容器 |
| `emit_file` | 分块（多片 + 本地拼接） | 拼接产物的容器 |
| `emit_file` | 时序堆叠（逐期下载 + 本地合并） | 合并产物的容器 |
| `emit_array` | 直接（xee 内存数组） | `to_netcdf` 的变量 dtype |
| `emit_array` | 分块（`computePixels` 分块） | 分块写入的变量 dtype |

同一 spec 的两个出口容器 dtype 必须一致。

### Scenario: 同一 spec 两个出口容器一致

Acceptance: A1

给同一份 spec（显式声明 `container_dtype=float32`）分别跑 `emit_file` 与 `emit_array`，
GeoTIFF 的 `ds.dtypes` 与 NetCDF 各数据变量的 `dtype` 都等于 `float32`。
未显式声明时（缺省）结果相同 —— 契约默认值不改变"两个出口一致"这条判据。

### Scenario: 容器不一致的旧产物被显式处置

Acceptance: A6

产物缓存命中且盘上既有产物的容器 dtype 与当前契约不符时（典型：S2 真彩色 GeoTIFF 现状为
`float64`、契约 `float32`），系统走**一次性归一化**：在产物同目录写 `.part` 后原子替换，
并留下可读的进度记录（写明文件名、原容器、目标容器）。容器已一致时整体跳过（不重写文件，
不乱动字节）。既有缓存不被删除，也不以"作废 + 重生成"替代归一化。

### Scenario: 非法容器组合被守卫拦下

Acceptance: A2

对"实测数据为 0–1 小数、却要求整数容器"的组合，写盘前必须报出可读错误，产物不得被静默量化。
守卫的证据来源是**实测数据的有界采样**（不是只看声明）：采样范围内若存在小数部分或 NaN，
而目标容器是整数类型，即拒绝并给出可读消息（写清"建议改成 float32 或 float64"）。
拒绝是**在写盘之前**发生的：不得先写出被量化/截断的产物再报错。

**破坏性自证**：验收必须构造出这条失败条件并证明它被拦下（而不是"恰好通过"），
最小可判据用合成数组即可（构造 `[0, 0.5]` 这类含小数的数组 + 整数目标容器）。

### Scenario: collapse_mask_bands 的整数提升与归一机制统一

Acceptance: A10

`gis/export_chunks.py::collapse_mask_bands` 把"n 个值波段 + n 个掩膜波段"折叠为纯值产物时，
把值波段的整数容器提升为 `float32`（与 `gis/emit.py` 的 nodata 归一提升口径一致）：
掩膜为 0 的像素写 `NaN`，输出容器的 `nodata` 声明为 `NaN` 不再因整数容器越界抛错。
c15 实测过的失败形态（整数输入 + `nodata=nan` → rasterio `ValueError: nodata value, nan,
is beyond the valid range of its data type, int32`）必须被这条判据封住。

### Scenario: 契约序列化不改变旧 spec 指纹

Acceptance: A9

未写 `container_dtype` 的旧 spec：`to_dict()` 的输出与 c18 之前逐字节相同（该键缺席），
`fingerprint()` 与 c18 之前逐字节相同 —— 金指纹 `b91c09c9c6451c16`（PV 3）与
`c9243efd40318c85`（PV 2）都不回退。显式写入非默认值时，该键出现在 `to_dict()` 中，
但指纹不变（容器不进指纹）。

## 数值域不变性

容器从 `float64` 收敛到 `float32` 只改变**表示精度**，不改变数值域。既有样本的像素值
min/max/mean 在 1e-6 容差内不变；这条判据必须打在**现状确为 float64** 的样本上
（S2 真彩色 / NDVI），不能拿现状已是 `float32` 的样本（DEM / WorldCover）充数。

### Scenario: 容器收敛不改变既有样本的数值域

Acceptance: A3

以盘上既有产物为对照基线 —— `data/derived/taian_dem_city.26f57c12`、
`taian_dem_county.3227ec35`、`taian_s2_ndvi.4e5dc772`、`taian_s2_truecolor.ff2f0ca1`、
`taian_s2_truecolor_10m.824afc80`（各 `.tif` + `.nc`）—— 在契约容器下重算/比对像素值：
逐样本的 min/max/mean 与改动前的差值 |Δ| ≤ 1e-6，报告给出实测数字与上界。
基线只复用、不重造；比对在 worktree 本地副本上进行，不在主工作区就地改写既有产物。

## 文档与判例

- 入库件 `README.md`：§9.7 的"已知边界"条目（原文声称"产物容器 dtype 不由 `spec.dtype` 决定 …
  属独立 change"）收敛为**已定义语义**：写清 `dtype` 是语义提示、`container_dtype` 是容器契约、
  默认值与取值规则、以及"容器不进指纹"的后果。
- 本地件 `docs/README.md`（被 `.gitignore` 忽略、只存在于主工作区）：以**待执行差异清单**载体交付，
  由归档轮在主工作区就地执行。清单含两处：
  ① §11 红线 3 下补判例注记 ——「容器精度截断（float64→float32 等）若数值域在 1e-6 容差内不变，
  不视为改变像素输出；nodata/掩膜语义的归一化改写同理（c15 判例）」；
  ② §3.1 字段表与 §9.7 的 `container_dtype` 语义同步。

### Scenario: 文档收敛

Acceptance: A4

`README.md` §9.7 不再声称容器 dtype 不可控；改为写清当前语义与取值规则，
并说明容器不进指纹导致的"旧容器与新契约同指纹"这一后果及其处置。
本地件的对应修订以清单形式交付并逐条可逆（现状 / 改为 / 依据 / 回退）。

### Scenario: 判例注记交付

Acceptance: A7

`docs/README.md` §11 红线 3 下的判例注记以清单条目交付，四列齐全（现状为逐字全文、含执行时行号），
内容与本节"文档与判例"所述一致；执行由归档轮在主工作区完成，本 worktree 不改动该文件。

## 回归

（回归项是本 change 验收集里的门禁条目，不构成本 capability 的新行为 —— 它们验证本 capability
的改动没有破坏既有行为；capability 自身的定义以上文各节为准。）

### Scenario: 回归基线不回落

Acceptance: A5

离线用例全绿（包含容器契约与量纲守卫的新用例）、`uvx ruff@0.17.0 check` 零告警、
`tests/verify_all.py` 离线层 RUN 全 PASS。

### Scenario: 回归口径按同步 main 后的基线留档

Acceptance: A8

全量离线用例 **≥ 352 条**全绿（352 = 2026-10-18 同步 main 后的实测基线，非 c18 立项时的 257），
报告附 change 开始时与交付时的实测条数；新增用例只增不减。
