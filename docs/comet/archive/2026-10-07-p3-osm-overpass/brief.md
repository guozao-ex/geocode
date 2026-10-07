# 目标

把 OpenStreetMap（Overpass API）接成 GeoCode 的**矢量数据源**，使 OSM 矢量以三种方式进入既有契约与链路：

1. 作为 **AOI 物化来源**喂进 `spec.aoi`（行政区 AOI 供给 + Overpass 边界查询）；
2. 作为 **GPKG 交付物**服务"下游接"；
3. 作为**叠加图层**进 map 出口（.qgz 与 arcpy layout）。

全程不破坏三出口共享契约、指纹纪律与 172 用例离线基线。对应台账：docs/README.md §9.2 C8 行（验收要点 = OSM 矢量可进入 spec / 三出口链路）。

# 范围

- **W1 矢量源模块（核心，新建 `gis/osm.py`）**：Overpass QL 查询构造**纯函数**（结构化参数：要素选择器、tag 过滤 dict、bbox/范围引用、timeout）→ HTTP 拉取（stdlib `urllib`，复用 `geoenv.apply_proxy_env()` 代理；endpoint 列表 geocode.json `osm.endpoints` 可覆盖；429/504 指数退避重试 ≤2 次；强制刷新钩子 `GEOCODE_OSM_REFRESH`）→ 解析为 GeoDataFrame（WGS84/EPSG:4326，按 osm id 确定性排序）→ AOI/范围裁剪 → GPKG 落盘。
- **多边形装配能力边界**：way（含闭合面）+ relation 的 **outer/inner 两级标准装配**（含洞）；超出能力的要素**跳过并计数留痕**（进结果 dict 的 skipped 列表），禁止静默丢弃。
- **GPKG 交付**：`data/deliver/{id}.{hash8}.gpkg` + 同名 `.json` sidecar（查询、endpoint、`osm3s.timestamp`、要素/跳过计数、hash 输入）；`hash8` = sha256(归一化查询 + AOI 摘要 + `osm3s.timestamp` + `VECTOR_VERSION`)[:8]；新增常量 `VECTOR_VERSION = 1`（矢量解析装配逻辑版本，独立于 PROCESSING_VERSION，只进矢量产物命名与 sidecar，不进栅格指纹）。
- **W2 行政区 AOI 供给（新建 `gis/aoi.py`）**：`admin_aoi(adcode)` 从本地合规边界数据 `_ref/contributions/china-admin-boundaries/skill/data/`（省 34 / 市 375 / 县 2891，EPSG:4326 GeoJSON，含 adcode 字段）按 **adcode 唯一键纪律**返回 GeoJSON geometry dict；路径可经 geocode.json 覆盖；`_ref/` 缺失时给**可读报错**并指向 docs/knowledge/README.md「出处」节的重新抓取程序。`osm_boundary_aoi(...)`：Overpass 边界查询，**仅限非中国研究区**（D2）。两者产物一律是**物化后的 GeoJSON dict**，由调用方/agent 写进 `spec.aoi`——spec 永远不持有"OSM 查询引用"这类活引用（D4）。
- **W3 map 出口矢量叠加（改 `gis/spec.py` + `gis/emit.py` + 双 bridge）**：`gis/spec.py` 新增 `OverlaySpec`（frozen dataclass，与 LayoutSpec 同类）：`source`（物化 GPKG/GeoJSON 路径）、`color`、`width`、`opacity`、`fill_color?`、`label_field?`；`ArtifactSpec.overlays: tuple[OverlaySpec, ...] = ()`。**呈现层字段，不参与指纹**——完全沿用 LayoutSpec 先例与既有指纹守卫机制。`emit_map` 把 `spec.overlays` 同时分发给 qgis_bridge（.qgz 增矢量图层）与 arcpy_bridge（layout 出 PDF/PNG 含矢量）——**两 bridge 共同消费同一 OverlaySpec，禁止各写一套样式参数**（§9.2 决定 2 的延伸）。`.png` 保持纯栅格烘焙不变（文档化：矢量可见性由 .qgz 与 arcpy PDF/PNG 承载）。

## Source coverage

