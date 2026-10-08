# 目标

对已归档的 C1–C9 做一次**只读审阅后的全量补丁**：修掉审阅发现的全部可修问题，使「代码行为、测试断言、归档 Spec 正文、开发文档实际状态」四处重新自洽；并收口 C9 归档后的台账（路线图清账 + dockpane 拆出另行立项的立项范围要点）。本 change 是**补丁 change**（非新功能），不新增产品行为、不改变任何像素输出、不改变任何已归档验收结论。C9 `p1b-arcgis-addin` 已于 2026-10-08 归档并推送（提交 `2817da6` / `a76a1f1`）。

审阅是触发材料（**排错/取证参考**，不是需求来源）：C1–C9 的归档 brief/spec/verification、`docs/README.md` 与当前仓库实际状态逐项比对，产出 12 条待修问题（P1×3 / P2×3 / P3×4 / 本地配置×1 / 合规归属×1）。**2026-10-08 复核修正**：其中 S6（`time_step`/`time_steps`）与 S7（`_ref/` 路径）两条前提与磁盘/代码**相反**，已撤销；S9 的「引用不存在模块 `gis/osmtools.py`」一条不成立。有效来源为 S1–S5、S8–S13。

# 范围

本 change 覆盖三类载体：**仓库内入库文件**（测试 + 归档 Spec 正文，走版本库）、**本地文档**（`docs/README.md`，gitignored，只存在于主工作区）、**本机配置**（`geocode.json`，skip-worktree 本地件）。

## Source coverage

