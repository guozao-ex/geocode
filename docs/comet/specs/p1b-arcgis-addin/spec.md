# Capability：p1b-arcgis-addin —— ArcGIS Pro 活会话接入（add-in + 6530 MCP server）

## 定位

交付一个 ArcGIS Pro 3.7 add-in（`Pro/` 下手写 csproj 的 C# 工程，net10.0-windows），在 Pro 进程内起 HTTP 型 MCP server（127.0.0.1:6530），暴露三个工具——`pro_get_view_aoi`、`pro_add_layer`、`pro_export_view`——使 agent 宿主把它作为第二 MCP server 接入（与 daemon 6531 并列、互不依赖），闭环"从当前视图取 AOI → 三出口出图 → 结果图层回贴活地图"。零 daemon 改动、零 geocode.json 改动、PV 保持 3、金指纹不回退、212 用例离线基线不回退。

需求来源：C9 立项任务书（2026-10-07，用户预裁决 D1–D8）；台账 docs/README.md §9.2 C9 行（dockpane 拆出，另行立项）。

## 行为规格

### Scenario: add-in 构建（离线）

验收：A1

`Pro/` 下新建 C# 工程（手写 csproj，`GeoCodePro.csproj`，TFM `net10.0-windows`），直接引用 `$(ProgramW6432)\ArcGIS\Pro\bin\*.dll`，`dotnet build -c Release` 零错误，构建日志留档；不用 Visual Studio、不用 Pro SDK VSIX、不用 Esri 打包 target。构建产物（bin/obj）与部署 zip 不入库（.gitignore 追加段）。

### Scenario: 打包结构与部署脚本（离线）

验收：A2

打包脚本（入库，单文件）产出标准布局 zip：zip 根 `Config.daml` + `Install/*.dll`；结构校验离线单测（读 zip 断言布局：根级 Config.daml 存在、Install 目录含程序集），脚本一键出包。部署脚本（入库）把 zip 拷贝到 `[MyDocuments]\ArcGIS\AddIns\ArcGISPro`（目录不存在则创建）。

### Scenario: DAML 合法性与部署路径文档化（离线）

验收：A3

`Config.daml` 为可解析 XML、模块/按钮声明齐全；部署路径在交付文档中文档化。

### Scenario: MCP server 与线程纪律（需 Pro 会话）

验收：A4

add-in 在 Pro 启动时于后台线程起 `HttpListener` 监听 `127.0.0.1:6530`（默认常量，`GEOCODE_PRO_PORT` 环境变量可覆盖；geocode.json 零改动）；MCP 协议与 daemon 一致：initialize（protocolVersion 2025-06-18）→ tools/list → tools/call。后台线程只做协议解析与 JSON 组装；**每个触碰 Pro API 的调用经 `QueuedTask.Run` 编组进 Pro UI 线程**——`Pro/` 下不允许任何直接触碰 Pro API 的裸方法（硬纪律，code review 检查项）。add-in 出现在 Pro 的 Add-In Manager 且状态 Enabled（截图留档 logs/acceptance/）。宿主接入说明文档化：agent 宿主把 `http://127.0.0.1:6530/mcp` 作为第二 MCP server 配置，与 daemon 6531 并列、互不依赖。

### Scenario: pro_get_view_aoi 当前视图取 AOI（需 Pro 会话）

验收：A5

工具 `pro_get_view_aoi`：活动地图视图 extent → 视图坐标系转 EPSG:4326 → 返回 GeoJSON Polygon dict。返回产物可直接写进 `spec.aoi`：闭环验证 = 返回的 GeoJSON 通过 `ArtifactSpec.validate(exit="map")`，且 `compute_grid(spec)` 离线算出网格（Python 侧复验，转录留档 logs/acceptance/）——证明"视图 AOI 能进 spec/三出口链路"。

### Scenario: pro_add_layer 图层回贴（需 Pro 会话）

验收：A6

工具 `pro_add_layer`：入参本地文件路径（.tif / .gpkg），加为活动地图图层，返回图层名与图层计数。对两种格式各验一次：既有 GeoTIFF（如 `data/deliver/s2_beijing_test.*.rgb8.tif`）与 GPKG（tests/unit fixtures 的边界 GeoJSON 经 geopandas 现生成，或 C8 smoke 产物）；每次验证图层计数 +1，转录留档。

### Scenario: pro_export_view 导出视图（需 Pro 会话）

验收：A7

工具 `pro_export_view`：当前视图导出 PNG（入参输出路径，默认落 `data/deliver/`）。PIL 读回断言尺寸 > 0；文件落约定目录，转录留档。

### Scenario: preflight 探测项与离线回归

验收：A8

`gis/preflight.py` 追加一类探测项（离线可测、mock 路径，不发真实网络依赖）：Pro 安装检测、add-in 是否部署（MyDocuments\ArcGIS\AddIns\ArcGISPro 下 zip 存在性）、6530 端口是否监听（占用可见）。新增项配离线单测。tests/unit 212 基线全绿不回退；`PROCESSING_VERSION` 保持 3、金指纹 `b91c09c9c6451c16` 不回退；不修改 C8 交付的 `gis/osm.py`、`gis/aoi.py` 与 OverlaySpec 语义。按 D8 顺序串行采集证据：离线构建/打包/DAML 校验 → 部署加载 → Pro 打开状态下逐工具实测，每步留档 `logs/acceptance/`（HTTP 转录 + 截图），需 Pro 会话项每项非空 evidence。

## Constraints

- **端口（D2）**：6530 默认常量 + `GEOCODE_PRO_PORT` 覆盖；geocode.json 零改动。
- **线程纪律（D3/硬纪律）**：Pro API 触碰一律 `QueuedTask.Run` 编组；后台线程零 Pro API 直调。
- **许可纪律（D5）**：`Knight60/ArcGIS-Pro-MCP` AGPL-3.0——只用 docs/README.md §9.4 已落档技术要点，禁止读其源码移植；add-in 仅个人学习使用，不分发。
- **TFM（D6）**：`net10.0-windows`（Pro 3.7 锁定）。
- **改动面（D7）**：只允许 `Pro/` 新目录及其构建/部署脚本、`gis/preflight.py` 追加探测项、tests/（preflight 离线单测）、docs/README.md（台账、§5.4 端口表）；其余 gis/ 模块一律不碰。
- **Pro 侧零 GEE 栈（红线 7）**：不 import ee、不装包进 `arcgispro-py3`；数据交换走文件。
- **基线守卫**：212 用例全绿、PV=3、金指纹 `b91c09c9c6451c16` 不回退；不产栅格像素。
- **构建产物不入库**：`Pro/` bin/obj 与部署 zip 进 .gitignore。
- **DoD**：`Pro/` 工程 + 打包/部署脚本 + preflight 探测项 + 宿主接入说明 + docs/README.md 更新（§9.1 台账、§9.2 C9 行含 dockpane 拆出注记、§5.4 端口表 6530 改"现用"、§8 踩坑新增条目）。