来源：《C8 立项任务书 —— p3-osm-overpass Overpass 矢量源接入》（用户于 2026-10-07 本会话提供的完整正文；整份材料为需求来源，覆盖边界 = 全文八个章节）。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：§一 背景与起点 | complete | C1–C7 已并入 main（ce40e45）基线事实：172 用例全绿、PV=3、金指纹 b91c09c9c6451c16、LayoutSpec 不参与指纹先例（gis/spec.py:141–147）、指纹 payload 缺省键整个缺席（gis/spec.py:494）、`GEOCODE_*` 测试钩子命名先例 | Constraints and invariants；spec.md 守卫场景 | A1、A6 | covered | 背景与既有先例约束；2026-10-07 在本 worktree 逐项复核属实（172 用例 3.0s 全绿、PV=3、LayoutSpec 守卫在位） |
| S2：§二 目标（一句话） | complete | OSM 三种进入方式：①AOI 物化进 spec.aoi ②GPKG 交付服务"下游接" ③叠加图层进 map 出口；不破坏三出口契约/指纹纪律/172 基线 | spec.md 定位 + 全部场景 | A1–A8 | covered | 目标总纲，由三个 workstream 场景共同承载 |
| S3：§三 W1 矢量源模块 | complete | gis/osm.py 全链路：纯函数查询构造→urllib 拉取（代理/endpoint 覆盖/429/504 退避≤2/GEOCODE_OSM_REFRESH）→GeoDataFrame（4326、osm id 确定性排序）→裁剪→GPKG；装配边界 outer/inner 两级含洞、skipped 留痕；GPKG 命名/sidecar/hash8/VECTOR_VERSION=1 | spec.md 场景"Overpass 客户端与多边形装配""GPKG 交付与幂等缓存" | A2、A3 | covered | 当前有效需求；hash8 精确序列化格式为实现细节，确定性必测 |
| S4：§三 W2 行政区 AOI 供给 | complete | gis/aoi.py：admin_aoi(adcode) 本地合规数据 adcode 唯一键；路径 geocode.json 可覆盖；_ref 缺失可读报错指向恢复程序；osm_boundary_aoi 仅限非中国研究区；产物一律物化 GeoJSON dict 进 spec.aoi，活引用禁止 | spec.md 场景"行政区 AOI 进契约" | A4 | covered | 当前有效需求；D2 合规硬约束同时进 Constraints |
| S5：§三 W3 map 出口矢量叠加 | complete | OverlaySpec frozen dataclass（source/color/width/opacity/fill_color?/label_field?）；ArtifactSpec.overlays 缺省 ()；呈现层不进指纹；emit_map 同一 OverlaySpec 同时分发双 bridge，禁止私有样式参数；.png 保持纯栅格并文档化 | spec.md 场景"矢量叠加进 map 出口""呈现层不进指纹" | A5、A6 | covered | 当前有效需求；.png 文档化义务进 A5 判据 |
| S6：§四 非目标 | complete | 八条非目标：不做 OSM 栅格化进网格；不做瓦片底图/XYZ、不做 Nominatim；不新增 MCP 工具/不改 daemon/jobs/TUI；不把矢量做成第四出口；不碰 source.py/不改 file/array 像素语义/不动预设表；PV 保持 3；零新增依赖（四库已在位，GPKG 走 pyogrio） | 非目标 | — | non-goal | 全文照录为范围边界 |
| S7：§五 预裁决 D1–D8 | complete | 模块划分（D1）；合规边界硬约束（D2）；指纹守卫（D3）；AOI 物化（D4）；命名与缓存（D5）；网络（D6）；装配边界（D7）；验证顺序（D8） | Decisions + Constraints and invariants | A7 | covered | 用户已预裁决"不再开放方案征询"，全文转入 Decisions，不再提问 |
| S8：§六 验收要点 A1–A8 | complete | A1–A8 八条验收判据原文 | 验收示例 + spec.md 对应场景 | A1–A8 | covered | 验收项一一对应，spec 场景以"验收：A1…A8"引用合并 |
| S9：§七 约束与红线 | complete | 红线 1–8：ee 只在 source.py（本 change 零 ee 对象）；网格 compute_grid 唯一；PV 不 bump；串行试点；指纹向后兼容整键缺席；物化禁活引用；worktree 先复制 geocode.json；DoD 含 smoke_osm.py + docs/README.md 四处更新 | Constraints and invariants + Verification expectations | A1 | covered | 当前有效约束；红线 7/8 落到验证期望 |
| S10：§八 验收预期（命令速查） | complete | 离线基线命令（PYTHONPATH=. + geo env python -m unittest discover -s tests/unit）；网络项标注"需网络"按 D8 串行；fixture <500KB/个 | Verification expectations | A1 | covered | 命令照录为验证基线 |

