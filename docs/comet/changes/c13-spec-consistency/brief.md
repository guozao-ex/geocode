# 目标

修复 2026-10-08 对 12 个已归档 change（C1–C12）做跨 change 审阅时发现的 **8 条矛盾/不一致**，让**发布面**（`docs/comet/specs/**`）不再同时存在互斥或陈旧的「当前行为」陈述，并把交付物载体、命名、可追溯性、措辞四类漂移一次性收口；同时加一道**机械防线**，使同类漂移今后能被静态检出。

审阅已确认的正面事实（本 change 不回退）：12 个 change 全部 `done`/`pass`；发布面 specs 与归档副本 **12/12 逐字节一致**；无孤儿 capability；§11 红线 1–8 无违反；端口契约一致；台账 12 行提交号全部真实存在。

8 条问题的完整修订方案见 **`spec-revision-list.md`**（本目录内，四列：现状/改为/依据/回退），本 brief 只给范围与判据。

# 范围

**R1 真冲突（F1）**：`check_pro_addin` 探测判据在发布面有三份互斥陈述（C9 定义「6530 端口是否监听」、C11 要求「三探测语义不变」、C12 改为「端点身份匹配」）。
→ 在 C12 spec 加 `Supersedes` 声明行；在 C9/C11 的两处被取代条款旁**只加** `⚠️ 已被 … 取代` 注记（不动原文）。

**R2 同类矛盾（F2）**：C1 spec 的「`tests/smoke_*.py` 保持原样；`gis/` 无行为性修改」与 C10（改三个 smoke）、C12（改 `gis/preflight.py` 行为）抵触。
→ 加注记（不动原文）。

**R3 陈旧口径（F3）**：C2 `p1a-arcpy-bridge` spec 仍以 PV2 时代指纹 `c9243efd` 指名缓存，而 C4 已 PV 2→3、C10 已把「指纹须随时代取值」立为验收。
→ 加时代口径注记（不动原文）。

**R4 交付物载体不一致（F4）**：C10 的四列 README 差异清单只存在于主工作区 gitignored 的 `logs/acceptance/c10-local-changes.md`，未进归档面（C11/C12 同类清单都在归档里）。
→ 把原件**回收**为 `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`（正文逐字不动，仅加一行来历注记）。

**R5 命名一致性（F5）**：`dockpane` 目录的 H1 声明 `c11-dockpane`（与目录名不符）；`p2-presets` 的 H1 缺 `Capability：` 前缀。
→ 就地修正两处 H1。

**R6 可追溯性（F6）**：5 份 spec（C7/C8/C9/C10/C11）的 `### Scenario:` 全部缺 `（验收：Ax）` 引用。
→ 按 `spec-revision-list.md` 的映射表逐 Scenario 补齐（Scenario 数与 acceptance 数均 1:1：5/5、8/8、8/8、9/9、10/10）。

**R7 台账缺口（F7）**：README §9.2 的 C3 行是 12 行中唯一没有 commit 号的已归档行。
→ 核实 C3 的真实归档提交号并回填（`docs/README.md` 为 gitignored 本地件，按 D9 以「待执行差异清单」交付，归档轮在主工作区就地执行）。

**R8 措辞偏差（F8）**：C12 spec 的 A16 场景写「进程内起假服务器」，实现是子进程（`tests/unit` 受离线守卫禁导入 `socket`）。
→ 就地改为与实现一致的表述。

**新增防线（预防性，非修订）**

- **G1**：`tests/unit/test_comet_spec_consistency.py` —— 四条结构不变量（H1 形如 `# Capability：<目录名> —— …`；发布面 spec 必有逐字节相同的归档副本；每个 `### Scenario:` 必带验收引用；每个归档目录必含 brief/comet-state/verification/specs）。
- **G2**：`docs/comet/specs/README.md` —— 条款级 supersession 索引 + 发布面规范（命名、验收引用、时代口径、双副本一致）。

## 交付内容（工作分解）

1. `spec-revision-list.md`（已落）：F1–F8 四列修订清单 + F6 映射表 + G1/G2 说明；执行后逐条回填状态。
2. 6 份 spec 的注记/修正（C1、C9、C11、p1a、p2-presets、C12）**双副本同步**。
3. 5 份 spec 的 Scenario 验收引用补齐（C7/C8/C9/C10/C11）**双副本同步**。
4. `docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md`（回收件）。
5. `docs/comet/specs/README.md`（新建索引）。
6. `tests/unit/test_comet_spec_consistency.py`（新建守卫）。
7. `local-changes.md`：`docs/README.md` 的待执行差异（§9.2 C3 行补号 + §9.1/§9.2 追加 C13 台账行），四列、逐条可逆。

# 非目标

- **不改任何 change 的已确认语义**：只加注记、补引用、改 H1 与措辞；不重写任何 Scenario 的判据内容，不重跑任何历史验收。
- **不重写 git 历史**：不 amend、不 rebase 已推送提交。
- **不动实现与产物面**：`gis/**`、`Pro/**`、`scripts/**`、`geocode.json` 零 diff；不 bump `PROCESSING_VERSION`；不动金指纹；不重建 zip。
- **不做语义级冲突的自动判定**：F1 的「谁取代谁」靠 `docs/comet/specs/README.md` 的人工索引 + 注记，G1 只覆盖可机械检出的四类结构漂移。
- **不追求发布面与实现的全面一致性审计**（那是另一个范围）；本 change 只处理审阅列出的 8 条。

