# Outcome

让全量验证入口 `tests/verify_all.py` 的**报告与事实一致**、并让条件项**自动升级**，同时把已存在的
静态检查门禁（ruff）接进入口 —— 一条命令同时覆盖「功能 + 静态检查」。

三处已被实测证实的错配，本 change 逐条消除：

1. **层位错配（假 SKIP）**：`smoke-map-renderers-qgis/arcpy` 在当代缓存命中时可离线跑通
   （2026-10-18 实测：qgis 5.5 s、arcpy 30.8 s，指纹 `b91c09c9c6451c16`，缓存
   `data/derived/s2_beijing_test.b91c09c9.tif` 在盘），但入口仍把它们固定在 SKIP 层，
   只在文案里承认「可离线复跑」—— 报告显示跳过的是**实际能跑**的检查。
   同类条件项 `smoke-array-chunking-rescan-big` 早已是「前置产物存在即自动升 RUN」的正确形态。
2. **措辞错配（假缺失）**：rescan-big 的 SKIP 文案在产物缺失时断言「不在主工作区」
   （`tests/verify_all.py:316`），而该产物 `s2_chunking_big_smoke.2965c18a.nc`（816 MB）
   **正在主工作区盘上**。worktree 里确实缺失，但报告把「本条 worktree 缺失」说成了
   「不在主工作区」—— 与事实不符。
3. **门禁未接入**：`ruff.toml`（提交 `d81dab0`）已存在且当前零告警，却只能手工执行，
   不在入口里；该提交自己的说明写着「门禁尚未接进 verify_all … 要接进去属规格变更」。

一句话目标：**入口报的每一行，都要么是跑过的、要么是盘上/环境里确实做不到的，且措辞不许说谎。**

## c17 追加范围（用户 2026-10-18 裁决「全量修复风险」）

原 D5 把 `gis/emit.py` 的渲染容忍度划到范围外、另立 change；用户现裁决**并入本 change 全量修复**。
已实测取证（`logs/acceptance/c17_risk_probe.py`，2026-10-18）确认三处**假 PASS**：

1. **qgis 分支局部失败被容忍**（`gis/emit.py:1048-1051`）：`branch_failed` 判据是
   `qgz_error and png_error`——**两者都失败**才算失败。实测：`.qgz` 抛错、`.png` 成功时
   `emit_map` 照常返回、`job.error` 为空，渲染项 PASS。
2. **布局失败被丢弃**（`gis/qgis_bridge.py:367` 产出 `layout_error`，`gis/emit.py:1025` 只读
   `layout` 不读 `layout_error`）：实测 `layout_error` 非空时结果里**完全没有痕迹**。
3. **arcpy 分支产物缺失未被核验**（`gis/emit.py:996-1003` 仅在 `res.get(key)` 为真时登记）：
   成功的 `write_aprx` 若缺 `pdf`/`png` 键，不报错也不计入失败。（bridge 侧导出异常目前会冒泡，
   属**防御性收紧**而非已复现缺陷，如实登记。）

同类「多产物只成其一仍算成功」的判定口径必须统一，否则 verify_all 的渲染项 PASS 不可信。

# Scope

- **条件项自动升级**：把 `smoke-map-renderers-qgis/arcpy` 改为条件项 —— 当代指纹的缓存产物存在
  （即离线可跑）时自动进入 RUN 层，缺失时保持 SKIP 且文案写实；与 `rescan-big` 同款语义与实现风格。
- **报告一致性**：报告里每一条 SKIP 的措辞必须与盘上/环境事实一致（缓存命中不得声称未命中、
  前置产物存在不得声称缺失、产物在主工作区却断言「不在主工作区」这类错配一并纠正）；
  SKIP 计数与实际条件一致。
- **ruff 门禁接进入口**：按 Q2 = (a) 把 ruff 作为**可选 RUN 项**接入 —— 有 uv/ruff 时执行并计分，
  缺失时 SKIP + 安装提示（不 FAIL）。
- **同步修订 C14 的发布面 spec**：按 Q1 = (a) 扩展 RUN 层，`verify-all` capability 的发布面 spec
  必须按 C13 纪律修订（A3/A4 口径、supersession 注记、发布面 ↔ 归档面双副本同步、结构守卫保持绿）。

## 目录结构

### 新建

无 —— 本 change 不新增源码文件；新增的只有运行时产物（`logs/verify_all_report.json` 与
`logs/verify_all/<check>.log`，均已被 .gitignore 忽略）。

