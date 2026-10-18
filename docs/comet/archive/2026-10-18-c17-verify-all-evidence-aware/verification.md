---
generated_from_state_version: 35
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 5
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-18T06:25:22.411Z
- 摘要: A1–A23 全 23 项 passed，verdict=passed。本轮重点复核两处修订：①gis/emit.py 新增 Path.is_file() 复核不会误判真实成功——真实 arcpy 子进程六组 formats 全 PASS 且产物均在盘（("pdf","jpg")118.3s、("jpg",)115.0s、("png",)114.5s、()114.8s 回落 pdf+png、("pdf",)116.9s、layout=None 115.5s 仅 aprx），伪造缺件（缺 png 键、pdf 键在但文件不存在、aprx 路径不存在）及「真跑成功结果篡改」全部 RAISE；②spec 三副本均无 24.3–24.6 硬编码残留，实测 117–121 s/轮与文案自洽。假 PASS 实锤：用 git show HEAD:gis/emit.py 载入修复前实现，同一桩下 qgz 崩+png 成 / layout_error 非空 / arcpy 缺 pdf 三场景修复前全部 PASSED，修复后全部 RAISE；job.error 经真实 Jobs() 生命周期确认 status=failed、error 非空、result=None，smoke_map_renderers.py 退出码 1。A1/A17 缓存缺失态为临时移走缓存、跑完立即归还（sha256 5a3b837e…c053 与基线一致，未删除未覆盖）；A2/A18 13 条 checks 逐条核对、summary.skipped=7==skip 条数、主工作区 816MB 产物确在盘且文案不再断言「不在主工作区」；A3 两对双副本 cmp 一致、旧文逐行零删除、结构守卫 8/8；A4/A19 暖缓存 PASS / 注入 F821 后 overall=fail 且退出码 1 / 冷 UV_CACHE_DIR 加黑洞代理转 SKIP 不 FAIL 且 DOWNLOADS=0；A5 一条命令跑通 RUN 6 PASS 6 / SKIP 7 退出码 0。中途 layout.png 字节变化经查是不同 spec 的 title 不同所致，同 spec 双跑证伪漂移。只读纪律守住：git status 仅含预期改动，注入文件已删除。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: 当代指纹的缓存产物存在时，`smoke-map-renderers-qgis` 与 `smoke-map-renderers-arcpy` 两项进入 RUN 层并 PASS（报告 layer=run、status=pass，附实测耗时）；缓存缺失时两项保持 SKIP 且文案写实（明确「当代缓存缺失，联网跑一次即可离线复跑」）。两种条件都要有实测报告片段。 | 缓存双条件实测：命中态两项 layer=run/status=pass（qgis 4.0s、arcpy 117.3s，probe.hit=true）；临时移走 data/derived/s2_beijing_test.b91c09c9.tif 得缺失态两项 layer=skip/status=skip 且文案「当代指纹缓存缺失…自动转 RUN」，跑完立即还原并核 sha256=5a3b837e…c053 与基线一致（logs/acceptance/v5_cache_states.py / v5_cache_states.json / v5_final_run.txt） |
| A2 | passed | brief.md | A2: 报告里所有条件项的措辞与实际状态一致：缓存/前置产物存在时不得出现「不存在 / 未命中」字样， 缺失时不得出现「已命中」字样；产物实际在主工作区盘上时不得断言「不在主工作区」； SKIP 计数与实际条件逐项吻合（`summary.skipped` 与 checks 中 status=skip 的条数相等）。 | 机械核对 13 条 checks：summary.skipped=7 == status=='skip' 条数 7、summary.run=6 == layer=='run' 6、passed 亦符；渲染项（命中态）reason/note 无「不存在/未命中」；rescan-big 文案已改为「本次执行根下无…（查找路径 D:\…\c17-verify-all-evidence-aware\data\derived\…）」不再断言「不在主工作区」，而该 816MB 产物确实在主工作区盘上（logs/acceptance/v5_report_audit.py 输出 problem count: 0） |
| A3 | passed | brief.md | A3: `verify-all` 的发布面 spec 与归档面副本逐字节一致，且 `tests/unit/test_comet_spec_consistency.py` 8 条断言全绿；`docs/comet/specs/README.md` 有对应 supersession 登记，且该 spec 的原文零删除（被修订条款保留原句 + 注记指向台账）。 | 发布面↔归档面 cmp 逐字节一致（verify-all 与 p1a-arcpy-bridge 两对皆 true）；旧文 78 行 / 32 行逐行核对 missing_count=0（零删除）；README 检索到两条 c17 supersession 台账行；tests/unit/test_comet_spec_consistency.py 8 条断言 OK（guard_rc=0，logs/acceptance/v5_zero_delete2.py） |
| A4 | passed | brief.md | A4: ruff 门禁按 Q2=(a) 接入为可选 RUN 项：uv/ruff 可用时执行 `uvx ruff@0.17.0 check`， 零告警为 PASS、有告警为 FAIL 且退出码语义生效（任一 RUN 项 FAIL → 进程退出码 1）； uv 或 ruff 不可用时报 SKIP + 安装提示，不 FAIL。 | 暖缓存：uvx --offline ruff@0.17.0 check → All checks passed，入口 ruff-check layer=run/status=pass；注入 zz_v5_ruff_violation.py（F821）后入口报 [FAIL] ruff-check、overall=fail、EXITCODE=1；冷 UV_CACHE_DIR + 代理指向 127.0.0.1:9 时 REAL_EXIT=1 且 DOWNLOADS=0，入口探针 ok=false → layer=skip + 安装/预热提示、不 FAIL（logs/acceptance/v5_ruff_dual.json / v5_ruff_fail_run.txt；注入文件已删除，git status 干净） |
| A5 | passed | brief.md | A5: 回归：离线用例全绿（`tests/unit` 全量）、`uvx ruff@0.17.0 check` 零告警、 `tests/verify_all.py` 在 geo 环境 + 仓库根 + 零手工前置下一条命令跑通，并给出与事实一致的报告。 | geo 环境（C:/ProgramData/miniforge3/envs/geo/python.exe）仓库根一条命令跑通：RUN 6 PASS 6 / FAIL 0 · SKIP 7，EXITCODE=0（logs/acceptance/v5_final_run.txt）；tests/unit 全量单独跑 257 tests OK（skipped=10）；ruff 单独跑零告警 |
| A6 | passed | brief.md | A6: 渲染失败语义收紧生效（qgis 一侧）：构造「`.qgz` 生成失败但 `.png` 成功」的条件时， `emit_map` **必须**判失败——`job.error` 非空、不返回成功结果；`smoke_map_renderers.py qgis` 退出码非 0。实测须给出失败消息含 qgz 失败原因的片段。 | qgz 崩 + png 成：HEAD(修复前) 实现返回成功（PASSED，假 PASS 实锤）→ 工作树实现抛 RuntimeError，消息含 qgz 真实原因；经真实 Jobs 生命周期 job.status=failed、job.error 非空、job.result=None；smoke_map_renderers.py qgis 子进程 OUTER_EXIT=1（logs/acceptance/v5_head_vs_worktree.json / v5_job_error.json / v5_smoke_exit.txt） |
| A7 | passed | brief.md | A7: 布局失败不再被吞：当 QGIS 侧返回 `layout_error` 非空时，`emit_map` 判失败并把该错误 写进失败消息/结果（不得出现「结果里对布局失败毫无痕迹」）；相应的成功路径（无 layout_error） 仍正常返回 `.qgz`。 | layout_error 非空：HEAD 实现返回成功且结果里无该错误（被吞）→ 工作树实现抛 RuntimeError 且消息含「布局生成失败：RuntimeError: 模拟布局失败」；layout_error 为空串/无该键/成功路径仍 PASS（边界不误判，logs/acceptance/v5_stub_qgis.py 与 v5_head_vs_worktree.json） |
| A8 | passed | brief.md | A8: arcpy 分支产物齐备性被核验：`write_aprx` 成功但**缺 `spec.layout.formats` 所要求的任一导出** 时，`emit_map` 判失败而非静默成功；正常情况下 formats（默认 `("pdf","png")`）所要求的导出齐备 仍 PASS，**不得把合法配置误判为失败** —— 特别是 `formats=("pdf",)` 这种只要求单一格式的 合法 spec 必须 PASS；`layout=None`（nolayout，无任何导出）也必须 PASS。 | 真实 arcpy 子进程六组 formats 全 PASS（all_exist=true）：("pdf","jpg") 118.3s / ("jpg",) 115.0s / ("png",) 114.5s / () 114.8s（回落 pdf+png）/ ("pdf",) 116.9s / layout=None 115.5s（仅 aprx）；伪造缺件全 FAIL（缺 png 键、pdf 路径不存在）（logs/acceptance/v5_real_arcpy_6formats.json、v5_real_arcpy_forged.json） |
| A9 | passed | brief.md | A9: 收紧后既有资产不回归：`tests/unit` 全量仍全绿、`uvx ruff@0.17.0 check` 零告警、 `tests/smoke_three_exits.py` 与 `tests/smoke_osm.py` 中读取 `qgz_error`/`overlay_errors` 的 代码**未被修改**（`git diff` 为空）且其判错逻辑语义不受影响；`tests/verify_all.py` 仍一条命令 跑通（渲染两项在缓存命中态 PASS）。 | git diff 证明 tests/smoke_three_exits.py、tests/smoke_osm.py 未被修改（UNCHANGED）；tests/unit 无 dirty；读取 qgz_error/overlay_errors 的代码位置原样（smoke_three_exits.py:31、smoke_osm.py:140/160）；tests/unit 257 用例全绿；ruff 零告警；verify_all 一条命令跑通且渲染两项 PASS |
| A10 | passed | specs/verify-all/spec.md | 全量验证一条命令跑通（验收：A10） 哥哥在仓库根执行 `python tests/verify_all.py`，入口自动起停 daemon，无需任何手工前置步骤；RUN 层全部执行，SKIP 层保持跳过；结束后打印汇总并按退出码语义返回。 > ⚠️ **c17 修订（2026-10-18）**：本条在 C14 归档时的验收编号为 A1；在 c17 中编号改为 **A10** > （brief 的验收示例占用 A1–A9）。语义不变：一条命令跑通的总纲。原文保留不删。 | 仓库根 python tests/verify_all.py 自动起停 daemon（日志见「临时 daemon 已停止」），RUN 层全执行、SKIP 层保持跳过，末尾打印汇总与退出码 0（logs/acceptance/v5_final_run.txt） |
| A11 | passed | specs/verify-all/spec.md | 覆盖矩阵防漏测（验收：A11） 报告中的覆盖矩阵覆盖 README 全部功能面模块；每个模块至少映射一项实际检查项（RUN 或 SKIP），无法映射的模块显式标 `uncovered` 而非静默缺失。 | coverage_matrix 16 个模块全部有映射行、uncovered_modules=[]、每行 status 不为 missing；含新增「静态检查（ruff 门禁）」模块映射 ruff-check=pass（logs/acceptance/v5_static_audit.json） |
| A12 | passed | specs/verify-all/spec.md | 离线层零网络通过（验收：A12） tests/unit 全量用例、tui-timeseries-probe、daemon-endpoint-probe（及前置产物存在时的 rescan-big）执行通过；全程对外网请求为零（仅本地回环 127.0.0.1 访问）。 > ⚠️ **c17 修订（2026-10-18）**：本条 RUN 层构成已被扩展 —— 当代缓存命中时， > `smoke-map-renderers-qgis` / `-arcpy` 亦在 RUN 层执行并通过；ruff 项以 > `uvx --offline` 执行（零外网请求）。「全程对外网请求为零」的口径不变， > 仍是本场景的硬断言。原文保留不删，修订依据见 `docs/comet/specs/README.md`。 | 入口源码内出现的 http(s) 主机仅 127.0.0.1，network_allowlist=["127.0.0.1"]；RUN 层含 tests-unit/tui/daemon-probe/渲染两项全部通过；ruff 以 uvx --offline 执行（冷缓存实测 DOWNLOADS=0、零外网） |
| A13 | passed | specs/verify-all/spec.md | 在线依赖项显式跳过（验收：A13） smoke_emit、smoke_three_exits、smoke_presets、smoke_timeseries、smoke_osm、smoke_tui、smoke_map_renderers（缓存未命中时）、smoke-array-chunking-rescan-big（前置产物缺失时）被标记 SKIP，报告中可见原因与单独复跑方式；入口不提供 --online 开关。 > ⚠️ **c17 修订（2026-10-18）**：本条的 SKIP 集合已收窄 —— > `smoke_map_renderers`（qgis/arcpy）与 `smoke-array-chunking-rescan-big` 改为**条件项**： > 前置产物存在时**不得**出现在 SKIP 集合中（自动入 RUN 层），缺失时才 SKIP 且文案写实。 > 「入口不提供 --online 开关」不变。原文保留不删，见 `docs/comet/specs/README.md` 台账。 | SKIP 集合实测 7 项（rescan-big、smoke-tui、smoke-emit、smoke-three-exits、smoke-presets、smoke-timeseries、smoke-osm），每项均有原因与单独复跑命令；smoke_map_renderers 两项因缓存命中不在 SKIP 集合内（符合收窄口径）；入口无 --online 开关（仅文档字符串提及「不提供」） |
| A14 | passed | specs/verify-all/spec.md | JSON 报告可机读（验收：A14） `logs/verify_all_report.json` 落盘且字段完整（名称/模块/层/状态/耗时/日志路径，失败项含输出摘要）；控制台摘要与 JSON 内容一致。 | logs/verify_all_report.json 落盘，顶层 9 个字段齐全、13 条 check 的 10 个字段无一缺失、log_path 全部真实存在；控制台逐项 [PASS/FAIL/SKIP] 与 JSON 状态一致（logs/acceptance/v5_static_audit.json） |
| A15 | passed | specs/verify-all/spec.md | 既有资产行为零修改（验收：A15） tests/ 下 9 个 smoke 与 tests/unit 的既有代码在本 change 中不被修改（git diff 为空）；入口仅编排运行。 | tests/ 下仅 tests/verify_all.py 被修改（git status 仅 M tests/verify_all.py），9 个 smoke 与 tests/unit 全部零改动（smoke_changed=[]、unit_dirty=[]） |
| A16 | passed | specs/verify-all/spec.md | 不真实启动 ArcGIS Pro（验收：A16） 全量验证全程不启动 ArcGIS Pro UI 进程；add-in/arcpy 面的验证由 tests/unit 断言（test_pro_addin、test_preflight_pro_endpoint）承担，并在覆盖矩阵中体现为 add-in 探测/arcpy bridge 模块的检查项。 > ⚠️ **c17 补充（2026-10-18）**：`smoke-map-renderers-arcpy` 进入 RUN 层后，本场景约束不变且 > 已实测复核 —— arcpy 出图经 `arcgispro-py3` 解释器的**子进程**完成（`arcpy.mp.CreateArcGISProject`）， > 2026-10-18 缓存命中的一轮 `tasklist` 核对**无** `ArcGISPro.exe` 进程；本入口仍不含任何启动 Pro UI 的调用。 | 全程 tasklist 核对无 ArcGISPro.exe（含 arcpy 真实渲染运行期间的多点抽样）；arcpy 出图经 arcgispro-py3 解释器子进程完成（进程命令行可见 make_aprx.py）；入口无需启动 Pro UI（logs/acceptance/v5_static_audit.json、进程抽样输出） |
| A17 | passed | specs/verify-all/spec.md | 条件项按盘上事实自动升降（验收：A17） 当代指纹的 P0 栅格缓存存在时，`smoke-map-renderers-qgis` 与 `smoke-map-renderers-arcpy` 在报告中为 `layer=run / status=pass` 并附真实耗时；缓存缺失时两项为 `layer=skip / status=skip`，文案写明「当代缓存缺失，联网跑一次即可离线复跑」，不得出现「已命中」字样。`smoke-array-chunking-rescan-big` 同款语义保持一致。 | 命中态两项 layer=run/status=pass 且 duration_s 为真实耗时（4.0s / 117.3s）；缺失态两项 layer=skip/status=skip、probe.hit=false、文案写「当代指纹缓存缺失…联网跑一次后本项自动转 RUN」且不含「已命中」；rescan-big 同款条件语义一致（logs/acceptance/v5_cache_states.json） |
| A18 | passed | specs/verify-all/spec.md | SKIP 文案与盘上事实逐条一致（验收：A18） 报告中每条 SKIP 的措辞与盘上/环境事实一致：产物存在时不含「不存在 / 未命中」，产物缺失时不含「已命中」，产物在主工作区盘上时不含「不在主工作区」；`summary.skipped` 等于 `status == "skip"` 的条数，且与各条件项的实际前置条件吻合。 | 逐条核对：产物存在的条件项文案无「不存在/未命中」；缺失态无「已命中」；rescan-big 不再出现「不在主工作区」；summary.skipped(7)==status=='skip'(7)（logs/acceptance/v5_report_audit.py，problem count: 0） |
| A19 | passed | specs/verify-all/spec.md | ruff 以可选 RUN 项接入（验收：A19） uv/ruff 可用时，入口以 `uvx --offline ruff@0.17.0 check` 执行 ruff 门禁并计分：零告警为 PASS、有告警为 FAIL（进程退出码 1）；uv 或 ruff 不可用（含 uv 缓存冷、`--offline` 无法解析）时该项为 SKIP 并给出安装/预热提示，不判 FAIL；两种条件下入口均不发起外网请求。 | 暖缓存零告警 PASS；有告警时 FAIL 且进程退出码 1（实测注入 F821 后 EXITCODE=1）；冷 uv 缓存（--offline 无法解析，REAL_EXIT=1、DOWNLOADS=0）时该项为 SKIP + 安装/预热提示、入口 overall 不受影响；两条件下入口均不发起外网请求（代理指向 127.0.0.1:9 仍无下载） |
| A20 | passed | specs/verify-all/spec.md | 渲染局部失败必须判失败（验收：A20） 构造「`.qgz` 生成失败但 `.png` 渲染成功」的条件时，`emit_map` 必须判失败：抛错、`job.error` 非空、 不返回成功结果，失败消息包含 qgz 一侧的真实原因；对应 `smoke_map_renderers.py qgis` 退出码非 0。 > ⚠️ **c17 修订（2026-10-18，用户裁决「全量修复风险」）**：本条推翻原实现口径 —— > `gis/emit.py` 原 `branch_failed` 判据为「`qgz_error` **且** `png_error`」， > 即两者都失败才算失败；已实测复现「qgz 失败 + png 成功 ⇒ 整体判成功」。 | qgz 失败但 png 成功条件：emit_map 抛 RuntimeError、失败消息含 qgz 侧真实原因（'RuntimeError: 模拟 QGIS 工程生成失败'）、job.status=failed/job.error 非空/job.result=None；对照 HEAD 版本同条件 PASSED（假 PASS 已闭合）；smoke_map_renderers.py qgis 退出码 1（logs/acceptance/v5_head_vs_worktree.json、v5_job_error.json、v5_smoke_exit.txt） |
| A21 | passed | specs/verify-all/spec.md | 布局失败不再被吞（验收：A21） QGIS 侧返回 `layout_error` 非空时，`emit_map` 判失败并把该错误写入失败消息/结果； 不得出现「报告里对布局失败毫无痕迹」。无 `layout_error` 的正常路径仍返回 `.qgz`。 > ⚠️ **c17 修订（2026-10-18）**：`gis/qgis_bridge.py` 一直产出 `layout_error`， > 但 `gis/emit.py` 只读 `layout` 键、丢弃该错误；已实测复现结果中无任何痕迹。 | layout_error 非空时 emit_map 判失败并把该错误写入消息（「布局生成失败：RuntimeError: 模拟布局失败」）与结果键 layout_error；无 layout_error 的正常路径仍返回 .qgz 且 PASS；layout_error 为空串亦不误判（logs/acceptance/v5_stub_qgis.py、v5_head_vs_worktree.json） |
| A22 | passed | specs/verify-all/spec.md | arcpy 产物齐备性核验（验收：A22） `write_aprx` 返回成功但**缺 `spec.layout.formats` 所要求的任一导出**时，`emit_map` 判失败而非 静默成功；`.aprx` 恒为预期产物。正常情况下 formats（默认 `("pdf","png")`）齐备仍 PASS； `formats=("pdf",)` 这类**只要求单一格式的合法配置必须 PASS**；`layout=None`（nolayout， 只出 map-only `.aprx`、无任何导出）**不**算失败。 > ⚠️ **c17 新增（2026-10-18）**：原实现仅在 `res.get(key)` 为真时登记产物，缺键不报错。 > 该条与上两条共同确立「预期产物缺一即失败」的统一口径。 | arcpy 预期产物按 spec.layout.formats 推导：真实成功六组全 PASS；12 例桩矩阵含「缺键」「键在文件不在（Path.is_file 复核）」「aprx 缺失」全按预期 RAISE；formats 单格式 （"pdf",)/("jpg",)/("png",) 与 formats=() 回落、layout=None nolayout 均 PASS；真实成功后再篡改（缺 png 键 / pdf 路径不存在）亦 RAISE（logs/acceptance/v5_arcpy_matrix.json、v5_real_arcpy_6formats.json、v5_real_arcpy_forged.json） |
| A23 | passed | specs/verify-all/spec.md | 收紧失败语义不回归既有资产（验收：A23） `tests/unit` 全量仍全绿、`uvx ruff@0.17.0 check` 零告警；`tests/smoke_three_exits.py` 与 `tests/smoke_osm.py` 中读取 `qgz_error`/`overlay_errors` 的代码**未被修改**且判错语义不受影响； `tests/verify_all.py` 仍一条命令跑通，缓存命中态渲染两项 PASS 且成功产物哈希不漂移。 > **跨 capability 说明（2026-10-18）**：`emit_map` 的失败判定实现位于 `gis/emit.py`， > 其 capability 归属为 `p1a-arcpy-bridge`（该 spec 定义了 `emit_map` 的 renderer 纪律与产物面）。 > 本 change 对「局部失败/布局失败/导出缺失」的收紧只直接影响 **verify-all 的 PASS 可信度**， > 因此验收与场景登记在本 spec；`p1a-arcpy-bridge` 的既有条款未被删除或改写。 > **用户 2026-10-18 选 (a)**：`p1a-arcpy-bridge` 的 spec 与归档副本**只追加一条 `> ⚠️` 注记** > 指向本次收紧（原文零删除、双副本逐字节一致、README 台账登记），**不改动**其 Scenario、 > Scenario 编号与既有验收；`emit_map` 的 renderer 纪律与产物面条款本身不变。 | tests/unit 257 用例全绿、ruff 零告警；smoke_three_exits.py / smoke_osm.py 读取 qgz_error/overlay_errors 的代码未改（UNCHANGED）；verify_all 一条命令跑通（EXITCODE=0）且渲染两项 PASS；像素级零漂移：同一 spec 连跑两次 layout.png 原生像素 sha 均为 64d3ff64…（与 Builder 两次快照一致）、rgb8.tif 字节 sha b201707a… 一致；.png 与 .rgb8.tif 与基线逐字节相同；.qgz 因 zip 内 uuid/时间戳天然不稳定故不比整文件字节；PDF 整文件字节不稳定（CreationDate/ModDate、XRef /ID、字体子集前缀）但 pdftoppm 渲染页逐字节相同 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| verify-all end-to-end | tests/verify_all.py | . | passed | 0 | 152234 ms |
| ruff gate | --offline ruff@0.17.0 check | . | passed | 0 | 161 ms |
| comet spec structural guard | -m unittest tests.unit.test_comet_spec_consistency | . | passed | 0 | 182 ms |
| tests/unit full | -m unittest discover -s tests/unit | . | passed | 0 | 17294 ms |
| render failure semantics self-check | logs/acceptance/c17_fix_verify.py | . | passed | 0 | 329 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- 破坏性自证（三处假 PASS 必须判失败）: passed — logs/acceptance/c17_fix_verify.py → 6 例全 OK（3 个必须失败 + 3 个边界必须成功），RESULT: ALL OK；已改为脚本自举 sys.path，不依赖外部 PYTHONPATH（首轮 Runtime 检查因缺 PYTHONPATH 报 ModuleNotFoundError: gis，已修复）
- 修复前对照取证: passed — logs/acceptance/c17_risk_probe.py 记录修复前同条件判成功（qgz_error 存在但 emit_map 返回成功）
- 真实渲染零回归: passed — smoke_map_renderers.py qgis 4.8s / arcpy 24.1s 均正常出产物
- verify_all 全量: passed — EXITCODE=0，RUN 6（PASS 6/FAIL 0）· SKIP 7
- A2 措辞机械检查: passed — 命中/缺失两态各一轮全通过
- 结构守卫: passed — Ran 8 tests OK；verify-all 与 p1a 双副本 md5 各自一致
- ruff: passed — uvx --offline ruff@0.17.0 check → All checks passed!
- tests/unit: passed — Ran 257 tests OK (skipped=10)
- 改动面: passed — gis/emit.py、tests/verify_all.py、verify-all spec×2、p1a spec×2、README；smoke/unit 零 diff
- A22 revision: jpg/空 formats 复现与修复: passed — logs/acceptance/c17_jpg_repro.py 修复前三例误判 → 修复后四例全 PASS；真实 arcpy 子进程无桩
- revision: 全量回归复跑: passed — unit 257 OK、ruff 零告警、结构守卫 8/8、selfcheck 10 例 ALL OK、verify_all RUN 6 PASS 6 / SKIP 7 exit 0
- revision5: Path.is_file() 闭合风险: passed — ghost-artifact 桩（键在文件不在）→ 判失败；自检 11 例 ALL OK
- revision5: 真实渲染复跑: passed — qgis EXIT=0 3.9s；arcpy EXIT=0 117.3s（机器劣化，HEAD 同刻 117.8s）
- revision5: 结构守卫与副本一致: passed — 三份 spec md5 同为 2e4a0a5e…；守卫 8/8 OK
- 已知限制: 运行环境相关：ruff 项层位取决于本机 uv 缓存是否预热（uvx --offline）；冷缓存按设计归 SKIP + 安装提示，不判失败（Q2=a 语义）
- 已知限制: 渲染两项层位取决于本 worktree 的 data/derived/ 是否有当代指纹缓存；data/ 不入库，换工作区需重新生成
- 已知限制: rescan-big 前置产物（816MB）只在主工作区，本 worktree 内该项恒 SKIP（文案已写明查找路径）
- 已知限制: overlay_errors 仍只作诊断信息、不升级为失败 —— 升级会改变 p3-osm-overpass（C8）已确认的可选/降级语义，本 change 未做
- 已知限制: arcpy 分支的「导出缺失」修复属防御性收紧：bridge 侧导出异常目前本就会冒泡，实测未复现真实缺键场景，故 A22 用桩验证
- 已知限制: 失败判定收紧后，若某环境 QGIS 布局本就不稳定（layout_error 偶发），该项会由「假 PASS」变为「真 FAIL」——这是预期行为，但会让该环境的 verify_all 转红

