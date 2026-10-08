---
generated_from_state_version: 23
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 4
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-08T01:36:01.261Z
- 摘要: A1–A9 全部 9/9 判定通过，无阻塞风险。本轮为需求修订轮：A2 判据文字已完成三方对齐（brief 示例 = spec 场景 = state 快照逐字一致），且与实现/磁盘事实相符（内联 spec 指纹独立复算 b91c09c9c6451c16；_output_path 命名含指纹；_ensure_raster 条件存在且 >4096B；主工作区 data/derived 无当代指纹产物故当前不命中走联网）；实现与证据面相对上一轮零改动（diff 仅 tests/ 与 docs/comet/specs* 面）。Runtime 三项检查（unit-discover/unit-dotted-path/delivery-scope）均 passed 且与本次亲跑结果一致（223 用例 OK/4 skip、dotted-path 20 OK、交付面 PASS、spec 对逐行一致、归档记录零修改）。两条轻微文档口径注记（不构成判据缺口、不影响执行）：①c10-local-changes.md 第二节验证注记「应打印上述三条」与实配 4 条 endpoint（主站+三镜像）表述略欠精确，但同节 JSON 块已明确列出 4 条，执行无歧义；②README §9.2 执行顺序行的「C9 视 C2 结果决定」属历史决策口径，未列入清单，按 A9 的「余量/条件性」口径不构成遗漏。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1 SMOKE-A3 指纹断言按时代取值：`tests/smoke_array_chunking.py` 不再以常量 `c9243efd` 作为判定条件，其期望值与 `ArtifactSpec.fingerprint()` 在 PV=3 下的金值一致（静态核查 + 离线单测断言「期望值随 `PROCESSING_VERSION` 取值」）；`tests/unit/_helpers.py` 的指纹注释/docstring 标注时代（PV2 旧值 / PV3 现行值），不再把 PV2 值表述为现状。 | tests/smoke_array_chunking.py 已无任何硬编码指纹（grep c9243efd\|b91c09c9 为空），期望值经 expected_p0_fingerprint() 单一事实源按 PV 时代取值；独立复算 make_p0_spec().fingerprint()=b91c09c9c6451c16 与 GOLDEN_FINGERPRINTS[3] 相等；_helpers.py 注释/docstring 明确标注 PV2 历史值/PV3 现行值；新增 test_expected_fingerprint_follows_processing_era 随 discover 223 用例全绿。 |
| A2 | passed | brief.md | A2 SMOKE-B1 离线地图冒烟自足：`tests/smoke_map_renderers.py` 的说明与实际一致——写明栅格缓存文件名带**当前时代指纹**（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`；PV3 现行 `b91c09c9`），离线命中的条件是「目标缓存文件已存在且 >4096B」，缓存缺失时**不静默跳过**、走联网生成；并写明主工作区现存的 P0 产物是 PV2 时代 `s2_beijing_test.c9243efd.tif`、当前 PV 下**不命中**（故当前实际走联网，先在当代 PV 下生成一次当代缓存才可离线复跑）；**不得**表述为「默认离线命中 c9243efd 缓存」或「新指纹 spec 复用旧栅格」。 | 三方一致：判据文字（brief A2 示例、spec A2 场景、state 快照文本逐字一致）与实现/磁盘相符——独立复算内联 spec 指纹 b91c09c9c6451c16，_output_path 命名 {slug}.{指纹8位}.tif，_ensure_raster 复用条件为「存在且 >4096B」，主工作区 data/derived 无 s2_beijing_test.b91c09c9.*（仅有 c9243efd 等历史/其它指纹）故当前 PV 不命中、走联网，docstring 与判据一致；「默认离线命中」「复用旧栅格」仅作为禁止项出现在 brief/spec 判据中。 |
| A3 | passed | brief.md | A3 SMOKE-C1 测试入口稳健性：`python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics`（dotted-path）两种入口均全绿；`tests/smoke_timeseries.py` 不依赖运行方注入 `sys.path` 亦可导入共享构造；README §12 写明两种入口命令（含 dotted-path 需要的 `-t` 说明，若仍需要）。 | 亲跑双入口：python -m unittest discover -s tests/unit → Ran 223 OK (skipped=4)；python -m unittest tests.unit.test_spec_basics → Ran 20 OK（无需 -t）；grep 'from _helpers import' tests/ 为空；tests/__init__.py 与 tests/unit/__init__.py 齐备、smoke_timeseries 自举仓库根并走 tests.unit._helpers；test_offline_guard 单跑 OK；README §12 双入口修正列入清单第 10 条（dotted-path 不再需要 -t，实测确认）。 |
| A4 | passed | brief.md | A4 C3 spec 正文与实现一致：`docs/comet/specs/p2-timeseries/spec.md` 与 archive 副本的 A3 场景写明「逐期 getDownloadURL + 本地合并」的等价实现及 50MB 上限依据；两份文件除该处正文修正外与归档时逐行一致（`time_step` 字段名经复核原样正确，不改），验收 ID 与场景标题未变。 | git diff -q/filecmp 证实 docs/comet/specs 与 archive 副本逐行一致；各自 git diff -U0 均为 @@ -48,0 +49,8 @@ 单处 8 行纯插入、0 删除；两文件各 8 个 Scenario / 8 个「验收：」；grep -rn '.toBands(' gis/ 为空；正文含逐期 getDownloadURL + 本地合并与 50MB 上限依据，time_step 字段名未动。 |
| A5 | passed | brief.md | A5 README 文档订正：§9.6 C8 行标注已归档（删除线 + ✅ + `2361082`）且不再引用不存在的模块名；§11 红线 2 含「时序不改变网格语义（C3）」；§13 的 P1b 引用为 §9.4；§9.2 C1 行写「红线 2/3/8」；§9.1 余量措辞为 worktree/分支残留清理；§8 含新增的时序期窗口推导踩坑条目，且 #18 与实配一致；§2.4 目录树含 `_ref/`。 | logs/acceptance/c10-local-changes.md 第一节 11 条（含 6bis）逐条与主工作区 docs/README.md 现状核对一致：§9.6 裸待办（454）、§11 红线2（499）、§13 §9.3/contributions 两处（570/565）、§9.2 C1 行（385）、§9.1 尾段（373）、§8 #18 镜像池声称（351）、§2.4 树缺 _ref/（138-155）、§9.4 标题与 §10 第3行「条件性」（430/490）、§12 仅一条 smoke（527）；§8 末号 28、新行 #29 落 §8.5（三列式）可执行；符合 D9（worktree 内不改 README，只出清单）。 |
| A6 | passed | brief.md | A6 本地配置补齐 OSM 镜像池：主工作区 `geocode.json` 含 `osm.endpoints`（≥2 个镜像）且 `gis.osm._endpoints()` 读回该列表；`gee`/`gdal`/`server` 段未变；文件仍为 skip-worktree 状态；README §8 #18 描述与之自洽。 | 主工作区 geocode.json 实测键仅 gee/gdal/server、无 osm 键；git ls-files -v geocode.json = S（skip-worktree）；gis/osm.py::_endpoints() 确为读 config osm.endpoints、否则回退单点默认；清单第二节给出主站+三镜像 4 条 endpoint（与 §8 #18 记录的 kumi/mail.ru/private.coffee 一一对应）、其余键不改、回退=删除 osm 键，可执行且与现状一致。 |
| A7 | passed | brief.md | A7 OSM fixture 归属标注：`tests/unit/fixtures/` 下有 ODbL 归属与抓取来源说明（© OpenStreetMap contributors, ODbL；录制时间与查询范围），fixture 正文未改，`tests/unit/test_osm.py` 仍全绿。 | tests/unit/fixtures/README.md 与 fixture 实测逐项一致：145,019B、generator Overpass API 0.7.62.11 87bfad18、timestamp_osm_base 2026-10-07T11:55:51Z、ODbL 声明、25 要素=21 way+4 relation 全 natural=water、bbox lon 116.2887-116.7848 / lat 39.7591-39.9511；fixture 正文 git diff 零改动，test_osm.py 在 discover 全绿批次内。 |
| A8 | passed | brief.md | A8 交付形态与可回退性：交付清单明确区分三类载体——入库改动（可 `git diff main` 逐项核对，不含 `gis/`、`Pro/`、`scripts/`、C9 目录）、本地文档改动（列出确切行）、本机配置改动（列出确切键与回退方式）；`docs/comet/archive/*/verification.md` 与 `comet-state.yaml` 零修改。 | 亲跑 logs/acceptance/c10-delivery-check.py → RESULT: PASS（exit 0）；独立核对 git diff --name-only main（16 项，全为 tests/ 与 docs/comet/specs\|archive 面）与 git status --porcelain -uall（+6 未跟踪，含本 change 目录与包文件）均落在允许面，无 gis/、Pro/、scripts/、p1b-arcgis-addin；archive verification.md 与 comet-state.yaml 零修改；清单第三节三类载体分列且各带回退方式。 |
| A9 | passed | brief.md | A9 C9 归档与路线图收口台账：主工作区 `docs/README.md` 的 §9.1「下一步」行写明 C1–C9 全部交付、路线图清账、余量仅 dockpane（拆出另行立项）并引用 C9 归档提交 `2817da6` / `a76a1f1`；§9.2 的 C9 行状态与提交号自洽且保留 dockpane 拆出注记；§9.4 P1b 节落定 dockpane 立项范围要点（GUI 状态面板：6530 状态与三工具入口的进程内展示）与前提（可复用 C9 的 add-in 骨架 / 打包部署 / Pro 取证流程）；全篇不再出现"C9 add-in（条件性）"等过期余量表述。 | 主工作区 README 三处过期「条件性」（373/430/490）现状核实，分别由清单第 5、6bis 条修改覆盖，全篇无其它余量类过期表述；§9.2 C9 行已自洽（✅ 归档 2817da6/a76a1f1 + dockpane 拆出注记，无需再改）；第 5 条新文案含 C1–C9 全部交付/清账、余量仅 dockpane、引用两提交号；第 9 条落定 §9.4 dockpane 立项范围（6530 状态与三工具入口进程内展示）与前提（复用 C9 骨架/打包/取证）。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| unit-discover | -m unittest discover -s tests/unit | . | passed | 0 | 12644 ms |
| unit-dotted-path | -m unittest tests.unit.test_spec_basics | . | passed | 0 | 274 ms |
| delivery-scope | logs/acceptance/c10-delivery-check.py | . | passed | 0 | 245 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- unittest-discover: passed — python -m unittest discover -s tests/unit（worktree 根，无 PYTHONPATH）→ Ran 223 tests, OK (skipped=4)；含 A1 新增的时代取值断言
- unittest-dotted-path: passed — python -m unittest tests.unit.test_spec_basics → Ran 20 tests, OK；C10 前该命令报 ModuleNotFoundError: _helpers
- golden-era-dispatch: passed — expected_p0_fingerprint() == make_p0_spec().fingerprint() == b91c09c9c6451c16；expected_p0_fingerprint(2) == c9243efd40318c85；未登记时代 raise AssertionError
- delivery-scope: passed — logs/acceptance/c10-delivery-check.py：scope PASS / spec-pair PASS / archive-records PASS
- smoke-scripts: not-run — smoke_array_chunking / smoke_map_renderers / smoke_timeseries 需 GEE 或 daemon 网络；本轮按离线纪律未实跑（改动仅涉断言取值来源、说明文案与导入路径）
- 已知限制: A5/A6/A9 的落地形态是「待执行差异清单」而非已改文件：docs/README.md（gitignored）与 geocode.json（skip-worktree）按 D9 不在本 change 的 worktree 内改动，由归档轮在主工作区就地执行。清单在 logs/acceptance/c10-local-changes.md（worktree 的 logs/，gitignored 不入库——change 目录除 brief.md/children.yaml/specs/*/spec.md 外由 Runtime 专有、agent 不可写），每条含现状/改为/依据/回退。故 A5/A6/A9 的判据是「清单完整、可执行、与现状一致」，不是「README/geocode.json 已被改」。
- 已知限制: 三个 smoke 脚本需网络（GEE/daemon），本轮未实跑；smoke_map_renderers 的离线缓存前提在 worktree 内不成立（data/derived 为空），已在说明中写明；smoke_timeseries 仅验证语法与包导入路径（自举后 from tests.unit._helpers 可用）。
- 已知限制: geocode.json 的 osm.endpoints 四条（主站 + 三个镜像）URL 在离线纪律下未联网复测连通性（取自 README §8 #18 记录为实测可用的 kumi / mail.ru / private.coffee 规范 endpoint）。
- 已知限制: 第一轮 Verifier 判定 9/9 通过并给出 4 条风险，本轮已逐条收口：风险 1 修正 smoke_map_renderers 的缓存/离线口径（原句「主工作区有 P0 缓存时才离线」经复核不成立）、风险 2 把 §9.4/§10 的「条件性」字样并入本地件清单（6bis）、风险 3 明确 §8 新增踩坑行落 §8.5/编号 29、风险 4 把镜像池补全为三镜像；第二轮 Verifier 判定 9/9 通过并确认上述 4 条收口，其剩余提示（change 自身 A2 判据文字未同步）已走需求修订对齐 brief/spec 两处判据。
- 已知限制: 审阅清单的 S6（time_step→time_steps）与 S7（_ref/contributions→_ref/skills）两条前提与磁盘/代码相反，已于 2026-10-08 复核撤销（证据见 brief 的 Source coverage 表）；S9 的「引用不存在模块 gis/osmtools.py」亦不成立。验收因此由 10 条收敛为 A1–A9。
- 已知限制: docs/comet/archive/*/verification.md 与各 comet-state.yaml 零修改（delivery-scope 检查已核）；p2-timeseries 的归档 Spec 只做正文级插入，验收 ID / 场景标题 / 场景数量均未变。

## 阻塞项

_无。_

## 风险与跳过的工作

_未报告风险。_

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-08T00:33:48.368Z |
| 2 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-08T00:39:05.882Z |
| 3 | 1 | 1 | pass | — | 9/9 验收通过（verdict=pass）。A1–A4、A7、A8 以 worktree 实物与独立复跑取证（223 单测 OK、双入口全绿、spec 两副本 8 行纯插入一致、fixture 元数据逐项吻合、交付路径面与归档零修改核查 PASS）；A5/A6/A9 按 D9 以待执行差异清单为落地形态，清单 10+1 条完整、可执行、与主工作区现状逐条吻合。非目标零触碰（gis/、Pro/、scripts/、C9 目录无改动），全程离线，未在 worktree 写任何仓库文件。4 条风险均为低危、不阻塞归档。 | 2026-10-08T01:05:43.381Z |
| 3 | 1 | 1 | recovery | — | 收下 Verifier 的 9/9 pass，但按其风险 1 走实现修订（用户裁决：先修再验收）。修订内容：smoke_map_renderers 的「数据来源/缓存语义」说明改为与磁盘事实一致的准确表述——脚本内联 spec 在 PV=3 下指纹 b91c09c9c6451c16（实测），_ensure_raster 找 data/derived/s2_beijing_test.b91c09c9.tif，而磁盘现存 P0 产物是 PV2 时代 s2_beijing_test.c9243efd.tif，当前必然未命中、实际走联网；先在当代 PV 下生成一次当代缓存才可离线复跑。同时把 §9.4/§10 残余「条件性」字样与 §8 新增踩坑行的落点（§8.5）补进本地件清单，并按 README §8 #18 记录把镜像池补全为三镜像。 | 2026-10-08T01:07:43.259Z |
| 3 | 2 | 1 | pass | — | 9/9 通过（verdict=pass）。上轮 4 条风险逐条独立复验收口：①A2 口径经独立复算+磁盘 ls+代码核对与事实一致；②6bis 覆盖 §9.4 标题与 §10 第 3 行「条件性」（现状逐字吻合）；③§8 新行明确落 §8.5/编号 29（§8 末号实测 28）；④镜像池三镜像与 §8 #18 一一对应。A1/A2/A3/A4/A7/A8 以 worktree 实物与独立复跑取证（223 单测双入口全绿、spec 两副本 8 行纯插入一致、fixture 元数据逐项吻合、交付路径面与归档零修改 PASS）；A5/A6/A9 按 D9 以待执行差异清单落地，11 条逐条与主工作区现状吻合。非目标零触碰，全程离线，worktree 零写入。残留风险均为低危/信息级，不阻塞归档。 | 2026-10-08T01:22:03.849Z |
| 3 | 2 | 1 | recovery | — | 用户裁决：对齐 A2 判据文字（走需求修订）。第二轮 Verifier 判 9/9 pass 并确认上轮 4 条风险收口，但指出 change 自身的 A2 判据仍写与实现相反的口径——spec A2 场景现文「默认离线命中 P0 历史指纹缓存 c9243efd 的 data/derived/*.tif（layout/render 不参与指纹，故当前新指纹 spec 也能复用旧栅格）」与 brief 的 A2 示例同源；事实是指纹进缓存文件名（_output_path → {slug}.{指纹8位}.tif），PV=3 下脚本要 s2_beijing_test.b91c09c9.tif，磁盘只有 PV2 时代 c9243efd.tif，既不默认离线命中、也不存在「新指纹复用旧栅格」。修订仅改这两处判据文字的表述（实现与证据不变）。 | 2026-10-08T01:24:17.258Z |
| 4 | 1 | 1 | pass | — | A1–A9 全部 9/9 判定通过，无阻塞风险。本轮为需求修订轮：A2 判据文字已完成三方对齐（brief 示例 = spec 场景 = state 快照逐字一致），且与实现/磁盘事实相符（内联 spec 指纹独立复算 b91c09c9c6451c16；_output_path 命名含指纹；_ensure_raster 条件存在且 >4096B；主工作区 data/derived 无当代指纹产物故当前不命中走联网）；实现与证据面相对上一轮零改动（diff 仅 tests/ 与 docs/comet/specs* 面）。Runtime 三项检查（unit-discover/unit-dotted-path/delivery-scope）均 passed 且与本次亲跑结果一致（223 用例 OK/4 skip、dotted-path 20 OK、交付面 PASS、spec 对逐行一致、归档记录零修改）。两条轻微文档口径注记（不构成判据缺口、不影响执行）：①c10-local-changes.md 第二节验证注记「应打印上述三条」与实配 4 条 endpoint（主站+三镜像）表述略欠精确，但同节 JSON 块已明确列出 4 条，执行无歧义；②README §9.2 执行顺序行的「C9 视 C2 结果决定」属历史决策口径，未列入清单，按 A9 的「余量/条件性」口径不构成遗漏。 | 2026-10-08T01:36:01.261Z |



## 结论

A1–A9 全部 9/9 判定通过，无阻塞风险。本轮为需求修订轮：A2 判据文字已完成三方对齐（brief 示例 = spec 场景 = state 快照逐字一致），且与实现/磁盘事实相符（内联 spec 指纹独立复算 b91c09c9c6451c16；_output_path 命名含指纹；_ensure_raster 条件存在且 >4096B；主工作区 data/derived 无当代指纹产物故当前不命中走联网）；实现与证据面相对上一轮零改动（diff 仅 tests/ 与 docs/comet/specs* 面）。Runtime 三项检查（unit-discover/unit-dotted-path/delivery-scope）均 passed 且与本次亲跑结果一致（223 用例 OK/4 skip、dotted-path 20 OK、交付面 PASS、spec 对逐行一致、归档记录零修改）。两条轻微文档口径注记（不构成判据缺口、不影响执行）：①c10-local-changes.md 第二节验证注记「应打印上述三条」与实配 4 条 endpoint（主站+三镜像）表述略欠精确，但同节 JSON 块已明确列出 4 条，执行无歧义；②README §9.2 执行顺序行的「C9 视 C2 结果决定」属历史决策口径，未列入清单，按 A9 的「余量/条件性」口径不构成遗漏。