### 修改

- `gis/emit.py` — **渲染失败语义收紧**：`branch_failed` 由「qgz+png 皆失败」改为「预期产物
  缺一即失败」；arcpy 分支核验 `aprx/pdf/png` 是否齐备；把 `layout_error`（及 `overlay_errors`）
  从 bridge 结果里取出并计入失败判定；失败时抛错让 `job.error` 非空（保持既有 `RuntimeError` 形态与消息风格）；
- `gis/qgis_bridge.py` — 仅在需要时把布局失败**显式化**（`layout_error` 已在 `detail` 中；
  本文件改动限于让失败可被上层读到所需的最小调整，不改变成功路径的返回形态）；
- `tests/verify_all.py` — 条件项判定（渲染两项改为缓存命中即 RUN、缺失则 SKIP 且文案写实）、
  rescan-big 缺失文案订正（不再断言「不在主工作区」）、新增 ruff 可选 RUN 项（探测 uv/ruff，
  缺失转 SKIP + 安装提示）、报告 note/skip 计数与覆盖矩阵随之对齐；
- `docs/comet/specs/verify-all/spec.md` — 发布面口径修订：RUN 层构成（渲染两项条件性入层、
  ruff 可选 RUN 项）、SKIP 层措辞、对应 Scenario 的验收口径；
- `docs/comet/archive/2026-10-11-c14-full-functional-verification/specs/verify-all/spec.md` —
  归档面副本，与发布面**逐字节一致**（C13 规范 4）；
- `docs/comet/specs/p1a-arcpy-bridge/spec.md` + 归档副本 — 仅追加 `> ⚠️` 注记（指向
  `emit_map` 预期产物缺失即失败的收紧），原文零删除、双副本逐字节一致、不改 Scenario 与编号；
- `docs/comet/specs/README.md` — 在「一、条款级 supersession 台账」追加一行，登记本次对
  C14 的 A3/A4 口径修订（原文零删除）。

### 删除

无

### 明确不建

- 不新增 `--online` 开关 —— C14 的 A4 明确无此开关，本轮不推翻；
- 不把「需要真实 GEE 像素」的检查并入 RUN 层 —— 那些确实依赖网络，SKIP 是正确的；
- 不建独立 lint 包装脚本 / 不引入 ruff 到 conda 环境 —— ruff 走 `uvx ruff@0.17.0`（零安装），
  缺失时降级为 SKIP；
- 不改 daemon 生命周期实现、不改覆盖矩阵结构、不改既有 smoke 与 tests/unit 行为（C14 A6 继续有效）。

# Non-goals

- 不改变在线层 SKIP 的既有语义（emit / three_exits / presets / timeseries / osm / tui 仍 SKIP）；
- 不新增对 uv/ruff 的强依赖（Q2 选的是可选 RUN 项：缺失报 SKIP 而非 FAIL）；
- 不改既有 smoke 与 tests/unit 的行为（C14 的 A6 继续有效）；
- 不改 daemon 生命周期实现与覆盖矩阵结构；
- 不改渲染**产物内容/样式**（像素、拉伸、布局元素构成、配色、DPI 默认值）—— 本 change 只改
  「失败如何判定与上报」，不触碰成功路径的渲染结果；
- 不改 `gis/arcpy_bridge.py` / `gis/qgis_bridge.py` 的 QGIS/ArcPy 子进程脚本行为与错误消息主结构；
- 不改 `tests/smoke_*.py` 与 `tests/unit/` 的既有断言（C14 A6 继续有效）——
  它们只**读取** `qgz_error`/`overlay_errors` 等键做打印或判错，收紧失败语义不会改变其读取面，
  但**必须实测确认**三者仍通过；
- 不改 `PROCESSING_VERSION`、不动金指纹 `b91c09c9c6451c16` 与既有 P0 缓存产物；
- 不把 worktree 里缺失的产物同步/复制到主工作区（数据面不入库，见 Constraints）。

# Acceptance examples

- A1: 当代指纹的缓存产物存在时，`smoke-map-renderers-qgis` 与 `smoke-map-renderers-arcpy`
  两项进入 RUN 层并 PASS（报告 layer=run、status=pass，附实测耗时）；缓存缺失时两项保持 SKIP
  且文案写实（明确「当代缓存缺失，联网跑一次即可离线复跑」）。两种条件都要有实测报告片段。
