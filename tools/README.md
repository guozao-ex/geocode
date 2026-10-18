# tools/ — 报告事实核查与漂移对比

本目录是报告核查工具集。两个工具全程**只读**（只读 `logs/` 与 `data/`），零网络访问。

**c21 起 `verify_facts_check.py` 已接进入口**：`tests/verify_all.py` 每轮写完报告后会自动跑它，
并把结论作为一条 RUN 检查项 `report-selfcheck` 写进同一份报告（工具缺失时该项转 SKIP，不假红）。
`verify_report_diff.py` 仍是**旁路**：按需手动调用，不参与入口判定。

## 为什么存在

c17 把 verify_all 的承诺立成「报告与事实一致」（条件项按盘上事实自动升/降层位 + 每条检查项带
`probe` 记录层位判据），但这条承诺当时没有机械防线：

- 报告里某条措辞与盘上事实脱节，只有人翻报告才会发现；
- 两次运行之间「哪些项从 RUN 掉回 SKIP、耗时是否异常漂移、probe 判据是否翻转」没有工具对比；
- c17 自己用的一次性核对脚本跑完即散落（`logs/` 被 gitignore），等于验完即失。

本目录把那套核对产品化：入库、离线、可重复执行。c21 起其中的「事实一致性核对」已由入口**每轮自动执行**，
不再是「记得去跑才有」的旁路。

## 环境

- 解释器：`C:/ProgramData/miniforge3/envs/geo/python.exe`（任意 Python 3.10+ 均可，只用标准库）。
- **零第三方依赖、零网络访问**（`tests/unit/test_verify_report_tools.py` 里有 AST 级禁网断言）。
- 报告路径参数按**当前工作目录**解析，建议在仓库根运行。

## tools/verify_report_diff.py —— 两份报告的漂移对比

```bash
# 当前报告 vs c14 基线（人类可读输出）
python tools/verify_report_diff.py logs/verify_all_report.json logs/verify_all_report.c14-baseline.json

# 结构化输出 + 自定义耗时阈值
python tools/verify_report_diff.py logs/verify_all_report.json logs/verify_all_report.c14-baseline.json \
    --json --duration-ratio 2.0 --duration-abs-s 5.0
```

参数：

| 参数 | 说明 |
|---|---|
| `<当前报告>`（位置参数） | 如 `logs/verify_all_report.json` |
| `<基线报告>`（位置参数） | 如 `logs/verify_all_report.c14-baseline.json` |
| `--json` | 以 JSON 输出结构化差异（供自动化消费） |
| `--duration-ratio` | 耗时漂移的倍数阈值，默认 `2.0` |
| `--duration-abs-s` | 耗时漂移的绝对阈值（秒），默认 `5.0` |

差异类别（`--json` 的 `categories` 键名与人类输出的小节一一对应）：

| 类别 | 含义 |
|---|---|
| `checks_added` / `checks_removed` | 检查项集合增删 |
| `layer_changes` | 层位变化（`run` <-> `skip`） |
| `status_changes` | 状态变化（`pass` / `fail` / `skip`） |
| `summary_changes` | summary 计数变化（`run` / `passed` / `failed` / `skipped`） |
| `duration_drifts` | 耗时漂移（含 `direction`：`slower` / `faster`） |
| `probe_changes` | probe 判据变化（`kind` / `path` / `exists` / `min_bytes` / `hit` / `ok` / `cmd` / `uvx`） |

**耗时漂移判据**：同一检查项**同时**满足 `max/min >= --duration-ratio` 与
`|delta| > --duration-abs-s` 才算漂移（默认「2 倍」且「绝对差超过 5 秒」）。
arcpy 项耗时受并发影响极大（实测 24-28 s，与其他重任务并发可涨到 117 s+），
「且」语义可压掉小基数放大（如 0.1 s -> 0.3 s）的误报。
`probe` 里的 `size_bytes` 是测量值（缓存重建就会变），**不**算判据变化。

## tools/verify_facts_check.py —— 报告措辞 vs 盘上事实

```bash
# 默认读 logs/verify_all_report.json，事实根从报告 log_path 反推
python tools/verify_facts_check.py

# 显式指定报告与事实根
python tools/verify_facts_check.py logs/verify_all_report.json --facts-root D:/DEV/geocode

# 结构化输出
python tools/verify_facts_check.py --json
```

参数：

| 参数 | 说明 |
|---|---|
| `[报告]`（位置参数，可省） | 默认 `logs/verify_all_report.json` |
| `--facts-root` | 核对盘上事实所用的根目录；缺省时三级回落（见下） |
| `--json` | 以 JSON 输出结构化结果（含逐条 `violations`） |

### 断言清单

全局（`G1`-`G4`，报告内部计数自洽）：

| ID | 断言 |
|---|---|
| `G1` | `summary.run` 等于 `layer == "run"` 的条数 |
| `G2` | `summary.skipped` 等于 `status == "skip"` 的条数 |
| `G3` | `summary.passed` 等于 `status == "pass"` 的条数 |
| `G4` | `summary.failed` 等于 `status == "fail"` 的条数 |

逐项（`P1`-`P7`）：

