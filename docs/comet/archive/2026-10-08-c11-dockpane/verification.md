---
generated_from_state_version: 24
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 1
- 迭代: 4
- 验证器尝试次数: 1
- 完成时间: 2026-10-08T13:29:36.309Z
- 摘要: iteration 4（全量修复轮）独立只读复验通过：10/10（A1–A10 全 passed）。离线侧：233 用例（≥223）+ dotted 20 全绿、PV3 金指纹不回退；跨路径 Release 重建逐字节一致（f750e624...）并与 zip/部署件字节绑定（zip=部署件=55f600b7...），Debug 仍产 PDB、XAML→BAML 键保留；gis/**、geocode.json、scripts/ 零 diff，PROCESSING_VERSION=3；A10 清单 8 处「现状」与主工作区 README 对应行逐字节 8/8 MATCH、无省略号、四列齐备且覆盖五处。活会话（Pro 3.7，加载沙箱 aprx，AssemblyCache DLL=本候选）：A5 Alt+Q 搜 'GeoCode' 重试后命中 'GeoCode 状态面板'(GeoCodePro_ShowDockpane) 并激活为右侧停靠面板；A6 两条执行路径计数语义在默认 6530 与覆写 6531 上均成立（面板按钮：工具执行 +1、HTTP 不变；HTTP：请求 +1 且工具执行 +1；零 UI 交互 965ms 自动刷新）；A7 占用→未监听+LastError→释放→重试监听→netstat/curl/preflight 全恢复；A8 面板 bbox 与 HTTP 同 extent 4dp 一致 + 剪贴板合法 GeoJSON Polygon；A9 tif/gpkg 入 TOC、默认 data/deliver 下 PNG 真实落盘（1302927 B，PNG magic）。只读纪律：worktree 零写入，git status --short 与本轮开始逐字一致。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1 离线回归不回退：`PYTHONPATH=. python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics`（仓库根、geo env）两条入口全绿；总用例数 ≥ 223 且新增用例计入（test_pro_addin.py 增 DAML/打包静态检查若干条）；skip 集 = 既有 4 条不变；金指纹断言用例绿（PV3 = b91c09c9c6451c16）。 | 独立实跑（geo env, PYTHONPATH=.）：discover -s tests/unit = Ran 233 OK（>=223，iter3 为 232，+1 计数语义断言，计入）；dotted tests.unit.test_spec_basics = Ran 20 OK；runtime skips=0（zip 在，既有 4 条 skipUnless 门控用例集合未变）；PV3 金指纹 b91c09c9c6451c16 断言绿。证据 %TEMP%\c11-verifier\a1r4-discover.txt / a1r4-dotted.txt / a1r4-discover-v.txt。 |
| A2 | passed | brief.md | A2 DAML dockpane 声明与入口：`Pro/Config.daml` 可解析 XML；`GeoCodePro_Module` 含 dockPane 声明（id `GeoCodePro_Dockpane`、className 指向新 DockPane 类、caption 非空）；GeoCode 选项卡新增「打开状态面板」按钮声明且激活该 dockpane id；既有 `GeoCodePro_ServerStatus` 按钮、tabs/groups 结构与 C9 语义一致（零挪动）。判据 = 离线单测新增断言全绿。 | 独立解析 Pro/Config.daml：XML 可解析；insertModule GeoCodePro_Module 含 dockPane id=GeoCodePro_Dockpane、className=GeoCodePro.GeoCodeDockpaneViewModel、caption='GeoCode Status'（非空）、content className=GeoCodePro.GeoCodeDockpaneView；GeoCode 选项卡 group GeoCodePro_Group 新增 button refID=GeoCodePro_ShowDockpane（caption='GeoCode 状态面板'，class ShowDockpaneButton，OnClick→DockPaneManager.Find('GeoCodePro_Dockpane').Activate()）；既有 GeoCodePro_ServerStatus 与 tabs/groups 结构零挪动（diff 仅追加）；DockpaneDamlTest/StatusSourceTest 全绿。证据 a2r4-daml.json / a4r4-proaddin.txt。 |
| A3 | passed | brief.md | A3 构建与打包：`dotnet build Pro/GeoCodePro.csproj -c Release` 零错误；新增 XAML 走 Page 构建动作编译进程序集；`python scripts/package_pro_addin.py build` 零错误退出并产出 `Pro/GeoCodePro.addin.zip`；既有 zip 布局断言（根 Config.daml + Install/*.dll）不回退。 | 自跑双路 Release 重建（两个不同路径长度临时副本，其一 git init+commit、另一无 .git）：DLL sha256 均为 f750e6245e64b3be084dff3d992a9ee12b6673fa80c3230ba1365288ecf2ce42（=期望）；Release bin 无 pdb，Debug 构建仍产 GeoCodePro.pdb（符号按配置拆分成立）；ResourceReader 读 obj/.../GeoCodePro.g.resources 含键 geocodedockpaneview.baml（DebugType=none 未破坏 XAML→BAML）；zip Pro/GeoCodePro.addin.zip=55f600b7... 且与部署件 .esriAddInX 逐字节相同(cmp IDENTICAL)，zip 内 Install/GeoCodePro.dll=f750e624...；Runtime 绑定检查 offline-build-deploy(package_pro_addin.py all) exit0，zip 布局 根 Config.daml + Install/*.dll 不回退。证据 a3r4-build.log / a3r4-resources.txt。 |
| A4 | passed | brief.md | A4 preflight 与部署链路不回退：`gis/preflight.py` 零 diff；test_pro_addin.py 既有 10 条（preflight mock、端口覆盖、zip 布局、DAML 基础）全绿；部署链路不变量（.esriAddInX 扩展名、部署目录）在脚本与测试中不变。 | git diff main -- gis/ 与 gis/preflight.py、scripts/ 均为 0 行（脚本/测试层不变量未动）；tests.unit.test_pro_addin = Ran 20 OK：main 的 10 条同名用例全部保留（comm 无 REMOVED），新增 10 条（DAML/打包/计数语义静态断言）；部署 .esriAddInX 扩展名与 AddIns 目录不变量在零 diff 脚本与既有用例中不变。证据 a4r4-proaddin.txt / a4r4-main-names.txt / a4r4-now-names.txt。 |
| A5 | passed | brief.md | A5 dockpane 可见可停靠（需 Pro 会话）：deploy 后启动 Pro 3.7，Alt+Q 命令搜索 "GeoCode" 能找到「打开状态面板」入口并激活；面板窗口出现且可停靠（拖到侧边不消失，取消停靠后仍正常）；证据 = UIA 转录 + 截图（≤800px JPEG，$TEMP）。 | 活会话（Pro 3.7，session 1，加载沙箱 aprx）：Alt+Q 搜 'GeoCode' —— 第 1 次查询 items=9 未命中（最近/建议分组），按 #29 重试后（第 2 次查询，session3 为第 2 次）命中 MenuItem N='GeoCode 状态面板' Aid='GeoCodePro_ShowDockpane'；InvokePattern.Invoke() → 面板出现 offscreen=False，父节点 ControlType.TabItem N='GeoCode Status' Aid='GeoCodePro_DockpaneTab'（停靠在右侧 dock，可停靠/可激活）；截图 a5r4-panel_small.jpg（800x450）显示右侧 'GeoCode Status' 面板与状态/工具/最近结果三区。证据 a5r4-try.txt / a7r4-open.txt。 |
| A6 | passed | brief.md | A6 服务状态区与真实状态一致（需 Pro 会话）：面板运行中态显示端口 = 6530（或 GEOCODE_PRO_PORT 覆盖值）与请求/错误计数，且计数随工具执行增长；与 `curl http://127.0.0.1:6530/` 及 `probe_all()` 的 pro_addin listening:true 交叉一致。 | 本轮新增判据两条路径分别取证（默认 6530 与覆写 6531）：面板点 AoiButton → 工具执行 +1 且 HTTP 请求不变（6530: HTTP 0 / tool 1；6531: HTTP 0 / tool 1）；GET / → HTTP +1、工具不变（6530:1/1；6531:1/1）；POST /mcp tools/call → HTTP +1 且工具执行 +1（6530:2/2；6531:2/2）；零 UI 交互自动刷新：3×GET 后 UI 空转读取 HTTP 2→5，且同会话计时测试 T0=HTTP5 → 发一个请求 → 965 ms 后 DetailText 变 HTTP6（1s DispatcherTimer）；端口显示 6531/6530 随 GEOCODE_PRO_PORT 变化（不写死）；与 curl http://127.0.0.1:6530/ (v1.1.0) 及 preflight.probe_all() pro_addin listening:true port=6530 deployed:true 交叉一致。证据 a6r4-baseline/panel-aoi/after-get/after-call/after-3get/timer/6531-* 、a6r4-probe-all.json。 |
| A7 | passed | brief.md | A7 端口占用态与恢复（需 Pro 会话）：注入端口占用后面板显示可读中文「未监听 + 端口被占用（LastError 摘要）」；释放端口后点「重试监听」回到运行中态（6530 重新监听、preflight listening 恢复 true）；注入/释放转录留档 $TEMP。 | 活会话：注入原始占用者 PID 28768 持 127.0.0.1:6530（netstat LISTENING 28768）→ 启动 Pro → 面板 STATUS '6530 服务：未监听'，DETAIL 'MCP 端点未在监听。最近错误：HttpListenerException: 另一个程序正在使用此文件，进程无法访问。'（可读中文 + LastError 摘要），RetryListenButton 可见（N='重试监听'）；释放占用者 → 6530 FREE → 点「重试监听」→ STATUS '6530 服务：正常'、DETAIL 端口 6530、netstat 6530 LISTENING、curl / → v1.1.0、preflight._port_listening(6530)=True 且 probe_all pro_addin listening:true。证据 a7r4-status-error.txt / a7r4-buttons.txt / a7r4-netstat-occupied.txt / a7r4-retry.txt / a7r4-netstat-listening.txt / a7r4-preflight.txt / a7r4-error_small.jpg。 |
| A8 | passed | brief.md | A8 一键取 AOI 与最近结果（需 Pro 会话）：面板点 pro_get_view_aoi 后最近结果区显示成功 + bbox 摘要，坐标与 HTTP 接口同参数返回一致（双证据交叉）；「复制 GeoJSON」后剪贴板内容为可被 python json 解析的合法 GeoJSON Polygon。 | 活会话同一视图兴趣区一对：面板点 pro_get_view_aoi → RESULT '[21:19:38] bbox=[116.2986, 39.9601, 116.3812, 40.0083] · ring 顶点数 5'；紧接着 HTTP tools/call pro_get_view_aoi 返回 x[116.298551..116.381212] y[39.960129..40.008311]（同参数、同 extent，4 位小数完全一致）；点「复制 GeoJSON」→ 剪贴板文本可被 json 解析、type=Polygon、rings=1、verts=5、首尾点闭合、bbox 与上一致。证据 a8r4-panel-aoi.txt / a8r4-http-aoi2.txt / a8r4-panel-copy.txt / a8r4-clipboard-check.txt / a8r4-clipboard.json。 |
| A9 | passed | brief.md | A9 add_layer / export_view 入口可用（需 Pro 会话）：面板走 pro_add_layer 加本地 .tif/.gpkg——结果区显示图层名/计数、TOC 出现该图层（截图）；面板走 pro_export_view 导出视图 PNG——结果区显示输出路径 + exported 标志、文件真实落盘（磁盘 stat）；走默认路径时落 data/deliver/ 惯例；两工具连做 Pro UI 不冻结（UI 线程 await 纪律）。 | 活会话：面板 pro_add_layer sample2.gpkg → '图层 main.pts · 当前图层数 2 · added=True'；sample10.tif → '图层 sample10.tif · 当前图层数 3 · added=True'；TOC UIA 实读含 mappingTOCItem_FeatureLayer_main.pts 与 mappingTOCItem_RasterLayer_sample10.tif（截图 a9r4-toc_small.jpg 800x450）；面板 pro_export_view（ExportPathBox 留空=默认）→ 'PNG 已导出：...\repo\data\deliver\pro_view.20261008_212144.png · exported=True'，磁盘 stat 1302927 B、mtime 21:21、magic 89 50 4E 47（真实 PNG 落盘，默认落 data/deliver/）；两工具连做后 UI 仍响应后续 UIA 读取（无冻结）。证据 a9r4-addlayer-gpkg.txt / a9r4-addlayer-tif.txt / a9r4-toc.txt / a9r4-export.txt。 |
| A10 | passed | brief.md | A10 改动面与文档差异清单（离线收尾核查）：`git diff main` 路径白名单 = `Pro/**`、`scripts/package_pro_addin.py`（仅确需时）、`tests/unit/test_pro_addin.py`、`docs/comet/changes/c11-dockpane/**`、Runtime 托管的 .gitignore 段位置调整；`gis/**`、`geocode.json`、PROCESSING_VERSION 零 diff 逐字核实；docs/README.md 待执行差异清单四列齐备（现状/改为/依据/回退，覆盖 §9.1/§9.2/§9.4/§line375/§8.6 五处）且在归档产物中。 | git diff main 路径全部在白名单：.gitignore（Comet 段纯位置迁移，6 行内容完全一致）+ Pro/Config.daml、GeoCodePro.csproj、McpServerHost.cs、ProTools.cs + tests/unit/test_pro_addin.py + 未跟踪新文件 Pro/*（dockpane 5 件）与 docs/comet/changes/**；gis/**、geocode.json 零 diff；PROCESSING_VERSION=3；git status --short 无 logs/ 条目。四列清单 docs/comet/changes/c11-dockpane/local-changes.md：8 个「现状」引用块与主工作区 D:\DEV\geocode\docs\README.md 的 L375/L379/L396/L398/L433/L437/L542/L554 逐字节比较 8/8 MATCH（无省略号；3 处 '…' 均在 回退/标题/配方，非现状值与 现状 单元格）；覆盖 §9.1/§9.2/§9.4/line375/§8.6 五处，现状/改为/依据/回退四列齐备；文件位于随 change 归档的 docs/comet/changes/ 内。证据 a10r4_compare.py / a6r4-probe-all.json。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| unit-discover | -m unittest discover -s tests/unit | . | passed | 0 | 12065 ms |
| unit-dotted-path | -m unittest tests.unit.test_spec_basics | . | passed | 0 | 237 ms |
| offline-build-deploy | scripts/package_pro_addin.py all | . | passed | 0 | 1854 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- offline-unit-discover: passed — geo env：discover -s tests/unit → Ran 233 tests, OK（iteration 3 为 232，+1 计数语义断言）
- offline-unit-dotted-path: passed — geo env：-m unittest tests.unit.test_spec_basics → Ran 20 tests, OK
- cross-path-reproducible-release-build: passed — Release：工作区 + 两个不同路径长度副本（其一有 .git）+ zip 内 DLL → 同一 sha256 f750e624…；Debug：仍产出 GeoCodePro.pdb
- build-package-deploy: passed — package_pro_addin.py all：build 成功 / zip 产出 / 部署 .esriAddInX；zip = 部署件 = 55f600b7…，zip 内 DLL = f750e624…
- verbatim-quote-selfcheck: passed — 脚本比对清单 8 处「现状」引用块 vs 主工作区 README 对应行 → 8/8 逐字节 MATCH
- whitelist-and-zero-diff: passed — git diff main 仅白名单内 6 个跟踪文件 + 5 个新增 Pro 文件 + change 目录；gis/、geocode.json、scripts/ 零 diff；PV=3
- pro-session-a5-a9: not-run — A5–A9 的活体 Pro 会话取证由 Verify 阶段的独立 Verifier 执行（#28 UIA 纪律；建议 A6 覆盖默认 6530 与覆写端口两条路径，并按 #29 对 Alt+Q 查询重试一次再判定）
- 已知限制: A5–A9 五项验收需 Pro 3.7 活会话 UIA 取证，由 Verify 阶段执行；package_pro_addin.py all 已把本候选（zip=部署件=55f600b7…）部署为 .esriAddInX，Pro 需以新进程加载。
- 已知限制: 测试必须在 conda env geo 下运行：系统 Python312 缺 pyproj，discover 会 40 error（环境差异，非回归）。
- 已知限制: 面板 VM 契约依赖 Esri 框架运行时行为（DataContext 绑定 / DockPaneManager.Find 按需创建单例），静态测试只能覆盖 DAML 结构、源码字段、计时器与构建属性，不能覆盖实际刷新时序与停靠行为。
- 已知限制: gis/preflight.py::_port_listening 是 TCP-connect 探针，在任意原始监听者占用端口时也报 true；受 spec 第 11 行「gis/ 零 diff」约束 C11 不改，记录为 §8.6 #30，占用态判定改用 netstat -ano；端点级探测的代码改进另立 change C12（改 gis/** 属需求变化，须走 C12 自身的 Shape 确认）。
- 已知限制: Alt+Q 命令搜索的结果面板存在渲染竞态（首次可能只显示「最近/建议」分组）：caption 索引本身正确（两轮独立验收均已命中），取证按 §8.6 #29 重试一次再判定。
- 已知限制: 面板「工具执行」计数（ResultRegistry.ToolCalls）含 __panel_retry_listen__ 这类面板内部登记项；「HTTP 请求」计数（McpServerHost.Requests）含义不变，两者分列展示、互不冒充。
- 已知限制: DebugType 仅在 Release 关符号；Debug/其他配置产出 portable 符号，故带符号构建不保证跨路径逐字节一致（交付件为 Release，不受影响）。

## 阻塞项

_无。_

## 风险与跳过的工作

- 踩坑 #29 复现：Alt+Q 命令搜索列表时序敏感——第 1 次查询只返回 9 项「最近/建议」无目标项，重试（session1 第 2 次、session2 第 3 次）才出现；caption 索引本身正确（'GeoCode 状态面板' 命中 Aid=GeoCodePro_ShowDockpane），纯取证竞态，非产品缺陷。
- gis/preflight.py::_port_listening 判别力（#30）：该探针是 TCP connect，原始占用者占 6530 时同样返回 true，不能单独证明是本 add-in 端点；C11 受 spec 第 11 行 gis/ 零 diff 红线约束不修，端点级探测另立 C12——A7 已改用 netstat -ano + 面板 LastError 判定。
- docs/comet/changes/c11-dockpane/local-changes.md 在 worktree 中当前为未跟踪（?? 条目），符合 Comet 归档前状态（change 目录随归档入库）；非缺陷，仅记录状态。
- A1 文案「skip 集 = 既有 4 条」与实际 runtime skips=0 的口径差异沿袭前几轮：4 条指 zip 存在时被 skipUnless 门控而实际执行的用例集合（PackageStructure 3 + DamlValidity 1），集合本轮未变。
- 本次独立 Verifier 运行在 session 0，Pro/UIA 需经计划任务（LogonType Interactive）在交互 session 1 驱动；Pro 与 add-in 均在 session 1 实测，AssemblyCache 内被加载的 GeoCodePro.dll sha256=f750e624... 与本候选 Release DLL 一致（活体绑定已核实）。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 1 | execution-error | — | 任务丢失：已派发的 Verifier 未回报启动回执（verifierStartup.confirmation=unconfirmed，注册于 2026-10-08T04:14:39.809Z），宿主会话在 2026-10-08T05:02:10Z 终止，托管该 Verifier 的外部 delegate 进程随父进程一并结束。核实现场：①平台侧无该任务（subagent status 查无、async-subagent-runs 为空）；②承载 Verifier 的临时会话 del_muz2ivu7_kdkl（acp-delegate）最后活动 2026-10-08T05:02:23Z，其 .out 为 0 字节、未产出任何结果，final-result.json 仍为全 blocked 骨架；③同一候选此前另两次 delegate 尝试（12:18-12:44 / 12:52-12:57 本地）同样在父进程终止时结束。已产出证据（A1/A2/A3/A4/A10 离线判定材料、A5/A7 部分 UIA 转录与截图、候选 sha256 与部署件比对）保留在 %TEMP%\c11-verifier\，未提交为验收结论。候选实现与已完成的 Runtime 检查均保留不变，本次仅为重新派发独立 Verifier；执行方式变化：改用平台原生 subagent 能力承载，不再依赖宿主的 acp-delegate 子进程。 | 2026-10-08T09:11:10.510Z |
| 1 | 1 | 2 | fail | A5, A6 | Independent offline+Pro-session verification of candidate ed328aba. Offline: A1 (228/20 OK, PV=3, fingerprint green), A2 (DAML structure), A3 (isolated-copy build exit0 + BAML 'geocodedockpaneview.baml' in dll), A4 (preflight/package zero diff, deploy invariants), A10 (whitelist + gis/geocode.json zero diff; worktree end-state identical to initial) all pass. Pro session (deployed addInX sha == candidate zip 32fe6ba0): A7 (own occupier -> readable 未监听+LastError, release -> 重试监听 -> 6530 rebinds + preflight listening), A8 (panel AOI == HTTP coords; clipboard valid GeoJSON Polygon), A9 (tif/gpkg add_layer -> result+TOC; export_view default path PNG on disk; UI responsive) pass. A5 fails the letter: panel is visible/docked and the command-search entry activates, but the required query 'GeoCode' does not surface it (only 'Status Panel' does). A6 fails: no auto-refresh timer (4 curls + 12s left the displayed count at 0) and the port is a hardcoded 6530 literal (override not shown). Overall verdict fail; worktree left byte-identical to the initial snapshot. | 2026-10-08T10:15:08.586Z |
| 1 | 2 | 1 | pass | — | 迭代2 复验：候选中新 caption 'GeoCode 状态面板'、host.Port 动态端口、1s DispatcherTimer 自动刷新均已实测生效。A1–A10 全部通过。关键活体证据：Alt+Q 搜 GeoCode 命中开面板入口并激活停靠面板(A5)；面板可见期零点击计数 1→6 且 6531 覆写会话显示覆写端口(A6)；6530 占用→'未监听+HttpListenerException'→释放后重试监听恢复(A7)；面板 AOI bbox 与 HTTP 一致、剪贴板为合法 GeoJSON Polygon(A8)；面板加 gpkg 入 TOC、默认导出落 data/deliver/ 且磁盘落盘(A9)。离线 231 用例双入口全绿、金指纹 PV3 不回退、gis/**+geocode.json 零 diff(A1/A4/A10)。git status 与开始时一致，未在 worktree 写入。 | 2026-10-08T11:20:48.773Z |
| 1 | 2 | 1 | recovery | — | 用户裁决：先修复风险再接受结果。按独立验收的 5 条风险分处置——(1) A3 跨路径重建可复现性未印证：本轮回 Build，csproj 增加确定化构建（Deterministic + PathMap 归一化源码/输出路径），并以「换路径双次重建 sha256 一致」自证；(2) A10 清单载体为 gitignored logs/acceptance/、不在 git 归档面：迁移到 A10 白名单内的 git 跟踪路径 docs/comet/changes/c11-dockpane/local-changes.md，随归档成为归档产物；(3) A1 skip 口径精确化（zip 已构建时 skipUnless 全部执行、运行期 skip=0，4 条为装饰器计数），不改判据；(5) A6(b) 默认 6530 路径列入下轮复验项；(4) A7 preflight._port_listening 判别力受 spec 第 11 行 gis/ 零 diff 红线约束，本 change 不改代码，仅记录已知局限与处置流程（占用态判定用 netstat -ano），代码改进另立 change。确认需求范围不变，只改实现。 | 2026-10-08T11:26:41.396Z |
| 1 | 3 | 1 | pass | — | Independent iteration-3 verification of candidate 77c76d1d on the rebuilt artifact (deployed sha == zip sha aaaf1d3b…). A1–A4,A10 offline re-run/re-derived; A3 cross-path rebuild reproduced sha 0a9a9e55… from two different temp paths and BAML presence re-confirmed after DebugType=none; A5–A9 fresh live Pro 3.7 sessions (default 6530, occupied-then-retry, GEOCODE_PRO_PORT=6531) all pass. No worktree writes; git status identical to start. | 2026-10-08T12:59:46.386Z |
| 1 | 3 | 1 | recovery | — | 用户裁决：全量修复（不做信息级遗留）。按 iteration 3 独立验收的 6 条风险逐条闭合，全部落在本 change 白名单内（Pro/** + tests/ + change 目录），不动 gis/**：①local-changes.md 的「现状」单元格去掉省略号、改为主工作区 README 逐字全文（line375/§9.1 末行/§9.2 C10 行/执行顺序行/§9.4 标题与 dockpane 段/§8.6 标题与 #28 行）；②A6 计数语义：面板按钮执行工具不增 HTTP 计数的口径缺口——在 ResultRegistry.Record（两路径唯一汇合点）加工具执行计数器并让面板状态文本同时显式展示「HTTP 请求 n 次（失败 m）/ 工具执行 k 次」，使「计数随工具执行增长」对两条路径都成立；③可复现性与符号共存：csproj 拆配置——Release 保持 DebugType=none（交付件跨路径逐字节可复现），非 Release 用 portable 符号供本地调试；④Alt+Q 命令搜索列表时序敏感（首次可能只显示最近/建议区块）——写入踩坑 #29 结论并固化「重试一次再判定」的取证流程；⑤A7 preflight._port_listening 判别力：C11 受 spec 第 11 行 gis/ 零 diff 红线约束，代码改进另立 change C12（不改 C11 需求范围），C11 内把占用态判定固化为 netstat -ano 并记为 #30；⑥跨路径复现的独立覆盖率注记：由下轮 Verifier 自行决定重跑路数，无需实现改动。确认需求范围不变，只改实现与文档载体。 | 2026-10-08T13:02:16.354Z |
| 1 | 4 | 1 | pass | — | iteration 4（全量修复轮）独立只读复验通过：10/10（A1–A10 全 passed）。离线侧：233 用例（≥223）+ dotted 20 全绿、PV3 金指纹不回退；跨路径 Release 重建逐字节一致（f750e624...）并与 zip/部署件字节绑定（zip=部署件=55f600b7...），Debug 仍产 PDB、XAML→BAML 键保留；gis/**、geocode.json、scripts/ 零 diff，PROCESSING_VERSION=3；A10 清单 8 处「现状」与主工作区 README 对应行逐字节 8/8 MATCH、无省略号、四列齐备且覆盖五处。活会话（Pro 3.7，加载沙箱 aprx，AssemblyCache DLL=本候选）：A5 Alt+Q 搜 'GeoCode' 重试后命中 'GeoCode 状态面板'(GeoCodePro_ShowDockpane) 并激活为右侧停靠面板；A6 两条执行路径计数语义在默认 6530 与覆写 6531 上均成立（面板按钮：工具执行 +1、HTTP 不变；HTTP：请求 +1 且工具执行 +1；零 UI 交互 965ms 自动刷新）；A7 占用→未监听+LastError→释放→重试监听→netstat/curl/preflight 全恢复；A8 面板 bbox 与 HTTP 同 extent 4dp 一致 + 剪贴板合法 GeoJSON Polygon；A9 tif/gpkg 入 TOC、默认 data/deliver 下 PNG 真实落盘（1302927 B，PNG magic）。只读纪律：worktree 零写入，git status --short 与本轮开始逐字一致。 | 2026-10-08T13:29:36.309Z |



## 结论

iteration 4（全量修复轮）独立只读复验通过：10/10（A1–A10 全 passed）。离线侧：233 用例（≥223）+ dotted 20 全绿、PV3 金指纹不回退；跨路径 Release 重建逐字节一致（f750e624...）并与 zip/部署件字节绑定（zip=部署件=55f600b7...），Debug 仍产 PDB、XAML→BAML 键保留；gis/**、geocode.json、scripts/ 零 diff，PROCESSING_VERSION=3；A10 清单 8 处「现状」与主工作区 README 对应行逐字节 8/8 MATCH、无省略号、四列齐备且覆盖五处。活会话（Pro 3.7，加载沙箱 aprx，AssemblyCache DLL=本候选）：A5 Alt+Q 搜 'GeoCode' 重试后命中 'GeoCode 状态面板'(GeoCodePro_ShowDockpane) 并激活为右侧停靠面板；A6 两条执行路径计数语义在默认 6530 与覆写 6531 上均成立（面板按钮：工具执行 +1、HTTP 不变；HTTP：请求 +1 且工具执行 +1；零 UI 交互 965ms 自动刷新）；A7 占用→未监听+LastError→释放→重试监听→netstat/curl/preflight 全恢复；A8 面板 bbox 与 HTTP 同 extent 4dp 一致 + 剪贴板合法 GeoJSON Polygon；A9 tif/gpkg 入 TOC、默认 data/deliver 下 PNG 真实落盘（1302927 B，PNG magic）。只读纪律：worktree 零写入，git status --short 与本轮开始逐字一致。
