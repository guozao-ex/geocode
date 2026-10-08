# Capability：c13-spec-consistency —— 跨 change 发布面一致性修订（supersession 注记 + 载体回收 + 结构守卫）

## 定位

2026-10-08 对 C1–C12 的跨 change 审阅确认：12 个 change 全部 `done`/`pass`、发布面 specs 与归档副本 12/12 逐字节一致、§11 红线 1–8 无违反；但**发布面同时存在互斥或陈旧的「当前行为」陈述**，以及载体/命名/可追溯性/措辞四类漂移，共 8 条。

本 Spec 定义这些问题的完整目标行为：**只加注记、不改历史正文**地声明取代关系；**就地修正**纯格式/措辞缺陷；**回收**一份未入库的交付物；并加一道机械防线让同类漂移今后可被静态检出。逐条四列方案见同目录 `spec-revision-list.md`。

边界与不变量：
- **不动实现与产物**：`gis/**`、`Pro/**`、`scripts/**`、`geocode.json` 零 diff；`PROCESSING_VERSION` 不 bump；金指纹不回退；不重建 zip。
- **不重写历史**：不 amend/rebase 已推送提交；被取代条款原文一字不改。
- **双副本铁律**：spec 修订必须同时落 `docs/comet/specs/<cap>/spec.md` 与 `docs/comet/archive/<change-dir>/specs/<cap>/spec.md`，且逐字节一致（修订前后都必须成立）。
- **纯离线**：全部验收不需要网络、不需要 ArcGIS Pro。
- **README 走 D9**：`docs/README.md` 为 gitignored 本地件，只以「待执行差异清单」交付，归档轮在主工作区就地执行。

需求来源：本 change 的 `brief.md` + `spec-revision-list.md`（审阅产出的 8 条四列方案）。

## 行为规格

### Scenario: 声明取代关系（F1：`check_pro_addin` 三份互斥陈述）（验收：A13）

在 C12 spec（`c12-preflight-endpoint-probe`）的「定位」段追加 `Supersedes` 行，声明其取代 `p1b-arcgis-addin`（C9）的 6530 探测判据条款与 `dockpane`（C11）的「`check_pro_addin` 三探测语义不变」条款；并在 C9/C11 两处被取代条款之后各追加一行 `> ⚠️ 已被 c12-preflight-endpoint-probe 修订（2026-10-08）…` 注记。三份 spec 均**双副本同步**，被取代条款原文逐字未变。

### Scenario: 标注 C1 的范围声明已被后续 change 修订（F2）（验收：A14）

在 `core-contract-unit-tests`（C1）的「`tests/smoke_*.py` 保持原样；`gis/` 无行为性修改」条款后追加 `⚠️` 注记，点名 C10 修改的三个 smoke 文件与 C12 修改的 `gis/preflight.py` 行为，并指向 `docs/comet/specs/README.md`。原文不改。

### Scenario: 标注指纹的时代口径（F3）（验收：A15）

在 `p1a-arcpy-bridge`（C2）的「优先复用 P0 缓存产物，指纹 `c9243efd`」句后追加 `⚠️` 时代口径注记：`c9243efd` 为 PV=2 历史值，当代金指纹为 `b91c09c9c6451c16`；缓存文件名含指纹（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`）；按指纹指名缓存的判据必须随 `PROCESSING_VERSION` 时代取值（C10 已把该口径立为验收 A1/A2）。原文不改。

### Scenario: 回收 C10 的四列差异清单进归档面（F4）（验收：A16）

把主工作区 gitignored 的 `logs/acceptance/c10-local-changes.md`（112 行）**逐字复制**为 `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`（git 跟踪），仅在文件头部（既有 `> 位置说明` 块之前）追加一行来历注记说明「原件位置 + 由 c13-spec-consistency 回收 + 正文未改动」。除此之外正文逐字相同；原 `logs/` 副本保留不动。

### Scenario: capability 命名与目录名对齐（F5）（验收：A17）

`docs/comet/specs/dockpane/spec.md` 的 H1 改为 `# Capability：dockpane —— Pro add-in 状态面板（change c11-dockpane 交付；C9/C10 拆出的唯一遗留项）`；`docs/comet/specs/p2-presets/spec.md` 的 H1 改为 `# Capability：p2-presets —— 数据集预设表（dataset presets）`。正文其余不动，双副本同步。

