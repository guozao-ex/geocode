# Capability：p3-osm-overpass —— Overpass 矢量源接入（OSM → spec / GPKG / map 叠加）

## 定位

把 OpenStreetMap（Overpass API）接成 GeoCode 的矢量数据源：OSM 矢量以三种方式进入既有契约与链路——① 作为 AOI 物化来源喂进 `spec.aoi`；② 作为 GPKG 交付物服务"下游接"；③ 作为叠加图层进 map 出口（.qgz 与 arcpy layout）。新增 `gis/osm.py`（Overpass 客户端 + GPKG 交付）与 `gis/aoi.py`（行政区 AOI 供给），`gis/spec.py` 增加 `OverlaySpec` 呈现层契约，`emit_map` 与双 bridge 消费。零 ee 对象、零 source.py 改动、PV 保持 3、金指纹不回退、172 用例离线基线不回退、零新增依赖。

需求来源：C8 立项任务书（2026-10-07，用户预裁决 D1–D8）；台账 docs/README.md §9.2 C8 行。

## 行为规格

### Scenario: 离线基线不回退

验收：A1

现有 172 个离线单元用例全绿；本 change 新增用例并入 `tests/unit/`，全部离线（不碰网络）、秒级完成。Overpass QL 查询构造是**纯函数**（结构化参数：要素选择器、tag 过滤 dict、bbox/范围引用、timeout），对相同输入生成逐字节相同的查询串，单测含确定性断言。fixture 入 `tests/unit/fixtures/`，单文件 <500KB、≤200 要素。

### Scenario: Overpass 客户端与多边形装配（离线完备）

验收：A2

`gis/osm.py` 的 HTTP transport 可注入（单测用假 transport，不发真实请求）。用入库 fixture（真实录制响应）断言完整解析链：

- way → 面（闭合 way）或线（非闭合 way）；
- relation 的 outer/inner 两级标准装配，含洞（inner 环成孔）；
- 超出装配能力的要素**跳过并计数留痕**：进结果 dict 的 skipped 列表（含原因），禁止静默丢弃；
- 输出 GeoDataFrame 按 osm id 确定性排序，CRS 为 EPSG:4326；
- 拉取侧行为：429/504 指数退避重试 ≤2 次（假 transport 模拟），超限报错含可执行提示（等 N 秒 / 换镜像 / 缩小查询）；endpoint 列表经 geocode.json `osm.endpoints` 覆盖；请求前应用 `geoenv.apply_proxy_env()` 代理；`GEOCODE_OSM_REFRESH` 环境变量强制绕过缓存重拉。

### Scenario: GPKG 交付与幂等缓存

验收：A3

GPKG 交付产物落 `data/deliver/{id}.{hash8}.gpkg` + 同名 `.json` sidecar。sidecar 记录：查询、endpoint、`osm3s.timestamp`、要素/跳过计数、hash 输入。`hash8` = sha256(归一化查询 + AOI 摘要 + `osm3s.timestamp` + `VECTOR_VERSION`) 前 8 位十六进制；新增常量 `VECTOR_VERSION = 1`（独立于 PROCESSING_VERSION，只进矢量产物命名与 sidecar，不进栅格指纹）。geopandas 读回 GPKG 图层与要素数和写入口径一致。同一输入重复导出：hash 相同、文件幂等复用（不重复落盘）；`GEOCODE_OSM_REFRESH` 强制刷新路径可验证。

### Scenario: 行政区 AOI 进契约

验收：A4

`gis/aoi.py` 的 `admin_aoi(adcode)` 从本地合规边界数据 `_ref/contributions/china-admin-boundaries/skill/data/`（省 34 / 市 375 / 县 2891，EPSG:4326 GeoJSON）按 **adcode 唯一键**返回 GeoJSON geometry dict；数据路径可经 geocode.json 覆盖（单测用小型 fixture 注入路径，不依赖真实 `_ref/`）。返回值写进 `spec.aoi` 后：`spec.validate()` 通过，`compute_grid(spec)` 离线可算出网格。`_ref/` 缺失时报错可读并指向 docs/knowledge/README.md「出处」节的重新抓取程序。`osm_boundary_aoi(...)` 提供同形态的 Overpass 边界查询，**仅限非中国研究区**；产物一律是物化 GeoJSON dict（含 OSM 数据时 `osm3s.timestamp` 记录到 note/sidecar），spec 永不持有活引用。

