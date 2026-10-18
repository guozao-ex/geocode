# 目标

把 c17 立下的「`verify_all` 报告必须与盘上/环境事实一致」这条承诺，从**一次性人工核对**升级为**入库、离线、可重复执行**的机械检查，并补齐「两次运行之间发生了什么」的对比能力。

交付两个互相独立、全程只读的开发者工具，加一套离线用例：

- `tools/verify_report_diff.py` —— 对比两份 `verify_all_report.json`（当前 vs 基线），输出结构化漂移：
  检查项集合增删、层位变化（run↔skip）、状态变化（pass/fail/skip）、summary 计数变化、
  耗时漂移（超阈时列出，阈值可配）、probe 判据变化（cache_probe.hit 翻转等）。
  必须支持 `--json`。退出码：无漂移 0 / 有漂移 1 / 用法或输入错误 2。
- `tools/verify_facts_check.py` —— 把 c17 的一次性核对脚本产品化：读报告 + 盘上事实，机械断言
  措辞、计数、层位、probe 类型一致。退出码：全通过 0 / 有违规 1 / 用法或输入错误 2（Q4=(a)）。
- `tests/unit/test_verify_report_tools.py` —— 两工具的离线用例（构造假报告，覆盖计数不一致、
  措辞违规、层位翻转、耗时漂移、probe 缺失/非法，以及「全对时零违规」）。

两个工具都是**旁路**：不接入 `tests/verify_all.py` 的 RUN 层、不改入口退出码语义、不改覆盖矩阵、
不引入任何网络导入。

# 范围

## 目录结构

### 新建

- `tools/` —— 新增顶层开发者工具目录（Q1=(a)）。依据：仓库此前**没有** `tools/`；既有 `scripts/` 承载的是
  「改盘 / 打包」类运维脚本（`prune_cache.py`、`package_pro_addin.py`），与本次「只读分析」类工具职责不同，
  故独立成目录而非塞进 `scripts/`。
  - `tools/verify_report_diff.py` —— 两份报告漂移对比；结构化差异 + `--json` + 退出码 0/1/2。
  - `tools/verify_facts_check.py` —— 报告措辞/计数/层位/probe 类型 vs 盘上事实的机械检查；退出码 0/1/2。
  - `tools/README.md` —— 两个工具的用法说明（Q5=(a)）：典型调用、退出码表、`--json` 字段说明、
    以及「主工作区 / worktree」两种情形下的事实根差异。
- `tests/unit/test_verify_report_tools.py` —— 上述两工具的离线用例；文件内自带对 `tools/*.py` 的
  AST 禁网扫描断言（既有 `test_offline_guard.py` 的 TARGETS 不含 `tools/`，且该文件属禁止修改面，
  故 `tools/` 的禁网断言只能落在本新文件里）。
- `docs/comet/changes/c19-verify-report-drift/local-changes.md` —— 仅当需要登记本地件差异时。

### 修改

无 —— 本 change 不改任何既有源码文件：`gis/**`、`tests/verify_all.py`、`tests/smoke_*.py`、
`tests/unit/` 既有用例、`README.md`、金指纹与 `PROCESSING_VERSION` 全部零 diff。
（Q3=(a) 已裁决走「不改变产品行为」豁免，不写发布面 Spec。）

### 删除

无

### 明确不建

- 不建 CI / GitHub Actions —— 本 change 只交付可手动/可被后续 change 调用的工具；
- 不新建 `tools/` 之外的第二套脚本目录 —— 避免与既有 `scripts/` 职责叠床架屋；
- 不把新检查接进 `tests/verify_all.py` 的 RUN 层、不改入口退出码语义与覆盖矩阵 —— 那是改入口契约；
- 不改 `data/` 下任何产物、不重建基线、不清理缓存 —— 缓存治理已有 `scripts/prune_cache.py` +
  `gis/cache_manage.py`；
- 不改压缩策略、不做性能优化；
- 不新增发布面 capability、不改 `docs/comet/specs/**`（Q3=(a)）。

# 非目标

- **不修任何既有缺陷**：本 change 只新增工具；过程中发现的既有问题一律记录到本 brief 的风险/待解决问题，
  由用户裁决是否另开 change，不自行扩 scope；
- **不替代人工审阅**：工具只做机械断言；语义级取代关系与台账仍靠人工索引
  （`docs/comet/specs/README.md`）；
