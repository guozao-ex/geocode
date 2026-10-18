---
generated_from_state_version: 14
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 2
- 迭代: 2
- 验证器尝试次数: 1
- 完成时间: 2026-10-14T05:56:19.015Z
- 摘要: 独立验收：逐项核对 A1–A14 全部满足。独立复跑关键断言：A1/A9 file↔array 逐像元 mask_match=True、max|diff|=1.78e-07（容差 0.5）；A2/A8 强制分块 vs 直写 max|diff|=0.0、P0 金指纹 b91c09c9c6451c16 未回退；A3/A10 注入断连文案齐全且零残留；A4/A11 tif/nc nodata 均 NaN 且 NaN 计数 344=344，nodata 不入指纹故无 PV bump；A5/A12 paths.data_dir 生效；A6/A13 缓存清单+当代守卫成立；A7/A14 Runtime 检查（341 用例/ruff 0/verify_all RUN 4/4）与本工作区 HEAD 7cb31bc 匹配。工作区干净（仅未跟踪 docs/comet/changes/），实现即该提交。残留风险见 risks（collapse_mask_bands 整数 dtype 防御缺口、A1 array 走缓存复用、文档口径与红线解释性判断）。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: 泰安市（adcode 370900）S2 真彩色 10m（网格 17680×9355 = 165.4M 像素；按守卫口径 5 B/像素/波段估算请求体积 ≈2.5 GB ≫ 48 MB）三出口全部成功： file 产出 GeoTIFF、array 产出 NetCDF、map 产出 .qgz + .png；file 与 array 在同一网格上逐像元一致 （容差 0.5，逐像元不是抽样）。 | c15_a1.json 三出口 ok；磁盘产物 tif/nc/qgz/png 均在。独立复跑 compare_exits：B2/B3/B4 mask_match=True、max\|diff\|=1.7776489258380934e-07 < 容差 0.5（逐像元 165.4M，非抽样），网格 17680x9355@10m。注：array 出口本轮命中缓存（nc 为此前真实 370900 array 运行产物，本提交未改 emit_array），已在磁盘产物上独立逐像元复核。 |
| A2 | passed | brief.md | A2: 分块路径与直写路径产物一致：对小 AOI 强制走分块（可用测试开关或缩小的 `MAX_DOWNLOAD_BYTES`）， 产物与直写路径逐像元完全相同（max\|diff\| = 0）；既有 P0 样本产物与金指纹 `b91c09c9c6451c16` 不回退。 | 独立强制分块（MAX_DOWNLOAD_BYTES=3MB，9 片）vs 直写：max\|diff\|=0.0、transform_equal=True、mask_equal=True、nan_positions_equal=True、无 .part 残留；P0 金指纹 b91c09c9c6451c16 未回退。 |
| A3 | passed | brief.md | A3: 失败路径可读且无残留：单片连续失败时错误信息含片号/片数、估算体积、上限、已重试次数与四条出路； 失败后不留 `.part` 或半截产物。 | 独立注入 RemoteDisconnected（第 2 片）：3 次尝试/重试 2 次；文案含 第 2/9 片、单片估算 2.8MB、单请求上限 3MB、已重试次数、四条出路（放大 scale/缩小 AOI/array/toDrive）；leftover_parts=[]、final_products=[]。 |
| A4 | passed | brief.md | A4: nodata 语义统一：GeoTIFF 与 NetCDF 的 nodata 均为 NaN，GDAL 读回逐项校验一致；若 nodata 进指纹， 按红线 3 完成 `PROCESSING_VERSION` bump 与金指纹预注册切换（并在 README §9 记一笔）。 | 独立跑 DEM：tif nodata=nan/n_neg_inf=0/n_nan=344；nc _FillValue=nan/n_nan=344，mask 计数一致；缓存命中 -inf→nan 归一有离线用例且目标产物现为 nan。指纹 payload（gis/spec.py:565-575）不含 nodata → 无需 PV bump。 |
| A5 | passed | brief.md | A5: `geocode.json` 设 `paths.data_dir` 后产物落该目录并自动创建目录；未设时行为与现在一致 （仓库 `data/{derived,deliver}`）。 | 独立设置 geocode.json:paths.data_dir 后 data_root 与 raw/derived/deliver 三子目录自动落目标、产物在目标下；未设时仍走仓库 data/（本轮所有默认跑一致）。 |
| A6 | passed | brief.md | A6: 缓存清单/清理入口：能列出当代与历史指纹各自的占用；清理只作用于历史指纹且需显式确认； 判定逻辑有离线用例（含「当代指纹产物不得被删」的守卫用例）。 | 独立只读清单：当代 8 / 历史 20(206.4MB) / 未登记 22；plan_prune 只含历史；未 --confirm 拒绝执行；当代指纹在任何参数下不进计划、产物完好；scripts/prune_cache.py list 可用；test_cache_manage 全绿。 |
| A7 | passed | brief.md | A7: 回归：离线用例全绿（≥257 条）、`uvx ruff@0.17.0 check` 零告警、`tests/verify_all.py` 离线层 RUN 全 PASS。 | Runtime 正式检查（state.json checks，candidateId 匹配本候选）：offline-unit-suite Ran 341 OK（≥257）、ruff@0.17.0 All checks passed、verify_all 离线 RUN 4/4 PASS；独立复跑 test_export_chunks/test_geoenv_data_dir/test_cache_manage/test_offline_guard 共 78 用例全绿。 |
| A8 | passed | specs/export-chunking/spec.md | 直写与分块路径产物一致（验收：A2） 对小 AOI（估算 ≤ 上限）继续走单次 `getDownloadURL`，产物文件名、网格、像素值、指纹与历史一致； P0 样本的产物仍为 `s2_beijing_test.b91c09c9.tif`，金指纹保持 `b91c09c9c6451c16`。 当估算超上限时，按目标网格切块逐片取数并在本地拼接。拼接结果的网格、CRS、transform、 像素值必须与同一 spec 走直写路径时**逐像元完全相同**（max\|diff\| = 0），片与片的接缝处不得 出现重采样、错位或空洞。测试须提供强制走分块的对照手段（缩小上限阈值或注入测试开关）。 | 同 A2（spec 场景）：分块 vs 直写逐像元 max\|diff\|=0.0，P0 金指纹 b91c09c9c6451c16 保持。 |
| A9 | passed | specs/export-chunking/spec.md | 真实城市尺度三出口可用（验收：A1） 以真实 adcode（如 370900 泰安市）在 10m 三波段真彩色（网格 17680×9355 = 165.4M 像素；按 5 B/像素/波段估算请求体积 ≈2.5 GB）上， `emit_file`、`emit_array`、`emit_map` 三出口全部成功；`emit_file` 的 GeoTIFF 与 `emit_array` 的 NetCDF 在同一网格上逐像元一致（容差 0.5）。分块路径不得另建网格 —— 三出口仍共享 `compute_grid` 的结果。 | 同 A1（spec 场景）：三出口同网格，file↔array 逐像元 max\|diff\|=1.78e-07 ≤ 0.5，mask 一致。 |
| A10 | passed | specs/export-chunking/spec.md | 瞬时中断有界重试、失败可读且无残留（验收：A3） 单片请求遇到瞬时错误（`http.client.RemoteDisconnected`、连接超时、HTTP 5xx）时按有界退避重试； 每次重试与最终结果写进 job 日志。重试次数有上限，耗尽后按失败路径处理，不无限重试。 整体失败时抛出的错误必须含：片号/片数、估算体积与上限、已重试次数，以及出路清单 （放大 scale / 缩小 AOI / 改用 array 出口 / 后续接 toDrive）。失败后不得留下 `.part` 临时文件或半截产物；`.part` 的清理与既有写盘纪律一致（同目录、同卷原子 rename）。 | 同 A3（spec 场景）：有界重试写入 job 日志，失败文案齐全，零 .part/半成品残留。 |
| A11 | passed | specs/export-chunking/spec.md | GeoTIFF 与 NetCDF 的 nodata 一致（验收：A4） 同一 spec 的 `emit_file` 产物（GeoTIFF）与 `emit_array` 产物（NetCDF）对无效像素使用同一语义： NaN。GDAL 读回校验：GeoTIFF 的 nodata 声明与 NetCDF 的 `_FillValue` 均为 NaN，`rasterio` masked read 两边一致（不再出现 `-inf` 与 NaN 并存）。若该变化影响指纹，按红线 3 完成 `PROCESSING_VERSION` bump 与金指纹预注册切换。 | 同 A4（spec 场景）：GeoTIFF 声明 nodata=nan 且非有限值为 0；NetCDF _FillValue=nan；rasterio masked read 与 nc NaN 计数一致；nodata 不入指纹。 |
| A12 | passed | specs/export-chunking/spec.md | 输出根可配置（验收：A5） `geocode.json` 支持 `paths.data_dir`：设置后 `data_path()` 的三个子目录（raw/derived/deliver） 都落在该目录下并自动创建；未设置时行为与历史逐字节一致（仓库 `data/`）。缓存目录（`.cache/`） 与日志目录的语义不变。 | 同 A5（spec 场景）：paths.data_dir 三子目录随产物根落盘并自动创建；未设行为不变。 |
| A13 | passed | specs/export-chunking/spec.md | 缓存清单与显式清理（验收：A6） 提供清单/清理入口：按「当代指纹 / 历史指纹」分类列出 `data/derived` 的占用（文件名、 指纹、体积、是否当代），并支持只删除历史指纹产物——删除前需显式确认，当代指纹产物在任何 参数组合下都不会被删除（该守卫须有离线用例）。不提供自动清理。 | 同 A6（spec 场景）：当代/历史/未登记分类列出占用，只删历史且需 --confirm，当代守卫有离线用例。 |
| A14 | passed | specs/export-chunking/spec.md | 既有基线与门禁不回退（验收：A7） 实现后：离线用例全绿（不少于 change 开始时的数量）、`uvx ruff@0.17.0 check` 零告警、 `tests/verify_all.py` 的离线层 RUN 项全 PASS，且 `tests/unit` 的离线守卫（AST 禁网）不被破坏 —— 分块计划与拼接逻辑不得引入网络依赖。 | 同 A7：离线用例 341 全绿、ruff 0 告警、verify_all 离线 RUN 全 PASS，tests/unit AST 禁网守卫（test_offline_guard）通过。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| tests/unit 离线用例（含 AST 禁网守卫） | -m unittest discover -s tests/unit -t . | . | passed | 0 | 22267 ms |
| tests/verify_all.py（离线层 RUN 4/4） | tests/verify_all.py | . | passed | 0 | 29757 ms |
| uvx ruff@0.17.0 check（零告警门禁） | ruff@0.17.0 check | . | passed | 0 | 660 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- uvx ruff@0.17.0 check: passed — 0 告警（静态门禁）
- python -m unittest discover -s tests/unit -t .: passed — 341 用例全绿（基线 257 → +84）
- python tests/verify_all.py: passed — RUN 4/4 PASS、SKIP 8（C14 设计：在线依赖层）
- tests/smoke_export_chunking.py --stage a2: passed — 分块 9 片 vs 直写 max|diff|=0.0
- tests/smoke_export_chunking.py --stage a3: passed — 注入 RemoteDisconnected：文案齐全 + 零残留
- tests/smoke_export_chunking.py --stage a4: passed — tif/nc nodata 均 NaN，NaN 计数一致
- tests/smoke_export_chunking.py --stage a5: passed — paths.data_dir 生效
- tests/smoke_export_chunking.py --stage a6: passed — 缓存清单 + 当代指纹守护
- tests/smoke_export_chunking.py --stage a1: passed — 真实 adcode 370900 10m 真彩色三出口（file 3251.1s / array 2.8s / map 90.4s）
- 已知限制: 估算口径实现层修正（实测驱动）：spec 写「像素×波段×5 B（float32）」，实测 GEE 按**输出 dtype**计费（double 9 / float 5 / uint16 3 B），因此分块预算改为问 img.bandTypes() 并按最坏 9 兵底。这是 A1（真彩色 spec 写 uint16、实际 double）能过的前提；用户可见行为与 A1–A14 验收文字不变。
- 已知限制: 直写两道守卫合并为「任一超限即分块」（spec 描述为像素守先、体积守后）：因 64M 像素 × 最低 3 B/px/波段 = 192 MB > 48 MiB，像素守卫实际总被体积守卫覆盖，可观察行为与 spec 一致（都走分块）。
- 已知限制: 分块串行下载（D5）：A1 的 file 出口 98 片、array 出口 66 块，均串行；并发是后续独立性能话题（GEE 对同项目并发会 503，10-11 实测）。
- 已知限制: A1 的对比是 file↔array（容差 0.5，逐像元）；file↔直写 的逐像元恒等由 A2 在 P0 样本上证明。
- 已知限制: 分块预算按 GEE 输出 dtype 计费 + 2% 安全系数 + 2 px 余量（region 外扩 1 px + GEE 吸附 ≤1 px）；region 为每边 16 段的加密多边形。
- 已知限制: array 分块路径的单块拉取也包了有界重试（与下载路径同口径：5 次退避 2/5/15/30s，只对瞬时错误）：A1 第 6 次实测（2026-10-12）本机代理瞬时拒连（WinError 10061）当场打断第 29/66 块 —— 一块值数分钟 GEE 渲染，瞬时抖动必须能自愈。离线用例见 tests/unit/test_array_chunking.py::TestChunkedFetchRetry。
- 已知限制: nodata 判据（两轮实测修正）：① 缓存命中的历史产物归一走 `normalize_nodata_to_nan`——多波段用**整文件级哨兵**（全波段都是哨兵才算无数据；GEO_TIFF 的 nodata 是文件级的，float32 -inf / float64 0.0）。② **新下载一律带逐波段 byte 掩膜带**（同一趟请求，`mask_<band>`），用真实掩膜定 NaN 后折叠掉掩膜带（`collapse_mask_bands`）——单波段 float64 也精确，不再依赖哨兵。代价：请求体积 +2 B/px/波段（真彩色 9→11 B/px，分片 98 → ~120）。⚠️ 掩膜必须 `mask().gt(0).byte()`：直接 `.byte()` 会把 AOI 边界半覆盖像素（0.5）截断成 0，实测多抹 1215 像素（A4 对比 1559 vs 344，改后 344=344）。⚠️ 残留：历史上已落盘的**旧单波段 float64 产物**若真值恰等于哨兵，归一后仍会误抹——重跑即可消除（新下载路径不再有这个问题）。
- 已知限制: nodata 归一会在缓存命中时就地重写既有 GeoTIFF（-inf/0 → NaN + 头部 nadat=nan），不改变 spec 指纹，但会改动既有产物字节（掩膜像素以外逐位不变）。
- 已知限制: 缓存“当代指纹”判定依赖产物根索引（.cache-index.json）：索引建立之前的存量产物需 mark-current 显式登记，否则按未登记保护（宁可留着，不可错删）。