- A2: 报告里所有条件项的措辞与实际状态一致：缓存/前置产物存在时不得出现「不存在 / 未命中」字样，
  缺失时不得出现「已命中」字样；产物实际在主工作区盘上时不得断言「不在主工作区」；
  SKIP 计数与实际条件逐项吻合（`summary.skipped` 与 checks 中 status=skip 的条数相等）。
- A3: `verify-all` 的发布面 spec 与归档面副本逐字节一致，且
  `tests/unit/test_comet_spec_consistency.py` 8 条断言全绿；`docs/comet/specs/README.md`
  有对应 supersession 登记，且该 spec 的原文零删除（被修订条款保留原句 + 注记指向台账）。
- A4: ruff 门禁按 Q2=(a) 接入为可选 RUN 项：uv/ruff 可用时执行 `uvx ruff@0.17.0 check`，
  零告警为 PASS、有告警为 FAIL 且退出码语义生效（任一 RUN 项 FAIL → 进程退出码 1）；
  uv 或 ruff 不可用时报 SKIP + 安装提示，不 FAIL。
- A5: 回归：离线用例全绿（`tests/unit` 全量）、`uvx ruff@0.17.0 check` 零告警、
  `tests/verify_all.py` 在 geo 环境 + 仓库根 + 零手工前置下一条命令跑通，并给出与事实一致的报告。
- A6: 渲染失败语义收紧生效（qgis 一侧）：构造「`.qgz` 生成失败但 `.png` 成功」的条件时，
  `emit_map` **必须**判失败——`job.error` 非空、不返回成功结果；`smoke_map_renderers.py qgis`
  退出码非 0。实测须给出失败消息含 qgz 失败原因的片段。
- A7: 布局失败不再被吞：当 QGIS 侧返回 `layout_error` 非空时，`emit_map` 判失败并把该错误
  写进失败消息/结果（不得出现「结果里对布局失败毫无痕迹」）；相应的成功路径（无 layout_error）
  仍正常返回 `.qgz`。
- A8: arcpy 分支产物齐备性被核验：`write_aprx` 成功但**缺 `spec.layout.formats` 所要求的任一导出**
  时，`emit_map` 判失败而非静默成功；正常情况下 formats（默认 `("pdf","png")`）所要求的导出齐备
  仍 PASS，**不得把合法配置误判为失败** —— 特别是 `formats=("pdf",)` 这种只要求单一格式的
  合法 spec 必须 PASS；`layout=None`（nolayout，无任何导出）也必须 PASS。
- A9: 收紧后既有资产不回归：`tests/unit` 全量仍全绿、`uvx ruff@0.17.0 check` 零告警、
  `tests/smoke_three_exits.py` 与 `tests/smoke_osm.py` 中读取 `qgz_error`/`overlay_errors` 的
  代码**未被修改**（`git diff` 为空）且其判错逻辑语义不受影响；`tests/verify_all.py` 仍一条命令
  跑通（渲染两项在缓存命中态 PASS）。

# Constraints and invariants

- **C13 发布面纪律**：改动已归档的 `verify-all` spec 必须（1）原文零删除、（2）发布面 ↔ 归档面
  双副本逐字节一致、（3）在 `docs/comet/specs/README.md` 登记 supersession 或就地订正、
  （4）结构不变量守卫（H1 form / Scenario 验收引用 / 双副本一致）保持绿 —— 现行 8 条断言必须全绿；
- **C14 的 A6（既有 smoke 与 tests/unit 零修改）继续有效**：本 change 只改 `tests/verify_all.py`，
  `tests/smoke_*.py` 与 `tests/unit/` 不做行为修改；
- **入口运行契约不变**：geo 环境、仓库根执行、daemon 自动检测/启动/停止、退出码任一 RUN 失败为 1；
- **新增 RUN 项不得引入外网请求**：渲染两项在缓存命中路径上纯本地（`_ensure_raster` 命中即复用，
  产物落 worktree 内 `data/derived`、`data/deliver`）；ruff 项经 `uvx --offline` 探测
  —— **实测（2026-10-18）**：uv 缓存已有时 `uvx --offline ruff@0.17.0 check` 零网络返回
  「All checks passed」；缓存冷时 `--offline` 退出码 1 并提示「network was disabled」。
  因此 ruff 项一律以 `--offline` 运行，冷缓存自然落到 SKIP（安装提示），绝不触发下载；
- **数据面不入库**：`data/`、`logs/` 均在 .gitignore 内；缓存产物只作为本机验证前置，
  不随本 change 提交；
