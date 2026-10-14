# Capability：export-chunking —— 出口层真实规模适配（分块下载 / 有界重试 / nodata 语义 / 输出根）

GeoCode 的三出口共用同一份 `ee` 计算图与同一个 `compute_grid` 网格。`emit_file` 通过
GEE `getDownloadURL` 取 GeoTIFF，而该接口对**单次请求**有 50,331,648 B（48 MiB）硬上限；
`emit_array` 走 xee 的 `computePixels`，`emit_map` 走本地渲染，二者不受该上限约束。
本 capability 让 `emit_file` 在超限规模下依然可用，并把出口层的失败语义、nodata 语义与
产物落盘位置统一为可预期行为。

## 触发与路径选择

`emit_file` 按估算下载体积选择取数路径：

- 估算 ≤ 上限：**直写路径**（单次 `getDownloadURL`），行为与产物与历史一致；
- 估算 > 上限：**分块路径**（多片请求 + 本地拼接）。

估算口径固定为 `网格像素数 × 波段数 × 5 B`（float32 4 B + mask 1 B），与 GEE 实际计数一致
（实测 18,383,386 像素 × 5 B = 91,916,930 B，与 GEE 报数逐字节吻合）。体积估算与像素数上限
（`MAX_DIRECT_PIXELS = 64_000_000`）是两道独立守卫：像素数守卫先判，体积守卫后判。

### Scenario: 直写与分块路径产物一致（验收：A2）

对小 AOI（估算 ≤ 上限）继续走单次 `getDownloadURL`，产物文件名、网格、像素值、指纹与历史一致；
P0 样本的产物仍为 `s2_beijing_test.b91c09c9.tif`，金指纹保持 `b91c09c9c6451c16`。
当估算超上限时，按目标网格切块逐片取数并在本地拼接。拼接结果的网格、CRS、transform、
像素值必须与同一 spec 走直写路径时**逐像元完全相同**（max|diff| = 0），片与片的接缝处不得
出现重采样、错位或空洞。测试须提供强制走分块的对照手段（缩小上限阈值或注入测试开关）。

### Scenario: 真实城市尺度三出口可用（验收：A1）

以真实 adcode（如 370900 泰安市）在 10m 三波段真彩色（网格 17680×9355 = 165.4M 像素；按 5 B/像素/波段估算请求体积 ≈2.5 GB）上，
`emit_file`、`emit_array`、`emit_map` 三出口全部成功；`emit_file` 的 GeoTIFF 与 `emit_array`
的 NetCDF 在同一网格上逐像元一致（容差 0.5）。分块路径不得另建网格 —— 三出口仍共享
`compute_grid` 的结果。

## 失败与重试语义

### Scenario: 瞬时中断有界重试、失败可读且无残留（验收：A3）

单片请求遇到瞬时错误（`http.client.RemoteDisconnected`、连接超时、HTTP 5xx）时按有界退避重试；
每次重试与最终结果写进 job 日志。重试次数有上限，耗尽后按失败路径处理，不无限重试。

整体失败时抛出的错误必须含：片号/片数、估算体积与上限、已重试次数，以及出路清单
（放大 scale / 缩小 AOI / 改用 array 出口 / 后续接 toDrive）。失败后不得留下 `.part`
临时文件或半截产物；`.part` 的清理与既有写盘纪律一致（同目录、同卷原子 rename）。

## nodata 语义

### Scenario: GeoTIFF 与 NetCDF 的 nodata 一致（验收：A4）

同一 spec 的 `emit_file` 产物（GeoTIFF）与 `emit_array` 产物（NetCDF）对无效像素使用同一语义：
NaN。GDAL 读回校验：GeoTIFF 的 nodata 声明与 NetCDF 的 `_FillValue` 均为 NaN，`rasterio`
masked read 两边一致（不再出现 `-inf` 与 NaN 并存）。若该变化影响指纹，按红线 3 完成
`PROCESSING_VERSION` bump 与金指纹预注册切换。

## 产物落盘位置

### Scenario: 输出根可配置（验收：A5）

`geocode.json` 支持 `paths.data_dir`：设置后 `data_path()` 的三个子目录（raw/derived/deliver）
都落在该目录下并自动创建；未设置时行为与历史逐字节一致（仓库 `data/`）。缓存目录（`.cache/`）
与日志目录的语义不变。

## 缓存保留

### Scenario: 缓存清单与显式清理（验收：A6）

提供清单/清理入口：按「当代指纹 / 历史指纹」分类列出 `data/derived` 的占用（文件名、
指纹、体积、是否当代），并支持只删除历史指纹产物——删除前需显式确认，当代指纹产物在任何
参数组合下都不会被删除（该守卫须有离线用例）。不提供自动清理。

## 回归约束

### Scenario: 既有基线与门禁不回退（验收：A7）

实现后：离线用例全绿（不少于 change 开始时的数量）、`uvx ruff@0.17.0 check` 零告警、
`tests/verify_all.py` 的离线层 RUN 项全 PASS，且 `tests/unit` 的离线守卫（AST 禁网）不被破坏 ——
分块计划与拼接逻辑不得引入网络依赖。
