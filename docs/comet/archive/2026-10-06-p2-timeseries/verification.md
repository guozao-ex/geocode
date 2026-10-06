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
- 完成时间: 2026-10-06T14:34:06.670Z
- 摘要: 修订版需求下 8/8 全部通过，verdict=pass。两项残余风险修复属实且经独立核实：smoke_tui 断言按 D7 授权精确修改（唯一 hunk、同步 RPC 事实成立、内部判定 7/7）；nodata=0.0 经事实核查为 GEE 自洽约定（float64+填充0+头部0.0）并已在 README §8.1 #18 与 spec A3/Constraints 文档化，与 rasterio 实测逐项相符，头部未改写。A1-A7 未受影响：产物级独立比对（array/file 各 3 期×3 波段）全部 max|diff|=0.0 且掩膜一致、金指纹 c9243efd40318c85 命中、94 离线单测全绿、CRF 读回达标。无新破坏，无未决风险，可进入归档轮。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | specs/p2-timeseries/spec.md | 时序立方体 emit_array（验收：A1）【需网络，已标注】 时序 spec（P0 样本参数：S2_SR_HARMONIZED、北京 AOI、EPSG:32650、10m、B4/B3/B2、 reducer=median，time_range=("2024-06-01","2024-08-31") + time_step="month"，N=3）经 `emit_array` 落盘 `.nc`：数据集含时间维（N=3）与每波段一个变量，变量 dims = `(time, y, x)`；time 坐标为各期窗口起点（datetime 语义）；空间网格与 `compute_grid(spec)` 一致（crs/scale/shape 同单期）。xee 打开纪律：`crs_transform` 传 tuple、`shape_2d=(grid.width, grid.height)`、不做事后 `.chunk()`（大网格分块属 C6）。 结果 dict 报告期数、期窗口与 time 坐标。文件名沿用 `{slug}.{指纹8位}.nc` 约定。 | 独立复核 data/derived/s2_beijing_test.efea0214.nc：time=3/y=784/x=860，变量 B4/B3/B2 均 (time,y,x)，time 坐标=2024-06-01/07-01/08-01（各期窗口起点），文件名符合 {slug}.{指纹8位}.nc；网格与单期一致（784×860）。在最终代码状态缓存复跑 smoke_timeseries 的 A1 结构断言通过；第一/二轮 Verifier 产物级独立证实持续有效。 |
| A2 | passed | specs/p2-timeseries/spec.md | N 期堆栈逐期对齐——array（验收：A2）【需网络，已标注】 对每一期 i 构造单期 spec（不含时序字段，time_range=第 i 期窗口，其余参数相同），各跑 一次 `emit_array` 得单期 `.nc`。立方体第 i 期切片与该单期产物逐像素比对：有效掩膜逐期 一致，且 max\|diff\| ≤ `ALIGN_TOLERANCE = 0.5`（两者走同一计算语义 + computePixels， 预期逐位一致；若出现非零差，须在验收报告中解释来源）。3 期全部达标。 | 本人以 numpy/xarray 只读独立比对：立方体第 i 期切片 vs 对应单期 .nc（547fe502=6月、2ed731c8=7月、0d400f13=8月），3 期×3 波段 max\|diff\|=0.0 且 NaN 掩膜逐位一致；最终代码状态复跑 smoke_timeseries 同结果（0.0×3）；与第一/二轮 18 组比对结论一致。 |
| A3 | passed | specs/p2-timeseries/spec.md | N 期堆栈逐期对齐——file（验收：A3）【需网络，已标注】 时序 spec 经 `emit_file`：期集合在 `source.py` 内 `toBands()` 成单张多波段 ee.Image （每期设置 `system:index` = 期起点 YYYYMMDD，波段名 = `{YYYYMMDD}_{波段}`），复用现有 getDownloadURL 直下路径落盘 `.tif`，含 N×B=9 个波段且波段描述与波段名一致；空间网格 与 `compute_grid(spec)` 一致；像素上限检查按 N×B 放大（时序模式 est = width×height×N×B）。对每期 i 的单期 spec 各跑一次 `emit_file` 得单期 `.tif`；堆栈 第 i 期对应波段与单期 `.tif` 波段逐像素比对：max\|diff\| ≤ 0.5（int32 量化容差）且 nodata 掩膜一致。3 期全部达标。堆叠与单期 `.tif` 的掩膜/填充约定保持一致： GEE 直下 GEO_TIFF 为 float64、掩膜像素填充 0、头部 nodata=0.0（三者自洽，实测 9352 个 0 像素与 .nc 的 9352 个 NaN 一一对应）；"有效像素恰为 0 不可与掩膜区分" 是 GEE 导出格式固有限制，以踩坑记录文档化，不改写头部。 | 独立复核堆叠 efea0214.tif：9 波段命名 20240601_B4…20240801_B2 符合期×波段约定，float64、头部 nodata=0.0、784×860 网格对齐；堆叠波段 vs 对应单期 .tif 3 期全部 max\|diff\|=0.0 且掩膜一致。修订版 nodata 约定文字与实测相符：rasterio 只读核实全部 .tif 为 float64+填充0+头部0.0；P0 缓存 c9243efd 每波段 9352 个 0 像素与 .nc 每波段 9352 个 NaN 一一对应；堆叠 9 波段 0 像素合计 88344 等于 .nc NaN 合计 88344 且掩膜一一对应为真；头部未改写（_merge_stack 沿用首期 nodata）；README §8.1 踩坑 #18 文字核实无误。 |
| A4 | passed | specs/p2-timeseries/spec.md | CRF 多维栅格（验收：A4）【转换离线，依赖 A1 产物】 A1 的 `.nc` 经 arcpy 桥（arcgispro-py3 `CopyRaster`，subprocess + 文件交换，红线 7） 转出 `.crf` 多维栅格，落盘 `data/derived/`，命名 `{slug}.{指纹8位}.crf`；读回验证期数 =3、变量/波段数与 `.nc` 一致（arcpy 或 GDAL 多维 API 读回均可，注明方式）。背景：geo env 与 rasterio 的 GDAL 3.13.3 均无 CRF 驱动（2026-10-06 实测），CRF 写出必须走 arcgispro-py3。 | efea0214.crf 在盘且命名合规；本人在最终代码状态复跑 smoke_timeseries 的 A4 步骤：write_crf 重转 + arcgispro-py3 读回 is_multidimensional=True、变量数=3、各 StdTime=3（crf_ok 判定通过）；转换离线、subprocess 纯文件交换（红线 7）。 |
| A5 | passed | specs/p2-timeseries/spec.md | 旧 spec 指纹不变（验收：A5）【离线】 `time_step`/`time_ranges` 缺省（None）的 spec，指纹与不含该字段的旧 spec 完全一致； 以 P0 参数构造的 spec 指纹金值断言仍为 `c9243efd40318c85`（锚定 data/derived/ 既有缓存 产物）。设置了 `time_step` 或 `time_ranges` 的 spec 指纹必然改变（新字段在白名单）。 `PROCESSING_VERSION` 保持 2 不 bump——不含新字段的 spec 走的代码路径与产物逐位不变， 时序差异由新指纹字段承载（红线 3）。 | 本人运行时重算 make_p0_spec().fingerprint()==c9243efd40318c85 为 True；94 用例中金指纹断言、缺省时序字段指纹不变、设值必变指纹全部通过；PROCESSING_VERSION=2；c9243efd 缓存产物仍在盘。 |
| A6 | passed | specs/p2-timeseries/spec.md | 指纹守卫名单同步（验收：A6）【离线】 红线 8 守卫同步：`tests/unit/test_spec_fingerprint.py` 的 `FINGERPRINT_FIELDS` 纳入 `time_step` 与 `time_ranges`；dataclass 字段全集仍被 白名单∪排除名单 覆盖，未决定归属的 新字段会被守卫拦截。D5 结案（2026-10-06 C3 用户裁决）：`nodata` **维持排除**——调查 依据为 spec.nodata 在计算与出口全链路零消费（仅出现在序列化与元信息报告），不影响像素 值；结论写入守卫注释与本 Spec 存档，nodata 现状归属不变。 | FINGERPRINT_FIELDS 已纳入 time_step/time_ranges；EXCLUDED_FIELDS 含 nodata 且 D5 结案注释在位（test_spec_fingerprint.py 19-31 行）；字段全集覆盖守卫与名单一致性测试随 94 用例全绿；结论已存档 spec.md Decisions 与 README §3.3。 |
| A7 | passed | specs/p2-timeseries/spec.md | spec 校验与序列化（验收：A7）【离线】 `ArtifactSpec` 新增两个互斥时序字段： - `time_step: "day" \| "week" \| "month" \| "year" \| None`——节奏切片模式：以 `time_range[0]` 为起点，第 i 期窗口 = `[t0 + i·step, t0 + (i+1)·step)`；期起点 < t1 的期全部生成（N 由 起止÷步长 确定性推导）；最后一期窗口终点可越过 `time_range[1]` 至多一个步长（保证末段覆盖完整）。月/年步进用年月加法，日超过当月天数时钳制到月末； 日/周步进用 timedelta。 - `time_ranges: tuple[tuple[str, str], ...] \| None`——显式多段模式：N = len(time_ranges)， 期 i 窗口 = 条目 i 原样使用；允许不等长窗口，不禁止间隔或重叠（显式列表即契约）。 校验（SpecError 消息写清怎么修）：`time_step` 取值必须是四个步长之一（消息列出可选项）； `time_step` 设置时必须提供 `time_range`；`time_ranges` 每个条目必须是 (起, 止) 且 起 ≤ 止；两字段同时设置报互斥错误；期数 N > `MAX_TIME_PERIODS`（=120）报错（提示 缩短范围或加大步长）。任一字段设置即进入时序模式（`is_collection` 为真）。 `to_dict`/`from_dict` 对两字段往返保真（None/元组/列表语义不丢）。 `emit_map` 对时序 spec（任一时序字段非 None）报可读 SpecError：说明 map 出口暂不支持 时序，并给出生路（单期 spec 或等待后续 change）；不静默塌缩、不产出歧义产物。 | test_spec_timeseries 23 用例随全量绿：互斥、非法步长、缺 time_range、起>止、N>120 上限（收敛于 time_periods 直调受保护）、月末钳制、to_dict/from_dict 往返、emit_map 时序拒绝；第一/二轮 Verifier 实测 map 拒绝可读；本轮 daemon time_ranges 归一化为契约面补全，行为无害。 |
| A8 | passed | specs/p2-timeseries/spec.md | 回归基线不回退（验收：A8）【离线单测 + 本机 smoke】 geo env 下 `python -m unittest discover -s tests/unit` 全绿（断网可跑）；现有 smoke_emit / smoke_three_exits / smoke_map_renderers 行为零修改且不回退；smoke_tui 修正一处与 P0 以来同步 RPC 设计不符的过时断言（2026-10-06 修复轮，用户指示）： describe 走 `gee.describe` 同步端点、不入任务队列（client.py:103 → daemon.py:180， 事实已核），『产生新任务』断言改为『describe 不产生任务行（同步语义）且 spec 面板 被默认值填充』，其余行为不变。现有 4 个 smoke 由 tests/smoke_all.py（daemon 生命周期 包装，用后即停）作为可重复检查运行。 | (a) 94/94 离线单测全绿（本人重跑 0.274s）；(b) smoke_emit/smoke_three_exits/smoke_map_renderers 零修改（git status 无此三文件）；(c) smoke_tui.py 的 git diff 恰为一个 hunk，仅按修订版 A8/D7 授权将『产生新任务』(n_after>n_before) 改为『describe 同步语义（不产生任务行）』(n_after==n_before) 并加注释，其余检查零改动；(d) 同步 RPC 事实核实：client.py describe_asset（107 行）经 POST /rpc gee.describe → daemon.py act_gee_describe（180 行）直调 source.describe_asset，不入任务队列；(e) logs/_tui_check.txt 7/7 PASS（新断言 12→12），生成于 22:14:22 晚于全部代码修改，属最终状态证据；(f) smoke_all 6/6（runner 提交后复跑，make_qgz/make_aprx/_tui_check 时间戳佐证）。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| 离线单测全量回归 | -m unittest discover -s tests/unit | . | passed | 0 | 654 ms |
| 时序立方体验收 A1–A4（首跑需 GEE 网络；有缓存后离线可跑） | tests/smoke_timeseries.py | . | passed | 0 | 22229 ms |
| 现有 smoke 全量回归 + TUI 时序探针（需网络与桌面环境，约 2 分钟） | tests/smoke_all.py | . | passed | 0 | 117453 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- 离线单测全量（第三轮）: passed — 94 用例 0.30s OK
- smoke_timeseries 复跑: passed — A1–A4 达标（缓存路径）
- smoke_all 全量（第三轮）: passed — 6/6：emit 3.3s/three_exits 36.4s/map_renderers qgis 6.1s/arcpy 27.8s/tui 15.2s/tui-probe 3.1s
- smoke_tui 内部判定（修正后）: passed — 7/7：新断言 'describe 同步语义（不产生任务行） 8 → 8' PASS
- nodata 事实核查: passed — 3 个 .tif：float64/9352 个 0 像素/头部 0.0，与 .nc 的 9352 个 NaN 一一对应
- 金指纹离线验证: passed — c9243efd40318c85 三轮均 MATCH
- 已知限制: 1) 无未决风险：第一轮 Verifier 的 11 项风险已全部闭环（8 项第二轮验讫 + 风险1/风险2 本轮闭环 + 3 项轻微随本轮收口：TUI 探针已并入 smoke_all 持久可重复、README 台账状态随归档轮翻转、网络依赖由缓存缓解）。
- 已知限制: 2) GEE 直下 .tif 的掩膜/填充约定（float64/填充0/头部0.0）已规格化：'有效像素恰为 0 不可与掩膜区分'为 GEE 导出格式固有限制，已文档化（README §8.1 #18、spec.md A3/Constraints）。
- 已知限制: 3) chk-smoke-timeseries 首跑需 GEE 网络；产物缓存生效后离线可跑。chk-smoke-all 依赖本机桌面环境（QGIS/ArcGIS Pro/TUI）。

