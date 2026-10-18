# 目标

把 c19 交付的报告核查工具从「旁路」提升为**入口的一部分**：`tests/verify_all.py` 写完报告后，自动对刚写出的报告做一次事实一致性自查，并把该自查作为一条 **RUN 检查项**写进同一份报告。入口从此机械保证「报告与盘上事实一致」，而不是靠人想起来跑工具。同时补掉 c20 独立验收报出的 **R5**：`docs/comet/specs/README.md` `三 的归档完整性条目尚未同步「合规豁免」说明。

# 范围

## 目录结构

### 新建

- `docs/comet/changes/c21-verify-all-report-selfcheck/specs/verify-all/spec.md` —— `verify-all` 能力的**完整规格**（含本次修订）。Build 期间必须与发布面 `docs/comet/specs/verify-all/spec.md` 及其 **2 份**归档副本（`2026-10-11-c14-full-functional-verification`、`2026-10-18-c17-verify-all-evidence-aware`）逐字节一致。

### 修改

- `tests/verify_all.py` —— `main()` 末尾（现第 579 行 `REPORT_PATH.write_text(...)` 与第 581 行 `return` 之间）改为**两遍写法**：①组装并写出第 1 版报告；②跑一次报告自查；③把自查结果作为 RUN 项插回 `checks`、重算 `summary` 与 `coverage_matrix`、重写报告；`MATRIX` 增一行模块（如「报告一致性」）。退出码语义按 Q2 裁决。
- `docs/comet/specs/verify-all/spec.md` —— 原文**保留不删**，就地补 `⚠️ c21 修订` 注记 + 新增 Scenario（自查接入、两遍写法、失败语义）。
- 两份 `docs/comet/archive/*/specs/verify-all/spec.md` —— 逐字节同步（不变量 2）。
- `docs/comet/specs/README.md` —— ①台账「就地订正」表追加一行登记 verify-all 的本次修订；②**R5**：`三 第 60 行「每个归档 change 目录含 `brief.md` / `comet-state.yaml` / `verification.md` / `specs/*/spec.md`」补上豁免说明。
- `tools/verify_facts_check.py` / `tools/verify_report_diff.py` —— **零改动**（Q1=(a) 走子进程调用，不耦合工具内部；Q3=(a) diff 不接入）。

### 删除

无

### 明确不建

- **不把 diff 工具接进入口**（Q3=(a) 已裁决）—— 它需要一个基线快照，而对固定基线会恒红（实测当代 vs c14 基线 = 12 处），对「与上一份比」又需要新增状态文件，且缓存层位翻转是**合法**变化；diff 保持旁路、按需手动调用；
- 不改 c19 两个工具的既有行为（除 Q1=(b) 的最小扩展）、不改它们的退出码语义；
- 不改渲染两项 / ruff-check 的既有条件项语义与其 probe 判据；
- 不动 `PROCESSING_VERSION` 与金指纹、不改 `gis/**`、不建 CI；
- 不重构 verify_all 的结构（只动 `main()` 尾部 + `MATRIX` 一行 + 必要的辅助函数）。

# 非目标

- **不追求「零前提可跑」**：自查依赖 `tools/verify_facts_check.py` 存在；缺失时按「工具不可用」处理（见 Q2 的失败语义，默认归 SKIP + 提示，与 c17 的 ruff 门禁同款风格）；
- **不做漂移门禁**：diff 保持旁路、按需手动跑；
- 不改入口对既有检查项的判定与覆盖矩阵归属；
- 不顺手修其它既有缺陷（发现即记录并报告）。

# 验收示例

- A1: 入口跑完后的报告里含一条 `report-selfcheck`（`layer=run`、`status=pass`），控制台有对应行；该项确实针对同一轮写出的报告。
- A2: **破坏性自证**：人为把报告与盘上事实搞成不一致（例如把某条 `skip_reason` 改成与盘上相反），自查必须 FAIL、入口退出码非 0，且报告里给出可读的失败摘要（含违规的 id、检查项名与断言）。
- A3: 自查失败**不掩盖**其它检查：失败时其余 RUN 项的 pass/fail 与覆盖矩阵仍如实写入，报告仍是完整合法 JSON，`logs/` 下留有自查日志。
- A4: 两遍写法下报告自洽：最终报告的 `summary` 与 `coverage_matrix` 都计入 `report-selfcheck`，且 `summary.run/passed/failed/skipped` 与 `checks` 逐项吻合（即最终报告能通过它自己那套 G1–G4 断言）。
- A5: 回归：`tests/unit` 全量全绿；`uvx --offline ruff@0.17.0 check` 零告警；入口在 worktree 内一条命令跑通（RUN 项包含新自查）。
- A6: 发布面 / 归档面（2 份）/ change 暂存**三处逐字节一致**；台账 `docs/comet/specs/README.md` 有 verify-all 本次修订的新行，且 `三 的归档完整性条目已写明「`brief.md` 含合规豁免时允许无 `specs/`」。
- A7: 零 diff：`gis/**`、`Pro/**`、`scripts/**`、`geocode.json`、`tests/smoke_*.py`、`tests/unit/` 既有用例、`PROCESSING_VERSION` 与金指纹；`docs/comet/specs/` 下**只有** `verify-all/spec.md` 与 `README.md` 有改动。

# 约束与不变量

- **报告仍是单一事实源**：第 2 版覆盖第 1 版，不产生额外中间文件（除既有的 `logs/verify_all/` 与报告本体）；
- **自指问题必须写明**：自查读的是**第 1 版**报告（不含 `report-selfcheck` 自身）的快照；这一点要写进 spec 的场景与 `tools/README.md`，避免「报告里有一条检查项却没被它自己检查到」被误读为漏洞；
- **失败语义与既有 RUN 项一致**（Q2=(a)）：自查 FAIL → 入口退出码 1；工具缺失 → SKIP + 提示，不 FAIL；
- **离线**：自查只跑本地工具，不引入任何网络导入；
- **发布面纪律**：原文零删除 + 发布面/归档面双副本逐字节一致 + 台账登记（C13 四条规范）；
- **不改 c19 工具的退出码语义**（0/1/2），入口只消费它们。

# 决策

- 自查的对象是**刚落盘的报告文件**而不是内存态 —— 工具是独立 CLI，检查真实落盘件更可信，也与「工具可单独复跑」的定位一致；
- **两遍写法**是唯一能既让自查看到完整报告、又让自查自己出现在报告里的办法；单遍写法会让自查项缺席自己的报告；
- **diff 保持旁路**：见「明确不建」的理由，它更适合人工/后续自动化按需调用；
- **R5 与本 change 合并**：R5 要改的 `docs/comet/specs/README.md` 正是本 change 登记 spec 修订的同一份文件，分两个 change 反而制造并发写；
- **Q1=(a) 接入方式**：两遍写法 + **子进程**调 `tools/verify_facts_check.py`。理由：工具保持独立 CLI、可单独复跑；入口不耦合工具内部（工具改签名不会断入口）；检查真实落盘件比内存态更可信；
- **Q2=(a) 失败语义**：自查 FAIL → 归 RUN 项失败 → `overall=fail` → 入口退出码 1（与既有 RUN 项一致，否则接入等于白接）；`tools/verify_facts_check.py` **不存在**时归 SKIP + 提示，不假红（与 c17 的 ruff 门禁同款风格）；
- **Q3=(a) diff 不接入**：保持旁路。理由见「明确不建」；
- 因此本 change **不改 c19 的两个工具**（零改动），只改入口与发布面。

# 待解决问题

无 —— 本轮 Q1–Q3 已由用户裁决，结论逐条记入「决策」。实现期间若出现会改变用户可见结果的新歧义，在此新增 `[blocking]` 项并停下提问。

# 验证预期

- **A2 必须做破坏性自证**：既要给「自查 PASS 且报告含该项」的证据，也要给「人为搞不一致 → 自查 FAIL + 退出码非 0 + 报告里有可读失败摘要」的证据，前后对照输出留在 `logs/acceptance/`；
- **A4 用报告自身验自洽**：对最终报告跑 `tools/verify_facts_check.py` 应退出 0（它的 G1–G4 会独立核对 `summary` 与 `checks` 的吻合）；
- **入口实跑只在 worktree 内**：不触碰主工作区的 `logs/` 与 `data/`；跑前确认 `127.0.0.1:6531` 空闲且无其他会话在跑 arcpy；
- **发布面三副本用哈希对照**；
- **独立验收**：由新的只读 Verifier 独立判断全部验收项，Builder 不自行宣布通过。