覆盖边界 = 审阅结论清单的**有效项**（S1–S5、S8–S12；S6/S7 于 2026-10-08 经磁盘与代码复核后撤销）+ C9 归档后的台账收口（S13，2026-10-08 用户要求并入）。每条对应一处可独立核验的缺陷。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
|---|---|---|---|---|---|---|
| S1：`tests/smoke_array_chunking.py:467,484` | complete | 判定条件硬编码 P0 指纹前缀 `c9243efd`（PV2 时代值），当前实际为 `b91c09c9`（PV=3）⇒ `client` stage 恒 FAIL 误报 | spec.md 场景"SMOKE-A3 指纹断言按时代取值" | A1 | covered | 当前有效需求（行为误报） |
| S2：`tests/unit/_helpers.py:16-17,54`（+ README §3.1/§9.5 同期文字） | complete | 注释把 `c9243efd40318c85` 写成金指纹现状，未标时代；`_helpers.py:54` docstring 与正文行 16 同错。PV=3 后唯一现行金值是 `b91c09c9c6451c16` | spec.md 场景"SMOKE-A3 指纹断言按时代取值" | A1 | covered | 与 S1 同族（金指纹时代标注），合并一个验收 |
| S3：`tests/smoke_map_renderers.py:12` | complete | 说明写"同指纹（c9243efd）的 derived/*.tif 已在 P0 产出"，未标明这是 P0 历史缓存；缓存缺失时的行为未说明 | spec.md 场景"SMOKE-B1 离线地图冒烟自足" | A2 | covered | 当前有效需求（说明失真） |
| S4：`tests/unit/*`（11 处）+ `tests/smoke_timeseries.py:25` + `docs/README.md` §12 | complete | 各测试用 `from _helpers import …` 依赖运行方注入 `sys.path`；以 dotted-path 运行（`python -m unittest tests.unit.test_spec_basics`）报 `ModuleNotFoundError: _helpers`（实测复现）；README §12 只给了 `discover -s tests/unit`，未说明 dotted-path 需要 `-t tests/unit` | spec.md 场景"SMOKE-C1 测试入口稳健性" | A3 | covered | 当前有效需求（入口脆弱 + 文档缺口） |
| S5：`docs/comet/{specs,archive/2026-10-06-p2-timeseries/specs}/p2-timeseries/spec.md` A3 | complete | Spec 正文写 `emit_file` 时序走"期集合 `toBands()` 成单张多波段 ee.Image → 复用 getDownloadURL 直下"，实际实现是逐期下载 + 本地合并（`gis/emit.py:397 _download_stack_to`；README §9.5 已记录 `toBands()` 单请求实测 54,613,440B 超 GEE 50,331,648B 上限被 400 拒） | spec.md 场景"C3 spec 正文与实现一致" | A4 | covered | 当前有效需求（归档 Spec 失真） |
| S6：~~同上两个 spec.md 的 A7/Constraints~~ | **不成立（2026-10-08 撤销）** | 复核：`gis/spec.py:427` 为 `time_step: str | None = None`（**单数**），`tests/unit/test_spec_fingerprint.py` 的 `FINGERPRINT_FIELDS` 亦含 `time_step`（单数）；全仓无 `time_steps`。原判「实际字段名是 `time_steps`」与磁盘/代码相反 —— Spec 正文原样正确，若照原判更正会把**正确正文改错** | — | — | dropped | 撤销：前提不成立 |
| S7：~~`docs/comet/{specs,archive/2026-10-07-p3-skill-knowledge/specs}/p3-skill-knowledge/spec.md` A1/A2~~ | **不成立（2026-10-08 撤销）** | 复核：主工作区磁盘为 `_ref/contributions/<skill>/`（5 个技能目录俱在），`_ref/PROVENANCE.md` 自述「路径相对本目录：`contributions/<skill>/`」；全盘无 `_ref/skills/`。原判「磁盘实际目录名是 `_ref/skills/`」不成立 —— C7 Spec 的 `_ref/contributions/` 表述正确 | — | — | dropped | 撤销：前提不成立 |
| S8：`docs/README.md` §8（新增条目）+ §11 红线 2 + §13 + §9.2 C1 行 + §9.1 余量措辞 | complete | ①§8 缺一条时序期窗口推导（月/年加法、月末钳制、N 上限）的踩坑记录；②§11 红线 2 未补 C3 确立的"时序不改变网格语义"；③§13 参考表写"P1b add-in 技术要点来源（§9.3）"，实际在 §9.4；④§9.2 C1 行写"覆盖红线 1/2/3"，实际断言的是红线 2/3/8；⑤§9.1 余量措辞"C4 分支清理"易误读（C4 已 merge，余的是 worktree/分支残留） | spec.md 场景"README 文档订正" | A5 | covered | 当前有效需求（引用/编号/表述失准 + 事实缺档） |
| S9：`docs/README.md` §9.6 | complete | C8 行仍是裸待办"OSM 工具（Overpass）作为矢量数据源（C8）"，而 §9.1 与 §9.2 已标 ✅ 归档（C7 行是删除线 + ✅ 范例）；（复核：全仓无 `gis/osmtools.py` 字样，「引用不存在模块」一条不成立，2026-10-08 撤销） | spec.md 场景"README 文档订正" | A5 | covered | 与 S8 同文件同族（README 一致性），合并一个验收 |
| S10：`docs/README.md` §8 #18 vs 主工作区 `geocode.json` | complete | README 声称镜像池已配置（kumi/mail.ru/private.coffee 实测可用），但主工作区 `geocode.json` 无 `osm` 键；实测 `gis.osm._endpoints()` 只返回默认单点 `https://overpass-api.de/api/interpreter`（当日 504 重灾区） | spec.md 场景"本地配置补齐 OSM 镜像池" | A6 | covered | 当前有效需求（文档与配置不符）；C8 在 worktree 的配置改动未回主工作区 |
| S11：`tests/unit/fixtures/osm_water_recorded.json` | complete | 真实 OSM 录制数据（北京水系，145,019B / 25 要素）；响应头自带 ODbL 字样，但仓库内无归属与抓取来源说明 | spec.md 场景"OSM fixture 归属标注" | A7 | covered | 当前有效需求（许可留档） |
| S12：审阅·交付形态 | complete | 入库改动与本地件（`docs/README.md` / `geocode.json`）必须在交付中分开列明，避免把个人环境写进版本库、也避免 worktree 与主工作区双写 | spec.md 场景"交付形态与可回退性" | A8 | covered | 当前有效需求（交付纪律） |
| S13：C9 归档后的路线图/台账收口（`docs/README.md` §9.1「下一步」行、§9.2 C9 行、§9.4 P1b 节） | complete | C9 已归档并推送（`2817da6`/`a76a1f1`），但 §9.1 仍在写"C9 add-in（条件性）"余量、§9.4 未落定 dockpane 拆出后的立项范围；需把"路线图清账 + dockpane 拆出另行立项"作为台账事实落定（含未来立项的范围要点与前提） | spec.md 场景"C9 归档与路线图收口台账" | A9 | covered | 当前有效需求（归档后事实未收口）；2026-10-08 用户指定并入本 change 执行 |