- **不动发布面语义**：不新增/删除 capability，不改 `gis/` 运行时行为、三出口契约、daemon/TUI/Pro 契约；
- **不改金指纹 / `PROCESSING_VERSION`**：单一事实源 `tests/unit/_helpers.py::GOLDEN_FINGERPRINTS`
  （当前 `b91c09c9c6451c16`）不被本 change 触碰；
- **不做调度**：不提供守护进程、定时器、文件监听；调用方式就是命令行。

# 验收示例

- A1: `tools/verify_facts_check.py` 在「报告与盘上事实一致」时退出码 0、零违规；人为制造一处违规
  （把某条 `skip_reason` 改成与盘上相反的说法）后，退出码 1，且输出能指出是**哪个检查项**的**哪条断言**失败。
  破坏性自证：不只给「全对时通过」的证据，还要保留「错的时候真的会红」的前后对照输出。
- A2: `tools/verify_report_diff.py` 对两份相同报告判「无漂移」（退出 0）；对构造出差异的两份
  （某项 run→skip、耗时翻倍、`probe.hit` 翻转）退出 1，且 `--json` 输出**逐项列出差异类别**。
- A3: 两个工具都不发起网络请求（AST 级证据）；`tests/unit` 新增用例全绿、既有 352 个用例零回归
  （`python -m unittest discover -s tests/unit` 全绿）；`uvx --offline ruff@0.17.0 check` 零告警。
- A4: 两个工具对「报告文件不存在 / 非 JSON / 缺 schema 必需字段」的输入给出**可读错误**与退出码 2
  （Q4=(a)），不抛裸 traceback、不影响调用方脚本继续执行。
- A5: 不修改 `tests/verify_all.py`、`gis/` 全部、`tests/smoke_*.py`、`tests/unit/` 既有用例
  （`git diff` 为空）；`PROCESSING_VERSION` 与金指纹未动；`docs/comet/specs/**` 零 diff。
- A6: 两个工具各自带 `--help` 与模块 docstring 用法示例，并有 `tools/README.md`（Q5=(a)），
  内容至少覆盖：典型调用、退出码表、`--json` 输出字段说明、以及在「主工作区 / worktree」两种情形下的
  事实根差异（worktree 无 `data/`，缓存探测必然 miss）。

# 约束与不变量

- **只读**：两工具只读 `logs/` 与 `data/`，绝不写、删、改盘上产物（报告与派生数据）；
- **离线**：只允许标准库（`json`/`argparse`/`pathlib`/`hashlib`/`subprocess` 等），
  禁止 `ee` / `requests` / `httpx` / `urllib` / `socket` / `http` 等任何网络或 GEE 导入；
- **不碰 c18 改动面**：`gis/spec.py`、`gis/emit.py`、`gis/export_chunks.py`、
  `tests/unit/` 下除本 change 新建文件以外的任何文件、`tests/verify_all.py`、`README.md` 一行不动；
- **不改入口契约**：`tests/verify_all.py` 零 diff，退出码语义与覆盖矩阵不变；
- **禁止整文件覆盖既有源码**：改既有文件一律定点 edit（本 change 预期不产生既有文件修改）；
- **一个 cwd 一个写者**：派只读 Verifier / 子代理核查期间不并发改代码；
- **提交前清点**：`git status` 不得出现 `logs/` 下一次性脚本、handoff JSON 等过程件；
- **报告 schema 事实**：`schema = "geocode.verify-all.report.v1"`；每条 check 的字段为
  `name / module / layer / status / duration_s / log_path / skip_reason / note / fail_summary / probe`；
  `probe` 三态：`null`、`{"kind":"cache_probe","path","exists","size_bytes","min_bytes","hit"}`、
  `{"kind":"tool_probe","cmd","uvx","ok",…}`；
- **盘上事实（开工实测 2026-10-18）**：main HEAD `2511389`；worktree `comet/c19-verify-report-drift`
  与 main 同点；`tools/` 不存在；`tests/unit` 现有 24 个文件、**352 用例全绿**；geo 环境
  `C:/ProgramData/miniforge3/envs/geo/python.exe` **无 pytest**（统一走 `unittest`）；
  主工作区 `data/derived` 53 文件 / 3.5 GB，其中 `s2_beijing_test.b91c09c9.tif`（4,633,924 B）在盘
  → 缓存探测在该根下为 hit；**worktree 完全没有 `data/`** → 该根下必然 miss；
  主工作区 `logs/verify_all_report.json` 是 **2026-10-14 的旧件、无 `probe` 字段**，相对 c17 代码已过期；
  `logs/verify_all_report.c14-baseline.json` 在盘；`logs/*` 已被 gitignore；`127.0.0.1:6531` 空闲。

