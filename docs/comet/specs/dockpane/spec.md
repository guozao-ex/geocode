# Capability：c11-dockpane —— Pro add-in dockpane 状态面板（C9/C10 拆出的唯一遗留项）

## 定位

在 C9 已交付的 add-in（`Pro/` 工程、6530 HTTP MCP server、三工具、打包部署链路）之上补
一块 Pro Dockpane 状态面板：不看 Python 会话、不点弹窗就知道 6530 服务是否健康，并从
正开着的 Pro 会话一键执行三个已交付工具（`pro_get_view_aoi` / `pro_add_layer` /
`pro_export_view`）、立即看到最近一次结果——补齐 README §9.4「headless 做不到的三件事」
中 GUI 状态面板一件的空白，兑现 C9 台账注记「dockpane 拆出另行立项」的遗留项。

零引擎层改动：`gis/` 零 diff、`PROCESSING_VERSION = 3` 不 bump、金指纹
`b91c09c9c6451c16` 不回退、geocode.json 零改动、6530 工具集（tools/list）不变。

需求来源：README §9.4 dockpane 段（2026-10-08 C10 落地的立项要点）+ §5.4 端口表 +
C9 归档产物（既有契约）+ C10 归档产物（流程纪律与订正事实）。

## 行为规格

### Scenario: DAML dockpane 声明与开面板入口（离线）

验收：A2

`Pro/Config.daml` 在 `GeoCodePro_Module` 内新增 dockPane 声明（id `GeoCodePro_Dockpane`，
className 指向新的 DockPane 类，caption 非空；保持既有 `GeoCodePro_Tab`/`GeoCodePro_Group`
结构，不移动既有 `GeoCodePro_ServerStatus` 按钮），并提供「打开状态面板」入口
（GeoCode 选项卡新增第二个按钮，className 指向新 Button 类，通过 Pro 的 dockpane
管理 API 激活 `GeoCodePro_Dockpane`）。既有按钮、tabs/groups 声明零挪动。
离线单测断言：daml 可解析、dockPane 声明存在且 id/className 齐全、开面板按钮存在
且引用该 dockPane id、既有 ServerStatus 按钮声明不回退。

### Scenario: 面板类与视图（离线构建）

验收：A3

新增 DockPane 类与 UserControl 视图（WPF XAML，Page/build 动作编译进程序集），
沿 Pro SDK dockpane 标准模式（DockPane 基类 + GetOrCreate 句柄 + 视图绑定）；
沿用手写 csproj（仅引 Pro bin DLL，无 NuGet/VSIX/Esri 打包 target），XAML 走
SDK 现成构建机制（Page 编译），`dotnet build -c Release` 零错误。面板类不触碰
Pro 数据 API（MapView/LayerFactory 等）——面板读写 McpServerHost 状态与结果
注册表（纯 .NET），工具执行走 ProTools 统一入口。

### Scenario: 服务状态区运行态（需 Pro 会话）

验收：A6

面板顶部服务状态区展示 `McpServerHost.Shared` 真实状态：运行中态显示端口
（默认 6530，`GEOCODE_PRO_PORT` 覆盖后显示覆盖值）、请求数、错误数。
自动刷新：面板可见期间由 UI 线程计时器周期刷新（纯 .NET 状态读取，零 Pro API），
面板隐藏或关闭时计时器停止。

### Scenario: 端口占用态与重试监听（需 Pro 会话）

验收：A7

未监听时面板显示端口 + LastError 摘要的可读中文反馈（端口占用时点名「端口被占用」，
不空白、不崩溃）；面板附「重试监听」按钮（调用共享 Start()，零 Pro API），
端口释放后可从面板直接恢复，不必重启 Pro。

### Scenario: 工具区与最近结果区（AOI 一键与复制）（需 Pro 会话）

验收：A8

面板中部为三工具区。`pro_get_view_aoi` 一键执行：最近结果区显示摘要（bbox 坐标
+ Polygon 顶点数）与「复制 GeoJSON」按钮；显示坐标与 HTTP 接口返回一致（同一实现
`ProTools`，面板非另行一套实现）。
每工具最近结果 = 时间戳 + 成功/失败 + 摘要 + 失败时错误全文；面板路径与
6530 HTTP 路径共用同一结果注册表——HTTP 侧执行的结果也会出现在面板。