- **worktree 隔离**：一切读写与命令在 `D:/DEV/geocode/.worktrees/c17-verify-all-evidence-aware` 内，
  不碰主工作区 `D:/DEV/geocode`，不碰 c16 / c18 worktree；
- **共享 daemon 端口 6531**：跑 `verify_all` / `smoke_all` / `smoke_tui` 前先确认 6531 未占用，
  与 c16 / c18 错峰，不并发抢 daemon。
- **渲染成功路径零回归**：收紧失败判定**不得**把正常成功判成失败 —— 缓存命中态两项渲染
  必须仍 PASS（实测 qgis ≈ 5 s、arcpy ≈ 25–27 s），`.qgz`/`.aprx`/`.pdf`/`.png` 产物齐备；
- **失败消息可诊断**：新抛出的失败必须带具体原因（哪一路产物的什么错误），不得只给一句
  「全部失败」；消息形态沿用既有 `RuntimeError` 风格，便于 smoke 打印与人工排查；
- **不改变 `Job.error` 的既有语义**：仍由 `run_emit` 捕获异常写入 `job.error`，退出码语义不变；
- **产物内容不漂移**：收紧失败判定不得改变任何成功产物字节（`.qgz`/`.png`/`.aprx`/`.pdf`）；
  若因实现方式必须动渲染代码，须给出产物哈希不变或差异说明。

# Decisions

- D1（Q1 = a，用户 2026-10-11 已拍板）：**同意扩展 RUN 层** —— 当代指纹缓存产物存在时，
  `smoke-map-renderers-qgis` / `-arcpy` 进入 RUN 层并 PASS；缺失时保持 SKIP 且文案写实；
  据此按 C13 纪律修订 C14 的 A3/A4 口径。**本轮补充实测支撑**（2026-10-18）：两条渲染路径在
  缓存命中下确实离线跑通（qgis 5.5 s / arcpy 30.8 s），且全程未启动 ArcGIS Pro UI 进程
  （`tasklist` 核对无 `ArcGISPro.exe`；arcpy bridge 走 `arcgispro-py3` 的 python 子进程），
  与 C14 A7 不冲突。→ 该选择无硬证据冲突，按原决定执行。
- D2（Q2 = a，用户 2026-10-11 已拍板）：**ruff 以可选 RUN 项接入** —— 有 uv/ruff 时执行并计分，
  缺失时报 SKIP + 安装提示（不 FAIL）。**本轮发现一处需要显式处置的硬证据**（见 D3）：
  `uvx` 默认会为冷缓存**下载** ruff，与「新增 RUN 项不得引入外网请求」红线直接冲突；
  处置方式是不改选型、只固定调用形态为 `uvx --offline`。
- D3（实现约束，2026-10-18 实测）：ruff 项**必须以 `uvx --offline ruff@0.17.0 check` 形式执行**。
  实测：冷缓存 + `--offline` → 退出码 1 + 「network was disabled / Packages were unavailable」；
  暖缓存 + `--offline` → 「All checks passed!」退出码 0。这样既守住「零外网请求」红线，
  又满足 Q2(a)「缺失时报 SKIP + 安装提示」的语义 —— 冷缓存等价于「工具不可用」，
  归 SKIP 并提示先联网安装一次（`uv tool install ruff==0.17.0` 或直接 `uvx ruff@0.17.0` 预热缓存）。
- D4（措辞订正，2026-10-18 实测）：rescan-big 的 SKIP 文案把「本条 worktree 缺失」写成
  「不在主工作区」，而产物 `s2_chunking_big_smoke.2965c18a.nc`（816 MB）确实在主工作区盘上。
  订正为按「本次执行根下缺失」措辞，不再断言主工作区有无。
- D5（范围划定，**用户 2026-10-18 改判**）：原决定「`gis/emit.py` 渲染容忍度另立 change、
  本 change `gis/` 零 diff」**已撤销**。用户裁决「全量修复风险」⇒ 三处假 PASS 并入本 change 修复
  （见 Outcome 的 c17 追加范围）。`gis/` 不再是零 diff；该风险从「登记」升级为「必须修复并验收」。