## 阻塞项

_无。_

## 风险与跳过的工作

- 【低】arcpy 本机当前 117–121 s/轮，比 spec 早期记录的 24 s 慢约五倍；已用改动前（HEAD）代码同时刻实测同样约 118 s，证实属环境因素、与本 change 无关（未深挖根因）。
- 【口径】.qgz 因 zip 内随机 uuid/时间戳与 QGIS 符号颜色随机化，跨次渲染字节天然不稳定；PDF 整文件亦不稳定（CreationDate/ModDate、XRef /ID、字体子集前缀），故零漂移判定必须用像素级产物（.png/.rgb8.tif/layout.png 或 pdftoppm 渲染页）而非整文件字节。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native Shape artifacts changed | 2026-10-18T01:50:02.058Z |
| 2 | 1 | 0 | recovery | — | Native Shape artifacts changed | 2026-10-18T01:58:19.309Z |
| 3 | 1 | 1 | pass | — | c17 三项改动（tests/verify_all.py、发布面+归档面 spec、specs/README.md）经独立复核全部成立：A1/A13 缓存命中与缺失两条件均亲造条件实跑（命中 qgis 5.0s / arcpy 24.8s，layer=run/status=pass；缺失两项 layer=skip/status=skip 且文案写实）；A2/A14 机械比对报告文本与盘上事实零违规，summary 计数三方相等；A3 发布面/归档面 sha256 同为 d7a0723…、原文 79 行零删除（仅 7 条 Scenario 标题内编号后移，均有对应新标题 + spec 内『c17 编号说明』）、结构守卫 8/8 OK；A4/A15 ruff 双条件（暖缓存 All checks passed、冷 UV_CACHE_DIR 转 SKIP 不 FAIL、注入 F401 后 FAIL 且退出码 1、黑洞代理证明零网络）；A5 tests/unit 257 通过 + ruff 零告警 + 一条命令端到端跑通；A11 gis/ tests/smoke_*.py tests/unit/ 零 diff；A12 全程轮询 tasklist 无 ArcGISPro.exe。只读纪律守住：缓存改名实验后 sha256 还原一致，data/ 与 logs/ 按快照逐字节还原。 | 2026-10-18T02:38:54.710Z |
| 3 | 1 | 1 | recovery | — | 回 Build 补一处实现瑕疵：tests/verify_all.py 文件末尾缺换行（HEAD 原版有，diff 出现 No newline at end of file），仅补齐末尾换行、不改任何逻辑与口径；补后重新交接验收。 | 2026-10-18T02:58:26.861Z |
| 3 | 2 | 1 | pass | — | iteration 2 独立只读复核 A1–A15 全部通过：末尾换行已补（tail -c 1 = 0a、diff 中 No newline 标记为 0、numstat 仍 139/23，HEAD 原文本就以 0a 结尾故属回归原状），四种自造条件（缓存命中/缺失、ruff 暖/冷/注入违规）均独立实跑留证，黑洞代理证明零外网、261 次 tasklist 采样证明无 ArcGISPro.exe；只读纪律守住——缓存 tif 前后 sha256 同为 5a3b837e…61f053，data/ 与 logs/ 按快照逐字节还原、git status 与开工前完全一致、无残留进程与监听端口。 | 2026-10-18T03:17:20.965Z |
| 3 | 2 | 1 | recovery | — | 需求变更（用户裁决「全量修复风险」）：把原先另立 change 的 gis/emit.py 渲染容忍度纳入本 change 范围。已实测复现两处假 PASS：①qgis 分支 .qgz 失败但 .png 成功时 emit_map 仍返回成功（job.error 为空）；②write_qgz 成功但 layout_error 非空时该错误被 emit_map 丢弃、结果里无痕迹。需回 Shape 重定范围与验收，并据此更新 verify-all spec 与发布面。 | 2026-10-18T03:39:25.285Z |
| 4 | 1 | 0 | recovery | — | Builder handoff Runtime checks failed: render-fix-selfcheck | 2026-10-18T04:00:46.464Z |
| 4 | 2 | 1 | recovery | — | 回 Build 重新冻结候选：Runtime 于 12:02 冻结的 candidate 67109959 及其 5 项检查证据对应的是修复 jpg 之前的 gis/emit.py，而我在 12:24 才修好 A22 的两处误判（jpg 登记面、formats=() 回落）；Verifier 第三轮核的是修复后版本（绑定 sha256 1ed2a9ce… 与当前一致）。为保证「检查证据与候选实现一致」，需重新交接以在修复后代码上重跑 Runtime 检查。 | 2026-10-18T04:41:49.973Z |
| 4 | 3 | 1 | pass | — | iteration 3 独立只读复核 A1-A23 全部 passed，verdict=pass。本轮焦点（上一轮 A22 FAIL 的两处修复）用真实 arcpy 子进程逐一实证：formats=(pdf, jpg) / (jpg,) / (png,) / () / (pdf,) / layout=None 六种情形全部 PASS——jpg 不再被判缺失，formats=() 按 bridge 的 or (pdf, png) 回落口径处理；同时缺件（bridge 返回成功但缺 formats 要求的键）仍判 FAIL。两处修复成立，未引入新误判。A6/A7/A20/A21 用同一套桩对照 git show HEAD:gis/emit.py（修复前）与工作区（修复后）：修复前三处均假 PASS（qgz 崩而 png 成仍返回成功、layout_error 无痕迹），修复后均抛错、job.error 非空、消息带真实原因，真实 smoke_map_renderers.py 退出码为 1。A1/A17/A18 双条件实跑（缓存 tif 改名、跑、还原，sha256 5a3b837e…61f053 逐字节还原），summary.skipped 7=7 / 9=9 与 status==skip 条数恒等，rescan-big 文案不再断言不在主工作区（主工作区 778.8 MiB 产物确在盘）。A3 双副本 cmp 逐字节一致、README 纯新增登记、原文零删除（仅 7 行 Scenario 标题改号，正文零缺失）、结构守卫 8/8 绿。A4/A19 ruff 暖/冷/违规三态齐备（PASS / SKIP 加提示零下载 / FAIL 且退出码 1）。A23 以像素级产物（png、layout.png、rgb8.tif）判零漂移：多轮实跑与 HEAD 对当前跨实现对照的像素 sha256 全同；.qgz 的 zip 随机成员前缀、6 个随机 uuid、saveDateTime 与 QGIS RandomizeDefaultSymbolColor 使同实现两次渲染字节本就不同（实测），.pdf 整文件同理但绘制指令流逐字节相同，故不以字节论漂移。只读纪律守住：未修改任何被跟踪文件（git status 与开工前一致），缓存与交付产物按原样留存并核验 sha256。 | 2026-10-18T05:31:48.169Z |
| 4 | 3 | 1 | recovery | — | 回 Build 修两处（用户裁决「继续修」）：①emit_map 登记 arcpy 产物时增加 Path.exists() 复核，闭合「键存在但文件不存在仍判 PASS」的缺口；②verify-all spec 写死的「arcpy ≈ 24.3–24.6 s」改为量级参考（实测同机可劣化到 120 s，HEAD 代码同时刻亦 117.8 s，属机器状态非本 change 引入）。 | 2026-10-18T05:32:54.034Z |
| 4 | 4 | 0 | recovery | — | Native Shape artifacts changed | 2026-10-18T05:45:00.779Z |
| 5 | 1 | 1 | pass | — | A1–A23 全 23 项 passed，verdict=passed。本轮重点复核两处修订：①gis/emit.py 新增 Path.is_file() 复核不会误判真实成功——真实 arcpy 子进程六组 formats 全 PASS 且产物均在盘（("pdf","jpg")118.3s、("jpg",)115.0s、("png",)114.5s、()114.8s 回落 pdf+png、("pdf",)116.9s、layout=None 115.5s 仅 aprx），伪造缺件（缺 png 键、pdf 键在但文件不存在、aprx 路径不存在）及「真跑成功结果篡改」全部 RAISE；②spec 三副本均无 24.3–24.6 硬编码残留，实测 117–121 s/轮与文案自洽。假 PASS 实锤：用 git show HEAD:gis/emit.py 载入修复前实现，同一桩下 qgz 崩+png 成 / layout_error 非空 / arcpy 缺 pdf 三场景修复前全部 PASSED，修复后全部 RAISE；job.error 经真实 Jobs() 生命周期确认 status=failed、error 非空、result=None，smoke_map_renderers.py 退出码 1。A1/A17 缓存缺失态为临时移走缓存、跑完立即归还（sha256 5a3b837e…c053 与基线一致，未删除未覆盖）；A2/A18 13 条 checks 逐条核对、summary.skipped=7==skip 条数、主工作区 816MB 产物确在盘且文案不再断言「不在主工作区」；A3 两对双副本 cmp 一致、旧文逐行零删除、结构守卫 8/8；A4/A19 暖缓存 PASS / 注入 F821 后 overall=fail 且退出码 1 / 冷 UV_CACHE_DIR 加黑洞代理转 SKIP 不 FAIL 且 DOWNLOADS=0；A5 一条命令跑通 RUN 6 PASS 6 / SKIP 7 退出码 0。中途 layout.png 字节变化经查是不同 spec 的 title 不同所致，同 spec 双跑证伪漂移。只读纪律守住：git status 仅含预期改动，注入文件已删除。 | 2026-10-18T06:25:22.411Z |