## 交付内容

1. **P1 测试断言与入口（入库）**
   - `tests/smoke_array_chunking.py`：指纹期望值改为按 `PROCESSING_VERSION` 取当代金值（单一事实源；可与 daemon 返回的 `spec.fingerprint()` 自洽），更新 467/484 两处文案；
   - `tests/unit/_helpers.py`：注释与 docstring 的金指纹标注时代（PV2 = `c9243efd40318c85` / PV3 = `b91c09c9c6451c16`）；
   - `tests/smoke_map_renderers.py`：说明改为"P0 历史指纹缓存（`c9243efd`）；当代金值见 `tests/unit`「按 PROCESSING_VERSION 时代登记」表"，并写清缓存缺失时走联网生成；
   - `tests/unit/*`（11 处 import）+ `tests/smoke_timeseries.py`（1 处）：改为不依赖 `sys.path` 注入的导入（加 `tests/unit/__init__.py`，统一包路径导入），保留 `discover -s tests/unit` 与 dotted-path 双入口可用。
2. **P2 归档 Spec 正文（入库，只改正文不改验收）**
   - `docs/comet/specs/p2-timeseries/spec.md` 与 `docs/comet/archive/2026-10-06-p2-timeseries/specs/p2-timeseries/spec.md`：A3 场景补等价实现注记（逐期 getDownloadURL + 本地合并，含 50MB 上限依据）（`time_step` 字段名经复核原样正确，不改）；
3. **README 订正（本地文档，归档轮主工作区执行）**：§9.6 C8 行改为删除线 + ✅（含提交哈希 `2361082`）；§11 红线 2 补"时序不改变网格语义（C3）"；§13 交叉引用 §9.3 → §9.4；§9.2 C1 行"红线 1/2/3"→"红线 2/3/8"；§9.1 余量措辞改为"worktree/分支残留清理"；§8 新增踩坑条目（时序期窗口推导），并修 #18 镜像池措辞与 S10 落地后的实际配置一致；§2.4 目录树补 `_ref/` 实际路径。**并按 S13 收口 C9 归档台账**：§9.1「下一步」行写明 C1–C9 全部交付、路线图清账、余量仅 dockpane（拆出另行立项）并引用归档提交 `2817da6`/`a76a1f1`；§9.2 的 C9 行与提交号保持自洽；§9.4 P1b 节落定 dockpane 立项范围要点（GUI 状态面板：6530 状态与三工具入口的进程内展示）与前提（C9 add-in 骨架/打包部署/Pro 取证流程可复用）。本 change 的 worktree 内**不改该文件**，Build 阶段产出待执行差异清单（章节 + 改动要点 + 回退方式）。
4. **本机配置（归档轮主工作区执行）**：主工作区 `geocode.json` 增 `osm.endpoints` 镜像池（≥2 个，主站与镜像的序位按 README 实测记录），`gee`/`gdal`/`server` 段不变；该文件为 skip-worktree 本地件，不入库。同样只产出差异清单，不在此 worktree 内写。
5. **合规归属（入库）**：`tests/unit/fixtures/` 下补 ODbL 归属与抓取来源说明文件（不改 fixture 正文，零解析风险）。
6. **回归**：`tests/unit` 全量（当前 222 用例，含 4 skip，实测于同步 C9 后的 `2817da6` 基线）全绿且数量不减；C1–C9 既有断言不回退；全程不触发 GEE / Overpass 请求。