# 决策

- 不改变产品行为：仅新增两个独立只读开发者工具与离线用例，不接入 `verify_all` 入口契约、不改 `gis/` 运行时，三出口 / daemon / TUI / Pro 契约零改动。
- **Q1=(a) 落点**：新建顶层 `tools/`，不塞进既有 `scripts/`（职责分离：`scripts/` 是改盘/打包）；
- **Q2=(a) 耗时漂移判据**：`相对倍数 ≥ 2.0` **且** `绝对差 > 5.0 s` **同时满足**才算漂移；两个阈值均可用
  CLI 覆盖（默认 2.0 / 5.0）。理由：arcpy 项耗时受并发影响极大（24–28 s → 117 s+），
  「且」语义避免小基数放大误报，同时保留对 tests-unit 这类大项的敏感度；
- **Q3=(a) 不写发布面 Spec**：走「不改变产品行为」豁免（见上条），`docs/comet/specs/**` 零 diff。
  理由：工具不接入入口、不改任何产品路径；且发布面守卫要求发布面 spec 必须有逐字节相同的归档副本
  （归档副本仅由 Runtime 在归档时生成），新建/改动发布面 spec 会让既有守卫在归档前转红，
  而 c18 正在改该守卫，避免语义耦合；
- **Q4=(a) 退出码**：`verify_facts_check.py` 扩展为 0/1/2 —— 0 全通过 / 1 有违规 / 2 用法或输入错误
  （文件不存在、非 JSON、缺 `schema`/`checks`/`summary` 等必需字段）。与 `verify_report_diff.py` 对齐；
- **Q5=(a) 用法文档**：新建 `tools/README.md`。理由：`.gitignore` 把 `/docs/*` 全忽略
  （只放行 `docs/comet/`、`docs/knowledge/`），写在 `docs/` 下的说明文件不会入库；
  `tools/README.md` 与工具同处、可入库、不碰任何被禁文件；
- **Q6=(a) 事实根三级回落**：① `--facts-root` 显式指定；② 从报告 `checks[].log_path` 反推报告生成根；
  ③ 当前工作目录。再用 `git rev-parse --git-common-dir` 从生成根推出**主工作区根**（worktree → main），
  专门核对「不在主工作区」类断言。理由：c17 的原始 bug 正是「报告在 worktree 生成、却断言产物不在
  主工作区，而产物其实在主工作区盘上」，只有解析出主工作区根才能机械抓到这一类；
- **旁路而非入口**：新检查不接入 `tests/verify_all.py` 的 RUN 层 —— 依据用户范围硬约束；
- **只读工具**：工具不落盘任何产物，差异/违规只经 stdout 与退出码表达 —— 依据红线 6；
- **标准库优先**：两工具不引入任何第三方依赖，避免给离线门禁增加新前置 —— 依据红线 5；
- **测试框架口径**：新用例用 `unittest`（`tests/unit` 既有全部为 unittest，且 geo 环境未装 pytest），
  经 `python -m unittest discover -s tests/unit` 收集；
- **证据落在 `logs/acceptance/`**（已 gitignore，不入库），关键结论写进 brief 与 verification。

# 待解决问题

无 —— 本轮 Q1–Q6 已全部由用户裁决，结论逐条记入「决策」。实现期间若出现会改变用户可见结果的新歧义，
在此新增 `[blocking]` 项并停下提问。

# 验证预期

- **A1 / A2 必须做破坏性自证**：先给「一致 / 无漂移」的通过证据，再给「人为违规 / 构造漂移」的转红证据，
  前后对照输出都保留在 `logs/acceptance/`；
- **构造条件可还原**：优先用**副本**（`logs/acceptance/c19_*.json`）而非改真件；确需改真件时按
  临时改名 → 跑 → 还原 → 核对 sha256 与体积的流程，严禁删除或覆盖；
- **不做无谓的全量重跑**：若为取得带 `probe` 的报告必须跑一次入口，只在 **worktree 内**跑
  （其 `logs/` 独立且被 gitignore），不触碰主工作区的报告与产物；跑前确认 `127.0.0.1:6531` 空闲
  且无其他会话在跑 arcpy；
- **独立验收**：由新的只读 Verifier 独立判断全部验收项，Builder 不自行宣布通过。
