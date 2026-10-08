# C11 `c11-dockpane` 本地件待执行差异清单（docs/README.md）+ 风险处置记录

> **载体说明**：本文件位于 `docs/comet/changes/c11-dockpane/`（git 跟踪、A10 白名单内），
> 随 change 归档进入 `docs/comet/archive/**`，因此是**归档产物**而非临时件。
> （早期曾落在 `logs/acceptance/c11-local-changes.md`，但 `logs/*` 被 .gitignore 忽略、不在 git 归档面
> ——独立验收第 2 条风险已修，本文件是**唯一事实源**。）
>
> **D9 说明**：`docs/README.md` 是 gitignored 本地文档，按 D9 不在 change worktree 内改动——
> 第一节只描述**待执行差异**，由归档轮在**主工作区**就地执行。
>
> **四列 = 现状 / 改为 / 依据 / 回退**。覆盖 A10 要求的五处：§9.1、§9.2、§9.4、line375、§8.6。
> **「现状」一律给出逐字全文**（引用块形式，避免表格内 `|` 转义歧义——被引的是 README 表格行本身）；
> 表格「现状」单元格只给行号与锚点，逐字内容见紧随的引用块。

---

## 一、§9.1 进度台账

### 1. line375「下一步」行

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L375**（逐字全文见下） |
| 改为 | 追加 C11 收口：`C11 dockpane 已交付并归档（<提交号归档后回填>）`；口径改为「路线图 **C1–C11 全部交付、清账**」；**删去**「余量仅 dockpane（已拆出另行立项，范围要点见 §9.4）与 worktree/分支残留清理」整句，改为「**无未清余量**（worktree / 分支残留已于归档前核实为空，见 §8.6 #31）」 |
| 依据 | C11 独立验收 10/10（A1–A10，iteration 3）；残留核实实测：`git worktree list`（仅 `main` + 活跃 worktree）、`git branch -vv`（仅 `main` + `comet/c11-dockpane`，C1–C10 的 `comet/*` 均已删除）、`git stash list`（空）、`git worktree prune --dry-run`（无输出）、`.comet/runtime/native/changes/`（空） |
| 回退 | 还原该行原文（含「余量仅 dockpane…与 worktree/分支残留清理」整句） |

现状逐字（L375）：

```text
| **下一步** | ~~C5~~ → **全部交付（2026-10-07）**：C5 批处理导出（D10 改判 toDrive）、C6 emit_array 分块、C7 领域知识接入均已归档合并推送（7038de5 / a03ea98 / 43cfcae）；C4 预设扩展随后并入 main（ce40e45，PV 2→3 落地，金指纹按预注册切换 `b91c09c9c6451c16`）。C8 OSM/Overpass 已交付并归档（`2361082`）；C9 add-in 已交付并归档（`2817da6` / `a76a1f1`，已推送）；C10 审阅补丁已归档（`d091bff`，含本清单要求的 C9 台账收口）——路线图 **C1–C10 全部交付、清账**；余量仅 **dockpane（已拆出另行立项，范围要点见 §9.4）** 与 worktree/分支残留清理 | ✅ |
```

### 2. §9.1 台账表追加一行（在 2026-10-08 C9 归档行之后）

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L379**（§9.1 台账表末行，逐字全文见下） |
| 改为 | 在该行之后追加新行：`\| 2026-10-08 \| C11 \`c11-dockpane\` 完成归档（Comet Native，隔离 worktree）：状态面板 dockpane（DAML dockPane + 开面板按钮 + 状态区 + 三工具入口 + 最近结果）；独立验收 10/10（A5–A9 Pro 会话实测：命令搜索可达、面板停靠、零点击自动刷新、GEOCODE_PRO_PORT 覆写端口显示、端口占用态注入/释放/重试闭环、面板 AOI 与 HTTP 交叉一致、加图层进 TOC、导出 PNG 落盘），离线 233 用例全绿、PV 保持 3、金指纹 \`b91c09c9c6451c16\` 不回退（提交 <回填>）；新增踩坑 #29（命令搜索只索引 caption + 列表时序敏感）/ #30（preflight 端口探针判别力）/ #31（残留已清核实）/ #32（add-in DLL 跨路径重建可复现） \| ✅ \|` |
| 依据 | C11 验收报告与探针实测（`verification.md` + 独立 Verifier 亲跑）；用例数 233 = 232 + 本轮新增 1 条计数语义断言 |
| 回退 | 删除该新行 |

现状逐字（L379）：