# 非目标

- **不动 C9 内容**：`Pro/`、`gis/preflight.py` 的 C9 改动、`scripts/package_pro_addin.py`、`tests/unit/test_pro_addin.py`、`docs/comet/changes/p1b-arcgis-addin/` 与 C9 归档产物一律不修改、不合并、不重排。C9 已于 2026-10-08 归档并推送（`2817da6`/`a76a1f1`），分支基线已同步；本 change 只做台账/文档层收口（A9），不触碰 C9 代码。
- **不实现 dockpane**：dockpane 保持"拆出另行立项"，本 change 只落台账与未来立项的范围要点（A9），不做 Pro/ 侧实现、不新增 Pro 会话取证、不新增验收运行依赖。
- **不做审阅中未列入清单的改进**：`Pro/ProTools.cs` 的 `JsonElement` 取值隐患、`McpServerHost` 端口占用告警、`preflight` 支持 `.esriAddIn`、A4–A7 证据转录规范——均不在本 change 范围（C9 已归档，如需处理须另立 change），本 change 不代做。
- **不新增产品行为**：不新增 spec 字段、不改 `gis/` 生产代码的计算结果、不改三出口语义、不动预设表、不新增依赖。
- **不改指纹**：`PROCESSING_VERSION` 保持 3；金指纹 `b91c09c9c6451c16` 与 PV2 对照值 `c9243efd40318c85` 双双不动。
- **不改已归档验收结论**：不动任何 `docs/comet/archive/*/verification.md` 与 `comet-state.yaml`；Spec 正文修正不改变任何验收项文字、ID、场景标题。
- **不动环境**：不安装/卸载软件，不改 `_ref/`（只读），不跑网络。

# 约束与不变量

- **红线 1/2**：不引入 ee 对象、不改 `source.py`、不改 `compute_grid()` 语义（纯测试/文档/配置补丁）。
- **红线 3**：`PROCESSING_VERSION` 不 bump（零像素输出变化）。
- **红线 8**：不新增 spec 字段，指纹守卫名单不变。
- **归档 Spec 只做正文级修正**：不改验收 ID、不改场景标题、不增删场景；每处修正必须有实现或磁盘事实支撑（S5–S7 三条已逐项核实）。
- **三类载体分开处理**：入库文件走版本库提交；`docs/README.md`（gitignored）与 `geocode.json`（skip-worktree）只在主工作区就地更新，并在交接中列出确切改动行与回退方式。
- **工作区纪律**：`isolation = worktree`（`comet/c10-review-patches`，已同步至 main `2817da6`，含 C9 归档）；本 change 不在主工作区写任何文件，本地件的落地时机按 Q2 决定。

# Decisions