### Scenario: add_layer / export_view 工具输入与执行（需 Pro 会话）

验收：A9

- `pro_add_layer`：本地路径输入框 +「浏览…」文件对话框（.tif/.tiff/.gpkg 过滤）
  + 可选子图层名输入框 + 执行按钮；结果显示图层名/图层计数。
- `pro_export_view`：可选输出路径框（留空 = 默认 `data/deliver/` 惯例）+ 执行
  按钮；结果显示输出路径与 exported 标志。
工具执行统一经 `ProTools` 的 async 门面（UI 线程 await QueuedTask，禁止 UI 线程
`.Result` 阻塞）；Pro API 触碰仍全部在其 QueuedTask.Run 闭包内（D3 纪律不变）；
两工具连做全程 Pro UI 不冻结。

### Scenario: 构建打包部署链路不变量（离线）

验收：A4

打包链路沿用 C9：`dotnet build` → `scripts/package_pro_addin.py`（zip 根
`Config.daml` + `Install/*.dll`）→ 部署 `[MyDocuments]\ArcGIS\AddIns\ArcGISPro`
且扩展名固定 `GeoCodePro-MCP.esriAddInX`。既有 zip 布局单测不回退；`gis/preflight.py`
零改动（`check_pro_addin` 的 installed/deployed/listening 三探测语义不变，既有
单测不回退）。deploy 后需重启 Pro 使新版本 add-in 生效（AssemblyCache 更新）。
add-in 标识版本 1.0.0 → 1.1.0（csproj `Version` 与 DAML `AddInInfo.version` 同步），
`AddInInfo id="GeoCodePro-MCP"` 不变。

### Scenario: 离线回归警戒线（离线）

验收：A1

`PYTHONPATH=. python -m unittest discover -s tests/unit` 与
`python -m unittest tests.unit.test_spec_basics` 两条入口全绿；基线 223 用例不回退
（本 change 在 test_pro_addin.py 增加 DAML/开面板入口静态检查若干条，总数只增）；
4 个既有 skip 保持 skip 集不变；`PROCESSING_VERSION` 仍为 3，金指纹
`b91c09c9c6451c16` 断言用例不回退。

### Scenario: Pro 会话取证纪律（需 Pro 会话）

验收：A5

部署后启动 Pro 3.7，用 #28 UIA 模式（`SelectionItemPattern` / `InvokePattern` +
Alt+Q 命令搜索）取证：Alt+Q 命令搜索 "GeoCode" 能找到「打开状态面板」入口并激活；
面板窗口可见、可停靠（拖到侧边停靠态不消失）；面板取消停靠后再停靠仍正常。
截图按 `物理 = 逻辑 / DPI缩放`（本机 1.5）换算裁剪，只读 ≤800px JPEG；临时件
一律写 `$TEMP`（#27：Pro 会话取证与 verify/archive 阶段禁写仓库，含 gitignored
的 `logs/`）。

### Scenario: 本地件差异清单与改动面白名单（D9 惯例）

验收：A10

改动面白名单：`git diff main`（worktree）范围只允许 `Pro/**`、
`scripts/package_pro_addin.py`（仅打包条目确需调整时）、
`tests/unit/test_pro_addin.py`、`docs/comet/changes/c11-dockpane/**`（及 Runtime
托管的 .gitignore 段位置调整）；`gis/**`、`geocode.json` 零 diff 逐字核实。

`docs/README.md` 为本仓 gitignored 本地文档，按 C10 D9 惯例不在本 change 工作区
改写；交付「待执行差异清单」（现状 / 改为 / 依据 / 回退），归档轮用户确认后于
主工作区落地：§9.1 台账加 C11 行、§9.2 补 C11 交付行、§9.4 dockpane 段
「另行立项」改「已交付（c11-dockpane）」并简述面板能力、line375「下一步」行加
C11 交付注记、§8.6 踩坑新增（Build 中发现的新坑，如 UI 线程 await / XAML 编译 /
dockpane DAML 相关事实，编号 #30 起）。geocode.json 零改动（无差异清单条目）。
