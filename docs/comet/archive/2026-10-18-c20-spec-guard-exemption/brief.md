# 目标

让发布面结构守卫的不变量 4 认识 Comet Runtime 的「不改变产品行为」豁免：当归档 change 的 `brief.md` 含**合规（非占位）**的豁免声明时，允许其归档目录没有 `specs/*/spec.md`；同时保留对「本该带 spec 变动却丢了 `specs/`」的检出。

要解决的问题（已实测）：c19-verify-report-drift 按用户裁决走「不改变产品行为」豁免（无目标 Spec），归档后 `docs/comet/archive/2026-10-18-c19-verify-report-drift/` 只有 `brief.md` / `comet-state.yaml` / `verification.md`，于是 main 上 `python -m unittest discover -s tests/unit` 由 393 例全绿变为 **393 例 1 失败**，唯一失败即既有守卫 `test_comet_spec_consistency.py::ArchiveCompletenessTest::test_archive_dirs_have_required_artifacts`（报错：`2026-10-18-c19-verify-report-drift: 缺  无 specs/*/spec.md`）。这是 **Runtime 的豁免能力与仓库结构守卫之间的契约缺口** —— c19 是第一个走豁免的 change，第一次把它暴露出来。

# 范围

## 目录结构

### 新建

- `docs/comet/changes/c20-spec-guard-exemption/specs/c13-spec-consistency/spec.md` —— 本 change 的目标规格：`c13-spec-consistency` 能力的**完整规格**（含本次对不变量 4 的修订）。归档时 Runtime 会把它变成该 change 的归档副本；**Build 期间它必须与发布面 + 既有归档副本逐字节一致**。

### 修改

- `tests/unit/test_comet_spec_consistency.py` —— 只动 `ArchiveCompletenessTest` 这一个类：不变量 4 增加豁免识别（`brief.md` 含合规豁免声明时放行无 `specs/` 的归档目录），并补一条破坏性自证用例（占位理由必须仍判红）。不变量 1/2/3 的语义不动。
- `docs/comet/specs/c13-spec-consistency/spec.md` —— Scenario G1（验收：A21）的正文：不变量 4 原文**保留不删**，就地补 `⚠️ c20 修订` 注记并写明豁免判据（C13/C17 先例：原文 + 注记 + 台账登记）。
- `docs/comet/archive/2026-10-08-c13-spec-consistency/specs/c13-spec-consistency/spec.md` —— 上条发布面规格的归档双副本，**逐字节同步**（不变量 2 要求）。
- `docs/comet/specs/README.md` —— 台账追加一行（就地订正表），登记本次对不变量 4 的修订、依据与日期。

### 删除

无

### 明确不建

- 不改不变量 1/2/3 的任何语义 —— 本次只动不变量 4 的判定；
- 不给「豁免型 change」自动生成最小 spec —— 那会让 Runtime 的豁免能力形同虚设；
- 不改 `docs/comet/archive/2026-10-18-c19-verify-report-drift/` 的既有内容（它是既成事实；本次是让守卫学会接受它）；
- 不碰 c18 的改动面（`gis/**`、`gis/container.py`、`tests/unit/test_container_dtype.py`、`tests/unit/test_export_chunks.py`、`tests/unit/test_spec_fingerprint.py`、`README.md`）；
- 不建 CI、不改 `tests/verify_all.py` 的 RUN 层与退出码语义。

# 非目标

- **不修 c18 的守卫改动**：c18 让守卫接受了 Runtime 的 Scenario 正文引用形态（中段 hunk），那是它自己的范围；本 change 只动文件末段的归档完整性断言；
- **不改 Runtime 本身**：豁免判据以 Runtime 现有实现为准（`native-portable-requirements.js` 的 `hasExplicitSpecExemption`），守卫只是**镜像**它，不发明新规则；
- **不重构守卫**：不抽公共模块、不改测试类组织，只做最小定点修改；
- **不顺手修其它既有缺陷**：发现即记录，报用户裁决。

# 验收示例