- **D1（工作区）**：`isolation = worktree`，分支 `comet/c10-review-patches`，目标 `main`。理由：立项时 C9 正在主工作区未提交写入，必须隔离（同 cwd 单写者纪律）。（2026-10-08 补记：C9 已归档并推送，分支快进同步至 `2817da6`；隔离安排在 S13 并入后保持不变。）
- **D2（归档 Spec 修正方式）**：只改正文（A3 实现路径注记；S6 的字段名与 S7 的 C7 路径两条经复核撤销，不在改动面），不改验收文字、不触碰 `verification.md`；`docs/comet/specs/**` 与 `docs/comet/archive/**/specs/**` 两处同步并保持逐文件一致。理由：归档验收已成立且与正文修正不冲突；改验收文字需重开验收，超出补丁性质。
- **D3（测试入口修法）**：加 `tests/unit/__init__.py` + 统一包路径导入，保留 `discover -s tests/unit` 兼容；若两种入口无法同时满足，以"两种入口都可用"为验收底线，容许调整 `_helpers.py` 的位置或名称（须同步全部 12 处引用）。理由：两种入口都是实际用法。
- **D4（本地配置）**：`geocode.json` 的 `osm.endpoints` 落地为**本地件**（不入库，与 `gee` 段同性质）；README §8 #18 措辞随之与实配对齐。理由：与既有本地配置纪律一致。
- **D5（归属形态）**：不改 fixture 正文（JSON 被解析测试消费），改用同目录说明文件承载 ODbL 归属与抓取说明。理由：零行为风险。
- **D6（验收粒度）**：有效来源 11 条（S1–S5、S8–S13）合并为 9 条验收（A1–A9）：S1+S2 → A1（金指纹时代标注）、S5 → A4（C3 正文与实现一致）、S8+S9 → A5（README 订正）、S12 → A8（交付形态）、S13 → A9（C9 归档台账收口）。理由：验收项须具体、可验证、互不重复。（2026-10-08 复核：S6/S7 撤销后不占验收位，原 A5（C7 路径）撤销，原 A6–A10 顺次前移为 A5–A9。）
- **D7（不拆 Supervisor）**：单一 change 推进。改动为同批小修且文件相互关联（测试入口与断言、归档 Spec 正文、README），无独立可验证边界，协调成本高于并行收益。
- **D8（Q1 裁决，2026-10-07 用户采纳推荐）**：归档 Spec 的正文修正**同步 `docs/comet/archive/**/specs/**` 副本**，两处保持逐文件一致。归档副本是「归档后完整行为」的正式载体，A4/A5 的判据以两处一致为准；仍只改正文，不动验收 ID、场景标题与 `verification.md`/`comet-state.yaml`。
- **D9（Q2 裁决，2026-10-07 用户采纳推荐）**：`docs/README.md`（gitignored）与 `geocode.json`（skip-worktree）**不在本 change 的 worktree 内改动**。Build 阶段只落地入库文件（`tests/`、`docs/comet/**`），并产出一份「本地件待执行差异清单」（确切章节/键 + 改动要点 + 回退方式）；归档轮由用户确认后在**主工作区**就地执行 A6/A7。理由：避免同一 cwd 双写与把个人环境写进版本库。

# 验收示例