- D6（修复口径，2026-10-18 取证后确定）：**「预期产物」缺一即失败**，但「预期」必须按
  `spec` 的真实配置推导，不得写死：
  - qgis 分支：`.qgz` 与 `.png` 都属预期（与现状产物面一致）⇒ 缺一即失败；
  - arcpy 分支：`.aprx` 恒为预期；导出格式按 **`layout.formats`**（默认 `("pdf","png")`，
    合法值含单格式如 `("pdf",)`）⇒ 只要求 formats 里列出的那些；
    `layout=None`（nolayout）⇒ 无导出预期、只出 map-only `.aprx`，**必须 PASS**；
  - `layout_error` 非空即失败（布局是 `layout` 非 None 时的明确预期）。
  理由：渲染验收语义是「产物齐备」，部分成功对使用者等价于失败，旧口径会让 verify_all 的 PASS
  不可信。`overlay_errors` 维持「诊断信息」定位、**不**升级为失败（矢量叠加有既定的可选/降级
  语义，升级会改变 C8 已确认行为）。
- D7（不误判，2026-10-18）：收紧仅针对「应产出却缺失」的产物；无 layout 的 nolayout 语义
  （`layout=None` ⇒ 只出 map-only .aprx、无 PDF/PNG 导出）**不**算失败，验收须覆盖该边界。
- D8（归属，用户 2026-10-18 选 (a)）：渲染失败语义的收紧**只在 `verify-all` 登记**（本 spec 的
  场景 A16–A19 与验收）。`p1a-arcpy-bridge` 的 spec 与归档副本**只追加一条 `> ⚠️` 注记**
  指向本次收紧（原文零删除、双副本逐字节一致、README 台账登记），**不改动**其 Scenario、
  Scenario 编号与既有验收；`emit_map` 的 renderer 纪律/产物面条款本身不变。

# Verification expectations

- **A1 必须两种条件各留实测报告片段**：缓存命中（渲染两项 layer=run / status=pass + 耗时）与
  缓存缺失（同两项 layer=skip + 写实文案）。造「缺失」条件时**不得破坏既有缓存产物** ——
  做法是把缓存临时改名/移到 worktree 内另一路径，跑完立即还原并核对字节一致（或改用指向空
  `data/derived` 的临时根），不得删除或覆盖任何既有产物；`data/derived` 内既有
  `s2_beijing_test.b91c09c9.*` 与其它历史时代产物一律原样保留。
- **A2 可机械检查**：报告文本与盘上事实的比对（至少覆盖全部条件项）——
  断言「产物存在 → 文案不含『不存在/未命中』」「产物缺失 → 文案不含『已命中』」
  「产物在主工作区盘上 → 文案不含『不在主工作区』」，并核对 `summary.skipped` 计数。
- **A3 需发布面一致性证据**：逐字节比对（`cmp` / 字节 hash）+ 结构守卫单测输出（8 条断言）+ 
  「原文零删除」的 diff 核对（被修订条款的原句仍在该 spec 内）。
- **A4 需两种条件证据**：uv/ruff 可用时的 PASS（真实跑一轮，零告警）与不可用时的 SKIP +
  安装提示（用冷 `UV_CACHE_DIR` 或 PATH 隔离造「不可用」条件，证明既不 FAIL 也不联网）。
- **A5 需一条命令端到端跑通留档**：`tests/verify_all.py` 完整一轮报告 + 退出码，
  且 `tests/unit` 全量与 `uvx ruff@0.17.0 check` 各自单跑留档。
- **A16/A17/A18 需「破坏性自证」**：必须构造出失败条件并证明被判失败，而不是「恰好通过」——
  做法参照 `logs/acceptance/c17_risk_probe.py`（当前已复现两处假 PASS）：用 monkeypatch/桩替换
  `write_qgz`、`write_aprx`、`_render_png` 造出「qgz 失败 / png 成功」「layout_error 非空」
  「write_aprx 成功但缺 pdf」三种条件，断言 `emit_map` 抛错、`job.error` 非空；
  并给出**修复前 vs 修复后**同一脚本的对照输出（修复前成功、修复后失败）。
- **A19 需零回归证据**：`tests/unit` 全量 + `ruff` 零告警 + `git diff` 证明
  `tests/smoke_three_exits.py` / `tests/smoke_osm.py` / `tests/unit/` 未被改动；
  并在缓存命中态实跑 `tests/verify_all.py`，渲染两项仍 PASS 且耗时正常。
- **成功路径产物不漂移**：给出修复前后 `.qgz`/`.png`/`.aprx`/`.pdf` 的哈希或体积对照，
  证明收紧失败判定没有改变成功产物。
- **边界**：`layout=None`（nolayout）必须仍判成功，给出该场景实测。

# Open questions

（无：Q1/Q2 已由用户 2026-10-11 拍板；Q3 已由用户 2026-10-18 选 (a) 结案，结论见 D8。）