```text
| 2026-10-08 | C9 `p1b-arcgis-addin` 完成归档（Comet Native，就地 main 工作区）：add-in + 6530 MCP server + 打包部署脚本 + preflight Pro 探测项；独立验收 8/8（Verifier 在只读沙箱内独立复算 A5 闭环 EPSG:32650 13847×9430、独立解包 zip 核 DAML/布局、独立读 GPKG 要素类、活体探测 6530（GET / initialize / tools-list）并比对 AssemblyCache 内实际被 Pro 加载的 DLL 与候选构建 sha256 相同、补录加载项管理器截图），离线 222 用例全绿、PV 保持 3、金指纹 `b91c09c9c6451c16` 不回退（提交 2817da6 / a76a1f1）；过程新增踩坑 #27（verify 期仓库写入即作废候选）/ #28（Pro 侧 UIA 取证与 DPI 坐标换算） | ✅ |
```

---

## 二、§9.2 Change 台账

### 3. 表末追加 C11 行（在 C10 行之后）

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L396**（§9.2 表末行 = C10 行，逐字全文见下） |
| 改为 | 在该行之后追加：`\| C11 \| c11-dockpane \| ArcGIS Pro 状态面板（dockpane）：6530 服务状态 + 三工具入口 + 最近结果（C9 拆出立项） \| A1–A10 全部取证；A5–A9 为 Pro 活会话实测（命令搜索/停靠、零点击刷新、覆写端口、端口占用态恢复、面板与 HTTP 双证据交叉、TOC 落图层、输出 PNG 落盘） \| ✅ 归档（<回填>） \|` |
| 依据 | C11 brief 的目标/范围与非目标；独立验收 A1–A10 |
| 回退 | 删除该新行 |

现状逐字（L396）：

```text
| C10 | `c10-review-patches` | 审阅补丁（C1–C9 只读审阅后的全量补丁） | 有效来源 11 条 → 验收 A1–A9：tests 金指纹单一事实源与测试入口双通道、归档 Spec 正文与实现一致、fixtures ODbL 归属、本地件清单（README 订正 + geocode.json 镜像池）三类载体分开交付 | ✅ 归档（d091bff） |
```

### 4. 表下「执行顺序」行

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L398**（逐字全文见下） |
| 改为 | 保留原句（历史顺序依据），末尾追加一句：`后续 C9 → C10 → C11 依 §9.2 表序推进，均已于 2026-10-08 归档清账。` |
| 依据 | §9.2 表 C9/C10/C11 三行状态均已为 ✅ 归档；「C9 视 C2 结果决定」属历史决策口径，不回改 |
| 回退 | 删除追加句 |

现状逐字（L398）：

```text
执行顺序：**C1 → C2 → C3 → C4 → C5 → C6（按需）→ C7 / C8**；C9 视 C2 结果决定；C3 / C4 可按研究需要互换。
```

---

## 三、§9.4 P1b 节

### 5. 节标题（C11 交付后不再只属 C9）

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L433**（逐字全文见下） |
| 改为 | `### 9.4 P1b — ArcGIS Pro add-in（change C9 + C11，已交付 2026-10-08）` |
| 依据 | dockpane 由 C11 交付（原属 C9 范围、C9 时拆出另行立项） |
| 回退 | 还原为 `### 9.4 P1b — ArcGIS Pro add-in（change C9，已交付 2026-10-08）` |

现状逐字（L433）：

```text
### 9.4 P1b — ArcGIS Pro add-in（change C9，已交付 2026-10-08）
```

### 6. 「dockpane（已拆出另行立项）」段整体替换

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L437**（逐字全文见下） |
| 改为 | `**dockpane（C11 已交付 2026-10-08）**：add-in 内的 Pro Dockpane 面板（DAML \`dockPane\` id \`GeoCodePro_Dockpane\` + 功能区「打开状态面板」按钮，caption \`GeoCode 状态面板\` 以便 Alt+Q 命令搜索命中）；进程内展示 6530 服务状态与三工具（\`pro_get_view_aoi\` / \`pro_add_layer\` / \`pro_export_view\`）的入口与最近结果。状态区**读 \`McpServerHost.Port\` 实际端口**（不写死 6530，\`GEOCODE_PRO_PORT\` 覆盖后随之变化）、由 **UI 线程 \`DispatcherTimer\`** 在面板可见期间周期刷新（纯 .NET 状态读取、零 Pro API）；计数分列展示 **HTTP 请求 n 次（失败 m）/ 工具执行 k 次**——工具执行计数在 \`ResultRegistry\`（HTTP 与面板两路径的唯一汇合点）累加，故面板按钮执行工具同样计入；三工具按钮一律经 \`ProTools.CallAsync\`（\`QueuedTask.Run\` 编组 + \`ConfigureAwait(true)\` 回 UI 线程），结果与 HTTP 路径同写 \`ResultRegistry\`。**` |
| 依据 | C11 实现（`Pro/GeoCodeDockpaneViewModel.cs` / `GeoCodeDockpaneView.xaml.cs` / `ResultRegistry.cs` / `Config.daml`）+ 独立验收 A5/A6/A8/A9 实测；caption 搜索词、无计时器、端口写死三条已在 C11 内修复并复验；计数语义缺口在 iteration 4 修复 |
| 回退 | 还原该段原文（含「已拆出另行立项」「本项不在 C10 范围内实现」两句） |

