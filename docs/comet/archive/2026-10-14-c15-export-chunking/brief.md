# Outcome

让**真实研究尺度**的 AOI 能走通 GeoTIFF 出口。

现状（2026-10-11 真实数据运行实测）：`emit_file` 走 GEE `getDownloadURL`，单次请求有
**50,331,648 B（48 MiB）** 硬上限，按 float32(4B) + mask(1B) = 5 B/像素/波段计 —— 直写路径
实测上限约**每波段 1000 万像素**。换算下来 10m 三波段真彩色约 1830×1830 ≈ 18km×18km 就到顶；
泰安市（adcode 370900）30m DEM 估算 88 MB 直接不可用（实测报错
`Total request size (91916930 bytes) must be less than or equal to 50331648 bytes`）。城市级 /
地级市级 AOI 目前只能用 array 出口（走 xee computePixels，无此上限）或放大 scale。

本 change 给 `emit_file` 增加**分块下载 + 本地拼接**，并收掉同一层在真实运行中暴露的另外三处
问题：瞬时网络中断无重试、GeoTIFF 的 nodata 写 `-inf`（与 NetCDF 及外部工具不一致）、产物
只能落仓库 `data/`（无法指向研究项目目录）。

# Scope

- **分块下载（核心）**：估算下载体积超上限时，把目标网格切块，逐块 `getDownloadURL` 后按
  目标网格**本地拼接**；触发条件与现有 `MAX_DOWNLOAD_BYTES` 守卫一致，小 AOI 仍走直写路径
  且产物逐像元不变；
- **有界重试**：`_fetch_tif` 对瞬时错误（`http.client.RemoteDisconnected`、超时、5xx）做有界
  退避重试（实测 NDVI 首跑即撞一次 `RemoteDisconnected`，原样重试即过），重试次数与间隔写进日志；
- **失败可读、无残留**：整体失败时报出「片号/片数、估算体积、上限、已重试次数」与四条出路
  （放大 scale / 缩 AOI / 换 array 出口 / 后续 toDrive），并清理 `.part` 半成品；
- **nodata 语义统一**：GeoTIFF 侧写 NaN（与 NetCDF 一致），下游 `rasterio` masked read 两边一致；
  需核实 nodata 是否进入指纹，若进入则按红线 3 处理；
- **输出根可配**：`geocode.json` 增加 `paths.data_dir`（缺省＝仓库 `data/`，行为逐字节不变），
  研究项目可把产物指到自己的工作目录；
- **缓存保留策略**：提供 `data/derived` 的清单/清理入口（区分当代指纹与历史指纹，只删历史且需
  显式确认），判定逻辑有离线用例覆盖。

## 目录结构

### 新建

- `gis/export_chunks.py`：分块计划纯函数（同输入同输出，无 IO）＋本地拼接实现；
- `tests/unit/test_export_chunks.py`：切块计划与拼接的离线用例（含边界块、缝像素、nodata 处理）；
- `scripts/prune_cache.py`（可选，或纳入既有脚本目录）：缓存清单/清理入口。

### 修改

- `gis/emit.py`：`_fetch_tif` 分块下载 + 拼接 + 有界重试 + 失败文案 + nodata 写法；
- `gis/geoenv.py`：`data` 根支持 `geocode.json: paths.data_dir` 覆盖；
- `tests/unit/`：受 nodata 影响的金指纹/产物断言（如确需改，按红线 3 预注册）。

### 删除

- 无（不删除现有文件；分块拼接不得改动既有产物路径与写盘纪律）。

### 明确不建

- 不建 CI、不建 `Export.image.toDrive` 异步路径、不改 `emit_array` / `emit_map` 取数路径、
  不改既有 smoke 断言语义。

# Non-goals

- 不接 `Export.image.toDrive` 服务端批处理（保留为后续独立 change；本轮只做同步分块）；
- 不改 `emit_array`（xee）与 `emit_map` 的取数路径；
- 不改 `ArtifactSpec` 契约字段集与指纹算法本身（除非 nodata 被证实进指纹，那也按红线 3 走
  PV bump 预注册，而不是改算法）；
- 不做跨平台适配（仅本机 Windows + conda geo 环境）；
- 不追求分块并发下载（先保证正确与可读；并发是后续优化，见 Open questions 说明）。

# Acceptance examples

