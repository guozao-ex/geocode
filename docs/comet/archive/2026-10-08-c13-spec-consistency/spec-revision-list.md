# C13 `c13-spec-consistency` 跨 change 矛盾修订清单（四列：现状 / 改为 / 依据 / 回退）

> **来源**：2026-10-08 对 12 个已归档 change（C1–C12）的发布面审阅。审阅结论：12 个 change 全部
> `done`/`pass`、发布面 specs 与归档副本 12/12 逐字节一致、§11 红线 1–8 无违反；但发现 **8 条**矛盾/不一致，
> 本清单逐条给出可执行修订。
>
> **放置位置**：本文件位于 change 目录（git 跟踪），随归档进入 `docs/comet/archive/**`。
> **双副本铁律**：凡修订 spec，必须**同时**改 `docs/comet/specs/<capability>/spec.md`（发布面）与
> `docs/comet/archive/<change-dir>/specs/<capability>/spec.md`（归档面），并保持两者逐字节一致
> ——该不变量现由 `tests/unit/test_comet_spec_consistency.py` 守卫。
> **历史正文原则**：被后发 change 取代的条款**只加注记、不改原文**（保留历史可追溯）；纯格式/措辞缺陷**就地修正**。

---

## F1｜`check_pro_addin` 探测判据：三份发布 spec 互斥（真冲突·高）

| 列 | 内容 |
|---|---|
| 现状 | ① C9 `docs/comet/specs/p1b-arcgis-addin/spec.md`：「`gis/preflight.py` 追加一类探测项…Pro 安装检测、add-in 是否部署（MyDocuments\ArcGIS\AddIns\ArcGISPro 下 zip 存在性）、**6530 端口是否监听**（占用可见）」；② C11 `docs/comet/specs/dockpane/spec.md`：「既有 zip 布局单测不回退；`gis/preflight.py` **零改动**（`check_pro_addin` 的 **installed/deployed/listening 三探测语义不变**，既有单测不回退）」；③ C12 `docs/comet/specs/c12-preflight-endpoint-probe/spec.md`：「`check_pro_addin()` 的 `ok` 判定由 `installed and deployed and listening` 改为 `installed and deployed and endpoint_alive`」 |
| 改为 | ①C12 spec 的「定位」段**声明取代关系**：新增一行 `> **Supersedes**：本条取代 `p1b-arcgis-addin`（C9）的 6530 探测判据条款与 `dockpane`（C11）的「`check_pro_addin` 三探测语义不变」条款——判据由「端口有监听」改为「端点身份匹配」，`listening` 降为诊断字段。` ②C9 的该条款旁**加注记**（不改原文）：`> ⚠️ 本条判据已被 c12-preflight-endpoint-probe 修订（2026-10-08）：探测判据由「6530 端口是否监听」改为「端点身份匹配 name==geocode-pro」；见 docs/comet/specs/README.md。` ③C11 的该条款旁**加注记**：`> ⚠️ 本句「`gis/preflight.py` 零改动 / 三探测语义不变」仅约束 C11 范围；该语义已由 c12-preflight-endpoint-probe 修订（2026-10-08），见 docs/comet/specs/README.md。` |
| 依据 | 审阅事实：三份 spec 均在发布面且互斥；C12 归档（`3c66c65` / `b160644`）改的正是 `check_pro_addin` 的 `ok` 判据与 `value` 字段；C12 的 `verification.md` 已据此判 A1–A17 全过 |
| 回退 | 删除 C12 spec 的 Supersedes 行与 C9/C11 两处 `⚠️` 注记（三段均为纯新增行，删除即还原） |

## F2｜C1 spec 的绝对表述 vs C10 / C12 的实际改动（同 F1 类·中）

| 列 | 内容 |
|---|---|
| 现状 | `docs/comet/specs/core-contract-unit-tests/spec.md`：「`tests/smoke_*.py` **保持原样**；`gis/` **无行为性修改**。若测试暴露生产缺陷，最小修复须逐条记…」 |
| 改为 | 该条款旁**加注记**（不改原文）：`> ⚠️ 本条为 C1 交付时的范围声明，已被后续 change 修订：tests/smoke_array_chunking.py、smoke_map_renderers.py、smoke_timeseries.py 经 c10-review-patches（2026-10-08）更新；gis/preflight.py 的探测行为经 c12-preflight-endpoint-probe（2026-10-08）更新。见 docs/comet/specs/README.md。` |
| 依据 | C10 归档 `d091bff`（其 spec 明确改了三个 smoke）；C12 归档 `b160644`（`gis/preflight.py` 行为变更）；两处均为已接受的验收范围 |
| 回退 | 删除该 `⚠️` 注记 |

