# 目标

交付一个 ArcGIS Pro 3.7 add-in（`Pro/` 下手写 csproj 的 C# 工程，net10.0-windows），在 Pro 进程内起 **HTTP 型 MCP server（127.0.0.1:6530）**，暴露三个工具——`pro_get_view_aoi`（当前视图范围 → EPSG:4326 GeoJSON）、`pro_add_layer`（把本地 GeoTIFF/GPKG 加进活动地图）、`pro_export_view`（导出当前视图 PNG）——使 agent 宿主把它作为第二 MCP server 接入，闭环"从当前视图取 AOI → 三出口出图 → 结果图层回贴活地图"。对应台账：docs/README.md §9.2 C9 行（dockpane 拆出，另行立项）。

C9 是路线图收官项：C1–C8 已全部交付并入 main。headless arcpy 已覆盖出版级出图；本 change 只补 headless 做不到的三件事（docs/README.md §9.4）：操作正开着的地图、当前视图取 AOI、活会话交互。

# 范围

- **W1 add-in 骨架与构建部署（新建 `Pro/`）**：手写 csproj，直接引用 `$(ProgramW6432)\ArcGIS\Pro\bin\*.dll`，`dotnet build` 出包；不用 Visual Studio、不用 Pro SDK VSIX、不用 Esri 打包 target（CodeTaskFactory 会失败）。`Config.daml` 置 zip 根 + `Install/*.dll` 的标准布局打包（打包脚本入库）；部署 = 拷贝 zip 到 `[MyDocuments]\ArcGIS\AddIns\ArcGISPro`（目录不存在则创建）。
- **W2 三个 MCP 工具（全部方法包 `QueuedTask.Run`）**：`HttpListener` 监听 `127.0.0.1:6530`（后台线程），MCP 协议与 daemon 一致（initialize protocolVersion 2025-06-18 → tools/list → tools/call）；后台线程收到的每个调用经 `QueuedTask.Run` 编组进 Pro UI 线程——`Pro/` 下不允许任何直接触碰 Pro API 的裸方法。
  - `pro_get_view_aoi`：活动地图视图 extent → 视图坐标系转 EPSG:4326 → GeoJSON Polygon dict 返回；产物可直接写进 `spec.aoi`（A5 闭环验证）。
  - `pro_add_layer`：入参本地文件路径（.tif / .gpkg），加为活动地图图层，返回图层名与图层计数。
  - `pro_export_view`：当前视图导出 PNG（入参输出路径，默认落 `data/deliver/`）。
- **W3 可观测与文档**：`gis/preflight.py` 增一类探测项（Pro 安装 / add-in 是否部署 / 6530 是否监听，离线可测、mock 路径；C8 未动过该文件，无交叠顾虑）；宿主接入说明：agent 宿主把 `http://127.0.0.1:6530/mcp` 作为第二 MCP server 配置，与 daemon 6531 并列、互不依赖。

## Source coverage