现状逐字（L437）：

```text
**dockpane（已拆出另行立项）**：范围要点 = add-in 内的 Pro Dockpane 面板，进程内展示 6530 服务状态与三工具（`pro_get_view_aoi` / `pro_add_layer` / `pro_export_view`）的入口与最近结果；前提 = 可复用 C9 已交付的 add-in 骨架、打包部署脚本（`.esriAddInX`）与 Pro 会话取证流程；**本项不在 C10 范围内实现**（C10 只落台账）。
```

---

## 四、§8.6 踩坑表

### 7. 节标题

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L542**（逐字全文见下） |
| 改为 | `### 8.6 ArcGIS Pro add-in 侧（C9 + C11，2026-10-08）` |
| 依据 | 本轮新增 #29–#32 四条 Pro / 构建侧事实 |
| 回退 | 还原为 `### 8.6 ArcGIS Pro add-in 侧（C9，2026-10-07）` |

现状逐字（L542）：

```text
### 8.6 ArcGIS Pro add-in 侧（C9，2026-10-07）
```

### 8. 表末追加 #29 / #30 / #31 / #32（现状：表末行为 #28）

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` **L554**（§8.6 表末行 = #28 行，逐字全文见下） |
| 改为 | 在该行之后追加四行（内容见下「新增四条」） |
| 依据 | #29：C11 两轮独立验收的搜索实测（`a5-postchars-geocode.txt` / `a5b-sni.txt` / `a5r3-*`）；#30：C11 独立 Verifier 的 A7 交叉观察；#31：本节第 1 条所列五条命令的本机实测；#32：多路重建实测见 §六.3 |
| 回退 | 删除 #29 / #30 / #31 / #32 四行，并还原 §8.6 标题 |

现状逐字（L554）：

```text
| 28 | 用合成鼠标点击驱动 Pro 界面（开 backstage / 切 ribbon tab）**不生效**：tab 不切换、backstage 不打开，只有悬停高亮 | 两点叠加：① `mouse_event` 注入的点击未被 Pro 的 WPF 接收为选中；② **150% DPI** 下 UIA 报的是逻辑坐标（宽 2560），窗口物理宽只有 1707——照 UIA 的 rect 直接点会落到按钮外 | 改用 UI Automation 模式驱动（`TabItem` 走 `SelectionItemPattern.Select()`；命令走 `InvokePattern.Invoke()`），配合 `SendKeys` 的 **Alt+Q 命令搜索**（`esri_core_AddInsTab` = 加载项管理器，`esri_core_OptionsButton` = 选项）。坐标换算：`物理 = 逻辑 / DPI缩放`（本机 1.5），截图裁剪同理 |
```

新增四条（追加到 §8.6 表末，编号按现末号 28 顺延）：

```text
| 29 | Alt+Q 命令搜索输入「GeoCode」找不到开面板按钮，输入「Status Panel」才命中；且**搜索列表时序敏感**——某次查询只显示「最近使用/建议」区块、不含目标项，重试一次才出现 | ① Pro 的命令搜索**只按 caption 建索引**，`id` / `tooltip` / `longDescription` 均不参与；② 搜索结果面板先渲染「最近/建议」分组，索引项在后续渲染中才出现（自动化读取存在竞态） | 要让搜索词命中，**caption 必须含该词**（C11 定为 `GeoCode 状态面板`，并加静态断言钉住）；UIA 取证时**同一查询重试一次再判定**，并在转录中标明是第几次查询的结果 |
| 30 | `gis/preflight.py::_port_listening` 在 6530 被**任意**原始监听者占用时仍报 `listening: true` | 该探测是 TCP connect，只证明端口有人接，不证明接的是本 add-in 的 MCP 端点 | 判定「端口占用态」用 `netstat -ano` 看 PID/持有者，`_port_listening` 只作连通性粗筛；**改成端点级探测属另一 change（C12）**——C11 受 spec 第 11 行「`gis/` 零 diff」红线约束不改 `gis/**` |
| 31 | README 长期记「余量 = worktree/分支残留清理」 | C1–C10 归档轮已逐次删除 `comet/*` 分支与 worktree，台账未同步 | 2026-10-08 实测 `git worktree list`（仅 main + 活跃 worktree）、`git branch -vv`（仅 main + `comet/c11-dockpane`）、`git stash list`（空）、`git worktree prune --dry-run`（无输出）、`.comet/runtime/native/changes/`（空）⇒ **无残留**，该项可结清 |
| 32 | 同一 add-in 源码在不同目录重建，DLL sha256 不一致（早期实测差 72 字节，全在 PDB GUID / 模块 MVID / COFF 时间戳这类哈希派生字段），导致「独立重建是否等价」无法自证 | ① 内嵌绝对构建路径（PDB/调试目录）；② `AssemblyInformationalVersion` 内嵌 git 提交号（有 `.git` 的树 vs 无 `.git` 的副本结果不同）；③ 调试符号的 PDB GUID 随构建路径变化 | csproj：`<Deterministic>true</Deterministic>` + `<IncludeSourceRevisionInInformationalVersion>false</IncludeSourceRevisionInInformationalVersion>` + `<PathMap>$(MSBuildProjectDirectory)=/_/geocodepro</PathMap>`；**符号按配置区分**——Release 用 `DebugType=none`（zip 本就不装 PDB，交付零影响）换取跨路径逐字节一致，其他配置保留 `portable` 符号供本地调试。改后**多路重建（工作区 + 不同路径长度/有无 .git 的副本）得到同一 sha256** |
```

---

## 五、不动的部分（明确排除，避免误改）

| 对象 | 处置 | 依据 |
|---|---|---|
| §9.2 执行顺序行中的「C9 视 C2 结果决定」 | **保留原文**，仅追加收口句（见第 4 条） | 属历史决策口径，非过期断言；C10 验收口径亦认可 |
| §11 红线 / §3.3 指纹 / PV 相关表述 | **零改动** | C11 未触碰 `gis/**`、`geocode.json`、`PROCESSING_VERSION`（A10 逐字核实） |
| §5.4 端口分配（6530/6531） | **零改动** | C11 未改端口契约 |
| §8.6 #24–#28 | **零改动** | C9/C10 已归档事实，本轮不改写 |

---

## 六、风险处置记录（全量闭合；iteration 3 的 6 条 → iteration 4）

独立验收 iteration 3 判 **10/10 通过**，并列 6 条风险。用户裁决「全量修复」，
逐条给出**最终处置**（不留信息级遗留）；全部改动落在本 change 白名单内（`Pro/**` + `tests/unit/test_pro_addin.py` + `docs/comet/changes/c11-dockpane/**`），`gis/**` 仍零 diff。

### 1. 风险 1（A10「现状」单元格用 `…` 省略）——已修

本文件第一节全部「现状」改为**逐字全文**（引用块形式，附主工作区 README 行号 L375 / L379 / L396 / L398 / L433 / L437 / L542 / L554），不再出现省略号；表格「现状」单元格只留行号与锚点。

### 2. 风险 2（`gis/preflight.py::_port_listening` 判别力）——本 change 不改代码，另立 C12

受 spec 第 11 行「零引擎层改动：`gis/` 零 diff」红线约束，**C11 内不修改 `gis/**`**（改它会直接判 A10 不通过）。C11 内的完整处置：
① 写入 §8.6 #30（已知局限）；
② 把「端口占用态」的判定流程固化为 `netstat -ano`（面板侧另有 add-in 自己的 `LastError` 信号，比端口探针更准）；
③ 代码级改进（端点级探测：HTTP/MCP 往返确认是本 add-in 的端点）**另立 change C12**——C12 需要改 `gis/**`，属需求变化，须走它自己的 Shape 确认，不改变 C11 的已确认需求范围。

### 3. 风险 3（`DebugType=none` 去掉 PDB，带符号构建的可复现语义未评估）——已修

csproj 按配置拆分（见新增 #32）：

```xml
<DebugType Condition="'$(Configuration)' == 'Release'">none</DebugType>
<DebugSymbols Condition="'$(Configuration)' == 'Release'">false</DebugSymbols>
<DebugType Condition="'$(Configuration)' != 'Release'">portable</DebugType>
<DebugSymbols Condition="'$(Configuration)' != 'Release'">true</DebugSymbols>
```

实测：**Release** 多路重建逐字节一致（工作区 + 两个不同路径长度/其一有 `.git` 的副本 + zip 内 DLL 全等于 `f750e6245e64b3be084dff3d992a9ee12b6673fa80c3230ba1365288ecf2ce42`）；**Debug** 配置照常产出符号（`GeoCodePro.dll` + `GeoCodePro.pdb`）。交付可复现性与本地调试符号不再互斥，风险关闭。

### 4. 风险 4（Alt+Q 搜索列表时序敏感）——已固化取证流程 + 记录

写入 §8.6 #29：同一查询**重试一次再判定**，转录须标明是第几次查询的结果；并说明列表先渲染「最近/建议」分组、索引项后到。这不是产品缺陷（caption 索引本身正确，两次独立验收均已命中），但取证过程必须抗这个竞态。

### 5. 风险 5（面板按钮执行工具不增 HTTP 计数）——已修（计数语义补全）

计数分列，语义不再含糊：

- `McpServerHost.Requests` / `Errors`：**只数 HTTP 请求**（含义不变，A6 的 curl 交叉核对仍用它）；
- 新增 `ResultRegistry.ToolCalls`：**HTTP 与面板两条路径合计的工具执行次数**，累加点在 `ResultRegistry.Record` —— 面板路径（`GeoCodeDockpaneViewModel.RunToolAsync`）与 HTTP 路径（`McpServerHost` → `RecordHttpCall` → `Record`）都经它汇合，故**从面板按钮执行工具同样让「工具执行」计数增长**；
- 面板状态文本：`监听端口 {port}（GEOCODE_PRO_PORT 可覆盖）。HTTP 请求 {n} 次（失败 {m} 次）；工具执行 {k} 次（HTTP + 面板）。`

于是验收文字「计数随工具执行增长」对两条执行路径都成立（此前仅 HTTP 路径成立）。回归断言：`test_status_counters_cover_both_execution_paths`。

### 6. 风险 6（跨路径复现的独立覆盖率：Verifier 自跑 2 路，builder 另称 3 路）——无需实现改动

覆盖率由下轮 Verifier 自行决定重跑路数；实现侧只保证「任意路径重建 → 同一 sha256」，不预设路数。独立复核配方见 §六.3 末段。

---

## 七、独立复核配方（Verifier 可照抄）

```bash
# 1) Release 跨路径可复现（两处不同路径长度；其一带 .git）
W=/d/DEV/geocode/.worktrees/c11-dockpane; T=$TEMP      # Git Bash 下 $TEMP 映射为 /tmp 语义
rm -rf "$T/A" "$T/B"; mkdir -p "$T/A/Pro" "$T/B/deep/deeper/Proxx"
for f in "$W"/Pro/*.cs "$W"/Pro/*.xaml "$W"/Pro/*.csproj; do cp "$f" "$T/A/Pro/"; cp "$f" "$T/B/deep/deeper/Proxx/"; done
(cd "$T/A" && git init -q . && git add -A && git -c user.email=t@t -c user.name=t commit -qm t)
(cd "$T/A/Pro" && dotnet build GeoCodePro.csproj -c Release --nologo -v q)
(cd "$T/B/deep/deeper/Proxx" && dotnet build GeoCodePro.csproj -c Release --nologo -v q)
sha256sum "$T/A/Pro/bin/Release/net10.0-windows/GeoCodePro.dll" "$T/B/deep/deeper/Proxx/bin/Release/net10.0-windows/GeoCodePro.dll"
# 2) 与交付件绑定
python -c "import zipfile,hashlib;print(hashlib.sha256(zipfile.ZipFile(r'$W/Pro/GeoCodePro.addin.zip').read('Install/GeoCodePro.dll')).hexdigest())"
# 3) 符号只在 Release 关掉
(cd "$T/A/Pro" && dotnet build GeoCodePro.csproj -c Debug --nologo -v q) && ls "$T/A/Pro/bin/Debug/net10.0-windows/" | grep -i pdb
# 4) XAML 仍编译进程序集
powershell -NoProfile -Command "$a=[Reflection.Assembly]::LoadFrom('$W\Pro\bin\Release\net10.0-windows\GeoCodePro.dll'); $s=$a.GetManifestResourceStream('GeoCodePro.g.resources'); (New-Object System.Resources.ResourceReader($s)).GetEnumerator() | %{ $_.Key }"
```

当前实测参考值：Release DLL = `f750e624…`；候选 zip = 部署件 = `55f600b7a39a8639ff7f1a44ad09a13e2ecb6932e1c05dc7bbd9da78d6fc6fa3`。