## F3｜p1a spec 以 PV2 时代指纹指名缓存（陈旧口径·中）

| 列 | 内容 |
|---|---|
| 现状 | `docs/comet/specs/p1a-arcpy-bridge/spec.md`：「给定同一 spec（含 LayoutSpec）与其 GeoTIFF（优先复用 P0 缓存产物，**指纹 `c9243efd`**；缺失时…）」 |
| 改为 | 在该句旁**加注记**（不改原文）：`> ⚠️ 时代口径：`c9243efd` 是 PV=2 时代指纹。C4（p2-presets）已把 PROCESSING_VERSION 2→3，当代金指纹为 `b91c09c9c6451c16`；缓存文件名含指纹（gis/emit.py::_output_path → {slug}.{指纹8位}.tif）。任何「按指纹指名缓存」的判据必须**随时代取值**（c10-review-patches 已把该口径立为验收 A1/A2）。` |
| 依据 | C4 归档 `ce40e45`（PV 2→3）；C10 归档（A1/A2：指纹期望值不得硬编码旧时代值）；`tests/unit/_helpers.py::GOLDEN_FINGERPRINTS` 为单一事实源 |
| 回退 | 删除该 `⚠️` 注记 |

## F4｜C10 的四列 README 差异清单不在归档产物（载体不一致 + 交付物丢失·中）

| 列 | 内容 |
|---|---|
| 现状 | C10 的清单落在**主工作区 gitignored** 的 `logs/acceptance/c10-local-changes.md`（112 行，仍在盘上）；归档目录 `docs/comet/archive/2026-10-08-c10-review-patches/` 只有 `brief.md`/`comet-state.yaml`/`specs/`/`verification.md`，**无该清单**。C11/C12 则把同类清单放在 change 目录（git 跟踪、随归档入库） |
| 改为 | **回收原件**：把 `logs/acceptance/c10-local-changes.md` **逐字节复制**为 `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`（入库、随归档），并在文件首行**追加一行来历注记**：`> 本文件为 C10 归档时的四列差异清单原件，原落在主工作区 gitignored 的 logs/acceptance/（不入库）；2026-10-08 由 c13-spec-consistency 回收进归档面，正文未改动。`（注记插在既有 `> 位置说明` 块之前，其余正文逐字不动） |
| 依据 | 审阅事实：C11 归档的 A10 已把「清单载体必须 git 跟踪、进归档面」立为判据（其第 2 条风险即此），但从未回头补 C10；原件仍在盘上，可无损回收 |
| 回退 | 删除 `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`（原 logs/ 副本保留不动） |

## F5｜capability 名与目录名不符 / H1 缺前缀（命名一致性·低）

| 列 | 内容 |
|---|---|
| 现状 | ① `docs/comet/specs/dockpane/spec.md` 的 H1 声明 `# Capability：c11-dockpane —— Pro add-in dockpane 状态面板（C9/C10 拆出的唯一遗留项）`，而目录/发布键是 `dockpane`；② `docs/comet/specs/p2-presets/spec.md` 的 H1 是 `# 数据集预设表（dataset presets）`，缺 `Capability：<name> —— ` 前缀；③ **（审阅漏网，执行时经机械核验补出）** `docs/comet/specs/p2-batch-export/spec.md` 的 H1 是 `# p2-batch-export —— GEE 服务端批处理导出与任务持久化（完整规格）`，同样缺 `Capability：` 前缀——合共 **3 处**不符 |
| 改为 | ①`dockpane` 的 H1 改为 `# Capability：dockpane —— Pro add-in 状态面板（change c11-dockpane 交付；C9/C10 拆出的唯一遗留项）`（capability 名与目录一致，change 名在正文点明）；②`p2-presets` 的 H1 改为 `# Capability：p2-presets —— 数据集预设表（dataset presets）`；③`p2-batch-export` 的 H1 改为 `# Capability：p2-batch-export —— GEE 服务端批处理导出与任务持久化（完整规格）`。三处正文其余不动，双副本同步 |
| 依据 | 其余 10 份 spec 的 H1 均为 `# Capability：<目录名> —— <标题>`；命名规则以「capability 名 = 发布面目录名」为准（Runtime 的 `specs/<capability>/spec.md` 路径约定） |
| 回退 | 两处 H1 还原为原文 |