### Scenario: 矢量叠加进 map 出口

验收：A5

`emit_map` 把 `spec.overlays` 同时分发给 qgis_bridge 与 arcpy_bridge，**两 bridge 共同消费同一 `OverlaySpec`**（frozen dataclass：`source` 物化 GPKG/GeoJSON 路径、`color`、`width`、`opacity`、`fill_color?`、`label_field?`），禁止各写一套私有样式参数（守卫与 LayoutSpec 同款）。同一 OverlaySpec 下：.qgz 工程含栅格 + N 个矢量图层（读回 .qgz 断言图层数与来源一致）；arcpy renderer 出 PDF/PNG 含矢量要素。`.png` 静态预览保持纯栅格烘焙不变，且该行为在交付文档中文档化（矢量可见性由 .qgz 与 arcpy PDF/PNG 承载）。

### Scenario: 呈现层不进指纹

验收：A6

`overlays` 为呈现层字段，**不参与指纹**：两个 spec 仅在 overlays 缺席/在场（或内容不同）上有差异时，指纹逐位相同；`overlays` 缺省时指纹 payload 整键缺席（§3.3 向后兼容先例，LayoutSpec 同款守卫单测扩展）。金指纹 `b91c09c9c6451c16` 不回退；`PROCESSING_VERSION` 保持 3。

### Scenario: 合规守卫

验收：A7

代码库（`gis/`、`tests/`、交付文档）内不存在任何"OSM 查询中国行政区划边界"的路径、示例或文档表述；中国边界数据消费点唯一——本地 `_ref/contributions/china-admin-boundaries/skill/data/`（adcode 纪律）。守卫以静态扫描单测固化（扫描 OSM 查询构造与示例中的中国边界要素选择）。研究区内 OSM 非边界要素（水系/道路/建筑/土地利用等）不受此限。

### Scenario: 端到端实测（需网络，串行）

验收：A8

按 D8 顺序串行放大：小范围 OSM 要素拉取（真实 Overpass 请求）→ GPKG 读回 → `admin_aoi` 选小组行政区（如东城区 110101）@100m 走三出口 mini smoke，证明 OSM/边界矢量确实进入 spec 与三出口链路。代理经 geocode.json 生效（从主工作区复制本地件）。429/504 退避路径至少验证一次（可用假 transport 离线覆盖）。网络项执行前满足：真实产物前先复制 geocode.json；真实 `_ref` 边界数据就位（geocode.json 覆盖路径指向主工作区 `_ref/`）。

## Constraints

- **合规硬约束（D2）**：禁止从 OSM / Natural Earth / GADM 取中国行政区划边界；中国行政区 AOI 只出自本地 `_ref` 合规数据；OSM 边界查询仅限非中国研究区。
- **指纹纪律（D3/红线 5）**：overlays 呈现层不进指纹、缺省整键缺席；金指纹 `b91c09c9c6451c16` 与 PV=3 不动。
- **物化纪律（D4/红线 6）**：进 spec 的外部数据一律物化 GeoJSON/路径，活引用禁止；`osm3s.timestamp` 留痕到 note/sidecar。
- **架构边界（红线 1/2）**：本 change 不引入 ee 对象、source.py 零改动；网格由 `compute_grid()` 唯一确定，AOI/overlay 只是喂料方。
- **零新增依赖（红线）**：geopandas 1.2.0 / pyogrio 0.13.0 / shapely 2.1.2 / fiona 1.10.1 已在 geo env 实测在位；GPKG 写盘走 pyogrio 引擎；HTTP 用 stdlib urllib。
- **改动面（D1）**：`gis/osm.py`（新）、`gis/aoi.py`（新）、`gis/spec.py`（OverlaySpec + overlays 字段）、`gis/emit.py`（emit_map 分发）、qgis_bridge / arcpy_bridge（消费 overlays）、tests/。
