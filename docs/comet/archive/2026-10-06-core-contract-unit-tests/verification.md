---
generated_from_state_version: 20
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 3
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-06T06:20:11.480Z
- 摘要: 第 3 轮独立验收：63 个离线用例全绿（0.552s，远低于 10 秒），运行期禁网重跑零网络调用、ee 全程未加载；两条残余风险的修复均经源码级核实成立——D9 的守卫 docstring 已精确化为『仅发生 import、不触发网络调用（urlopen 位于 emit._download 函数体内）』并注明 pyproj 允许导入，与 emit.py:183/185、geoenv.py:218 事实一致；D10 的 spec.md A1 场景文字已更新为标准库+gis+pyproj 白名单表述，与 brief D10、D7 及测试实现三方一致，字面冲突消除。指纹行为与向后兼容守卫、三出口校验、with_/JSON 往返/slug、网格确定性与容差边界两侧断言、CGCS2000 中央经线属性校验、smoke 与 gis/ 资产保护全部独立复核成立。6/6 通过，verdict=pass。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | specs/core-contract-unit-tests/spec.md | 离线运行全绿（验收：A1） 在 geo env（`C:\ProgramData\miniforge3\envs\geo\python.exe`）、断网条件下执行单测套件（`python -m unittest discover -s tests/unit` 或等价 pytest 命令），全部用例通过。测试代码只导入标准库、被测的 gis 模块与 pyproj（D7 授权的 CRS 元数据查询，且为 `compute_grid` 生产实现的既有依赖）；**不导入 ee 或任何网络库**。 | geo env 下 python -m unittest discover -s tests/unit 全绿：63 用例 OK（returncode 0）。导入白名单核实：6 个测试文件仅导入标准库（ast/pathlib/unittest/dataclasses/json/re/mock）、被测 gis 模块（gis.spec/gis.grid/gis.crs_rules）与 pyproj（test_crs_rules.py:92 函数内导入），无 ee、无网络库。断网印证：运行期挂钩 socket.connect/connect_ex/create_connection/getaddrinfo 强制禁网后重跑 63 用例全绿且 network_attempts=0；套件运行后 sys.modules 中无 ee、无第三方网络库（urllib.request 仅被导入，无调用）。残余 1（D9）已修复：test_offline_guard.py docstring 第 12-13 行为「测试导入链仅发生 import、不触发网络调用（urlopen 位于 emit._download 函数体内，仅下载路径才执行）」，与源码事实一致（gis/emit.py:185 的 urlopen 位于 183 行 def _download 函数体内；gis/geoenv.py:218 import ee 为函数内延迟导入），第 16-17 行显式注明 pyproj 为 D7/D10 授权的允许导入。残余 2（D10）已修复：spec.md A1 场景（第 13 行）已更新为「只导入标准库、被测的 gis 模块与 pyproj（D7 授权的 CRS 元数据查询，且为 compute_grid 生产实现的既有依赖）；不导入 ee 或任何网络库」，与 brief D10 及测试实现一致，与 D7 的字面冲突消除。 |
| A2 | passed | specs/core-contract-unit-tests/spec.md | 运行时长（验收：A2） 全套用例在本机 geo env 下运行时长 < 10 秒。 | 全套 63 用例墙钟 0.552s（unittest 内部 0.280s），复跑 0.230s-0.241s，远小于 10 秒；与 Runtime 既有检查 unit-tests-offline（passed，533ms）量级一致。 |
| A3 | passed | specs/core-contract-unit-tests/spec.md | 指纹稳定性（验收：A3） - 仅 `note` / `tags` / `id` / `render` 不同的两个 `ArtifactSpec`，`fingerprint()` 返回值相同； - 同一 spec 重复调用 `fingerprint()` 结果一致； - `PROCESSING_VERSION` 变化（以等价手段模拟版本变化）后指纹变化。 | test_spec_fingerprint.py：test_meta_fields_do_not_change_fingerprint 对 id/note/tags/render 四个变体断言指纹与基准相同；test_repeated_calls_stable 断言同一 spec 重复调用一致；test_processing_version_changes_fingerprint 以 mock.patch 将 PROCESSING_VERSION+1 后断言指纹改变。三项全部通过，并与 gis/spec.py:209-220 的 payload 实现事实一致（排除 id/note/tags/render/nodata，含 _processing_version 与 9 个白名单字段）。另以 test_output_fields_change_fingerprint 反向锁定了全部 9 个白名单字段确实参与指纹。 |
| A4 | passed | specs/core-contract-unit-tests/spec.md | 指纹向后兼容守卫（验收：A4） 守卫测试显式声明两组名单：指纹白名单（asset / band_expr / crs / scale / aoi / dtype / bands / time_range / reducer，外加版本分量 `_processing_version`）与排除名单（id / note / tags / render / nodata——nodata 与其余元信息字段一样被 `spec.fingerprint()` 的 payload 现状排除；若未来认定 nodata 影响像素输出，须按红线 8 移入白名单并评估历史缓存影响），并断言 `ArtifactSpec` 的 dataclass 字段全集被两名单之并集覆盖。未来新增字段而未显式决定其指纹归属时，守卫测试失败，报错消息提示「决定入指纹白名单或加入排除名单」。 | 守卫测试显式声明 FINGERPRINT_FIELDS={asset,band_expr,crs,scale,aoi,dtype,bands,time_range,reducer} 与 EXCLUDED_FIELDS={id,note,tags,render,nodata}，与 spec A4 文字逐项一致；test_every_dataclass_field_is_accounted_for 断言 dataclass 字段全集（14 个）被并集覆盖，失败消息含处理方式（指明加入哪组名单并补回归断言评估缓存影响）；test_rosters_consistent_with_dataclass 断言两组名单不重叠且均为 dataclass 字段子集。版本分量 _processing_version 非 dataclass 字段、无法入字段名单，其指纹参与由 A3 的 PROCESSING_VERSION 测试单独断言（payload 实证含该键）——名单结构与守卫意图完整。 |
| A5 | passed | specs/core-contract-unit-tests/spec.md | 契约行为覆盖（验收：A5） - `validate(exit=...)`：array / file 出口要求 crs + scale + aoi，map 出口仅要求 aoi；缺失时报错消息含缺失字段名与修复提示；非法 dtype / reducer / time_range / aoi 均被拒绝； - `with_()` 返回新实例且原 spec 不变；`to_dict` / `from_dict` JSON 往返还原全部字段；`slug` 输出安全文件名； - `compute_grid`：同一 spec 多次计算结果一致（crs / transform / shape 相同），`Grid.matches()` 对一致参数返回真、不一致参数返回假； - `crs_rules`：PCS / GCS 判定与 CGCS2000 关键映射正确。 | validate(exit=...)：array/file 缺 crs/scale/aoi 逐项报错且消息含字段名，map 仅要求 aoi，报错含 spec.defaults 修复提示，非法 exit 被拒（ValidateExitTest）；with_ 返回新实例且原 spec 不变、to_json/from_json 往返逐字段相等、from_dict 元信息默认值、slug 清洗（含 '###'→'unnamed'）；compute_grid 同 spec 两次计算全等（crs/transform/shape，test_deterministic），Grid.matches 一致参数返回 True、错误尺寸/CRS 返回 False，容差边界两侧显式断言（1 米偏移在 rtol=1e-3 容差内不报警 / 5%\|xmin\| 偏移报警，D8 语义固化）；crs_rules PCS/GCS 判定（is_projected/is_metric/unit_of）与 CGCS2000 中央经线一致性属性校验（中国范围 7 个经度验证 EPSG 名称中 CM==3*round(lon/3)，不硬编码码位，PROJ 表为空时断言 cgcs2000_3deg_epsg 返回 None 且 suggest_crs 落 UTM 兜底，D7）。全部通过。 |
| A6 | passed | specs/core-contract-unit-tests/spec.md | 现有资产保护（验收：A6） `tests/smoke_*.py` 保持原样；`gis/` 无行为性修改。若测试暴露生产缺陷，最小修复须逐条记录于 Builder 交接，且改变像素输出的修复必须 `PROCESSING_VERSION += 1`（红线 3）。 | git status/diff 核对：gis/ 下无任何修改；tests/smoke_emit.py、tests/smoke_three_exits.py、tests/smoke_tui.py 为已跟踪文件且无改动。工作区其余变更仅为 .gitignore 追加 Comet 托管状态（+5 行，与 gis/、smoke 无关）、未跟踪工具目录（.codegraph/.comet/.zcode/AGENTS.md）及新增交付 tests/unit/。无生产缺陷修复发生，不涉及 PROCESSING_VERSION 变更。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| unit-tests-offline | -m unittest discover -s tests/unit | . | passed | 0 | 533 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- unittest 全套（geo env，开发期，第 3 轮）: passed — 63 用例 OK，0.241s
- 已知限制: gis 包 __init__ 传递导入 emit→urllib.request：导入链不触发网络调用（docstring 已如实描述）；彻底消除需把 __init__ 改为懒加载，属生产代码变更，超出 C1 范围。
- 已知限制: nodata 是否应参与指纹是留给后续 change 的契约议题（D5）。
- 已知限制: Grid.matches 的 rtol=1e-3 容差现状已由显式测试固化；收紧属生产语义变更，另立 change（D8）。