| ID | 断言 |
|---|---|
| `P1` | `probe` 字段存在且类型合法（`null` / `cache_probe` / `tool_probe`），并带齐该类型的必需字段 |
| `P2` | `layer` 取值只能是 `"run"` 或 `"skip"` |
| `P3` | `layer == "run"` 的项必须有真实 `status`（`pass` / `fail`）与大于 0 的耗时 |
| `P4` | `layer == "skip"` 的项 `status` 必须为 `"skip"` 且耗时必须为 0 |
| `P5` | `cache_probe` 措辞与盘上事实一致：产物在盘时 `skip_reason` 不得出现「不存在 / 未命中 / 缺失」；产物缺失时不得出现「已命中 / 在盘」 |
| `P6` | 断言「不在主工作区」的 `skip_reason`，若其点名的 `data/...` 产物确实存在于主工作区盘上，即为违规 |
| `P7` | `cache_probe.hit` 与层位自洽：命中应在 `run` 层，未命中不应在 `run` 层 |

> 措辞判定细节：「命中 / 在盘」用负向后顾排除否定形态，所以 `未命中`、`未在盘` 不会被误判成
> 「声称命中」。`P1` 把「缺 `probe` 键」也判为违规（c17 之前的旧报告 schema）；
> 显式写 `"probe": null` 是合法的。`P7` 是 c17「条件项自动升降层位」契约的机械兜底。

## 事实根与主工作区根

`verify_facts_check.py` 需要知道「去哪里看盘上事实」：

1. `--facts-root` 显式指定；
2. 从报告 `checks[].log_path` 反推报告生成根（形态 `<root>/logs/verify_all/<name>.log`）；
3. 回落到当前工作目录。

再用 `git rev-parse --git-common-dir` 从事实根推出**主工作区根**（worktree -> main），
专门核对 `P6` 这类「不在主工作区」断言 —— c17 的原始 bug 正是报告在 worktree 里生成、
却断言某产物不在主工作区，而该产物其实在主工作区盘上。

> 关于 `subprocess`：`verify_facts_check.py` 是**唯一**会调外部程序的地方，且只调一条只读命令
> （`git rev-parse --git-common-dir`，超时 20 s）。它不是网络访问；git 不可用、或事实根不在
> git 仓库内时会静默回落到「主工作区根 = 事实根」（此时 `P6` 退化为同根核对）。

**主工作区 / worktree 的差异（重要）**：`data/` 与 `logs/*` 都在 `.gitignore` 里，因此
linked worktree **没有** `data/`、也没有主工作区那份 `logs/verify_all_report.json`。
于是：

- 在 worktree 里跑 `tests/verify_all.py` 生成的报告，其 `cache_probe` 必然 `hit=false`
  （该根下确实没有 `data/derived/...`），对应项按 `skip` 落层、措辞写「不存在」——这是**一致**的；
- 拿这样一份报告去比对主工作区（`--facts-root D:/DEV/geocode`）就会红：主工作区**确有**该产物，
  而报告声称不存在 —— 这正是「跨根核对」要抓的失配。

## 退出码

| 工具 | 0 | 1 | 2 |
|---|---|---|---|
| `verify_report_diff.py` | 无漂移 | 有漂移 | 用法或输入错误 |
| `verify_facts_check.py` | 零违规 | 有违规 | 用法或输入错误 |

`2` 覆盖：文件不存在、非 UTF-8、非 JSON、顶层非对象、`schema` 不符、缺 `checks`/`summary`、
同一报告内检查项重名、`--facts-root` 不是已存在目录、阈值非法（`--duration-ratio <= 0` 等）。
输入错误只打印可读消息（`--json` 时同时在 stdout 给一个 `{"ok": false, "error": ...}` 对象），
不抛裸 traceback，调用方脚本可继续执行。

## 与 tests/verify_all.py 的关系

**入口接入（c21 起）**

- `verify_facts_check.py` 由入口在**写完第 1 版报告之后**以子进程调用，对应检查项名 `report-selfcheck`：
  退出码 `0` → PASS；`1`（有违规）或 `2`（输入错误）→ FAIL，失败摘要附报告正文前若干行；
  `tools/verify_facts_check.py` **不存在**时该项转 SKIP + 提示，不 FAIL（与 c17 的 ruff 门禁同款风格）。
  它因此参与入口的 RUN 层、覆盖矩阵（模块「报告一致性」）与退出码语义。
- 入口采用**两遍写法**：先落一份**不含自查项**的报告 → 用它跑本工具 → 把结论插回 `checks`、重算
  `summary` 与 `coverage_matrix` → 整体重写。**自指说明（重要）**：自查读到的是**第 1 版**快照
  （**不含** `report-selfcheck` 自身），所以最终报告里出现这一项**不构成自我循环**；反过来，对最终
  报告单独复跑本工具仍应退出 `0` —— 它的 `G1`-`G4` 会独立核对 `summary` 与 `checks` 的吻合，
  多一条检查项不影响。
- `verify_report_diff.py` **不接入口**（保持旁路）：对固定基线会恒红，改成「与上一份报告比」又需要
  新增状态文件，且缓存层位翻转属于**合法**变化 —— 它适合按需手动调用、或由后续自动化自己管基线。

**不改盘**：两工具只读，差异/违规只经 stdout 与退出码表达（入口侧写盘的是报告本身，不是本工具）。

**不进 CI**：调用方式是命令行，是否纳入 CI 由后续 change 决定。