## 结论

A1–A23 全 23 项 passed，verdict=passed。本轮重点复核两处修订：①gis/emit.py 新增 Path.is_file() 复核不会误判真实成功——真实 arcpy 子进程六组 formats 全 PASS 且产物均在盘（("pdf","jpg")118.3s、("jpg",)115.0s、("png",)114.5s、()114.8s 回落 pdf+png、("pdf",)116.9s、layout=None 115.5s 仅 aprx），伪造缺件（缺 png 键、pdf 键在但文件不存在、aprx 路径不存在）及「真跑成功结果篡改」全部 RAISE；②spec 三副本均无 24.3–24.6 硬编码残留，实测 117–121 s/轮与文案自洽。假 PASS 实锤：用 git show HEAD:gis/emit.py 载入修复前实现，同一桩下 qgz 崩+png 成 / layout_error 非空 / arcpy 缺 pdf 三场景修复前全部 PASSED，修复后全部 RAISE；job.error 经真实 Jobs() 生命周期确认 status=failed、error 非空、result=None，smoke_map_renderers.py 退出码 1。A1/A17 缓存缺失态为临时移走缓存、跑完立即归还（sha256 5a3b837e…c053 与基线一致，未删除未覆盖）；A2/A18 13 条 checks 逐条核对、summary.skipped=7==skip 条数、主工作区 816MB 产物确在盘且文案不再断言「不在主工作区」；A3 两对双副本 cmp 一致、旧文逐行零删除、结构守卫 8/8；A4/A19 暖缓存 PASS / 注入 F821 后 overall=fail 且退出码 1 / 冷 UV_CACHE_DIR 加黑洞代理转 SKIP 不 FAIL 且 DOWNLOADS=0；A5 一条命令跑通 RUN 6 PASS 6 / SKIP 7 退出码 0。中途 layout.png 字节变化经查是不同 spec 的 title 不同所致，同 spec 双跑证伪漂移。只读纪律守住：git status 仅含预期改动，注入文件已删除。