- A1: 泰安市（adcode 370900）S2 真彩色 10m（网格 17680×9355 = 165.4M 像素；按守卫口径 5 B/像素/波段估算请求体积 ≈2.5 GB ≫ 48 MB）三出口全部成功：
  file 产出 GeoTIFF、array 产出 NetCDF、map 产出 .qgz + .png；file 与 array 在同一网格上逐像元一致
  （容差 0.5，逐像元不是抽样）。
- A2: 分块路径与直写路径产物一致：对小 AOI 强制走分块（可用测试开关或缩小的 `MAX_DOWNLOAD_BYTES`），
  产物与直写路径逐像元完全相同（max|diff| = 0）；既有 P0 样本产物与金指纹 `b91c09c9c6451c16` 不回退。
- A3: 失败路径可读且无残留：单片连续失败时错误信息含片号/片数、估算体积、上限、已重试次数与四条出路；
  失败后不留 `.part` 或半截产物。
- A4: nodata 语义统一：GeoTIFF 与 NetCDF 的 nodata 均为 NaN，GDAL 读回逐项校验一致；若 nodata 进指纹，
  按红线 3 完成 `PROCESSING_VERSION` bump 与金指纹预注册切换（并在 README §9 记一笔）。
- A5: `geocode.json` 设 `paths.data_dir` 后产物落该目录并自动创建目录；未设时行为与现在一致
  （仓库 `data/{derived,deliver}`）。
- A6: 缓存清单/清理入口：能列出当代与历史指纹各自的占用；清理只作用于历史指纹且需显式确认；
  判定逻辑有离线用例（含「当代指纹产物不得被删」的守卫用例）。
- A7: 回归：离线用例全绿（≥257 条）、`uvx ruff@0.17.0 check` 零告警、`tests/verify_all.py` 离线层
  RUN 全 PASS。

# Constraints and invariants

- GEE 硬限：单次 `getDownloadURL` ≤ 50,331,648 B；每像素每波段按 5 B 计（实测 18,383,386 × 5 =
  91,916,930 与 GEE 报数逐字节吻合）；
- `MAX_DIRECT_PIXELS = 64_000_000`（直写像素上限）保持；
- 红线：三出口共享同一 `ee` 计算图与同一个 `compute_grid` 网格 —— 分块**不得另建网格**；
  指纹向后兼容；改变像素输出必须 bump `PROCESSING_VERSION` 并预注册金指纹；
- `tests/unit` 受 `test_offline_guard` 的 AST 禁网约束（禁 import ee / socket / requests 等），
  因此切块计划必须是纯函数，拼接逻辑不得依赖网络；
- 运行环境：conda `geo`（python 3.12）、daemon 端口 6531；`geocode.json` 为本地件不入库。

# Decisions

- D1：采用**同步分块 + 本地拼接**，不接 toDrive —— 无 Drive/额度依赖、不引入服务端任务态，
  且直接复用现有网格与写盘纪律；
- D2：nodata 统一为 **NaN**（与 NetCDF、以及本项目外部对照（cn-dem 产物）一致），消除 `-inf`；
- D3：输出根通过 `geocode.json: paths.data_dir` 覆盖，缺省仍为仓库 `data/`（保持既有文档口径）；
- D4：缓存保留策略**只做清单 + 显式清理**，不自动删除（研究产物不可静默丢弃）；
- D5：本轮分块**串行**下载（正确性优先）；并发留待有实测需求再做（`--stage big` 的分块实测显示
  瓶颈在 GEE 取数，串行 51 s/块，并发是独立的性能话题）。

# Verification expectations

- 分块与直写的一致性证据必须是**逐像元**的（不接受抽样或仅统计量）；
- 大 AOI 三出口必须在**真实 adcode**（370900）上实测留档，不接受仅合成大网格；
- 失败路径需实测证据（注入受限体积或制造断连），不止离线单测；
- 可复用 2026-10-11 的真实运行基线（泰安市 DEM/NDVI/真彩色产物与指纹 `26f57c12`/`4e5dc772`/`ff2f0ca1`；
  跨链路对照 AWS GLO-30 vs GEE GLO-30：r = 0.99995、MAD 1.355 m）。

# Open questions

（无：范围与 D1–D5 已按 2026-10-11 真实运行证据确定。若新会话在 Build 期发现必须改 toDrive 或
必须改 nodata 口径，按 `--revise-requirements` 回 Shape。）