## F6｜5 份 spec 缺验收引用（可追溯性·低）

| 列 | 内容 |
|---|---|
| 现状 | 12 份 spec 中 **5 份（C7 `p3-skill-knowledge`、C8 `p3-osm-overpass`、C9 `p1b-arcgis-addin`、C10 `c10-review-patches`、C11 `dockpane`）完全没有 `（验收：Ax）` 引用**；其余 7 份（C1–C6、C12）逐 Scenario 标注 |
| 改为 | 为这 5 份的每个 `### Scenario:` 标题**补 `（验收：Ax）`**，映射取自各自归档 `comet-state.yaml` 的 acceptance 列表（Scenario 数与 acceptance 数均为 **1:1**：C7 5/5、C8 8/8、C9 8/8、C10 9/9、C11 10/10）。映射**逐条落表留档**在本清单末「§F6 映射表」，便于核对与原样回退 |
| 依据 | 审阅事实（Scenario 数 = acceptance 数 = 上列值）；补引用不改判据内容，只把「场景 ↔ 验收项」的对应关系显式化 |
| 回退 | 按 §F6 映射表逐条删除标题尾部的 `（验收：Ax）` |

## F7｜README §9.2 台账 C3 行缺 commit 号（台账缺口·低）

| 列 | 内容 |
|---|---|
| 现状 | 主工作区 `docs/README.md` 的 §9.2 表：`| C3 | \`p2-timeseries\` | … | ✅ 归档（2026-10-06，三轮独立验收 8/8） |`——是 12 行中**唯一没有 commit 号**的已归档行 |
| 改为 | 补上 C3 的归档提交号（取 `git log` 中 C3 归档相关的真实提交，回填为 `✅ 归档（2026-10-06，三轮独立验收 8/8；提交 <回填>）`）；若历史中确无单一归档提交，则按 §9.1 已记的三个提交号（`75e14a5` 属 C1，不适用）另行核实后回填或注明「并入 main 于 <hash>」 |
| 依据 | 其余 11 行均带 commit 号（已核对全部存在于 git 历史）；C3 行缺号使台账无法按号追溯 |
| 回退 | 删除回填的提交号，还原为 `✅ 归档（2026-10-06，三轮独立验收 8/8）` |

## F8｜C12 spec 与实现的措辞偏差（发布面措辞·低）

| 列 | 内容 |
|---|---|
| 现状 | `docs/comet/specs/c12-preflight-endpoint-probe/spec.md` 的「测试全部离线且不污染本机」场景写：「通过**进程内起假服务器**（绑定 `127.0.0.1:0` 由系统分配端口后注入 `port=`）或**假原始监听者**覆盖各分支」；而实现**用子进程承载**假服务器（因 `tests/unit` 受离线守卫禁止导入 `socket`/`http`/`urllib`）。C12 的 `verification.md` 已记录该偏差（判 A16/A8 passed，实质满足） |
| 改为 | 把该句改为与实现一致的表述：`通过**子进程承载的假服务器**（`subprocess` + `sys.executable -c`；子进程内绑定 `127.0.0.1:0` 由内核分配端口并回传，用例退出即 terminate）或**假原始监听者**覆盖各分支——`tests/unit` 受离线守卫约束不得导入 socket/http/urllib，故假服务必须外置为子进程。` |
| 依据 | C12 的 `verification.md`（独立 Verifier 记录）；`tests/unit/test_offline_guard.py` 的 BANNED 名单；C12 实现 `tests/unit/test_preflight_endpoint_probe*.py` 的 `_FakeServer` |
| 回退 | 该句还原为原文 |

---

## F6b｜C12 的验收引用形态与编号不规范（执行时补出·低）

