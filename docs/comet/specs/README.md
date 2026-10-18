# 发布面 Specs 索引与 supersession 台账

> 本文件是**发布面索引**，不是正式 Spec。正式 Spec 一律位于 `specs/<capability>/spec.md`
> （Runtime 只认这个路径；`specs/` 下的其他文件不会被当作正式规格）。
>
> 建立于 2026-10-08 的 **c13-spec-consistency**：跨 change 审阅（C1–C12）发现发布面同时存在互斥或
> 陈旧的「当前行为」陈述，本文件把**条款级取代关系**显式登记，并把四条发布面规范固定下来。
> 逐条修订方案见 `docs/comet/changes/c13-spec-consistency/spec-revision-list.md`；条目级修订由
> `tests/unit/test_comet_spec_consistency.py` 机械守卫。

## 一、条款级 supersession 台账

被取代的条款**原文保留不删**，各自在条款旁带 `> ⚠️ …` 注记指向本表。新增 change 若改动既有
capability 的行为，必须在此**追加一行**并给对方 spec 加注记。

| 被取代/被修订的条款 | 取代/修订方 | 日期 | 说明 |
|---|---|---|---|
| `p1b-arcgis-addin`（C9）：`gis/preflight.py` 探测项判据「**6530 端口是否监听（占用可见）**」 | `c12-preflight-endpoint-probe`（C12，`3c66c65` / `b160644`） | 2026-10-08 | 判据改为**端点身份匹配**：`GET /` 须 200 + 合法 JSON + `name == "geocode-pro"`；`listening` 降为诊断字段；端口被别的进程占用时报独立失败码 `pro-port-occupied-by-other` |
| `dockpane`（C11）：「`gis/preflight.py` **零改动**（`check_pro_addin` 的 installed/deployed/listening 三探测语义不变）」 | 同上 | 2026-10-08 | 该句仅约束 C11 范围；三探测语义已被 C12 修订（`ok` 改以端点为准） |
| `core-contract-unit-tests`（C1）：「`tests/smoke_*.py` **保持原样**；`gis/` **无行为性修改**」 | `c10-review-patches`（C10，`d091bff`）＋ `c12-preflight-endpoint-probe`（C12） | 2026-10-08 | C10 更新了 `smoke_array_chunking.py` / `smoke_map_renderers.py` / `smoke_timeseries.py`；C12 更新了 `gis/preflight.py` 的探测行为 |
| `p1a-arcpy-bridge`（C2）：「优先复用 P0 缓存产物，**指纹 `c9243efd`**」 | `p2-presets`（C4，`ce40e45`，`PROCESSING_VERSION` 2→3）＋ `c10-review-patches`（C10，指纹须随时代取值） | 2026-10-08 | 缓存文件名含指纹（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`），`c9243efd` 是 PV=2 历史值；当代金指纹为 `b91c09c9c6451c16`。**按指纹指名缓存/写期望值必须随时代取值** |
| `verify-all`（C14）：RUN 层「固定 4 项（tests-unit / tui-timeseries-probe / daemon-endpoint-probe / ＋前置产物存在时的 rescan-big）」与 SKIP 层「恰好 9 项、其中含 `smoke_map_renderers` qgis/arcpy」 | `c17-verify-all-evidence-aware`（c17，2026-10-18） | 2026-10-18 | 条件项的层位改由**盘上/环境事实**决定：①`smoke-map-renderers-qgis`/`-arcpy` 在当代指纹缓存 `data/derived/s2_beijing_test.<指纹8位>.tif`（>4096 B）存在时**自动入 RUN 层**（与 rescan-big 同款语义），缺失时 SKIP 且文案写实；②新增 `ruff-check` 可选 RUN 项（`uvx --offline ruff@0.17.0 check`，缺失时 SKIP + 安装提示，不 FAIL）。SKIP 集合因此不再是固定 9 项。**另有措辞订正**：rescan-big 的「不在主工作区」断言与事实相悖（产物确在主工作区盘上），改为「本次执行根下无」 |
| `p1a-arcpy-bridge`（C2）：`emit_map` 产物面与 renderer 纪律条款 — **未删除、未改写**；其失败判定行为（局部失败容忍 / layout_error 被丢弃 / arcpy 导出缺失不报错）已被收紧 | `c17-verify-all-evidence-aware`（c17，2026-10-18） | 2026-10-18 | `emit_map` 失败判定改为「**预期产物缺一即失败**」，且「预期」按 spec 真实配置推导：qgis 需 `.qgz`+`.png`；arcpy 需 `.aprx` + `layout.formats` 所列导出（`formats=("pdf",)` 这类单格式合法配置必须 PASS）；`layout=None`（nolayout，无导出）必须 PASS；`layout_error` 非空即失败。原条款与 Scenario/编号/验收全部保留，仅在文件末尾追加 `> ⚠️` 注记（双副本逐字节一致）；验收落在 `verify-all` 的 A20–A22 |

**就地订正（非跨 change 取代，仅格式/措辞对齐实现）**：

| spec | 订正内容 | 日期 |
|---|---|---|
| `c12-preflight-endpoint-probe`（C12） | ①A16 场景「进程内起假服务器」→「**子进程承载**的假服务器」（`tests/unit` 受离线守卫约束不得导入 `socket`/`http`/`urllib`）；②Scenario 验收引用移入标题并改用 Runtime 验收编号 A9–A17（原先写在标题外独立行、混用 brief 编号） | 2026-10-08（C13） |
| `dockpane`（C11） | H1 由 `# Capability：c11-dockpane …` 改为 `# Capability：dockpane …`（capability 名对齐目录名，change 名在正文点明） | 2026-10-08（C13） |
| `p2-presets`（C4）、`p2-batch-export`（C5） | H1 补 `Capability：<目录名> —— ` 前缀（此前为裸标题） | 2026-10-08（C13） |
| `c13-spec-consistency`（C13，自身） | 本 change 自己的 spec 也曾用「引用写在标题外独立行」形态（与 C12 同类）——**由本 change 新增的结构守卫抓出**（全量测试转红）；已把 12 个 Scenario 的 `（验收：Ax）` 移入标题并改用 Runtime 编号 **A13–A24**、删除 12 行标题外引用，双副本同步 | 2026-10-08（C13 归档后自纠） |
| `p3-skill-knowledge`(C7) / `p3-osm-overpass`(C8) / `p1b-arcgis-addin`(C9) / `c10-review-patches`(C10) / `dockpane`(C11) | 各 Scenario 标题补 `（验收：Ax）`（共 40 条：5+8+8+9+10），映射见 `spec-revision-list.md` §F6 | 2026-10-08（C13） |
| `verify-all`（C14，自身） | 本 change 自己的 spec 偏离两条发布面规范：①H1 为裸标题 `# verify-all — …`（补齐 `Capability：` 前缀与 ` —— ` 分隔）；②Scenarios 写成 `## Scenario:`（与章节同级）且引用写在标题外独立行——已改为 `### Scenario: …（验收：Ax）`（A1–A7，与 brief 验收集同号）并删除 7 行独立引用。**由 C13 结构守卫在 C14 归档后抓出**（全量单测转红：H1 前缀 / Scenario 存在性共 3 条断言）；发布面与归档面双副本同步 | 2026-10-11（C14 归档后自纠） |
| `verify-all`（C14 → c17） | C14 原文的 7 个 Scenario 引用为 A1–A7；c17 的 brief 验收示例也占用 A1–A5（语义不同：条件项升级 / 措辞一致 / 发布面一致 / ruff 接入 / 回归）。若沿用原编号会造成**同名不同义的假映射**，故按规范 2「编号用该 change 的验收集编号」把这 7 个 Scenario 整体后移为 **A6–A12**，c17 新增的 3 个场景为 **A13–A15**。**场景正文逐字未改**，仅标题内引用编号后移；spec 内已加「c17 编号说明」注明对应关系（A6←A1 … A12←A7）。（与 C13 自身 spec 的 A13–A24 自纠同类） | 2026-10-18（c17） |
| `verify-all`（C14 → c17） | 原文「入口按静态的『网络依赖分类表』把检查项分为 RUN 与 SKIP 两层」在条件项引入后不再字面成立（层位由盘上/环境事实决定），已就地加 `⚠️ c17 修订` 注记说明；SKIP 层 `smoke_map_renderers` 一条加注记收窄为「仅缓存缺失时 SKIP」；退出码段补注 `ruff-check` 参与同一退出码语义。**原文全部保留未删** | 2026-10-18（c17） |
| `verify-all`（C14 → c17，第二批） | 第二批范围（渲染失败语义收紧）新增 4 项验收，原编号方案出现空档（brief A1–A5 + A16–A19，spec 占 A6–A15），违反「编号连续且 brief/spec 互不重叠」；已重排为 **brief A1–A9 / spec A10–A23**（共 23 项，连续无空档）。spec 内「c17 编号说明」已同步给出 C14 旧号映射（A10←A1 … A16←A7）。场景正文逐字未改 | 2026-10-18（c17） |
| `verify-all`（C14 → c17 → c21 → c22） | c22 就地订正与判据澄清三处（**均追加注记、原文零删除**）：①A13「9 个 smoke」订正为「**10 个**（含 `smoke_all.py` 汇总器）」并注明沿革；②A10 的「全程对外网请求为零」按用户裁决**收窄为「入口自身发起的对外请求为零」**，写明 arcpy/QGIS 渲染子进程属第三方运行时、其厂商回连不计入本断言（实测命中态观测到 443/80 出站约 12 s+，qgis 侧未观测到）；③A13 追加 c22 范围说明（为修测试健壮性改了 `tests/unit/test_verify_report_tools.py` 的 import 形态与 skip 语义、不动任何断言；smoke 仍零 diff）；④A21 明确「成功产物哈希不漂移」的判据是「**生产路径零 diff**」——`.aprx`/`.layout.pdf` 含时间戳非字节可复现，`.png`/`.qgz`/`.rgb8.tif` 稳定 | 2026-10-18（c22） |
| `verify-all`（C14 → c17 → c21） | c21 按 C13 规范 2（编号用该 change 的验收集编号）把 14 个既有场景的标题内引用从 c17 的 **A10–A23** 整体前移为 **A8–A21**，新增 4 个场景 **A22–A25**（报告自查接入 RUN 层 / 自查失败即入口失败 / 两遍写法下报告自洽 / 缺少自查工具时归 SKIP）；**各场景正文逐字未改**，仅标题内编号重排，文末加 c21 编号说明（c17 编号说明原文保留）。同时 RUN 层新增条件项 `report-selfcheck`、报告节补「两遍写法」与「自指说明」、退出码节补 c21 说明。原文零删除，发布面与两份归档副本逐字节同步 | 2026-10-18（c21） |
| `c13-spec-consistency`（C13） | 不变量 4 原句「每个归档 change 目录含 `brief.md`、`comet-state.yaml`、`verification.md`、`specs/*/spec.md`」未考虑 Comet Runtime 的「不改变产品行为」豁免（change 的 `brief.md` 写一行合规声明即可免写目标 Spec）。**原文保留**，就地补 ⚠️ c20 修订注记：`specs/*/spec.md` 缺失时，仅当 `brief.md` 的可见行含合规豁免声明（`不改变产品行为` / `不涉及产品行为` / `仅文档` / `no product behavior change` / `documentation-only` + `：`，理由非占位）才放行；其余必备件仍强制。判据与 Runtime 的 `hasExplicitSpecExemption` / `isPlaceholderExemptionReason` 同源。触发事故：c19-verify-report-drift 走豁免归档后 main 全量单测 393 例 1 失败 | 2026-10-18（c20） |