# 约束与不变量

- **双副本铁律**：任何 spec 修订必须同时改 `docs/comet/specs/<cap>/spec.md` 与 `docs/comet/archive/<change-dir>/specs/<cap>/spec.md`，且两者逐字节一致（当前 12/12 一致，本 change 必须保持）。
- **历史正文只加不改**：被取代条款的原文一字不改，注记以 `> ⚠️` 引用行形式追加在条款之后。
- **纯离线**：G1 守卫只读文件；全部验收不需要网络、不需要 ArcGIS Pro。
- **README 走 D9**：`docs/README.md` 与 `geocode.json` 是本地件，只以差异清单交付、归档轮在主工作区执行。
- **改动面白名单**：`docs/comet/**`（specs 与 archive 面、change 目录）、`tests/unit/**`、以及归档轮的 `docs/README.md` 本地件。此外零 diff。

# 关键决定

1. **只加注记、不重写历史正文**：被取代条款保留原样 + `⚠️` 指针，既消除「互斥的当前陈述」歧义，又不伪造历史（可回退性最好）。
2. **capability 名以发布面目录名为准**：`dockpane` 的 H1 改为 `Capability：dockpane`，用正文点明 change 名 —— 与其余 10 份一致（Runtime 的 `specs/<capability>/spec.md` 路径约定）。
3. **F6 用「补引用 + 映射表留档」而非改判据**：映射逐条落表（含 1:1 计数证据），执行异常时以 acceptance 文本为准。
4. **F4 是回收而非重造**：原件仍在盘上，逐字复制 + 一行来历注记，不做任何重构。
5. **加 G1/G2 防线**：F1–F6 本质是同一类漂移的不同实例，其中四类可机械检出；不建防线的话下次审阅还要手工重来。

# 验收示例

- **A1（F1）**：C12 spec 含 `Supersedes` 声明行；C9（`p1b-arcgis-addin`）与 C11（`dockpane`）的对应条款旁各有 `⚠️ 已被 … 取代` 注记；三份 spec 双副本逐字节一致；被取代条款原文逐字未变（可与 C13 前归档副本比对）。
- **A2（F2）**：C1 spec 的绝对表述旁有 `⚠️` 注记，明确点出 C10 改的三个 smoke 与 C12 改的 `gis/preflight.py`。
- **A3（F3）**：`p1a-arcpy-bridge` spec 的 `c9243efd` 处有时代口径注记（PV2 历史值 / 当代 `b91c09c9c6451c16` / 缓存名含指纹 / 须随时代取值）。
- **A4（F4）**：`docs/comet/archive/2026-10-08-c10-review-patches/local-changes.md` 存在且 **git 跟踪**；其正文与原 `logs/acceptance/c10-local-changes.md` 除新增一行来历注记外**逐字相同**（可用 diff 核）。
- **A5（F5）**：`docs/comet/specs/dockpane/spec.md` 的 H1 以 `# Capability：dockpane —— ` 开头；`p2-presets` 的 H1 以 `# Capability：p2-presets —— ` 开头；两份双副本一致。
- **A6（F6）**：C7/C8/C9/C10/C11 五份 spec 的**每个** `### Scenario:` 标题都带 `（验收：A…）`，且与 `spec-revision-list.md` 的映射表一致；总数 5+8+8+9+10=40 个 Scenario 全部覆盖。
- **A7（F7）**：`local-changes.md` 含 §9.2 C3 行补号条目（四列齐备、含真实提交号与回退动作），且该提交号已核实存在于 git 历史。
- **A8（F8）**：C12 spec 的 A16 场景表述改为「子进程承载的假服务器」并说明离线守卫原因；双副本一致。
- **A9（G1）**：`tests/unit/test_comet_spec_consistency.py` 存在且全绿；其四条断言在人为破坏任一不变量时确实失败（可用临时副本或 mock 演示，不改仓库文件）。
- **A10（G2）**：`docs/comet/specs/README.md` 存在，含 F1–F3、F8 的条款级条目与四条发布面规范。
- **A11（不变量）**：发布面 specs ↔ 归档副本 **12/12（含修订后）逐字节一致**；`gis/**`、`Pro/**`、`scripts/**`、`geocode.json` 零 diff；`PROCESSING_VERSION = 3` 未改；`python -m unittest discover -s tests/unit` 与 dotted-path 入口全绿（含新增守卫）。
- **A12（清单）**：`spec-revision-list.md` 的 8 条全部四列齐备、且执行后逐条回填了执行状态与证据（行号/提交号/校验方式）。

# 验证预期

- 全部离线：G1 守卫只读文件；spec 修订可用逐字节比对与原文保留性检查验证（与 C13 前的归档副本对比可证明「只加不改」）。
- 独立验收需复跑两条测试入口，并**独立**核：双副本一致性（12/12 + 修订后仍一致）、F4 回收件的正文同一性（diff 仅一行来历注记）、F6 的 40 个 Scenario 覆盖率与映射一致性、被取代条款原文未变。
- 归档轮在主工作区执行 `docs/README.md` 差异（§9.2 C3 补号 + C13 台账行），并回填 C13 的提交号。