| 列 | 内容 |
|---|---|
| 现状 | `docs/comet/specs/c12-preflight-endpoint-probe/spec.md` 是 12 份里**唯一**把 `（验收：…）` 写在 `### Scenario:` **标题之外的独立行**的（其 9 个 Scenario 对应 9 行独立引用）；且引用用的是 **brief 编号**（A1/A2、A3/A4/A5/A6/A7/A8/A1–A6/A8 片段），而该 change 的验收集编号为 **A1–A17**（brief A1–A8 + Spec 场景依次编 A9–A17）——同一文件内存在两套编号，无法与 Verifier 看到的 ID 对齐 |
| 改为 | 每个 `### Scenario:` 标题末尾补 `（验收：A9）` … `（验收：A17）`（按场景顺序对应 Runtime 验收编号），并**删除**那 9 行标题外独立引用（消除双重编号）；双副本同步 |
| 依据 | 其余 11 份的引用全部写在标题内（机械核验：11 份 `标题内=全部、独立行=0`）；C12 归档的 `comet-state.yaml` 验收列表为 17 项，其中 A9–A17 即 spec 的 9 个 Scenario（顺序一致） |
| 回退 | 删掉 9 个标题里的 `（验收：A9–A17）`，并把原 9 行独立引用按原顺序插回各场景末尾 |

---

## 附：新增防线（非「修订」，属预防性范围；需在 Shape 中一并确认）

**G1｜结构不变量守卫** `tests/unit/test_comet_spec_consistency.py`（离线，只读文件）：

- 每个 `docs/comet/specs/<cap>/spec.md` 的 H1 必须是 `# Capability：<cap> —— …`（cap == 目录名）；
- 每个发布面 spec 必须在 `docs/comet/archive/*/specs/<cap>/spec.md` 有**逐字节相同**的归档副本；
- 每个 `### Scenario:` 标题必须带 `（验收：A…）` 引用；
- 每个归档 change 目录必须含 `brief.md`、`comet-state.yaml`、`verification.md`、`specs/*/spec.md`。

依据：本次审阅的 F1–F6 全部是「同一类漂移」的不同实例，而这四类都可由静态断言机械检出（F1 的语义取代关系无法自动化，靠 `docs/comet/specs/README.md` 的条款级索引 + 人工）。回退：删除该测试文件。

**G2｜条款级 supersession 索引** `docs/comet/specs/README.md`（新建）：

列出「哪条条款被哪个 change 取代/修订」（至少收录 F1–F3、F8 四条），并写明发布面规范：capability 命名 = 目录名、每个 Scenario 必须带验收引用、按指纹指名缓存必须随 `PROCESSING_VERSION` 时代取值、spec 双副本必须逐字节一致。回退：删除该文件。

---

## §F6 映射表（Scenario → 验收项；补引用与回退均以此为准）

| change | Scenario（按 spec 出现顺序） | 验收 |
|---|---|---|
| C7 `p3-skill-knowledge` | 素材落位与出处 / 筛选边界 / 指针与索引 / 新会话可用性 / 零管线改动 | A1 / A2 / A3 / A4 / A5 |
| C8 `p3-osm-overpass` | 查询构造纯函数 / Overpass 客户端与重试装配 / GPKG 交付与数据等效 / 本地合规边界（admin_aoi）/ 矢量叠加进 map 出口 / 时序分层不回退指纹 / 合规与许可证 / 端到端实测（需网络、需 Pro） | A1–A8（1:1） |
| C9 `p1b-arcgis-addin` | add-in 工程与入口 / 打包结构与部署脚本 / DAML 合法性与部署路径 / MCP server 与线程纪律 / pro_get_view_aoi / pro_add_layer / pro_export_view / preflight 探测项与离线回归 | A1–A8（1:1） |
| C10 `c10-review-patches` | SMOKE-A3 指纹断言按时代取值 / SMOKE-B1 离线地图冒烟自足 / SMOKE-C1 测试入口稳健性 / C3 spec 正文与实现一致 / README 文档订正 / 本地配置补齐 OSM 镜像池 / OSM fixture 归属标注 / 交付形态与可回退性 / C9 归档与路线图收口台账 | A1–A9（1:1） |
| C11 `dockpane` | DAML dockpane 声明与开面板入口 / 面板类与视图 / 服务状态区运行态 / 端口占用态与重试监听 / 工具区与最近结果区 / add_layer 与 export_view / 构建打包部署链路不变量 / 离线回归警戒线 / Pro 会话取证纪律 / 本地件差异清单与改动面白名单 | A1–A10（1:1） |