## 阻塞项

_无。_

## 风险与跳过的工作

- A1 的『断网条件』在本环境无法物理断网验证，以运行期挂钩真实联网原语（connect/connect_ex/create_connection/getaddrinfo，0 次尝试）+ 静态导入白名单核实 + 套件运行后 ee 未加载三重证据近似验证，结论可信。
- 离线守卫的 AST 扫描范围限于三个被测契约模块与 tests/unit/（含 _helpers.py），不含 gis/emit.py、gis/geoenv.py 自身——这是 D6 与守卫 docstring 明文声明的范围；gis/__init__ 传递链中 emit 顶层的 import urllib.request 依赖『仅 import、运行期零调用』这一经运行期禁网印证的事实，属已文档化的范围约定而非缺陷。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 1 | pass | — | 独立验收通过。6 个新增测试文件（61 用例）真实覆盖 brief 交付内容 1-6 与 spec 全部 6 个场景，断言与 docs/README.md §3.3/§11 红线 2/3/8 契约一致且未放松。我不仅复跑了 bound evidence 命令（61 tests OK, 0.24s），还做了增强验证：屏蔽全部出网原语后套件仍全绿（证明断网可运行）、ee 确认未被传递加载、A3 指纹行为与 A4 守卫逻辑用独立脚本复算（含假想新字段拦截与 nodata 反事实）、A5 关键报错消息与 CGCS2000 映射（EPSG:4548=CM 117E，正确）独立抽查、A6 用 git 三重核对 gis/ 与 smoke 零修改。A4 存在的唯一出入（排除名单额外含 nodata）忠实反映指纹实现现状、经测试注释与 Builder known_limits 显式记录，不构成验收意图违背，已列为风险。无未完成的核查项。 | 2026-10-06T05:35:08.846Z |
| 1 | 1 | 1 | recovery | — | 用户要求修复 Verifier 列出的四条风险后再接受结果：R1 nodata 名单出入——spec.md A4 场景的排除名单文字更新为 id/note/tags/render/nodata，与 fingerprint() 实现现状及守卫测试一致；R2 离线守卫 docstring 精确化（ee 为 geoenv 延迟导入、传递链仅 emit→urllib.request 且仅 import）并把 _helpers.py 纳入 AST 扫描；R3 CGCS2000 用例升级为中央经线一致性属性校验（对多个经度验证返回 EPSG 的 CM 与 3*round(lon/3) 一致，表为空时断言 UTM 兜底分支），不再只断言『是投影 CRS』；R4 Grid.matches 容差行为显式固化——新增用例断言容差内小偏移不报警（文档化现状）、超容差偏移必须报警。四项均为测试与文档强化，被测生产行为与红线不变。 | 2026-10-06T05:40:49.428Z |
| 2 | 1 | 1 | pass | — | 第 2 轮独立验收 6/6 通过。四条风险修复全部真实落地并经独立复算/实测确认：R1（A4）spec.md 排除名单文字与测试 EXCLUDED_FIELDS 逐字一致且与 fingerprint payload 现状吻合，守卫对 14 个 dataclass 字段全覆盖且模拟新增字段时端到端失败并给出二选一提示；R2（A1）AST 扫描运行时实测覆盖 tests/unit 全部 6 个文件（含 _helpers.py 与守卫自身，glob 保证未来新增文件自动纳入），docstring 的关键事实声明经实测成立（全套件运行后 ee 不在 sys.modules、断网沙箱全绿）；R3（A5）CGCS2000 中央经线一致性用例真实执行（表 21 条，7 个经度 CM 全部等于 3*round(lon/3)），表空兜底分支代码审查合理；R4（A5）容差两侧显式断言经数值复算确认位于有效容差（±440m）两侧且方向正确。63 例在 geo env 断网沙箱下 0.266s 全绿，gis/ 与 smoke 资产零改动。残余风险仅文档措辞与不可达分支两项轻微事项，不构成验收障碍。 | 2026-10-06T05:57:59.166Z |
| 2 | 1 | 1 | recovery | — | 用户要求继续修复第 2 轮验收列出的两条轻微残余风险：残余 1（docstring 措辞）——test_offline_guard.py 的传递链描述从『emit→urllib.request 仅 import 无调用』精确化为『测试导入链仅发生 import、不触发网络调用；urlopen 位于 emit._download 函数体内，仅下载路径才执行』，并在守卫注释中显式注明 pyproj 为 D7 授权的允许导入；残余 2（A1 文字与 D7 字面冲突）——spec.md A1 场景文字更新为『测试代码只导入标准库、被测的 gis 模块与 pyproj（D7 授权的 CRS 元数据查询）；不导入 ee 或任何网络库』，消除字面冲突。两项均为文档/文字强化，无任何行为变化。 | 2026-10-06T06:09:14.930Z |
| 3 | 1 | 1 | pass | — | 第 3 轮独立验收：63 个离线用例全绿（0.552s，远低于 10 秒），运行期禁网重跑零网络调用、ee 全程未加载；两条残余风险的修复均经源码级核实成立——D9 的守卫 docstring 已精确化为『仅发生 import、不触发网络调用（urlopen 位于 emit._download 函数体内）』并注明 pyproj 允许导入，与 emit.py:183/185、geoenv.py:218 事实一致；D10 的 spec.md A1 场景文字已更新为标准库+gis+pyproj 白名单表述，与 brief D10、D7 及测试实现三方一致，字面冲突消除。指纹行为与向后兼容守卫、三出口校验、with_/JSON 往返/slug、网格确定性与容差边界两侧断言、CGCS2000 中央经线属性校验、smoke 与 gis/ 资产保护全部独立复核成立。6/6 通过，verdict=pass。 | 2026-10-06T06:20:11.480Z |



## 结论

第 3 轮独立验收：63 个离线用例全绿（0.552s，远低于 10 秒），运行期禁网重跑零网络调用、ee 全程未加载；两条残余风险的修复均经源码级核实成立——D9 的守卫 docstring 已精确化为『仅发生 import、不触发网络调用（urlopen 位于 emit._download 函数体内）』并注明 pyproj 允许导入，与 emit.py:183/185、geoenv.py:218 事实一致；D10 的 spec.md A1 场景文字已更新为标准库+gis+pyproj 白名单表述，与 brief D10、D7 及测试实现三方一致，字面冲突消除。指纹行为与向后兼容守卫、三出口校验、with_/JSON 往返/slug、网格确定性与容差边界两侧断言、CGCS2000 中央经线属性校验、smoke 与 gis/ 资产保护全部独立复核成立。6/6 通过，verdict=pass。