来源：《C9 立项任务书 —— p1b-arcgis-addin ArcGIS Pro 活会话接入》（用户于 2026-10-07 本会话提供的完整正文；整份材料为需求来源，覆盖边界 = 全文八个章节）。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：§一 背景与起点 | complete | C1–C8 已并入 main（C8 合并提交 2361082）；基线 212 用例 3.6s 离线全绿、PV=3、金指纹 b91c09c9c6451c16（PV2 旧值双时代并存）；本 change 不产栅格像素、PV 不 bump；机器前提：dotnet SDK 10.0.300/10.0.401、Pro 3.7 bin、MyDocuments 无 OneDrive 重定向；与 C8 交付物只消费不修改 | Constraints and invariants；spec.md 守卫场景 | A1、A8 | covered | 背景与基线约束；2026-10-07 本机复核属实 |
| S2：§二 目标（一句话） | complete | add-in + 6530 MCP server + 三工具 + 第二 MCP server 接入闭环 | spec.md 定位 + 全部场景 | A1–A8 | covered | 目标总纲 |
| S3：§三 W1 add-in 骨架与构建部署 | complete | Pro/ 手写 csproj 引 Pro bin DLL；不用 VS/VSIX/Esri 打包 target；Config.daml 置 zip 根 + Install/*.dll 标准布局；打包脚本入库；部署到 MyDocuments\ArcGIS\AddIns\ArcGISPro | spec.md 场景"add-in 构建打包与部署" | A1、A2、A3 | covered | 当前有效需求 |
| S4：§三 W2 三个 MCP 工具 | complete | HttpListener 127.0.0.1:6530 后台线程；MCP 协议与 daemon 一致（2025-06-18）；QueuedTask.Run 编组硬纪律；三工具各自入参/出参/行为 | spec.md 场景"MCP server 与线程纪律""pro_get_view_aoi""pro_add_layer""pro_export_view" | A4、A5、A6、A7 | covered | 当前有效需求；D3 线程纪律同时进 Constraints |
| S5：§三 W3 可观测与文档 | complete | preflight.py 增探测项（Pro 安装/add-in 部署/6530 监听，离线 mock 可测）；宿主接入说明（6530 与 daemon 6531 并列互不依赖） | spec.md 场景"preflight 探测项与宿主接入" | A8 | covered | 当前有效需求 |
| S6：§四 非目标 | complete | dockpane 延后（完成后修订 §9.2 台账行注记"拆出另行立项"，Shape 阶段用户要求纳入才升级 W4）；不做符号修改（CIM renderer 延后）；不碰 daemon/jobs/TUI/client；不在 Pro/add-in 进程加载任何 GEE 栈（红线 7）；geocode.json 零改动；不写 C# 单测框架；PV 不 bump、不修改 C8 交付的 gis/osm.py、gis/aoi.py 与 OverlaySpec 语义 | 非目标 | — | non-goal | 全文照录为范围边界 |
| S7：§五 预裁决 D1–D8 | complete | D1 工具面 3+9 两 server 独立；D2 端口 6530 常量 + GEOCODE_PRO_PORT 覆盖；D3 QueuedTask.Run 硬纪律；D4 打包部署一个脚本；D5 许可纪律（只用 §9.4 已落档技术要点，禁止读其源码移植；仅个人学习不分发）；D6 TFM net10.0-windows；D7 改动面纪律；D8 验证顺序离线→部署→逐工具实测，证据留档 logs/acceptance/ | Decisions + Constraints and invariants | A1–A8 | covered | 用户已预裁决"不再开放方案征询"，全文转入 Decisions，不再提问 |
| S8：§六 验收要点 A1–A8 | complete | A1–A8 八条验收判据原文（A4–A7 标注"需 Pro 会话"，证据 = HTTP 转录 + 截图） | 验收示例 + spec.md 对应场景 | A1–A8 | covered | 验收项一一对应，spec 场景以"验收：A1…A8"引用合并 |
| S9：§七 约束与红线 | complete | §11 全程适用；红线 7（Pro 侧零 GEE 栈）、D3/D5/D7；构建产物与部署 zip 不入库（.gitignore 追加段）；6530 占用在 preflight 探测项可见；DoD 含 docs/README.md 更新（§9.1 台账、§9.2 C9 行 dockpane 拆出注记、§5.4 端口表 6530 改"现用"、§8 踩坑新增条目） | Constraints and invariants + Verification expectations | A1 | covered | 当前有效约束 |
| S10：§八 验收预期（命令速查） | complete | dotnet build Pro/GeoCodePro.csproj -c Release；PYTHONPATH=. + geo env unittest discover；212 + preflight 新增用例全绿 | Verification expectations | A1、A8 | covered | 命令照录为验证基线 |

# 非目标

- **dockpane 延后**：台账 C9 行原文含 dockpane，本 change 不做（TUI 已覆盖管理面）；完成后同步修订 docs/README.md §9.2 台账行注记"dockpane 拆出，另行立项"。若 Shape 阶段用户要求纳入，才升级为 W4。
- 不做符号修改（CIM renderer 操作延后；add_layer 已覆盖核心闭环）。
- 不碰 daemon / jobs / TUI / client——add-in 是独立第二 MCP server，daemon 零改动。
- **不在 Pro / add-in 进程加载任何 GEE 栈**（红线 7）：不 import ee、不装包进 `arcgispro-py3`；数据交换走文件。
- `geocode.json` 零改动（端口走常量 + `GEOCODE_PRO_PORT` 环境变量覆盖）。
- 不写 C# 单测框架；契约证据走 HTTP 调用转录（A 组）。
- `PROCESSING_VERSION` 不 bump；不修改 C8 交付的 `gis/osm.py`、`gis/aoi.py` 与 OverlaySpec 语义。

# Constraints and invariants

- **D2 端口**：默认 6530 写死常量，`GEOCODE_PRO_PORT` 环境变量可覆盖；geocode.json 零改动。
- **D3 线程亲和性（硬纪律）**：`Pro/` 下所有触碰 Pro API 的方法一律经 `QueuedTask.Run` 编组进 Pro UI 线程；后台 HttpListener 线程只做协议解析与 JSON 组装；code review 检查项。
- **D5 许可纪律**：`Knight60/ArcGIS-Pro-MCP` 是 AGPL-3.0——只用 docs/README.md §9.4 已落档的技术要点，**禁止读其源码后移植**；add-in 仅个人学习使用（Pro 学习版授权），不分发。
- **D6 TFM**：`net10.0-windows`（Pro 3.7 锁定）；机器 dotnet SDK 10.0.300/10.0.401 在位。
- **D7 改动面纪律**：文件改动只允许 `Pro/` 新目录及其构建/部署脚本、`gis/preflight.py` 追加探测项、tests/（preflight 离线单测）、docs/README.md（台账、§5.4 端口表）；其余 gis/ 模块一律不碰。
- **基线守卫**：212 用例离线基线全绿不回退；`PROCESSING_VERSION = 3` 不 bump；金指纹 `b91c09c9c6451c16` 不回退；本 change 不产栅格像素。
- **红线 7（Pro 侧零 GEE 栈）**：不 import ee、不装包进 `arcgispro-py3`；数据交换走文件。
- **构建产物不入库**：`Pro/` bin/obj 与部署 zip 追加进 .gitignore；6530 端口占用需在 preflight 探测项里可见。
- **DoD**：`Pro/` 工程 + 打包/部署脚本 + preflight 探测项 + 宿主接入说明 + docs/README.md 更新（§9.1 台账、§9.2 C9 行含 dockpane 拆出注记、§5.4 端口表 6530 改"现用"、§8 踩坑新增条目）。

# Decisions

- **D1 工具面**：3 个 pro_* 工具（6530 add-in）；6531 daemon 9 个不变，两 server 独立。
- **D4 打包部署**：手写 csproj + 标准 zip 布局 + AddIns 目录拷贝；打包/部署脚本入库（PowerShell 或 Python，一个文件）。
- **D8 验证顺序（红线 6）**：离线构建/打包/DAML 校验 → 部署加载 → Pro 打开状态下逐工具实测，每步证据留档 `logs/acceptance/`（HTTP 转录 + 截图）。
- **单 Native change 不拆分**：W1/W2/W3 同属一个 add-in 工程、需反复修改同一核心区域，无独立验收边界；不建 Supervisor Change。

# 验收示例

- **A1【离线】构建**：`dotnet build Pro/GeoCodePro.csproj -c Release` 零错误，net10.0-windows，仅引用 Pro bin DLL；构建日志留档。
- **A2【离线】打包结构**：zip 根 `Config.daml` + `Install/*.dll`，脚本一键出包；结构校验离线单测（读 zip 断言布局）。
- **A3【离线】DAML 合法性**：XML 可解析、模块/按钮声明齐全；部署路径文档化。
- **A4【需 Pro 会话】加载**：add-in 出现在 Pro 的 Add-In Manager 且状态 Enabled（截图留档 logs/acceptance/）。
- **A5【需 Pro 会话】当前视图取 AOI 闭环**：`pro_get_view_aoi` 返回的 GeoJSON 通过 `ArtifactSpec.validate(exit="map")`，且 `compute_grid()` 离线算出网格（Python 侧复验转录留档）——证明"视图 AOI 能进 spec/三出口链路"。
- **A6【需 Pro 会话】加图层**：`pro_add_layer` 对两种格式各验一次——既有 GeoTIFF（如 `data/deliver/s2_beijing_test.*.rgb8.tif`）与 GPKG（tests/unit fixtures 边界 GeoJSON 经 geopandas 现生成，或 C8 smoke 产物）；图层计数 +1 转录留档。
- **A7【需 Pro 会话】导出视图**：`pro_export_view` 出 PNG，PIL 读回断言尺寸 > 0；文件落约定目录。
- **A8【离线】回归**：tests/unit 212 基线全绿 + preflight 新增项单测；PV 保持 3、金指纹不回退。

# Verification expectations

离线项（A1–A3、A8）直接在主工作区跑命令取证；需 Pro 会话项（A4–A7）按 D8 顺序串行采集 HTTP 转录与截图，全部留档 logs/acceptance/。验证基线命令：

```bash
# 离线构建（主工作区根）
dotnet build Pro/GeoCodePro.csproj -c Release
# 离线基线（Python 侧改动仅 preflight）
PYTHONPATH=. C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit
# 预期：212 + preflight 新增用例，全绿
```

需 Pro 会话的验收项（A4–A7）逐项标注"需 Pro 会话"，证据 = `logs/acceptance/` 下的 HTTP 调用转录 + 截图，按 D8 顺序串行采集；验收交接时每项都要有非空 evidence。