# 非目标

- 不做 OSM 栅格化进网格（rasterize 到 compute_grid）——未来独立 change。
- 不做瓦片底图/XYZ、不做 Nominatim 地理编码（研究区定位靠 adcode/显式 bbox）。
- 不新增 MCP 工具、不改 daemon/jobs/TUI——C8 是库级能力，agent 直接 import 使用。
- 不把矢量做成"第四出口"——GPKG 走 `gis/osm.py` 库函数落盘，三出口架构叙事不动。
- 不碰 `source.py`（ee 计算图零变化）、不改 file/array 出口像素语义、不动预设表。
- `PROCESSING_VERSION` 保持 3 不 bump（栅格像素输出零变化）。
- 零新增依赖：geopandas 1.2.0 / pyogrio 0.13.0 / shapely 2.1.2 / fiona 1.10.1 已在 geo env 实测在位（2026-10-07 复核），GPKG 写盘走 pyogrio 引擎。
- 不做 C9 add-in 相关内容。

# Constraints and invariants

- **D2 合规边界（硬约束）**：知识库 china-admin-boundaries 行明文——禁止从 OSM / Natural Earth / GADM 取**中国行政区划边界**（表述不合规）。因此：中国行政区 AOI **只**出自本地 `_ref` 合规数据（adcode 纪律）；OSM 边界查询仅限非中国研究区；代码中不存在任何"OSM 查询中国边界"的路径或示例；研究区内 OSM **非边界要素**（水系/道路/建筑/土地利用等）不受此限。
- **D3 指纹**：overlays 为呈现层，缺席与在场**都不改变** spec 指纹（LayoutSpec 同款守卫单测扩展）；金指纹 `b91c09c9c6451c16` 与 PV=3 双双不动；`overlays` 缺省时指纹 payload 整键缺席（§3.3 向后兼容先例）。
- **D4 AOI 物化**：进 spec.aoi 的永远是物化 GeoJSON 结果（含 OSM 数据则记录 `osm3s.timestamp` 到 note/sidecar），不做活引用——保住确定性、可序列化与指纹纪律。
- **D5 命名与缓存**：见 W1 的 hash8 公式与 `GEOCODE_OSM_REFRESH` 钩子；重复导出同 hash 幂等复用。
- **D6 网络**：urllib 标准库 + `apply_proxy_env()`；默认 endpoint `https://overpass-api.de/api/interpreter`，geocode.json `osm.endpoints` 可加镜像；退避 ≤2 次；超限报错给可执行提示（等 N 秒 / 换镜像 / 缩小查询）。
- **D7 装配边界**：outer/inner 两级；跳过留痕不静默。
- **红线 1/2**：ee 对象只在 source.py 构建（本 change 根本不引入 ee 对象，source.py 零改动）；网格由 `compute_grid()` 唯一确定，AOI 只是喂料方，不得私算网格。
- **红线 5（指纹向后兼容）**：新增 spec 字段 `overlays` 缺席时 payload 整键缺席。
- **红线 6**：进 spec 的外部数据一律物化，活引用禁止。
- **测试纪律**：tests/unit 新增用例离线、不碰网络、秒级完成；fixture 入 `tests/unit/fixtures/` 控制体积（<500KB/个，≤200 要素，可为中国**非边界**要素的真实录制响应）。
- **工作区**：worktree 隔离，分支 comet/p3-osm-overpass（Runtime 默认惯例，与既往 C4–C7 一致），目标分支 main。网络/真实产物前先从主工作区复制本地件 `geocode.json`（worktree 检出的是占位模板，skip-worktree 先例）。
- **DoD**：除代码与测试外，含 `tests/smoke_osm.py`（网络项标注）、docs/README.md 更新（§9.1 台账、§9.2 C8 行、§8 踩坑新增条目、§2.2 代码地图补行数）——docs/README.md 为本地件不入库，在主工作区就地更新。