## 阻塞项

_无。_

## 风险与跳过的工作

- collapse_mask_bands（gis/export_chunks.py:406-444）未像 normalize_nodata_to_nan 那样把整数 value band 提升为 float32：对 int 容器会因 profile nodata=nan 越界抛 ValueError（实测 int32 输入报 'nodata value, nan, is beyond the valid range of its data type, int32'）。当前不可达（source.build_image 恒 toFloat()；独立实测 WorldCover 整数类资产下载为 float32+nodata=nan），但若 GEE 导出行为回退为 Int32，文件出口会硬失败，建议后续补齐防御。
- A1 的 array 出口本轮为缓存命中（nc 为此前迭代真实 370900 array 运行产物），未在本提交重新拉取；array 取数路径本提交未改，且已在磁盘产物上独立逐像元复核（通过）。
- 交接摘要写 file 走 98 片，而 c15_a1.out.log 实际为 120 片（掩膜带使请求体积增加）；known_limits 已更正为 98→~120，仅文档口径不一致。
- 估算口径偏离 spec 文字：spec 写 5 B/px/band，实现按 GEE 输出 dtype 计费并加掩膜带 2B/px/band（真彩色 double 9→11B）。已记入 known_limits，可观察行为与 A1–A14 验收文字一致。
- nodata 写 NaN 会就地改写既有 GeoTIFF 的掩膜像素字节，并恢复此前被误抹的 7 个真值像素；因 nodata 不入指纹（A4/A11 的 bump 条件为‘影响指纹’）故未 bump PROCESSING_VERSION。此为对红线 3 的解释性判断：若按‘任何落盘像素字节变化’从严解释，可能需要 bump，但与本 change 的验收文字一致。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-11T13:20:41.003Z |
| 2 | 1 | 1 | pass | — | 逐项核对 A1–A14 全部通过。实现与验收文字吻合：分块计划/拼接为纯函数+本地 IO、有界重试、失败文案与零残留、nodata 统一 NaN（不入指纹）、paths.data_dir、缓存清单与当代守卫、回归门禁均满足。独立复跑 A1 逐像元比对（max\|diff\|=1.78e-07）、A6 清单/拒绝删除、P0 指纹、用例计数（257→336）均与留档一致。 | 2026-10-14T03:53:59.329Z |
| 2 | 1 | 1 | recovery | — | Verifier 指出单波段 float64 哨兵/真值 0 碰撞仍存在（多波段已修）；回 Build 改为下载时附带逐波段掩膜带，彻底消除哨兵歧义 | 2026-10-14T04:07:58.523Z |
| 2 | 2 | 1 | pass | — | 独立验收：逐项核对 A1–A14 全部满足。独立复跑关键断言：A1/A9 file↔array 逐像元 mask_match=True、max\|diff\|=1.78e-07（容差 0.5）；A2/A8 强制分块 vs 直写 max\|diff\|=0.0、P0 金指纹 b91c09c9c6451c16 未回退；A3/A10 注入断连文案齐全且零残留；A4/A11 tif/nc nodata 均 NaN 且 NaN 计数 344=344，nodata 不入指纹故无 PV bump；A5/A12 paths.data_dir 生效；A6/A13 缓存清单+当代守卫成立；A7/A14 Runtime 检查（341 用例/ruff 0/verify_all RUN 4/4）与本工作区 HEAD 7cb31bc 匹配。工作区干净（仅未跟踪 docs/comet/changes/），实现即该提交。残留风险见 risks（collapse_mask_bands 整数 dtype 防御缺口、A1 array 走缓存复用、文档口径与红线解释性判断）。 | 2026-10-14T05:56:19.015Z |



## 结论

独立验收：逐项核对 A1–A14 全部满足。独立复跑关键断言：A1/A9 file↔array 逐像元 mask_match=True、max|diff|=1.78e-07（容差 0.5）；A2/A8 强制分块 vs 直写 max|diff|=0.0、P0 金指纹 b91c09c9c6451c16 未回退；A3/A10 注入断连文案齐全且零残留；A4/A11 tif/nc nodata 均 NaN 且 NaN 计数 344=344，nodata 不入指纹故无 PV bump；A5/A12 paths.data_dir 生效；A6/A13 缓存清单+当代守卫成立；A7/A14 Runtime 检查（341 用例/ruff 0/verify_all RUN 4/4）与本工作区 HEAD 7cb31bc 匹配。工作区干净（仅未跟踪 docs/comet/changes/），实现即该提交。残留风险见 risks（collapse_mask_bands 整数 dtype 防御缺口、A1 array 走缓存复用、文档口径与红线解释性判断）。
