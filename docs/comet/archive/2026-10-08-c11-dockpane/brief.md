# 目标

在 C9 已交付的 add-in（`Pro/` 工程、6530 HTTP MCP server、三工具、打包部署链路）之上补
一块 Pro Dockpane 状态面板：不看 Python 会话、不点弹窗就能看到 6530 服务是否健康，并
能从正开着的 Pro 会话一键执行三个已交付工具（`pro_get_view_aoi` / `pro_add_layer` /
`pro_export_view`）、立即看到最近一次结果——补齐 README §9.4「headless 做不到的三件事」
中 GUI 状态面板一件的空白，兑现 C9 台账注记「dockpane 拆出另行立项」的遗留项。

零引擎层改动：`gis/` 零 diff、`PROCESSING_VERSION = 3` 不 bump、金指纹
`b91c09c9c6451c16` 不回退、geocode.json 零改动、6530 工具集（tools/list）不变。

# 范围

## Source coverage

来源（按用户指定，2026-10-08 全部读毕）：
- README §9.4 dockpane 段（2026-10-08 C10 落地的立项要点）；
- README §9.4 同节其余内容（P1b 定位、headless 三件事）；
- README §5.4 端口表；
- C9 归档 `docs/comet/archive/2026-10-08-p1b-arcgis-addin/`（brief/spec/verification）；
- C10 归档 `docs/comet/archive/2026-10-08-c10-review-patches/`（brief/spec/verification）。