## 阻塞项

_无。_

## 风险与跳过的工作

- 口径差（非阻断）：交接称本轮仅改 smoke_tui.py 与 docs/README.md，但 client.py/daemon.py（21:48）与 tui.py/jobs.py/emit.py（22:10-22:13）在修订版 spec 确认（21:58）前后仍有保存。经 git diff 核查，改动为 pyright 类型标注、noqa 注释、jobs.py progress 空实现兜底与 daemon time_ranges 归一化，无验收路径行为变化；emit.py 最后修改（22:13:14）无法从 C3 主 diff 分离，但同属清理模式，且最终状态上 94 单测全绿、金指纹命中、smoke_tui 7/7（22:14:22）、smoke_timeseries 缓存复跑 A1-A4 达标，无破坏证据。建议归档轮在 verification.md 记录该口径。
- 极轻微：spec.md A8 引用 client.py:103，实际 describe_asset 定义在 107 行（daemon.py:180 精确）；同步语义实质无误。
- 极轻微：README #18 与 spec A3 的 9352 为 per-band/单期口径（8 月期每波段 10744；堆叠 9 波段合计 88344），与 P0 缓存实测一致、无事实错误，但可能被误读为堆叠总数。
- 设计内：README §9.2 台账 C3 状态仍未勾选，按 brief 约定随归档轮翻转。
- A1-A3 的 GEE 网络证据沿用第一/二轮产物级复算与本轮缓存路径复跑，未重新联网下载（按任务指示复用运行时绑定证据）。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-06T11:37:50.081Z |
| 2 | 1 | 1 | pass | — | 独立验证全部通过（8/8）。核心证据均为本验证独立取得而非转述：①离线重跑单测 94 用例全绿；②金指纹离线重算 c9243efd40318c85 精确命中（A5）；③对落盘产物做像素级独立比对——立方体 .nc（time=3, y=784, x=860, time 坐标=期起点, 变量 dims=(time,y,x)）、堆叠 .tif（9 波段期前缀命名、网格对齐）、逐期 vs 单期 array/file 共 18 组比对全部掩膜一致且 max\|diff\|=0.0（A1/A2/A3）；④用 arcgispro-py3 独立读回 .crf：is_multidimensional=True、B4/B3/B2 各 StdTime=3（A4）；⑤离线实跑 dispatch(map) 确认时序 spec 被可读 SpecError 拒绝（A7）；⑥红线核对：ee 对象仅 source.py 构建、云掩膜在 select 之前、PROCESSING_VERSION=2、指纹白名单缺省键缺席、守卫名单含 time_step/time_ranges 且 nodata 维持排除（D5 已结案存档）、crf 桥纯文件交换、daemon 仅一行归一化。唯一实质性偏差（A3 的 toBands 单请求改为逐期下载+本地合并）有实测 50MB 上限依据且被 spec Constraints 明确授权，验收判据全部满足。verdict=pass。 | 2026-10-06T13:10:02.119Z |
| 2 | 1 | 1 | recovery | — | Verifier 独立验收 8/8 pass，但按用户预留修复轮约定（全部风险含轻微修完才接受），回 Build 修复 Verifier 列出的风险：R2-1 新增 tests/smoke_all.py 守护进程生命周期包装跑 4 个既有 smoke（把 A8 的 smoke 证据变为 Runtime 可重复检查）；R2-2 emit_array 产物缓存（复用既有 .nc，对齐 _ensure_raster 哲学）；R2-3 source.diagnose_cube 逐期影像数诊断（计算失败时给出精确空期/期数报告，成功路径零开销）；R2-4 定向抑制 xee time_start 良性 UserWarning；R2-5 _merge_stack 增加逐期 dtype 一致性校验；R2-6 N 上限收敛进 time_periods()（两模式统一，直接调 API 也受保护）；R2-7 TUI 时序展示 headless 实测（并入 smoke_all）；R2-8 README 台账注明 A3 等价实现路径。风险 3（smoke_tui 先在失败）与 7（GEE nodata 头部怪癖）按 Verifier 建议留档另立 change/保持单期一致性。需求范围不变（--revise-implementation）。 | 2026-10-06T13:16:30.720Z |
| 2 | 2 | 1 | pass | — | 第二轮（修复轮）判定：pass。8 项修复（R2-1..R2-8）声明全部属实：smoke_all 生命周期包装、emit_array 指纹化产物缓存、diagnose_cube 失败路径诊断、xee 良性警告定向抑制、_merge_stack dtype 校验、N 上限收敛进 time_periods 直调受保护、TUI 时序探针、README 三处注记。所有新增代码均未改变 A1–A5 的产物与判据——本轮以产物级独立复核重新证实：立方体 .nc 结构/期数/time 坐标、A2 与 A3 各 3 期×3 波段逐像素比对全部掩膜一致且 max\|diff\|=0.0（逐位一致）、CRF 经 arcgispro-py3 独立读回 is_multidimensional=True 且 StdTime=3、金指纹 c9243efd40318c85 精确命中、守卫名单与 D5 结案在位、R2-6 直调缺口实测堵住、emit_map 时序拒绝可读、离线单测 94 用例 0.342s 全绿。两项先在风险（smoke_tui 先在失败、GEE nodata=0.0 头部怪癖）按第一轮建议如实留档，未被掩盖。验收 8/8 passed，可进入归档轮。 | 2026-10-06T13:43:35.639Z |
| 2 | 2 | 1 | recovery | — | 按用户指示修复残余风险，触发验收标准变化（--revise-requirements）：(1) 修复 smoke_tui『产生新任务』过时断言——describe 是同步 RPC 不入任务队列（client.py:103 → daemon.py:180，事实已核），将断言改为与设计一致（describe 不产生任务行 + spec 面板更新），这需要修改 A8『不修改既有 smoke 的行为』的文字；(2) nodata 风险经事实核查改判：GEE 直下 .tif 为 float64、掩膜填充=0、头部 nodata=0.0 三者自洽（9352 个 0 像素与 .nc 的 9352 个 NaN 逐一对应），『有效 0 值像素不可区分』是 GEE 导出格式固有限制，处置=精确文档化（README 踩坑记录新增条目 + spec/known limits），不改头部（改 -2147483648 反而会破坏掩膜语义）。 | 2026-10-06T13:56:23.463Z |
| 3 | 1 | 1 | pass | — | 修订版需求下 8/8 全部通过，verdict=pass。两项残余风险修复属实且经独立核实：smoke_tui 断言按 D7 授权精确修改（唯一 hunk、同步 RPC 事实成立、内部判定 7/7）；nodata=0.0 经事实核查为 GEE 自洽约定（float64+填充0+头部0.0）并已在 README §8.1 #18 与 spec A3/Constraints 文档化，与 rasterio 实测逐项相符，头部未改写。A1-A7 未受影响：产物级独立比对（array/file 各 3 期×3 波段）全部 max\|diff\|=0.0 且掩膜一致、金指纹 c9243efd40318c85 命中、94 离线单测全绿、CRF 读回达标。无新破坏，无未决风险，可进入归档轮。 | 2026-10-06T14:34:06.670Z |



## 结论

修订版需求下 8/8 全部通过，verdict=pass。两项残余风险修复属实且经独立核实：smoke_tui 断言按 D7 授权精确修改（唯一 hunk、同步 RPC 事实成立、内部判定 7/7）；nodata=0.0 经事实核查为 GEE 自洽约定（float64+填充0+头部0.0）并已在 README §8.1 #18 与 spec A3/Constraints 文档化，与 rasterio 实测逐项相符，头部未改写。A1-A7 未受影响：产物级独立比对（array/file 各 3 期×3 波段）全部 max|diff|=0.0 且掩膜一致、金指纹 c9243efd40318c85 命中、94 离线单测全绿、CRF 读回达标。无新破坏，无未决风险，可进入归档轮。