> 注：C8/C9/C10/C11 的 Scenario 顺序即其归档 `comet-state.yaml` 的 `acceptance` 顺序（已逐条比对 Scenario 数与 acceptance 数：8/8、8/8、9/9、10/10）；执行时若发现某条 Scenario 与对应 acceptance 文本不符，**以 acceptance 文本为准**并在本表标注调整。

---

## 执行记录（2026-10-08 Build 轮）

**总览**：8 条修订 + 2 项防线**全部执行完毕**；发布面 specs ↔ 归档副本 **12/12 逐字节一致**；12 份 spec 的 H1 全部合规；**91** 个 Scenario 全部带标题内验收引用（40 条为本次补齐、9 条为 C12 重映射）；零 `gis/**`、`Pro/**`、`scripts/**`、`geocode.json` 改动，`PROCESSING_VERSION = 3` 未改。

| 条目 | 执行状态 | 证据 |
|---|---|---|
| F1（真冲突） | ✅ 已修 | C12 spec 定位段加 `Supersedes` 行；C9 `p1b-arcgis-addin` L57 后、C11 `dockpane` 打包段后各加 `⚠️` 注记；三份均双副本同步（发布面/归档面逐字节一致）；被取代条款原文未改（未删除、未改写） |
| F2（C1 绝对表述） | ✅ 已修 | `core-contract-unit-tests` 的 smoke/gis 条款后加 `⚠️` 注记（点名 C10 改的三个 smoke + C12 改的 preflight），双副本同步 |
| F3（p1a 时代口径） | ✅ 已修 | `p1a-arcpy-bridge` 的 `c9243efd` 句后加时代口径注记（当代 `b91c09c9c6451c16` + 缓存名含指纹 + 须随时代取值），双副本同步 |
| F4（C10 清单回收） | ✅ 已回收 | 新建 `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`；与原件 `logs/acceptance/c10-local-changes.md` 的 diff = **新增 3 行（来历块）、删除 0 行**，正文逐字未改（5800 → 6003 字节） |
| F5（H1 命名，**扩为 3 处**） | ✅ 已修 | `dockpane`、`p2-presets`、`p2-batch-export` 三处 H1 均已改为 `# Capability：<目录名> —— …`；机械核验 12/12 合规 |
| F6（补验收引用） | ✅ 已修 | C7/C8/C9/C10/C11 共补齐 **40** 条（5+8+8+9+10），写入标题内；双副本同步；机械核验全库 Scenario 均带引用 |
| F6b（C12 引用形态与编号，执行时补出） | ✅ 已修 | C12 的 9 个标题补 `（验收：A9–A17）`、删 9 行标题外独立引用；机械核验「仅标题内引用」且全库无残留独立引用行 |
| F7（台账补号） | ⏳ 待归档轮执行 | 已核实 C3 的归档提交 = **`1fae53d`**（定位方式：`git log --diff-filter=A -- docs/comet/archive/2026-10-06-p2-timeseries/comet-state.yaml`，说明为 `feat: C3 时序立方体 —— …`）；README 为 gitignored 本地件，条目落在 `local-changes.md`，由归档轮在主工作区就地执行 |
| F8（C12 措辞） | ✅ 已修 | C12 spec 的 A16 场景改为「子进程承载的假服务器（`subprocess` + `sys.executable -c`…）」并说明离线守卫原因；双副本同步 |
| G1（结构守卫） | ✅ 已建 | 新增 `tests/unit/test_comet_spec_consistency.py`（8 条断言覆盖四类不变量），单跑 OK；全量批次内亦绿 |
| G2（条款级索引） | ✅ 已建 | 新增 `docs/comet/specs/README.md`：4 条 supersession 条目 + 4 条发布面规范 + 就地订正表 + 守卫说明 |
| A12（清单回填） | ✅ 已完成 | 即本表 |