## 二、发布面四条规范

1. **capability 命名 = 发布面目录名**：H1 必须形如 `# Capability：<目录名> —— <标题>`。
   （Runtime 按 `specs/<capability>/spec.md` 落库；名字不符会让「capability ↔ 文件」失去唯一对应。）
2. **每个 `### Scenario:` 标题必须带 `（验收：Ax）`**：引用写在标题内，不接受标题外的独立引用行。
   编号用该 change 的验收集编号（Verifier 看到的同一套 ID）；Scenario 与 acceptance 不要求 1:1，但必须可追溯。
3. **按指纹指名缓存或写期望值必须随时代取值**：指纹进缓存文件名（`{slug}.{指纹8位}.tif`），
   `PROCESSING_VERSION` 变化会改变文件名与期望值；不得把某时代的常量当作跨时代判据
   （单一事实源：`tests/unit/_helpers.py::GOLDEN_FINGERPRINTS`；口径来源：`c10-review-patches` A1/A2）。
4. **双副本逐字节一致**：任何 spec 修订必须同时改发布面 `docs/comet/specs/<cap>/spec.md` 与归档面
   `docs/comet/archive/<change-dir>/specs/<cap>/spec.md`，两者必须逐字节相同。

## 三、机械守卫

`tests/unit/test_comet_spec_consistency.py` 检查规范 1、2、4 与归档产物完整性（离线、只读文件）：

- 发布面 spec 存在且数量合理（≥12）；
- H1 前缀与目录名一致（规范 1）；
- 发布面 spec 在归档面有逐字节相同副本，且无孤儿 capability（规范 4）；
- 每个 Scenario 带标题内引用、且无标题外独立引用行（规范 2）；
- 每个归档 change 目录含 `brief.md` / `comet-state.yaml` / `verification.md` / `specs/*/spec.md`；
  **例外（c20 修订）**：`brief.md` 声明了合规（非占位）的「不改变产品行为」豁免时，允许没有
  `specs/` —— 判据与 Comet Runtime 的 `hasExplicitSpecExemption` / `isPlaceholderExemptionReason`
  同源，见 `c13-spec-consistency` 的 Scenario G1 注记与下方「就地订正」表。

规范 3 与语义级取代关系无法自动判定，靠本文件的人工台账 + 审阅。