### Scenario: 补齐 5 份 spec 的验收引用（F6）（验收：A18）

为 C7（`p3-skill-knowledge`）、C8（`p3-osm-overpass`）、C9（`p1b-arcgis-addin`）、C10（`c10-review-patches`）、C11（`dockpane`）五份 spec 的**每个** `### Scenario:` 标题补 `（验收：Ax）`，映射以 `spec-revision-list.md` 的 §F6 映射表为准（Scenario 数与 acceptance 数 1:1：5/5、8/8、8/8、9/9、10/10，合计 **40** 个 Scenario）。只补引用，不改任何判据文字；双副本同步。

### Scenario: 台账补号（F7）（验收：A19）

`docs/README.md` §9.2 中 C3 行的 `✅ 归档（2026-10-06，三轮独立验收 8/8）` 补上经核实的真实归档提交号。因该文件为 gitignored 本地件，按 D9 只产出**四列差异清单条目**（现状逐字 + 改为 + 依据含提交号核实方式 + 回退），由归档轮就地执行。

### Scenario: 措辞与实现对齐（F8）（验收：A20）

`c12-preflight-endpoint-probe` spec 的「测试全部离线且不污染本机」场景中，「进程内起假服务器」改为「子进程承载的假服务器」并说明原因（`tests/unit` 受离线守卫约束不得导入 `socket`/`http`/`urllib`，故假服务必须外置为 `subprocess` + `sys.executable -c`）。双副本同步。

### Scenario: 结构不变量守卫（G1）（验收：A21）

新增 `tests/unit/test_comet_spec_consistency.py`（离线、只读文件、不导入网络库），断言四条不变量：
1. `docs/comet/specs/<cap>/spec.md` 的 H1 形如 `# Capability：<cap> —— …`（cap 恰为目录名）；
2. 每个发布面 spec 在 `docs/comet/archive/*/specs/<cap>/spec.md` 有**逐字节相同**的副本；
3. 每个 `### Scenario:` 标题都带 `（验收：A…）` 引用；
4. 每个归档 change 目录含 `brief.md`、`comet-state.yaml`、`verification.md`、`specs/*/spec.md`。
该守卫在本次修订**之后**必须全绿；对任一不变量的破坏（例如改名 H1、删副本、去引用）必须使它失败。

### Scenario: 条款级 supersession 索引（G2）（验收：A22）

新增 `docs/comet/specs/README.md`：列出 F1/F2/F3/F8 四条的条款级条目（被取代方 → 取代方 → 日期 → 一句话说明），并写明发布面四条规范：capability 命名 = 发布面目录名；每个 Scenario 必须带验收引用；按指纹指名缓存必须随时代取值；spec 双副本必须逐字节一致。

### Scenario: 不变量与回归（A11）（验收：A23）

修订完成后：发布面 specs ↔ 归档副本**逐字节一致**（含修订后的 12 份）；`gis/**`、`Pro/**`、`scripts/**`、`geocode.json` 零 diff；`gis/spec.py` 的 `PROCESSING_VERSION = 3` 未改；`python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics` 两条入口全绿（含新增守卫）。

### Scenario: 修订清单回填（A12）（验收：A24）

`spec-revision-list.md` 的 8 条全部四列齐备（现状/改为/依据/回退），且执行后逐条回填执行状态与证据（涉及文件行号、双副本一致性校验方式、F4 的 diff 结论、F6 的 40 个 Scenario 计数、F7 的提交号核实方式）。
