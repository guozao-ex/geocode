---
generated_from_state_version: 11
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 2
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-18T08:09:15.965Z
- 摘要: 独立核查（自建 26 例对立样本 + 8 例不变量敏感性样本 + 旧守卫基线复现 + 两条入口实跑 + 零 diff/双副本哈希/提交考古）确认：守卫对「brief.md 含合规豁免声明」的无 specs 归档目录放行（A1，含真实 c19），对无豁免（A2）、占位理由与缺必备件（A3）一律转红并点名；main 上那 1 例红（c19）确由本次修订转绿（A4，旧守卫副本实跑复现）；gis/Pro/scripts/geocode.json/tests 相关面与 PROCESSING_VERSION、金指纹零 diff（A5）；发布面与归档面双副本逐字节一致、台账已登记、Scenario 引用齐全（A6）；A7–A14、A16–A18 所述 C13 既有条款在今日仓库均成立（含「只加注记/只补引用」的逐行配对证明、C12 场景措辞与 40 条 Scenario 计数、F7 提交号 1fae53d 的独立复核与就地执行）。18 项全部 passed，总判定 pass；风险集中在「镜像而非共享代码」「豁免不核对理由相称性」与三处历史括注/措辞形态的落差，均不改变各条验收的成立。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: 守卫对「无 `specs/` 且 `brief.md` 含合规豁免声明」的归档目录放行：构造一个最小归档目录（`brief.md` 带一行「不改变产品行为：<具体理由>」+ `comet-state.yaml` + `verification.md`，**无** `specs/`）后，该目录不再出现在违规列表里。 | 自建最小归档目录（brief.md 一行「- 不改变产品行为：仅新增两个只读开发者工具与离线用例，不接入任何产品路径。」+ comet-state.yaml + verification.md，无 specs/）→ archive_completeness_problems 返回 []；真实 c19 归档目录（无 specs/、三件必备件齐全、brief L110 有合规豁免）同样返回 []。放行确由豁免触发：把 c19 brief 的「不改变产品行为：」改成「行为说明：」后同一守卫立刻点名该目录。 |
| A2 | passed | brief.md | A2: 守卫对「无 `specs/` 且 `brief.md` 未声明豁免」的归档目录**仍然报错**并点名该目录（证明放行不是无条件放宽）。 | 同构目录但 brief 无豁免声明 → 报 1 条问题并点名目录（`<dir>: 缺 无 specs/*.spec.md 且 brief.md 未声明合规的「不改变产品行为」豁免`）。26 个目录混合根同测：如实只报 17 个该红的目录，无一漏报、无误伤。 |
| A3 | passed | brief.md | A3: 破坏性自证：把豁免理由改成占位形态（空理由、`<TODO>`、`{{reason}}`）后必须重新转红；且把 `missings` 的其它必备件（`brief.md` / `comet-state.yaml` / `verification.md` 之一）去掉时也必须转红。 | 破坏性自证全部转红并点名：空理由、纯空白、<TODO>、{{reason}}、TODO、待填写、<具体理由>；豁免写在 H1/围栏内/HTML 注释里也转红；有合规豁免但分别去掉 verification.md / comet-state.yaml / brief.md 三个变体各自转红并点名缺失件。 |
| A4 | passed | brief.md | A4: 回归：main 当前那 1 例红（c19 归档目录）转绿，`python -m unittest discover -s tests/unit` 全量 393 例 OK（skipped=10）；`uvx --offline ruff@0.17.0 check` 零告警。 | 用 9b72b8a 的旧守卫源码临时副本对当前归档面实跑 = 1 例失败，正是 `2026-10-18-c19-verify-report-drift: 缺 无 specs/*.spec.md`（复现 main 唯一红）；新守卫实跑 `-m unittest discover -s tests/unit` = Ran 399 tests, OK (skipped=10)；旧文件 8 个 def test_ → 新 14 个（+6），故 399-6=393 与验收文字「393 例」的基数一致；`uvx --offline ruff@0.17.0 check` = All checks passed。 |
| A5 | passed | brief.md | A5: 零 diff：`gis/**`、`Pro/**`、`scripts/**`、`geocode.json`、`tests/verify_all.py`、`tests/smoke_*.py`、`PROCESSING_VERSION` 与金指纹 `b91c09c9c6451c16` 均零 diff；`docs/comet/specs/` 下**只有** `c13-spec-consistency/spec.md` 与 `README.md` 有改动。 | git diff 9b72b8a..448fbe2 对 gis/、Pro/、scripts/、geocode.json、tests/verify_all.py、tests/unit/_helpers.py 的 name-only 为空；10 个 tests/smoke_*.py 逐文件 numstat 为空；gis/spec.py L45 PROCESSING_VERSION = 3；_helpers.py 金指纹 3: "b91c09c9c6451c16"；docs/comet/specs/ 下仅 README.md 与 c13-spec-consistency/spec.md 有改动。 |
| A6 | passed | brief.md | A6: 发布面/归档面双副本逐字节一致：`docs/comet/specs/c13-spec-consistency/spec.md` 与其**全部**归档副本哈希相同；台账 `docs/comet/specs/README.md` 确有登记本次修订的新行；修订后的 spec 里 Scenario 标题全部仍带 `（验收：A…）`。 | 发布面 c13 spec 与唯一归档副本 sha256 同为 ca500e74db690c93…（逐字节相同）；448fbe2 对 docs/comet/specs/README.md = +1 行，即台账末行「2026-10-18（c20）」；修订后 spec 的 12 个 `### Scenario:` 标题 12/12 带（验收：A…）。 |
| A7 | passed | specs/c13-spec-consistency/spec.md | 声明取代关系（F1：`check_pro_addin` 三份互斥陈述）（验收：A13） 在 C12 spec（`c12-preflight-endpoint-probe`）的「定位」段追加 `Supersedes` 行，声明其取代 `p1b-arcgis-addin`（C9）的 6530 探测判据条款与 `dockpane`（C11）的「`check_pro_addin` 三探测语义不变」条款；并在 C9/C11 两处被取代条款之后各追加一行 `> ⚠️ 已被 c12-preflight-endpoint-probe 修订（2026-10-08）…` 注记。三份 spec 均**双副本同步**，被取代条款原文逐字未变。 | c12 spec L8 `> **Supersedes**：…` 落在 `## 定位`（L3–L15）段内；C9 spec 被取代条款 L57 之后 L58 有 `> ⚠️ 本条判据已被 `c12-preflight-endpoint-probe` 修订（2026-10-08）…`，C11 spec L88-89 条款后 L90 同款项；三份 spec 发布面/归档面哈希两两相同；9db9849 逐行配对：C9 +9/-8、C11 +12/-11 的删除行全为 Scenario 标题行与 C11 的 H1（F5），被取代条款原文无任何删除或改写。 |
| A8 | passed | specs/c13-spec-consistency/spec.md | 标注 C1 的范围声明已被后续 change 修订（F2）（验收：A14） 在 `core-contract-unit-tests`（C1）的「`tests/smoke_*.py` 保持原样；`gis/` 无行为性修改」条款后追加 `⚠️` 注记，点名 C10 修改的三个 smoke 文件与 C12 修改的 `gis/preflight.py` 行为，并指向 `docs/comet/specs/README.md`。原文不改。 | C1 spec L38「`tests/smoke_*.py` 保持原样；`gis/` 无行为性修改」条款后 L39 追加 ⚠️ 注记，点名三个 smoke 文件（C10）与 gis/preflight.py（C12），并指向 docs/comet/specs/README.md；9db9849 对 C1 spec 为 +1/-0，原文未改。 |
| A9 | passed | specs/c13-spec-consistency/spec.md | 标注指纹的时代口径（F3）（验收：A15） 在 `p1a-arcpy-bridge`（C2）的「优先复用 P0 缓存产物，指纹 `c9243efd`」句后追加 `⚠️` 时代口径注记：`c9243efd` 为 PV=2 历史值，当代金指纹为 `b91c09c9c6451c16`；缓存文件名含指纹（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`）；按指纹指名缓存的判据必须随 `PROCESSING_VERSION` 时代取值（C10 已把该口径立为验收 A1/A2）。原文不改。 | C2 spec L11「优先复用 P0 缓存产物，指纹 `c9243efd`」句后 L12 追加时代口径注记：PV=2 历史值、当代金指纹 b91c09c9c6451c16、缓存名 `gis/emit.py::_output_path → {slug}.{指纹8位}.tif`、必须随 PROCESSING_VERSION 时代取值（C10 A1/A2）；+1/-0，原文未改。 |
| A10 | passed | specs/c13-spec-consistency/spec.md | 回收 C10 的四列差异清单进归档面（F4）（验收：A16） 把主工作区 gitignored 的 `logs/acceptance/c10-local-changes.md`（112 行）**逐字复制**为 `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`（git 跟踪），仅在文件头部（既有 `> 位置说明` 块之前）追加一行来历注记说明「原件位置 + 由 c13-spec-consistency 回收 + 正文未改动」。除此之外正文逐字相同；原 `logs/` 副本保留不动。 | 归档件 local-changes.md 存在且 git 跟踪；与原件 logs/acceptance/c10-local-changes.md（主工作区，112 行）的 diff = 纯插入 `2a3,5`，插入点在文件头部、`> 位置说明` 块之前，内容含原件位置 + 由 c13-spec-consistency 回收 + 正文一字未改；其余正文逐字相同（首尾字节比对一致），原 logs/ 副本仍在盘上未动。注记渲染为 1 个引用块、物理 3 行（执行记录已如实写明「新增 3 行、删除 0 行」）。 |
| A11 | passed | specs/c13-spec-consistency/spec.md | capability 命名与目录名对齐（F5）（验收：A17） `docs/comet/specs/dockpane/spec.md` 的 H1 改为 `# Capability：dockpane —— Pro add-in 状态面板（change c11-dockpane 交付；C9/C10 拆出的唯一遗留项）`；`docs/comet/specs/p2-presets/spec.md` 的 H1 改为 `# Capability：p2-presets —— 数据集预设表（dataset presets）`。正文其余不动，双副本同步。 | dockpane H1 = `# Capability：dockpane —— Pro add-in 状态面板（change c11-dockpane 交付；C9/C10 拆出的唯一遗留项）`、p2-presets H1 = `# Capability：p2-presets —— 数据集预设表（dataset presets）`，发布面与归档面四份逐字符相同；9db9849 对二者分别 +12/-11（H1 1 行 + 10 个标题补引用 + 1 注记）与 +1/-1（仅 H1），正文其余未动。 |
| A12 | passed | specs/c13-spec-consistency/spec.md | 补齐 5 份 spec 的验收引用（F6）（验收：A18） 为 C7（`p3-skill-knowledge`）、C8（`p3-osm-overpass`）、C9（`p1b-arcgis-addin`）、C10（`c10-review-patches`）、C11（`dockpane`）五份 spec 的**每个** `### Scenario:` 标题补 `（验收：Ax）`，映射以 `spec-revision-list.md` 的 §F6 映射表为准（Scenario 数与 acceptance 数 1:1：5/5、8/8、8/8、9/9、10/10，合计 **40** 个 Scenario）。只补引用，不改任何判据文字；双副本同步。 | 五份 spec 的 `### Scenario:` 计数/带引用计数 = 5/5、8/8、8/8、9/9、10/10，合计 40；9db9849 的删除行全部能以「去掉（验收：Ax）后相同」在新增行中配对（orphan=NONE），证明只补引用未改判据；发布面/归档面 numstat 成对相同。 |
| A13 | passed | specs/c13-spec-consistency/spec.md | 台账补号（F7）（验收：A19） `docs/README.md` §9.2 中 C3 行的 `✅ 归档（2026-10-06，三轮独立验收 8/8）` 补上经核实的真实归档提交号。因该文件为 gitignored 本地件，按 D9 只产出**四列差异清单条目**（现状逐字 + 改为 + 依据含提交号核实方式 + 回退），由归档轮就地执行。 | 归档 spec-revision-list.md §F7 四列齐备（现状逐字含 `✅ 归档（2026-10-06，三轮独立验收 8/8）`、改为、依据、回退）；提交号核实方式与结果登记在同文件 F7 执行记录行（1fae53d，方法 `git log --diff-filter=A -- docs/comet/archive/2026-10-06-p2-timeseries/comet-state.yaml`）。我按该方法复跑得到同一 1fae53d（真实提交），且主工作区 docs/README.md L406 已就地执行为 `✅ 归档（2026-10-06，三轮独立验收 8/8；提交 1fae53d）`。 |
| A14 | passed | specs/c13-spec-consistency/spec.md | 措辞与实现对齐（F8）（验收：A20） `c12-preflight-endpoint-probe` spec 的「测试全部离线且不污染本机」场景中，「进程内起假服务器」改为「子进程承载的假服务器」并说明原因（`tests/unit` 受离线守卫约束不得导入 `socket`/`http`/`urllib`，故假服务必须外置为 `subprocess` + `sys.executable -c`）。双副本同步。 | c12 spec L52 场景「测试全部离线且不污染本机（验收：A16）」正文 L54 已是「**子进程承载的假服务器**（`subprocess` + `sys.executable -c`…）」并写明原因（tests/unit 受离线守卫约束不得导入 socket/http/urllib）；旧表述「进程内起假服务器」全文 0 命中；发布面/归档面哈希相同；test_offline_guard.py 的 BANNED 名单（含 socket/http/urllib）印证理由。 |
| A15 | passed | specs/c13-spec-consistency/spec.md | 结构不变量守卫（G1）（验收：A21） 新增 `tests/unit/test_comet_spec_consistency.py`（离线、只读文件、不导入网络库），断言四条不变量： 1. `docs/comet/specs/<cap>/spec.md` 的 H1 形如 `# Capability：<cap> —— …`（cap 恰为目录名）； 2. 每个发布面 spec 在 `docs/comet/archive/*/specs/<cap>/spec.md` 有**逐字节相同**的副本； 3. 每个 `### Scenario:` 标题都带 `（验收：A…）` 引用； 4. 每个归档 change 目录含 `brief.md`、`comet-state.yaml`、`verification.md`、`specs/*/spec.md`。 该守卫在本次修订**之后**必须全绿；对任一不变量的破坏（例如改名 H1、删副本、去引用）必须使它失败。 > ⚠️ **c20 修订（不变量 4 的豁免）**：原句要求**每个**归档 change 目录都含 `specs/*/spec.md`， > 未考虑 Comet Runtime 的「**不改变产品行为**」豁免 —— change 的 `brief.md` 写一行合规声明即可 > 免写目标 Spec，此类 change 归档后其归档目录**本来就没有** `specs/`，原判据会让本守卫长期转红 > （c19-verify-report-drift 归档后 main 全量单测 393 例 1 失败即此）。现判定改为：归档目录必须含 > `brief.md`/`comet-state.yaml`/`verification.md`；`specs/*/spec.md` 缺失时，**仅当** `brief.md` 的 > 可见行（排除标题行与围栏内代码）含合规豁免声明 —— 形如 `不改变产品行为` / `不涉及产品行为` / > `仅文档` / `no product behavior change` / `documentation-only` 后紧跟 `：` 或 `:`，且理由非占位 > （空、`<…>`、`{{…}}`、TODO/待填写一类）—— 才放行。判据与 Runtime 的 `hasExplicitSpecExemption` / > `isPlaceholderExemptionReason` 同源。原句保留不删；实现见 `tests/unit/test_comet_spec_consistency.py` > 的 `archive_completeness_problems` / `spec_exemption_reason`。 | guard 只 import os/pathlib/re/tempfile/unittest（无网络库），test_offline_guard 在全量批次内通过；四类不变量分别由 PublishedSpecSurfaceTest / PublishedArchivePairTest / ScenarioAcceptanceReferenceTest / ArchiveCompletenessTest(+ArchiveSpecExemptionTest) 断言；本次修订后全绿。我在临时假仓库逐条破坏：改 H1、改一份归档副本、去掉一个标题引用、删 specs 且无豁免、造孤儿 capability —— 每次只有对应断言转红，完整基线与合规豁免样本全绿。 |
| A16 | passed | specs/c13-spec-consistency/spec.md | 条款级 supersession 索引（G2）（验收：A22） 新增 `docs/comet/specs/README.md`：列出 F1/F2/F3/F8 四条的条款级条目（被取代方 → 取代方 → 日期 → 一句话说明），并写明发布面四条规范：capability 命名 = 发布面目录名；每个 Scenario 必须带验收引用；按指纹指名缓存必须随时代取值；spec 双副本必须逐字节一致。 | docs/comet/specs/README.md 存在；§一 台账含 F1（C9 6530 条 + C11 三探测条两行）、F2（C1 行）、F3（C2 指纹行）的条款级条目（被取代方/取代方/日期/说明），F8 列在「就地订正」表；§二 逐条写明四条发布面规范（capability 命名=目录名；Scenario 必须带标题内引用；按指纹指名缓存必须随时代取值；双副本逐字节一致）。 |
| A17 | passed | specs/c13-spec-consistency/spec.md | 不变量与回归（A11）（验收：A23） 修订完成后：发布面 specs ↔ 归档副本**逐字节一致**（含修订后的 12 份）；`gis/**`、`Pro/**`、`scripts/**`、`geocode.json` 零 diff；`gis/spec.py` 的 `PROCESSING_VERSION = 3` 未改；`python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics` 两条入口全绿（含新增守卫）。 | 独立脚本核对 16/16 发布面 spec 均有逐字节相同的归档副本（0 缺副本/0 不一致）；gis/**、Pro/**、scripts/**、geocode.json 对本 change 零 diff；gis/spec.py L45 `PROCESSING_VERSION = 3`；两条入口实跑全绿（discover -s tests/unit = 399 OK skipped=10；tests.unit.test_spec_basics = 20 OK）。场景括注「含修订后的 12 份」是 C13 时代数量，今日 16 份全部满足该不变量（更严格成立）。 |
| A18 | passed | specs/c13-spec-consistency/spec.md | 修订清单回填（A12）（验收：A24） `spec-revision-list.md` 的 8 条全部四列齐备（现状/改为/依据/回退），且执行后逐条回填执行状态与证据（涉及文件行号、双副本一致性校验方式、F4 的 diff 结论、F6 的 40 个 Scenario 计数、F7 的提交号核实方式）。 | 归档 spec-revision-list.md 的 F1–F8 每条都有「现状/改为/依据/回退」四列；文末执行记录逐条回填状态（F1–F8、G1、G2、A12；F7 如实标 ⏳ 待归档轮执行，与 D9 一致）与证据：F1 给出 C9 L57 与 C11 段落锚点及双副本逐字节一致方式、F4 给出 diff 结论（新增 3 行、删除 0 行，5800→6003 字节）、F6 给出 40 条计数（5+8+8+9+10）、F7 给出提交号核实方式。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| tests/unit 全量离线单测（unittest discover） | -m unittest discover -s tests/unit | . | passed | 0 | 21709 ms |
| ruff 门禁（离线，零下载） | --offline ruff@0.17.0 check | . | passed | 0 | 214 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- tests/unit/test_comet_spec_consistency.py（守卫单模块）: passed — Ran 14 tests, OK；修好前 main 上为 8 tests / 1 failed
- python -m unittest discover -s tests/unit（全量）: passed — Ran 399 tests, OK (skipped=10)；既有 393 例零回归 + 新增 6 例
- python -m unittest tests.unit.test_spec_basics: passed — Ran 20 tests, OK
- uvx --offline ruff@0.17.0 check: passed — All checks passed!
- 合成用例豁免判定演示（logs/acceptance/c20_exemption_demo.py）: passed — 9 个用例：合规豁免放行、无豁免/占位/不可见形态/缺必备件全部转红
- A5 零 diff / A6 双副本与台账核对: passed — 见 logs/acceptance/c20_a5_zero_diff.txt 与 c20_a6_dual_copy.txt
- 已知限制: A4 的字面数字与实测不同：brief 的 A4 写「全量 393 例 OK」，那是改动前基数；本 change 新增 6 条用例，实测 399 例 OK。既有 393 例全部通过、c19 造成的那 1 例红已消失。
- 已知限制: 验收项由 6 增至 18：本轮 Shape 重认时目标 Spec 首次就位，Runtime 为该能力完整规格里的 12 个既有 Scenario 各生成一条验收（brief 6 + spec 12）。A7–A18 即这 12 条 C13 时代的场景，本 change 未改其条款。
- 已知限制: A17 的场景括注「（含修订后的 12 份）」是 C13 当时的发布面 spec 数量，今日为 16 份。本 change 只对「被自身改写真假值」的条款加 ⚠️ 注记（即不变量 4），未改写这类历史括注；若 Verifier 认为该括注需就地说明，本溱回 Build 补注记。
- 已知限制: imports 块与 c18 的合并面：c18 在 import os 后插入 import re；本 change 在 import pathlib 后插入 import re 与 import tempfile。两处 hunk 相邻，若合并时该小块冲突属可读可解的局部冲突。
- 已知限制: 豁免判据是「镜像」Runtime（hasExplicitSpecExemption / isPlaceholderExemptionReason）而非共享代码：Runtime 升级时守卫需人工同步；已写进被修订 spec 的 ⚠️ 注记与台账。
- 已知限制: 守卫只核对 brief.md 是否声明了合规豁免，不核对理由与改动范围是否相称（语义级判断留给 Verifier 与人工审阅）。
- 已知限制: 本 change 不改 c19 归档目录既有内容（仍无 specs/，现由豁免规则放行）；也不改 c18 的 Scenario 引用形态放宽。
- 已知限制: 未跑 tests/verify_all.py 入口（本 change 不涉及入口契约）；Runtime 已独立执行 unit-tests 与 ruff 两项检查。证据文件在 logs/acceptance/（gitignore），可用 bash logs/acceptance/c20_evidence.sh 复现。

## 阻塞项

_无。_

## 风险与跳过的工作

- 豁免判据是「手工镜像」Runtime（hasExplicitSpecExemption / isPlaceholderExemptionReason）而非共享代码。我未能在本机定位 Runtime 实现（comet 包内搜索超时、DSH resources 无命中），故「同源」只能按规格 ⚠️ 注记所列判据逐条对拍（已全部对上），无法做源码级对拍；Runtime 若变更判据，守卫会静默漂移。
- 守卫只核对 brief.md 是否声明了合规豁免，不核对理由与改动范围是否相称：任何一行非占位文字即可放行无 specs 的归档目录。这是本 change 选定的判据（镜像 Runtime），但语义层面仍可被滥用。
- 豁免正则在可见行内做 search：句中表述（如「本 change 不改变产品行为：只改文档」）也算声明；理由写「见上」这类弱内容也放行（不在空/<…>/{{…}}/TODO/待填写 的占位枚举内）。属从宽边界。
- A4 的「393 例」与 A17 的「（含修订后的 12 份）」是历史基数/历史括注：实测今日为 399 例、16 份发布面 spec。子项均成立，但文字与今日事实有落差，后续读者按字面核对会误判。
- docs/comet/specs/README.md §三「机械守卫」描述仍写「每个归档 change 目录含 … specs/*/spec.md」，未同步本次豁免（该行不在任何验收项内，属台账自身措辞滞后）。
- 三处形态与字面表述有细微差别，均已在执行记录中如实披露、信息齐全：A10 的「追加一行来历注记」实际是 3 行折行引用块；A13 的 F7 提交号与核实方式落在执行记录行而非「依据」列；A16 的 F8 条目为 3 列表格（取代方 C13 写在日期单元格）。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 0 | recovery | — | Native target specification declarations changed | 2026-10-18T07:50:54.037Z |
| 2 | 1 | 1 | pass | — | 独立核查（自建 26 例对立样本 + 8 例不变量敏感性样本 + 旧守卫基线复现 + 两条入口实跑 + 零 diff/双副本哈希/提交考古）确认：守卫对「brief.md 含合规豁免声明」的无 specs 归档目录放行（A1，含真实 c19），对无豁免（A2）、占位理由与缺必备件（A3）一律转红并点名；main 上那 1 例红（c19）确由本次修订转绿（A4，旧守卫副本实跑复现）；gis/Pro/scripts/geocode.json/tests 相关面与 PROCESSING_VERSION、金指纹零 diff（A5）；发布面与归档面双副本逐字节一致、台账已登记、Scenario 引用齐全（A6）；A7–A14、A16–A18 所述 C13 既有条款在今日仓库均成立（含「只加注记/只补引用」的逐行配对证明、C12 场景措辞与 40 条 Scenario 计数、F7 提交号 1fae53d 的独立复核与就地执行）。18 项全部 passed，总判定 pass；风险集中在「镜像而非共享代码」「豁免不核对理由相称性」与三处历史括注/措辞形态的落差，均不改变各条验收的成立。 | 2026-10-18T08:09:15.965Z |



## 结论

独立核查（自建 26 例对立样本 + 8 例不变量敏感性样本 + 旧守卫基线复现 + 两条入口实跑 + 零 diff/双副本哈希/提交考古）确认：守卫对「brief.md 含合规豁免声明」的无 specs 归档目录放行（A1，含真实 c19），对无豁免（A2）、占位理由与缺必备件（A3）一律转红并点名；main 上那 1 例红（c19）确由本次修订转绿（A4，旧守卫副本实跑复现）；gis/Pro/scripts/geocode.json/tests 相关面与 PROCESSING_VERSION、金指纹零 diff（A5）；发布面与归档面双副本逐字节一致、台账已登记、Scenario 引用齐全（A6）；A7–A14、A16–A18 所述 C13 既有条款在今日仓库均成立（含「只加注记/只补引用」的逐行配对证明、C12 场景措辞与 40 条 Scenario 计数、F7 提交号 1fae53d 的独立复核与就地执行）。18 项全部 passed，总判定 pass；风险集中在「镜像而非共享代码」「豁免不核对理由相称性」与三处历史括注/措辞形态的落差，均不改变各条验收的成立。
