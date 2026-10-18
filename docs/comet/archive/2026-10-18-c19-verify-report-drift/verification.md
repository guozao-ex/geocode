---
generated_from_state_version: 8
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 1
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-18T07:35:56.601Z
- 摘要: 六项验收 A1-A6 全部通过，全部结论由我自己跑命令、读文件、构造对立样本独立得出，未采信 Builder 的结论（其 logs/acceptance/* 仅当线索，且抽样复跑结果与我自建样本一致）。实测要点：facts_check 一致→0／措辞反向→1 且点名检查项与断言（P5 + check 名 + 盘上证据）／还原→0；diff 相同→0／构造 run↔skip + 耗时翻倍 + probe.hit 翻转→1 且 --json 逐类别逐项列出；两工具 AST 级零网络导入，唯一子进程是只读 git rev-parse；393 例全绿（352 存量 def test_ + 41 新增，10 skip 全部来自存量 skipUnless）；ruff 零告警；损坏输入统一退出码 2、可读错误、无裸 traceback、调用方继续执行；禁改面（gis/、tests/verify_all.py、tests/smoke_*.py、tests/unit 既有用例、根 README.md、docs/comet/specs/**）零 diff，PROCESSING_VERSION=3 与金指纹 b91c09c9c6451c16 未动；A6 的 --help、docstring 用法与 README 四项覆盖（含 worktree 无 data/ 的事实根差异）齐备。残留风险为文档粒度、启发式覆盖面与证据自持性一类，均不构成验收项缺口。全程只读：所有构造件与输出写在 C:/Users/Administrator/AppData/Local/Temp/ 下，工作区真件 mtime 与 sha256 未被本会话触碰。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: `tools/verify_facts_check.py` 在「报告与盘上事实一致」时退出码 0、零违规；人为制造一处违规 （把某条 `skip_reason` 改成与盘上相反的说法）后，退出码 1，且输出能指出是**哪个检查项**的**哪条断言**失败。 破坏性自证：不只给「全对时通过」的证据，还要保留「错的时候真的会红」的前后对照输出。 | 独立复跑：worktree 报告 logs/verify_all_report.json（13 项）→ EXIT=0，stdout「全部通过：13 个检查项在 G1-G4 / P1-P7 上零违规」。自建 doctored 副本（仅把 smoke-map-renderers-qgis 的 skip_reason 改成「已命中…在盘」，盘上实为空）→ EXIT=1，--json 精确点名 {"id":"P5","check":"smoke-map-renderers-qgis","assertion":"cache_probe 措辞与盘上事实一致","message":"前置产物缺失（data/derived/s2_beijing_test.b91c09c9.tif：exists=False，size=0 B，阈值 4096 B），但 skip_reason 出现「命中」"}；把同一副本措辞还原为真实文本 → 回到 EXIT=0，前后对照两侧齐备。另做反向失配：--facts-root D:/DEV/geocode 时同一报告声称「不存在」而主工作区盘上确有 4633924 B 该产物 → EXIT=1、2 条 P5 点名 qgis 与 arcpy；主工作区 2026-10-14 旧报告（缺 probe 字段）→ EXIT=1、12 条 P1 逐项点名。Builder 的 c19_a1_doctored.json 我单独复跑同样 EXIT=1、同一条 P5。 |
| A2 | passed | brief.md | A2: `tools/verify_report_diff.py` 对两份相同报告判「无漂移」（退出 0）；对构造出差异的两份 （某项 run→skip、耗时翻倍、`probe.hit` 翻转）退出 1，且 `--json` 输出**逐项列出差异类别**。 | 同一份报告自比 → EXIT=0（「无漂移：检查项集合、层位、状态、summary 计数、耗时与 probe 判据完全一致」）。自建 current/baseline（qgis skip→run + 状态 skip→pass + probe exists/hit false→true，tests-unit 20.7s→45.0s，summary 同步改）→ EXIT=1，--json 逐项列出：layer_changes=[{smoke-map-renderers-qgis, skip→run}]、status_changes 1、duration_drifts=[{tests-unit, from 20.7, to 45.0, delta 24.3, ratio 2.174, slower}]、probe_changes=[{exists,false→true},{hit,false→true}]、summary_changes 3。Builder 的 c19_a2_drifted.json 复跑同样 EXIT=1，给出 run→skip 方向（daemon-endpoint-probe run→skip）与耗时翻倍（20.7→45.5，2.198x slower）；反向 probe hit true→false 亦被抓到；阈值「且」语义（0.1→0.3s 不算漂移）经用例与 393 例全绿共同确认。 |
| A3 | passed | brief.md | A3: 两个工具都不发起网络请求（AST 级证据）；`tests/unit` 新增用例全绿、既有 352 个用例零回归 （`python -m unittest discover -s tests/unit` 全绿）；`uvx --offline ruff@0.17.0 check` 零告警。 | 自写 AST 扫描（独立于用例）：tools/verify_facts_check.py 仅导入 __future__/argparse/json/re/subprocess/sys/pathlib，tools/verify_report_diff.py 仅 __future__/argparse/json/sys/pathlib，banned_hits=[]，且 urlopen/socket/connect/HTTPConnection/urlretrieve 等符号零命中；唯一外部进程调用是 facts_check 的只读 git rev-parse --git-common-dir（超时 20s，非网络，失败静默回落）。我独立重跑 python -m unittest discover -s tests/unit：Ran 393 tests, OK (skipped=10)，exit 0；新文件单独跑 Ran 41 tests OK；24 个既有文件 def test_ 计数恰为 352，10 个 skip 全部来自既有 test_pro_addin.py 的 skipUnless，新文件无 skip。uvx --offline ruff@0.17.0 check --no-cache . → All checks passed!，exit 0（与 Runtime 记录一致；加 --no-cache 以免写工作区缓存）。 |
| A4 | passed | brief.md | A4: 两个工具对「报告文件不存在 / 非 JSON / 缺 schema 必需字段」的输入给出**可读错误**与退出码 2 （Q4=(a)），不抛裸 traceback、不影响调用方脚本继续执行。 | 自建 10 组损坏输入独立复跑全部 EXIT=2：diff 工具（文件不存在／非 JSON／缺 summary／schema 不符）、facts 工具（文件不存在／非 JSON --json／缺 checks／schema 不符／--facts-root 非目录）。stderr 为单行可读中文，含文件绝对路径与 JSON 定位（「第 1 行第 3 列」）；--json 时 stdout 另给 {"ok": false, "error": …}；全量扫描无任何 Traceback；exit 2 后同一 shell 继续执行后续命令（caller_still_alive=yes）。顶层必需字段口径为 schema/checks/summary，与 Q4=(a) 文字一致；逐项字段缺失（如 checks 项缺 probe 键）按断言违规判 1 而非 2，属设计口径，不构成 A4 缺口。 |
| A5 | passed | brief.md | A5: 不修改 `tests/verify_all.py`、`gis/` 全部、`tests/smoke_*.py`、`tests/unit/` 既有用例 （`git diff` 为空）；`PROCESSING_VERSION` 与金指纹未动；`docs/comet/specs/**` 零 diff。 | git diff --name-only -- gis/ tests/verify_all.py 'tests/smoke_*.py' tests/unit/ README.md docs/comet/specs/ 输出 0 行，main...HEAD 区间同样 0 行；git status --porcelain 恰为 ?? docs/comet/changes/、?? tests/unit/test_verify_report_tools.py、?? tools/（--untracked-files=all 展开为 brief.md、comet-state.yaml、新用例、tools/README.md 与两个工具），无 M/D/A；git diff --cached 为空。gis/spec.py:45 PROCESSING_VERSION = 3 未动；tests/unit/_helpers.py:45 金指纹仍 "b91c09c9c6451c16" 且零 diff；docs/comet/specs/（17 文件）零 diff 零新增；worktree HEAD = main = 2511389f6d51ba2b61bd5017048642771829cc06。brief 第 110 行确有「不改变产品行为：仅新增两个独立只读开发者工具与离线用例」豁免声明，change 目录 specs/ 无文件、无发布面 Spec 目标，与该豁免自洽。 |
| A6 | passed | brief.md | A6: 两个工具各自带 `--help` 与模块 docstring 用法示例，并有 `tools/README.md`（Q5=(a)）， 内容至少覆盖：典型调用、退出码表、`--json` 输出字段说明、以及在「主工作区 / worktree」两种情形下的 事实根差异（worktree 无 `data/`，缓存探测必然 miss）。 | 两个工具 --help 均 EXIT=0 并列出全部参数（facts_check：report/--facts-root/--json；diff：current/baseline/--json/--duration-ratio 2.0/--duration-abs-s 5.0）；两份模块 docstring 都含「用法」段与示例命令行。tools/README.md（151 行）覆盖四项要求：典型调用（两工具各 2-3 条示例）、退出码表（0/1/2 双工具对照 + 2 的覆盖清单）、--json 说明（categories 六类键名与含义、probe_changes 字段清单、facts_check 逐条 violations 与 G1-G4/P1-P7 断言 ID 表、错误态 {"ok": false, "error": ...}）、以及「主工作区 / worktree 事实根差异」（三级回落 + git --git-common-dir 推主工作区根 + linked worktree 无 data/ 故 cache_probe 必然 hit=false、跨根核对会红）。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| tests/unit 全量离线单测（unittest discover） | -m unittest discover -s tests/unit | . | passed | 0 | 20297 ms |
| ruff 门禁（离线，零下载） | --offline ruff@0.17.0 check | . | passed | 0 | 182 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- tests/unit 全量（python -m unittest discover -s tests/unit）: passed — Ran 393 tests，OK (skipped=10)；既有 352 例零回归，新增 41 例
- uvx --offline ruff@0.17.0 check: passed — All checks passed!（零告警）
- tests/verify_all.py 在 worktree 内一条命令跑通: passed — RUN 4 PASS / FAIL 0 / SKIP 9，含新 ruff-check 项；报告已带 probe；logs/acceptance/c19_entry_run.txt。全程未触碰主工作区产物，跑前确认 6531 空闲、未跑 arcpy
- A1 破坏性自证（措辞与盘上事实相反）: passed — 一致时 EXIT=0 零违规；人为反转一条 skip_reason 后 EXIT=1 且点名 P5/检查项/断言
- A2 破坏性自证（构造漂移）: passed — 相同报告 EXIT=0 无漂移；构造 run->skip + 耗时翻倍 + probe.hit 翻转后 EXIT=1，--json 逐类别列出
- A4 损坏输入: passed — 5 例（缺文件/非 JSON/缺 summary/缺 checks/阈值非法）全部 EXIT=2，可读错误、无 Traceback
- A5 零 diff 核对: passed — gis/、tests/verify_all.py、tests/smoke_*.py、tests/unit/ 既有用例、README.md、docs/comet/specs/ 的 git diff 全为空
- 已知限制: P1 把「缺 probe 键」判为违规：c17 之前的旧报告（如主工作区 logs/ 下那份 2026-10-14 的 verify_all_report.json）会因此红 12 条 P1。这是有意的旧 schema 检出，但使用者需知道「红」不等于本 change 出错；显式写 "probe": null 是合法的。
- 已知限制: P7（cache_probe.hit 与层位自洽）、P1 的缺键判定、G3/G4（passed/failed 计数）超出用户提示词逐条列举的断言清单，属同一主题（措辞/计数/层位/probe 与事实一致）下的补充断言；已在 tools/README.md 与本次交接显式披露，用户可否决。
- 已知限制: verify_facts_check.py 会调用一条只读 git 命令（git rev-parse --git-common-dir，subprocess，超时 20s）用于解析主工作区根；不引入任何网络导入。git 不可用或事实根不在 git 仓库内时静默回落到「主工作区根 = 事实根」，此时 P6 退化为同根核对。
- 已知限制: 跨根语义：事实根默认从报告 checks[].log_path 反推；显式传一个与报告生成根不同的根（例如 worktree 报告 + --facts-root 指向主工作区）会让 P5 按该根判定并转红 —— 这是「跨根核对」的设计用途，不是缺陷，但使用者需理解其含义。
- 已知限制: 耗时漂移双向都算漂移（direction=slower/faster）：机器变快同样会转红，可用 --duration-ratio 放宽。
- 已知限制: 差异类别只覆盖 brief 列出的六类（检查项集合/层位/状态/summary 计数/耗时/probe）；coverage_matrix、uncovered_modules、overall 的变化不在对比范围内。
- 已知限制: 两工具未接入 tests/verify_all.py 的 RUN 层、也不进 CI（按范围硬约束），需人工或后续 change 调用。
- 已知限制: 本 change 未驱动任何 arcpy 项（worktree 无 data/，渲染两项自然 SKIP），故未受 arcpy 耗时抖动影响，也未验证「缓存命中态下渲染两项自动入 RUN」的新旧对比 —— 该场景需在主工作区（有 data/derived）生成报告，属本 change 范围之外。
- 已知限制: P6 只识别 skip_reason 里 data/ 开头的产物路径；若断言以其它形态提及产物（例如只写文件名或换用 logs/ 路径），不会被机械抓到。

## 阻塞项

_无。_

## 风险与跳过的工作

- tools/README.md 的 --json 说明以「类别/键名 + 断言 ID」为主，未逐一枚举顶层键 schema/ok/counts/current/baseline/duration_thresholds；满足「至少覆盖」，但字段清单不完整。
- 两工具都以 except Exception 兜底，把任何未预期异常折叠成退出码 2（前缀「未预期的内部错误」）；对调用方友好，但实现缺陷会被表述成「输入错误」且不再暴露 traceback。本次未触发该分支。
- brief/README 称「worktree 完全没有 data/」措辞不精确：实测存在空目录 data/{deliver,derived,raw}（0 个文件）；操作性结论（该根下 cache_probe 必然 miss）成立，已被独立核对（a1_real 报 exists=False 与盘上一致，跨根核对在主工作区确见 4633924 B 产物）。
- P5 是关键词 + 负向后顾的启发式，只覆盖「不存在/未命中/未在盘/缺失/不在主工作区」与「命中/在盘」两组词形，同义改写（如「尚未生成」「无缓存」）不会被抓；tool_probe 的措辞不在断言面内。
- A1 的「一致」输入是 worktree 内 gitignore 的 logs/verify_all_report.json（Builder 在 worktree 跑入口生成）；我用盘上 logs/verify_all/*.log、started_at/finished_at、入口输出与磁盘事实交叉印证其真实性，但该报告不入库，复现需重跑入口（写 logs/，超出只读 Verifier 权限）。
- 我未重跑 tests/verify_all.py 入口（会写 logs/ 并启动 arcpy/daemon），A1 复用 Builder 生成的报告；六项验收判据均不依赖该重跑，Runtime 的 unit-tests / ruff-check 两项执行记录与我的独立复跑一致。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 1 | pass | — | 六项验收 A1-A6 全部通过，全部结论由我自己跑命令、读文件、构造对立样本独立得出，未采信 Builder 的结论（其 logs/acceptance/* 仅当线索，且抽样复跑结果与我自建样本一致）。实测要点：facts_check 一致→0／措辞反向→1 且点名检查项与断言（P5 + check 名 + 盘上证据）／还原→0；diff 相同→0／构造 run↔skip + 耗时翻倍 + probe.hit 翻转→1 且 --json 逐类别逐项列出；两工具 AST 级零网络导入，唯一子进程是只读 git rev-parse；393 例全绿（352 存量 def test_ + 41 新增，10 skip 全部来自存量 skipUnless）；ruff 零告警；损坏输入统一退出码 2、可读错误、无裸 traceback、调用方继续执行；禁改面（gis/、tests/verify_all.py、tests/smoke_*.py、tests/unit 既有用例、根 README.md、docs/comet/specs/**）零 diff，PROCESSING_VERSION=3 与金指纹 b91c09c9c6451c16 未动；A6 的 --help、docstring 用法与 README 四项覆盖（含 worktree 无 data/ 的事实根差异）齐备。残留风险为文档粒度、启发式覆盖面与证据自持性一类，均不构成验收项缺口。全程只读：所有构造件与输出写在 C:/Users/Administrator/AppData/Local/Temp/ 下，工作区真件 mtime 与 sha256 未被本会话触碰。 | 2026-10-18T07:35:56.601Z |



## 结论

六项验收 A1-A6 全部通过，全部结论由我自己跑命令、读文件、构造对立样本独立得出，未采信 Builder 的结论（其 logs/acceptance/* 仅当线索，且抽样复跑结果与我自建样本一致）。实测要点：facts_check 一致→0／措辞反向→1 且点名检查项与断言（P5 + check 名 + 盘上证据）／还原→0；diff 相同→0／构造 run↔skip + 耗时翻倍 + probe.hit 翻转→1 且 --json 逐类别逐项列出；两工具 AST 级零网络导入，唯一子进程是只读 git rev-parse；393 例全绿（352 存量 def test_ + 41 新增，10 skip 全部来自存量 skipUnless）；ruff 零告警；损坏输入统一退出码 2、可读错误、无裸 traceback、调用方继续执行；禁改面（gis/、tests/verify_all.py、tests/smoke_*.py、tests/unit 既有用例、根 README.md、docs/comet/specs/**）零 diff，PROCESSING_VERSION=3 与金指纹 b91c09c9c6451c16 未动；A6 的 --help、docstring 用法与 README 四项覆盖（含 worktree 无 data/ 的事实根差异）齐备。残留风险为文档粒度、启发式覆盖面与证据自持性一类，均不构成验收项缺口。全程只读：所有构造件与输出写在 C:/Users/Administrator/AppData/Local/Temp/ 下，工作区真件 mtime 与 sha256 未被本会话触碰。