- A1: 守卫对「无 `specs/` 且 `brief.md` 含合规豁免声明」的归档目录放行：构造一个最小归档目录（`brief.md` 带一行「不改变产品行为：<具体理由>」+ `comet-state.yaml` + `verification.md`，**无** `specs/`）后，该目录不再出现在违规列表里。
- A2: 守卫对「无 `specs/` 且 `brief.md` 未声明豁免」的归档目录**仍然报错**并点名该目录（证明放行不是无条件放宽）。
- A3: 破坏性自证：把豁免理由改成占位形态（空理由、`<TODO>`、`{{reason}}`）后必须重新转红；且把 `missings` 的其它必备件（`brief.md` / `comet-state.yaml` / `verification.md` 之一）去掉时也必须转红。
- A4: 回归：main 当前那 1 例红（c19 归档目录）转绿，`python -m unittest discover -s tests/unit` 全量 393 例 OK（skipped=10）；`uvx --offline ruff@0.17.0 check` 零告警。
- A5: 零 diff：`gis/**`、`Pro/**`、`scripts/**`、`geocode.json`、`tests/verify_all.py`、`tests/smoke_*.py`、`PROCESSING_VERSION` 与金指纹 `b91c09c9c6451c16` 均零 diff；`docs/comet/specs/` 下**只有** `c13-spec-consistency/spec.md` 与 `README.md` 有改动。
- A6: 发布面/归档面双副本逐字节一致：`docs/comet/specs/c13-spec-consistency/spec.md` 与其**全部**归档副本哈希相同；台账 `docs/comet/specs/README.md` 确有登记本次修订的新行；修订后的 spec 里 Scenario 标题全部仍带 `（验收：A…）`。

# 约束与不变量

- **豁免判据与 Runtime 同源**（镜像 `hasExplicitSpecExemption` + `isPlaceholderExemptionReason`）：只看 `brief.md` 中**可见行**（排除标题行与围栏内代码），行内匹配 `不改变产品行为 / 不涉及产品行为 / 仅文档 / no product behavior change / documentation-only` 之后紧跟 `：` 或 `:`，且分隔符之后的理由**非占位**（空、`<…>`、`{{…}}`、去装饰后为空）。
- **原文零删除**：对 `docs/comet/specs/c13-spec-consistency/spec.md` 只追加注记与最小改写，被改条款原句保留。
- **双副本纪律**：任何发布面 spec 修订必须同步其全部归档副本，逐字节一致。
- **只动末段**：`tests/unit/test_comet_spec_consistency.py` 的改动限定在 `ArchiveCompletenessTest` 类内。
- **与 c18 的协调风险**：c18（`comet/c18-container-dtype`，已提交 `3ab6d39`，停在 verify/await-user）改过同一守卫文件的**中段**。本 change 只动**末段**，git hunk 不重叠，预期自动合并；一旦归档合并出现冲突 → **停下报告**，不自行 rebase 已归档分支。
- **离线**：守卫与其用例只读文件、不导入网络库（既有 `test_offline_guard.py` 会扫 `tests/unit/*.py`）。
- **不改 `tests/verify_all.py`**、不改入口退出码语义。

# 决策

- **只改守卫的判定、不改 Runtime**：豁免是 Runtime 的正式能力（brief 里一行即可免写目标 Spec），守卫不应与之矛盾；镜像同一判据可保证两边不漂移；
- **必须同时修订发布面 Spec**：`c13-spec-consistency` 的 Scenario G1 把不变量 4 写成了能力条款，改行为就必须改规格（台账纪律：改动既有 capability 行为须登记）；仅改测试而不改规格会让发布面与实现脱节 —— 这正是 C13 立这条守卫要防的事情；
- **放行条件挂在 `brief.md` 的豁免声明上**，而不是「归档目录没有 `specs/` 就一律放行」—— 后者会掩盖「有 spec 变动却丢了 `specs/`」的真事故；
- **不做 c18 的活**：Scenario 引用形态（标题内 vs 正文行）归 c18，本 change 不碰；
- **最小定点修改**：不抽公共模块、不重构守卫文件。

# 待解决问题

无 —— 本 change 的范围由「c19 归档暴露的守卫缺口」与仓库既有的发布面纪律共同确定；实现层面的判据与落点属可由 Agent 决定的选择，已在「决策」中写明依据。实现期间若出现会改变用户可见结果的新歧义，在此新增 `[blocking]` 项并停下提问。

# 验证预期

- **A1–A3 必须做破坏性自证**：既要给「合规豁免 → 放行」的证据，也要给「无豁免 / 占位理由 / 缺必备件 → 转红」的证据，前后对照输出都保留在 `logs/acceptance/`（已 gitignore）；
- **A4 的回归是本次的核心价值**：必须在修好后实跑全量 `unittest discover -s tests/unit`，确认 393 例 OK、main 上那条红消失；
- **A6 用哈希对照**：`docs/comet/specs/c13-spec-consistency/spec.md` 与 `docs/comet/archive/*/specs/c13-spec-consistency/spec.md` 逐字节比较；
- 构造件优先放 `logs/acceptance/` 与系统临时目录，不写真实产物；确需临时改动时按「临时改 → 跑 → 立即还原 → 核哈希」；
- **独立验收**：由新的只读 Verifier 独立判断全部验收项，Builder 不自行宣布通过。