覆盖边界 = 上述五份材料的全部需求性内容；历史 change 的过程性叙述不重实现（归档制品只
作为契约与流程纪律来源）。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：README §9.4「dockpane（已拆出另行立项）」段（line437 附近，2026-10-08 C10 落地） | complete | 范围要点 = add-in 内 Pro Dockpane 面板，进程内展示 6530 服务状态与三工具（pro_get_view_aoi / pro_add_layer / pro_export_view）入口与最近结果；前提 = 复用 C9 已交付 add-in 骨架、打包部署脚本（.esriAddInX）与 Pro 会话取证流程；C10 只落台账、不在 C10 实现 | specs/dockpane/spec.md 的 DAML dockpane 声明 / 面板类与视图 / 服务状态区与端口占用态 / 工具入口与最近结果区 场景 | A5–A9 | covered | 本 change 的核心需求原文 |
| S2：README §9.4 P1b 定位与「headless 做不到的三件事」（line435 附近） | complete | 三件事 = 操作正开着的地图、GUI 状态面板（dockpane）、从当前视图取 AOI；C9 已覆盖后两件的工具面，本项收口 GUI 面板一件 | specs/dockpane/spec.md 的本地件差异清单场景（line435 措辞随交付更新） | A5 | covered | 背景定位；交付后措辞更新走本地件差异清单 |
| S3：README §5.4 端口表 6530 行 | complete | 6530 = add-in MCP HTTP 现用（C9 交付），`GEOCODE_PRO_PORT` 可覆盖；覆盖值需在面板显示（面板显示真实生效端口，不是常量 6530） | specs/dockpane/spec.md 的服务状态区与端口占用态场景 | A6、A7 | covered | 端口语义延续 C9 D2，零改动，展示层如实反映 |
| S4：C9 归档 brief/spec/verification（add-in 既有契约） | complete | 手写 csproj（net10.0-windows、仅引 Pro bin DLL、无 NuGet/VSIX/Esri 打包 target）；zip 布局 = 根 Config.daml + Install/*.dll；部署 = MyDocuments\ArcGIS\AddIns\ArcGISPro + .esriAddInX；QueuedTask.Run 硬纪律；三工具语义/schema 不变（tools/list 不变）；preflight check_pro_addin 三探测；UI 风格（DAML caption 英文 + 消息中文） | specs/dockpane/spec.md 的构建打包部署链路不变量 / 工具入口与最近结果区场景 + 本 brief 的 Constraints and invariants | A3、A4、A8、A9、A10 | covered | C9 契约全部继承为不变量，只增不改 |
| S5：C10 归档 brief/spec/verification（流程纪律与订正事实） | complete | 基线 223 用例（4 skip）全绿基线；tests/unit/_helpers.py GOLDEN_FINGERPRINTS 时代取值（PV3=b91c09c9c6451c16）；#27 verify/archive 禁写仓库（临时件 $TEMP）；D9 docs/README.md 与 geocode.json 不在 change 工作区改写、交付待执行差异清单归档轮主工作区落地；worktree 实现前 --ff-only 同步 main；两条测试入口都要可用 | 本 brief 的 Constraints and invariants + specs/dockpane/spec.md 的离线回归与档案警戒线 / 本地件差异清单场景 | A1、A10 | covered | 流程纪律与基线来源 |
| S6：README §9.2 C9 行注记「dockpane 拆出，另行立项」（line395） | complete | 立项凭证：本 change 是该注记的兑现；交付后该行注记与 §9.1 台账、§9.3 计划表同步更新 | specs/dockpane/spec.md 的本地件差异清单场景 | A10 | covered | 文档面；不动 git 内档案（archive 目录由归档流程产出） |

覆盖状态汇总：6 条来源全部 covered，无 uncovered、无 partially covered，无需替代判断。

## 交付内容（工作分解）

- **W1 DAML 声明与入口**：`Pro/Config.daml` 增 dockPane 声明（id `GeoCodePro_Dockpane`）
  与「打开状态面板」按钮（GeoCode 选项卡第二个按钮，激活该 dockpane）；既有
  `GeoCodePro_Tab`/`GeoCodePro_Group`/`GeoCodePro_ServerStatus` 结构零挪动。
- **W2 面板类与视图**：DockPane 类 + UserControl 视图（XAML Page 编译进程序集）；
  服务状态区（运行中/未监听可读反馈 + 重试监听按钮 + 可见期 UI 线程计时器自动刷新）；
  三工具区（一键 AOI 摘要 + 复制 GeoJSON；add_layer 路径框+浏览对话框+可选子图层框；
  export_view 可选输出路径框留空走默认）；最近结果区（每工具最近一次，时间戳 +
  成败 + 摘要 + 失败错误全文）。
- **W3 执行管线与结果注册表**：`ProTools` 增 async 门面（UI 线程 await、禁 UI 线程
  `.Result`）；HTTP 路径与面板路径统一写线程安全结果注册表，工具执行语义与
  tools/list 完全不变；Pro API 触碰仍全部在 QueuedTask.Run 闭包内。
- **W4 打包链路沿用 + 仅必要调整**：zip 布局不变量不变；如 XAML 构建产物需要
  随包携带时才动 `scripts/package_pro_addin.py`（最小 diff）；版本 1.0.0 → 1.1.0。
- **W5 离线测试**：`tests/unit/test_pro_addin.py` 增加 DAML dockPane/开面板入口
  静态检查与打包布局回归（既有 10 条不回退）。
- **W6 本地件差异清单**：docs/README.md 四处更新 + 可能的 §8.6 新坑，按 D9 惯例
  归档轮主工作区落地。

# Non-goals

- 不做新 MCP 工具、不改三工具语义/入参 schema/tools/list（6530 工具集保持三件）。
- 不做符号修改、CIM renderer 操作（沿 C9 延后判断）。
- 不碰 daemon / jobs / TUI / client / gis/**（6531 与 6530 两 server 独立不变）；
  `PROCESSING_VERSION` 不 bump、不产栅格像素、金指纹不动（红线 3/8）。
- 不在 Pro / add-in 进程加载任何 GEE 栈（红线 7）：不 import ee、不装包进
  `arcgispro-py3`；数据交换走文件。
- 不做面板服务「停止监听」按钮（只给重试启动）；不做结果历史列表（只保留每工具
  最近一次）；不做面板自动弹出（Pro 启动后默认不开面板）。
- 不改部署目标路径、不改 `.esriAddInX` 部署件名；geocode.json 零改动。
- 不写 C# 单测框架；契约证据走离线静态检查 + Pro 会话 UIA 取证（A 组）。
- docs/README.md 不在本 change 工作区改写（D9：差异清单交付）；geocode.json 同。
- 实现期间不加超出 W1–W6 的 UI 花活（无主题定制、无图标美化、无多语言切换）。

# Constraints and invariants

- **红线集合（README §11）**：ee 计算图只在 gis/source.py；网格只由 compute_grid()
  定；像素输出红线（本 change 不触）；PROCESSING_VERSION = 3 不 bump；本 change
  零 gis/ diff；指纹向后兼容；红线 6（验证顺序：离线→部署→Pro 会话逐项实测）；红线 7
  （Pro 侧零 GEE 栈）。
- **D3 线程纪律（硬纪律，加严一条）**：`Pro/` 下所有触碰 Pro API 的方法一律经
  QueuedTask.Run 编组进 Pro UI 线程；后台 HttpListener 线程只做协议解析与 JSON
  组装；**新增**：UI 线程不得 `.Result` 阻塞 QueuedTask（面板按钮一律 await
  async 门面），code review 检查项。
- **打包与部署不变量**：部署件扩展名 `GeoCodePro-MCP.esriAddInX`（#24，Pro 3.7 只认
  带 X）；zip 布局 = 根 Config.daml + Install/*.dll；部署目录
  `[MyDocuments]\ArcGIS\AddIns\ArcGISPro`；deploy 后需重启 Pro 使新版本生效。
- **#27 取证纪律**：Pro 会话取证与 verify/archive 阶段禁写仓库任何位置（含
  gitignored 的 `logs/`）；派发记录、UIA 转录、截图临时件一律写 `$TEMP`。
- **#28 UIA 取证纪律**：`SelectionItemPattern`/`InvokePattern` + Alt+Q 命令搜索
  驱动 Pro UI；截图按 `物理 = 逻辑 / DPI缩放`（本机 1.5）换算裁剪；只读
  ≤800px JPEG。
- **基线警戒线**：223 用例（4 skip）全绿不回退，change 新增用例只增；两条测试入口
  （`PYTHONPATH=. python -m unittest discover -s tests/unit` 与
  `python -m unittest tests.unit.test_spec_basics`）都要可用；PV=3、金指纹
  `b91c09c9c6451c16`（_helpers 时代取向表验证型用例）不回退。
- **D9 本地件纪律**：docs/README.md（gitignored）与 geocode.json（skip-worktree）
  不在 change 工作区改写；差异清单「现状/改为/依据/回退」四列齐备，归档轮用户
  确认后于主工作区落地。
- **D5 许可纪律（沿 C9）**：仅个人学习使用（Pro 学习版授权），不分发。
- **机器前提已核实**：dotnet SDK 10.0.300/10.0.401 在位；Pro 3.7.0.1901（学习版）；
  Pro 会话取证流程 C9/C10 已跑通。

# Decisions

- **D1 面板输入交互（自选，已写入 spec）**：pro_add_layer 用「路径文本框 + 浏览
  对话框（文件过滤 .tif/.tiff/.gpkg）+ 可选子图层名框」；pro_export_view 用可选
  输出路径框（留空 = 默认 data/deliver）。理由：add_layer 需要精确本地路径，
  对话框比手输可靠；export_view 的默认值惯例已存在，留空最常用。
- **D2 重试监听按钮纳入 W2**：端口占用是 README 记录在案的实际故障态；恢复动作
  零 Pro API、代码量极小。理由：A7 场景需要可恢复出口。
- **D3 结果注册表两路径统一**：HTTP 侧与面板侧执行的同名工具共用最近结果存储——
  面板是 6530 进程内镜子，不是第二套实现。理由：状态一致性验收（A6）的直接根据。
- **D4 文案风格沿 C9**：DAML caption 英文（如 "GeoCode Status" / "Open Status
  Panel"），面板内部与错误文案中文（沿 ServerStatusButton 消息风格）。
- **D5 add-in 版本 1.0.0 → 1.1.0**：csproj `Version` 与 DAML `AddInInfo.version`
  同步 bump，标记 C11 交付；`AddInInfo id="GeoCodePro-MCP"` 不变（部署同名覆盖）。
- **D6 docs/README.md 走差异清单（D9 惯例）**：不在本 change 工作区改写，归档轮
  主工作区落地；geocode.json 零改动无条目。

# Acceptance examples

- A1 离线回归不回退：`PYTHONPATH=. python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics`（仓库根、geo env）两条入口全绿；总用例数 ≥ 223 且新增用例计入（test_pro_addin.py 增 DAML/打包静态检查若干条）；skip 集 = 既有 4 条不变；金指纹断言用例绿（PV3 = b91c09c9c6451c16）。
- A2 DAML dockpane 声明与入口：`Pro/Config.daml` 可解析 XML；`GeoCodePro_Module` 含 dockPane 声明（id `GeoCodePro_Dockpane`、className 指向新 DockPane 类、caption 非空）；GeoCode 选项卡新增「打开状态面板」按钮声明且激活该 dockpane id；既有 `GeoCodePro_ServerStatus` 按钮、tabs/groups 结构与 C9 语义一致（零挪动）。判据 = 离线单测新增断言全绿。
- A3 构建与打包：`dotnet build Pro/GeoCodePro.csproj -c Release` 零错误；新增 XAML 走 Page 构建动作编译进程序集；`python scripts/package_pro_addin.py build` 零错误退出并产出 `Pro/GeoCodePro.addin.zip`；既有 zip 布局断言（根 Config.daml + Install/*.dll）不回退。
- A4 preflight 与部署链路不回退：`gis/preflight.py` 零 diff；test_pro_addin.py 既有 10 条（preflight mock、端口覆盖、zip 布局、DAML 基础）全绿；部署链路不变量（.esriAddInX 扩展名、部署目录）在脚本与测试中不变。
- A5 dockpane 可见可停靠（需 Pro 会话）：deploy 后启动 Pro 3.7，Alt+Q 命令搜索 "GeoCode" 能找到「打开状态面板」入口并激活；面板窗口出现且可停靠（拖到侧边不消失，取消停靠后仍正常）；证据 = UIA 转录 + 截图（≤800px JPEG，$TEMP）。
- A6 服务状态区与真实状态一致（需 Pro 会话）：面板运行中态显示端口 = 6530（或 GEOCODE_PRO_PORT 覆盖值）与请求/错误计数，且计数随工具执行增长；与 `curl http://127.0.0.1:6530/` 及 `probe_all()` 的 pro_addin listening:true 交叉一致。
- A7 端口占用态与恢复（需 Pro 会话）：注入端口占用后面板显示可读中文「未监听 + 端口被占用（LastError 摘要）」；释放端口后点「重试监听」回到运行中态（6530 重新监听、preflight listening 恢复 true）；注入/释放转录留档 $TEMP。
- A8 一键取 AOI 与最近结果（需 Pro 会话）：面板点 pro_get_view_aoi 后最近结果区显示成功 + bbox 摘要，坐标与 HTTP 接口同参数返回一致（双证据交叉）；「复制 GeoJSON」后剪贴板内容为可被 python json 解析的合法 GeoJSON Polygon。
- A9 add_layer / export_view 入口可用（需 Pro 会话）：面板走 pro_add_layer 加本地 .tif/.gpkg——结果区显示图层名/计数、TOC 出现该图层（截图）；面板走 pro_export_view 导出视图 PNG——结果区显示输出路径 + exported 标志、文件真实落盘（磁盘 stat）；走默认路径时落 data/deliver/ 惯例；两工具连做 Pro UI 不冻结（UI 线程 await 纪律）。
- A10 改动面与文档差异清单（离线收尾核查）：`git diff main` 路径白名单 = `Pro/**`、`scripts/package_pro_addin.py`（仅确需时）、`tests/unit/test_pro_addin.py`、`docs/comet/changes/c11-dockpane/**`、Runtime 托管的 .gitignore 段位置调整；`gis/**`、`geocode.json`、PROCESSING_VERSION 零 diff 逐字核实；docs/README.md 待执行差异清单四列齐备（现状/改为/依据/回退，覆盖 §9.1/§9.2/§9.4/§line375/§8.6 五处）且在归档产物中。

# Verification expectations

- **顺序（红线 6）**：全部离线项（A1–A4、A10 前半）先行 → Build 自查 → Runtime
  复检 → deploy → Pro 会话项（A5–A9）逐条取证 → 全过后交用户接受。
- **离线复跑**：两条测试入口命令如 Constraints 原文；dotnet build 与 package 脚本
  直接跑（Runtime 侧复跑成本低，走一遍）。
- **Pro 会话取证**：C9/C10 已跑通 UIA 流程（#28）；全部临时件写 `$TEMP`（#27）；
  截图 ≤800px JPEG；HTTP 侧对照用 curl 转录（6530 或覆盖端口）。
- **测试样本**：add_layer/export_view 需要真实数据文件时，用仓库 tests/fixtures
  或 $TEMP 生成的最小样本（.tif 用 gdal 生成 10×10 假数据，gpkg 用 fiona/ogr
  生成 2 要素），不依赖用户数据。
- **收尾（用户偏好）**：全部 accepted 后 merge 进 main → `git push origin main`；
  worktree 清理等用户独立授权。
