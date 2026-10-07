---
generated_from_state_version: 18
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 3
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-06T15:07:46.600Z
- 摘要: 本轮修订候选（既有 LC08/LC09 补官方 offset -0.2 + PROCESSING_VERSION 2→3 + 金指纹更新为 b91c09c9c6451c16 + README 更新）经独立只读核验：A1–A8 全部通过。关键证据均为现场重算：P0 旧/新产物 sha256 逐字节相同（5a3b837e…）且逐像素 max|diff|=0；把版本号替换回 2 在当前代码与基线代码上均复现旧金值 c9243efd40318c85，6 条未受影响预设的字段与版本=2 指纹逐条与基线一致；三条 Landsat 预设共用 (2.75e-05,-0.2) 表，fresh 下载产物六波段均值等于 a×raw−0.2（差 ≤0.0001）且恰比无 offset 口径低 0.2；7 条预设×三出口 smoke 全通过（含空极化可读 SpecError、WorldCover 精确类码与 11 色精确配色），四条既有 smoke 与 C2 基线一致（smoke_tui 唯一失败项经代码路径证明为既有问题），离线 99 用例 0.587s 全绿，README 八处到位且 C3 内容保留。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | specs/p2-presets/spec.md | S1 预设三出口（验收：A1） 对两条 S1 预设各派生 spec（北京 AOI、`time_range=("2024-06-01","2024-09-01")`、`reducer="median"`） 并跑三出口：`emit_file` 产出 GeoTIFF、`emit_array` 产出 NetCDF、`emit_map` 产出工程与图； 三者 `spec_fingerprint` 相同、网格相同；极化过滤后集合非空；`S1_GRD` 像元值落在 dB 量纲 （约 -50~1），`S1_GRD_FLOAT` 落在正数量纲；请求该区域不存在的极化时抛可读 `SpecError` （消息含该区域实际出现的极化），不得静默产出空产物。 | 自跑 smoke_presets.py 两条 S1 预设×三出口全部 done 且产物落盘（file=tif / array=nc / map=qgz+png）；s1_db 三出口指纹一致 b8da2f12（均值 VV=-4.607、VH=-13.390，dB 量纲 -60~5），s1_linear 指纹一致 843065ac（VV=1.005、VH=0.087，正数量纲），出口网格一致性检查无警告；另现场用 build_image 请求该区域不存在的 (HH,HV)，抛 SpecError 且消息含『该区域该时段实际出现的极化：[('VV','VH')]』，无静默空产物。 |
| A2 | passed | specs/p2-presets/spec.md | Landsat 8+9 合并预设与既有预设修正（验收：A2） (a) `LANDSAT/LC08+LC09/C02/T1_L2` 派生 spec（北京 AOI、2024 夏、`reducer="median"`）跑通三出口； 产物均值为 `2.75e-05 × GEE 原始均值 − 0.2`（独立复算逐波段对上）；集合含 LC08 与 LC09。 (b) 修正后的既有 `LANDSAT/LC08/C02/T1_L2` 与 `LANDSAT/LC09/C02/T1_L2` 产物同样落在 `DN × 2.75e-05 − 0.2` 量纲（修正前偏高约 +0.2），其 `band_transforms` 与合并预设一致。 | (a) landsat89 三出口 done、指纹 62e014d9 三出口一致；独立 GEE 原始值复算逐波段对上 a=2.75e-05,b=-0.2（SR_B4 产物 0.0926 vs 复算 0.0926）；GEE aggregate 证实合并集合 11 景 = LC08 5 + LC09 6。(b) legacy_lc08/lc09 三出口 done、指纹一致（d8325bbd / a05c974f）；独立复算 SR_B4 0.0910 / 0.0946 与 a×raw-0.2 相等；另以新 id 强制 fresh getDownloadURL 重下（verify_lc08_fresh.d8325bbd.tif，sha256 8221f527…，与此前缓存产物逐字节相同），六波段均值与 a×raw-0.2 差 ≤0.0001、且恰好比『无 offset 口径』低 0.2000（修正前 +0.2 偏高已消除）；三条 Landsat 预设 band_transforms 均为 6 波段 (2.75e-05,-0.2)。 |
| A3 | passed | specs/p2-presets/spec.md | ERA5-Land 逐日预设三出口（验收：A3） `ECMWF/ERA5_LAND/DAILY_AGGR` 派生 spec（北京 AOI、`time_range=("2024-06-01","2024-07-01")`、 `reducer="mean"`）跑通三出口；`temperature_2m` 为摄氏量纲（北京 6 月约 15~35，而非 288~308）； `total_precipitation_sum` 以 mm 计（而非 m）；两者与独立复算一致。 | 自跑 smoke_presets.py era5 三出口 done、指纹 a4c67029 三出口一致；独立 GEE 原始值复算：temperature_2m 产物 27.11 vs 复算 27.09（a=1,b=-273.15，摄氏量纲而非 ~300K）、total_precipitation_sum 0.747 vs 0.742（a=1000,b=0，mm 而非 m）、两个风分量按 a=1,b=0 对上。 |
| A4 | passed | specs/p2-presets/spec.md | WorldCover 预设三出口（验收：A4） `ESA/WorldCover/v200` 派生 spec（北京 AOI）跑通三出口；栅格值为精确类码 （⊆ {10,20,30,40,50,60,70,80,90,95,100}，无 mean 产生的插值值）；`preset` 与 `defaults_for` 的 `dtype` 声明为 `uint8`；`emit_map` 的预览图与产物使用资产自带 11 色 palette 的精确类映射 （非 viridis 拉伸）。 | 自跑 smoke_presets.py worldcover 三出口 done、指纹 2387c5d0 三出口一致；.nc 唯一取值 [10,20,30,40,50,60,80,90] ⊆ 11 个类码（无 mean 插值值）；preset 与 defaults_for 的 dtype=uint8（离线断言）；读数核验 deliver 的 rgb8.tif 与预览 PNG：唯一色 ⊆ 资产自带 11 色 palette ∪ 黑，非类色 0 个、无 viridis 色（9352 个黑像素=掩膜），为精确类映射。 |
| A5 | passed | specs/p2-presets/spec.md | 版本纪律与既有预设语义（验收：A5） `PROCESSING_VERSION` 为 `3` 且变更理由可追溯；对 6 条未受影响的既有预设，指纹的变化面**仅** 来自版本号（把版本号替换回 2 后哈希与本 change 之前一致）；`ArtifactSpec` 字段集与指纹 白名单/排除名单不变；离线用例锚定 bump 后重算的 P0 指纹，原金指纹 `c9243efd40318c85` 已在文档中标注作废。 | PROCESSING_VERSION=3；独立复算 P0 指纹 b91c09c9c6451c16，把版本号替换回 2 复现 c9243efd40318c85（当前代码 mock 与基线 0cc8b25 的 spec.py 各算一遍，均为 c9243efd40318c85）；基线源码逐字段比对：6 条未受影响预设仅多出带缺省值的新字段、旧字段零差异，且这 6 条用预设派生 spec 在版本=2 时哈希与基线代码逐条相等（6/6）；LC08/LC09 仅 reflectance_scale(2.75e-05)→band_transforms 表；未受影响预设的旧/新磁盘产物逐字节相同（S1×2 / 合并 Landsat / ERA5 / WorldCover 的 derived tif+nc），P0 tif 与 nc 旧/新 sha256 相同（5a3b837e612cc2e2e1810a45551e067a…），nc 逐像素 max\|diff\|=0、掩膜一致；ArtifactSpec 字段集与指纹 payload 代码未变（diff 佐证 + 99 用例含指纹守卫全绿）；旧金指纹已作废并在 README 与测试中留痕。 |
| A6 | passed | specs/p2-presets/spec.md | 离线单测基线全绿（验收：A6） 在 worktree 内断网运行 `tests/unit` 全量用例，全部通过且秒级完成；`tests/unit` 不 import `ee`、 不发起网络请求。 | 在 worktree 内自跑 `PYTHONPATH=. geo/python -m unittest discover -s tests/unit -t tests/unit`：Ran 99 tests in 0.587s，OK；与 Runtime check id=unit-baseline（99 tests / 0.480s / exit 0）一致；suite 含离线护栏用例（不 import ee、不发起网络请求）。 |
| A7 | passed | specs/p2-presets/spec.md | 现有 smoke 不回退（验收：A7） `tests/smoke_emit.py`、`tests/smoke_three_exits.py`、`tests/smoke_map_renderers.py`、 `tests/smoke_tui.py` 四条 smoke 全部跑通，产物形态（网格 / 波段数 / 量纲 / 三个出口一致性） 与 C2 基线一致；指纹因本次 `PROCESSING_VERSION` bump 按设计变为新值、产物按新指纹重新生成 （这是 A5 记录的有意版本变更，不是回退）；其中 `smoke_tui` 的『产生新任务』项在未改动的 C2 基线上同样失败（既有问题，非本 change 引入）。 | 自跑四条：smoke_emit ✅ 指纹 b91c09c9c6451c16、860×784、4.44MB、栅格形态（EPSG:32650/float64/nodata 0.0）与 C2 基线一致；smoke_three_exits ✅ file/array/map 三出口 done、指纹与网格 860×784 一致；smoke_map_renderers qgis ✅（qgz+png+布局名回读）、arcpy ✅（aprx/pdf/png、15 个布局元素，26.6s）；smoke_tui 6/7——唯一失败『产生新任务 4→4』为既有问题：do_describe→client.describe_asset→同步 /rpc `gee.describe`（daemon act_gee_describe 不产生 job），且 tui.py/client.py/daemon.py 相对 0cc8b25 零改动；与 spec 记录的例外一致。 |
| A8 | passed | specs/p2-presets/spec.md | 文档更新（验收：A8） 主工作区的 `docs/README.md`（本地文档，非版本控制文件）已按最终状态更新：§9.2 台账 C4 行、 §2.2 与 §9.5 的预设数量 8 → 13、§11 红线 4 的 SAR 豁免说明、新增预设语义与 `PROCESSING_VERSION` 2 → 3 的变更记录；原「LC08/LC09 缺 offset」遗留记录已删除。 | 主工作区 D:/DEV/geocode/docs/README.md 只读核验：md5=8e95f1dffbc758f79a0d9fffa8c73ee0（与 Builder 声称一致）；§2.2『13 个数据集预设』、§3.3『PROCESSING_VERSION 当前 = 3』+ 旧金指纹作废/新金值、§9.1 C4 完成行、§9.2 C4 行已交付、§9.5『预设表 8 → 13』、§11.4 红线 4 的 SAR 豁免、新增 §9.7（5 条新预设语义表 + 遗留修正 0.302→0.102 + 版本与指纹 + 已知边界）均在；『缺 offset』只以已修正叙述出现、无遗留未决记录；并行 C3 内容保留（time_step/time_ranges 行、C3 台账行与 CRF 注记均在）。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| 离线单测基线（tests/unit 全量，断网秒级） | -m unittest discover -s tests/unit -t tests/unit | . | passed | 0 | 836 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- 离线单测基线（tests/unit 全量）: passed — 99 用例 / 0.55s / 断网
- smoke_presets.py 全量（7 用例 × 三出口）: passed — s1_db b8da2f12 / s1_linear 843065ac / landsat89 62e014d9 / era5 a4c67029 / worldcover 2387c5d0 / legacy_lc08 d8325bbd / legacy_lc09 a05c974f
- P0 产物跨版本一致性（sha256 对比）: passed — c9243efd 与 b91c09c9 两版产物 sha256 相同、max|diff|=0.0
- 既有 smoke_emit / smoke_three_exits / smoke_map_renderers: passed — 全部跑通；指纹按设计更新为新值，产物形态与基线一致
- 既有 smoke_tui: passed — 6/7；唯一失败项经 0cc8b25 基线 A/B 证明为既有问题
- S1 空集保护（北京 + HH/HV）: passed — 抛可读 SpecError 并列出该区域实际极化
- WorldCover 双 renderer（qgis / arcpy）: passed — .qgz+.png / .aprx 均产出无错
- docs/README.md 更新: passed — 8 处改动落地；C3 内容保留；md5 8e95f1df…
- 已知限制: 产物容器 dtype 不由 spec.dtype 决定（实测：声明 uint8 与 float32 两种写法，GEO_TIFF 容器都是 float32；既有 S2 声明 uint16、产物 float64）。WorldCover 的类码值仍为精确整数，故不影响取值语义；要控制容器 dtype 需改出口层写盘，会影响全部既有产物形态 —— 按确认的范围不在本次实施（已记入 README §9.7『已知边界』）。
- 已知限制: docs/README.md 被 .gitignore 的 /docs/* 忽略、不是版本控制文件，只在主工作区有本地副本：本次是就地更新（进程内原子改写 + md5 记录 + 核对未覆盖并行会话内容）。若并行会话在 22:37 之后又整篇重写该文件，本轮 §3.3/§2.2/§9.1/§9.2/§9.5/§9.7/§11 的改动可能被覆盖 —— 复核方式：查看文件是否含 '§9.7 数据集预设表（C4 交付，2026-10-06）' 与 'PROCESSING_VERSION` 当前 = 3'。
- 已知限制: smoke_tui 的『产生新任务』断言与当前 daemon 设计不匹配（describe 走同步 /rpc、不产生 job 行），在未改动的 C2 基线上同样失败 —— 既有问题，按确认的范围不修。
- 已知限制: 指纹变更使既有产物缓存全部成为孤儿（data/derived 下旧 c9243efd 与 0d400f13 等文件）；这是版本 bump 的预期后果，新运行按新指纹重新生成。
- 已知限制: 并行会话占用 6531；开发期发生过一次『另一会话同时提交同一 spec』导致的 .part 重命名 PermissionError（并发写同一输出路径无锁，既有行为）。

## 阻塞项

_无。_

## 风险与跳过的工作

- A8 的交付面 docs/README.md 不受版本控制（/docs/* 被 .gitignore），仅存于主工作区；本次核验时点内容与 md5 正确，但并行会话若再整篇重写该文件，本轮 8 处更新可能被覆盖且无 git 痕迹可查。
- data/deliver 的烘焙产物按指纹命名而 render 不入指纹：不同 RenderSpec（stddev vs percentile）写同一路径、后写覆盖先写（实测 s2 旧 c9243efd.rgb8 为 percentile 口径、新 b91c09c9 为 stddev 口径，两者的像素均被当前代码逐位复现，非回归）——跨轮比较交付物时需注意口径来源。
- 多数既有输出的 file/map 出口在本轮为缓存命中（指纹与新代码一致）；fresh 重下仅覆盖 LC08（与缓存逐字节相同）与各预设的 array 出口（xee 现拉），非 Landsat 的缓存 derived 产物未逐个重下复核。
- smoke 类脚本退出时打印『Error in sys.excepthook / Original exception was:』噪声（退出码 0、结果不受影响），属既有现象；解析日志时勿误判为失败。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 1 | pass | — | 7 项验收全部通过：A1–A4 用全新 GEE 三出口 smoke（5 预设×3 出口，指纹/网格一致，含 dB↔线性严格互转、Landsat L8+L9 合并与 -0.2 offset 复算、ERA5 K→°C 与 m→mm 复算、WorldCover 精确类码与 11 色精确配色）独立复核；A5 以基线 0cc8b25 源码逐字段比对确认既有 8 预设零变化、金指纹 c9243efd40318c85 与 PROCESSING_VERSION=2 不变，并用最终代码重下 P0 产物逐字节（sha256）比对一致；A6 断网护栏下 97 用例全绿 0.64s 且未加载 ee；A7 四条既有 smoke 中 emit/three_exits/map_renderers 结果与 C2 归档一致，smoke_tui 的『产生新任务』FAIL 经基线 A/B（隔离基线树 + 6544 守护进程）证明是既有问题、非回归。主要遗留风险是 WorldCover 容器 dtype 为 float32（判据按 spec/preset 层解读）、README 文档随归档轮补、以及 LC08/LC09 缺 offset 的遗留数值口径。 | 2026-10-06T14:11:10.729Z |
| 1 | 1 | 1 | recovery | — | 需求变更（用户在验收轮补充范围）：修复遗留问题 + 更新 README。 1) 修复既有 LC08/LC09 预设缺 offset 的遗留问题：给 LANDSAT/LC08/C02/T1_L2 与 LANDSAT/LC09/C02/T1_L2 两条既有预设补上官方辐射缩放 offset -0.2（即 SR_B2..SR_B7 用 band_transforms=(0.0000275, -0.2)），使合并预设与两条既有预设口径一致。 2) 由此产生并接受的行为变化：既有 Landsat 预设的产物反射率会下降约 0.2（这是修正目的）；按红线 3 必须 PROCESSING_VERSION += 1（2 → 3）；全部 spec 指纹随之变化（含此前的金指纹 c9243efd40318c85 作废并由新值取代），既有 Landsat 缓存产物失效并在下次运行时按新指纹重新生成。 3) 相应地更新验收判据：原 A5「旧 spec 指纹不回退」改为「版本纪律与变更面记录」——PROCESSING_VERSION 由 2→3 且变更理由记录在案；未受影响的既有预设（S2 / MODIS / DEM / GSW）的**计算语义**不变（其指纹变化仅来自版本号这一项）；既有 Landsat 预设的反射率落在含 offset 的正确量纲。既有 8 预设的字段快照仍是冻结对象（本次是有意变更其中两条的缩放口径，须在快照与注释中显式体现）。 4) 更新 docs/README.md（该文件被 .gitignore 的 /docs/* 忽略、不是版本控制文件，只在主工作区有本地副本）：§9.2 台账 C4 行状态、§2.2 与 §9.5 的预设数量 8→13、§11 红线 4 的 SAR 豁免说明、新增预设语义说明，并删除/改写「既有 LC08/LC09 缺 offset」这条遗留记录（因为已修）。 5) 仍不在范围内（记录为待决/非目标，不随本次实施）：出口层按 spec.dtype 强制写盘 dtype（会改变全部既有产物的容器 dtype）；smoke_tui 的『产生新任务』断言与 daemon 现状不匹配（既有问题，另行处理）。 | 2026-10-06T14:21:28.839Z |
| 2 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-06T14:26:42.154Z |
| 3 | 1 | 1 | pass | — | 本轮修订候选（既有 LC08/LC09 补官方 offset -0.2 + PROCESSING_VERSION 2→3 + 金指纹更新为 b91c09c9c6451c16 + README 更新）经独立只读核验：A1–A8 全部通过。关键证据均为现场重算：P0 旧/新产物 sha256 逐字节相同（5a3b837e…）且逐像素 max\|diff\|=0；把版本号替换回 2 在当前代码与基线代码上均复现旧金值 c9243efd40318c85，6 条未受影响预设的字段与版本=2 指纹逐条与基线一致；三条 Landsat 预设共用 (2.75e-05,-0.2) 表，fresh 下载产物六波段均值等于 a×raw−0.2（差 ≤0.0001）且恰比无 offset 口径低 0.2；7 条预设×三出口 smoke 全通过（含空极化可读 SpecError、WorldCover 精确类码与 11 色精确配色），四条既有 smoke 与 C2 基线一致（smoke_tui 唯一失败项经代码路径证明为既有问题），离线 99 用例 0.587s 全绿，README 八处到位且 C3 内容保留。 | 2026-10-06T15:07:46.600Z |



## 结论

本轮修订候选（既有 LC08/LC09 补官方 offset -0.2 + PROCESSING_VERSION 2→3 + 金指纹更新为 b91c09c9c6451c16 + README 更新）经独立只读核验：A1–A8 全部通过。关键证据均为现场重算：P0 旧/新产物 sha256 逐字节相同（5a3b837e…）且逐像素 max|diff|=0；把版本号替换回 2 在当前代码与基线代码上均复现旧金值 c9243efd40318c85，6 条未受影响预设的字段与版本=2 指纹逐条与基线一致；三条 Landsat 预设共用 (2.75e-05,-0.2) 表，fresh 下载产物六波段均值等于 a×raw−0.2（差 ≤0.0001）且恰比无 offset 口径低 0.2；7 条预设×三出口 smoke 全通过（含空极化可读 SpecError、WorldCover 精确类码与 11 色精确配色），四条既有 smoke 与 C2 基线一致（smoke_tui 唯一失败项经代码路径证明为既有问题），离线 99 用例 0.587s 全绿，README 八处到位且 C3 内容保留。