- A1 SMOKE-A3 指纹断言按时代取值：`tests/smoke_array_chunking.py` 不再以常量 `c9243efd` 作为判定条件，其期望值与 `ArtifactSpec.fingerprint()` 在 PV=3 下的金值一致（静态核查 + 离线单测断言「期望值随 `PROCESSING_VERSION` 取值」）；`tests/unit/_helpers.py` 的指纹注释/docstring 标注时代（PV2 旧值 / PV3 现行值），不再把 PV2 值表述为现状。
- A2 SMOKE-B1 离线地图冒烟自足：`tests/smoke_map_renderers.py` 的说明与实际一致——写明栅格缓存文件名带**当前时代指纹**（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`；PV3 现行 `b91c09c9`），离线命中的条件是「目标缓存文件已存在且 >4096B」，缓存缺失时**不静默跳过**、走联网生成；并写明主工作区现存的 P0 产物是 PV2 时代 `s2_beijing_test.c9243efd.tif`、当前 PV 下**不命中**（故当前实际走联网，先在当代 PV 下生成一次当代缓存才可离线复跑）；**不得**表述为「默认离线命中 c9243efd 缓存」或「新指纹 spec 复用旧栅格」。
- A3 SMOKE-C1 测试入口稳健性：`python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics`（dotted-path）两种入口均全绿；`tests/smoke_timeseries.py` 不依赖运行方注入 `sys.path` 亦可导入共享构造；README §12 写明两种入口命令（含 dotted-path 需要的 `-t` 说明，若仍需要）。
- A4 C3 spec 正文与实现一致：`docs/comet/specs/p2-timeseries/spec.md` 与 archive 副本的 A3 场景写明「逐期 getDownloadURL + 本地合并」的等价实现及 50MB 上限依据；两份文件除该处正文修正外与归档时逐行一致（`time_step` 字段名经复核原样正确，不改），验收 ID 与场景标题未变。
- A5 README 文档订正：§9.6 C8 行标注已归档（删除线 + ✅ + `2361082`）且不再引用不存在的模块名；§11 红线 2 含「时序不改变网格语义（C3）」；§13 的 P1b 引用为 §9.4；§9.2 C1 行写「红线 2/3/8」；§9.1 余量措辞为 worktree/分支残留清理；§8 含新增的时序期窗口推导踩坑条目，且 #18 与实配一致；§2.4 目录树含 `_ref/`。
- A6 本地配置补齐 OSM 镜像池：主工作区 `geocode.json` 含 `osm.endpoints`（≥2 个镜像）且 `gis.osm._endpoints()` 读回该列表；`gee`/`gdal`/`server` 段未变；文件仍为 skip-worktree 状态；README §8 #18 描述与之自洽。
- A7 OSM fixture 归属标注：`tests/unit/fixtures/` 下有 ODbL 归属与抓取来源说明（© OpenStreetMap contributors, ODbL；录制时间与查询范围），fixture 正文未改，`tests/unit/test_osm.py` 仍全绿。
- A8 交付形态与可回退性：交付清单明确区分三类载体——入库改动（可 `git diff main` 逐项核对，不含 `gis/`、`Pro/`、`scripts/`、C9 目录）、本地文档改动（列出确切行）、本机配置改动（列出确切键与回退方式）；`docs/comet/archive/*/verification.md` 与 `comet-state.yaml` 零修改。
- A9 C9 归档与路线图收口台账：主工作区 `docs/README.md` 的 §9.1「下一步」行写明 C1–C9 全部交付、路线图清账、余量仅 dockpane（拆出另行立项）并引用 C9 归档提交 `2817da6` / `a76a1f1`；§9.2 的 C9 行状态与提交号自洽且保留 dockpane 拆出注记；§9.4 P1b 节落定 dockpane 立项范围要点（GUI 状态面板：6530 状态与三工具入口的进程内展示）与前提（可复用 C9 的 add-in 骨架 / 打包部署 / Pro 取证流程）；全篇不再出现"C9 add-in（条件性）"等过期余量表述。

# Verification expectations

- 离线基线（每轮必跑）：`PYTHONPATH=. C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit`，预期现有 222 用例（含 4 skip；同步 C9 后的 `2817da6` 实测）全绿且数量不减；本 change 新增断言并入。
- **双入口实证**：另跑 `python -m unittest tests.unit.test_spec_basics` 证明 A3。
- 入库改动核查：`git diff --name-only main` 只允许出现 `tests/`、`docs/comet/specs/`、`docs/comet/archive/*/specs/`、`docs/comet/changes/c10-review-patches/`；**不得**出现 `gis/`、`Pro/`、`scripts/`、`docs/comet/changes/p1b-arcgis-addin/`。
- 归档完整性核查：修正后的 Spec 与归档副本 `diff -q` 一致；archive 的 `verification.md` / `comet-state.yaml` 未被修改。
- 本地件（A5/A6/A9）在主工作区按 Q2 决定的时机就地落地；交接中列出改动行/键与回退方式。
- 网络：全程离线，不触发 GEE 与 Overpass。

# Open questions

（无。Q1 已由 D8 裁决、Q2 已由 D9 裁决，2026-10-07 用户采纳推荐方案。）