# Decisions

以下 D1–D8 由任务书**预裁决**（"除明确标注外不再开放方案征询"），本 change 不再提问：

- **D1 模块划分**：`gis/osm.py`（Overpass 客户端+GPKG）、`gis/aoi.py`（行政区 AOI）、`spec.py` 加 OverlaySpec、emit/qgis/arcpy 消费。改动面集中在这五处 + tests/。
- **D2 合规边界**：见 Constraints and invariants（硬约束）。
- **D3 指纹**：overlays 缺席与在场都不改变 spec 指纹；金指纹与 PV 双双不动。
- **D4 AOI 物化**：物化 GeoJSON dict，活引用禁止。
- **D5 命名与缓存**：hash8 公式 + `GEOCODE_OSM_REFRESH`，同 hash 幂等复用。
- **D6 网络**：urllib + 代理 + endpoint 覆盖 + 退避 ≤2 + 可执行报错提示。
- **D7 装配边界**：outer/inner 两级，跳过留痕。
- **D8 验证顺序（红线 6）**：离线单测 → 小范围要素拉取 → admin-AOI 三出口 mini run，串行放大，先小后大。

# Verification expectations

- **离线基线（每轮必跑，秒级、不碰网络）**：`PYTHONPATH=. C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit`，预期 172 + 新增用例全绿。
- **D8 串行放大顺序**：① 离线单测 → ② 小范围 OSM 要素拉取（真实网络）→ ③ admin-AOI 三出口 mini run（东城区 110101 @100m）。网络项在验收清单逐项标注"需网络"并串行执行；429/504 退避路径用假 transport 离线覆盖。
- **网络前提**：真实产物前从主工作区复制 `geocode.json`（代理/GEE 凭据/endpoint 覆盖）；A8 的 admin_aoi 需真实 `_ref` 边界数据（路径经 geocode.json 覆盖指向主工作区 `_ref/` 或按索引「出处」节程序抓取）。
- **文档更新义务**：docs/README.md 在主工作区就地更新四处（§9.1 / §9.2 C8 行 / §8 踩坑 / §2.2 代码地图）；`tests/smoke_osm.py` 交付且网络项标注。

# 验收示例

- A1 离线基线不回退：现有 172 用例全绿；新增用例并入 tests/unit，秒级完成、不碰网络；查询构造纯函数确定性断言。
- A2 Overpass 客户端离线完备：transport 可注入；用入库 fixture（真实录制响应、小型、≤200 要素、<500KB，可为中国非边界要素）断言：way→面/线、带洞 relation 装配、skipped 计数、osm id 确定性排序、CRS=4326。
- A3 GPKG 交付：geopandas 读回图层与要素数一致；文件名/sidecar 符合 D5；幂等复用成立。
- A4 行政区 AOI 进契约：`admin_aoi(adcode)` 返回值通过 `spec.validate`，`compute_grid(spec)` 离线可算出网格；`_ref` 缺失报错可读且指向恢复程序。
- A5 矢量进 map 出口（离线+需网络）：同一 OverlaySpec 下 .qgz 含栅格+N 个矢量图层（读回断言），arcpy renderer 出 PDF/PNG 含矢量；两 bridge 样式参数同源（禁止私有布局参数的守卫与 LayoutSpec 同款）。
- A6 呈现层不进指纹：overlays 缺席与在场指纹逐位相同；金指纹 `b91c09c9c6451c16` 不回退；PV 保持 3。
- A7 合规守卫：代码库内不存在 OSM 中国边界查询路径/示例/文档表述；中国边界数据消费点唯一（本地 `_ref`，adcode）。
- A8 端到端实测（需网络，串行）：小范围 OSM 要素拉取→GPKG 读回→`admin_aoi` 选一个小组行政区（如东城区 110101）@100m 走三出口 mini smoke，证明 OSM/边界矢量确实进入 spec 与三出口链路；代理经 geocode.json 生效；429/504 退避路径至少验证一次（可用假 transport 离线覆盖）。
