# 目标

大范围导出新增 GEE 服务端批处理路径（现状只有 `getDownloadURL`，上限约 64M 像素），把 GEE 服务端长任务的状态映射进现有 `jobs.py` 五态任务模型，并为任务追踪加最小持久化——daemon 重启不丢任务追踪。对应开发文档 §9.2 台账 C5 行、§9.2 决定 4、§9.5、§9.6。

**目的地（2026-10-06 D10 裁决）：`ee.batch.Export.image.toDrive`**。台账 C5 行原文为 `toCloudStorage`，但用户无可用信用卡、无法开通 GCS 计费，且 GEE 的导出写入由 Google 服务端执行、只能写真正的 GCS 桶（自建 S3 兼容存储——用户服务器上的 Garage——不能作为目的地）。`toDrive` 同为服务端批处理任务（同一套六态状态机、task id、恢复模型），产物落用户自己的 Google Drive（免费配额，无需绑卡）。

导出是既有计算图上的新出口：ee 对象仍只建在 `source.py`（红线 1），网格仍由 `compute_grid()` 定（红线 2），既有像素输出不变（`PROCESSING_VERSION` 不 bump）。实现放新文件（`gis/export.py` + `gis/jobstore.py`），不碰 `spec.py` / `emit.py`，与 C3（`p2-timeseries`，主工作区）和 C4（`p2-presets`，独立 worktree）零冲突。

# 范围

## Source coverage

需求来源：`docs/README.md`（用户 2026-10-06 指定为本项目开发文档，仅存在于主工作区、被 .gitignore 忽略）。C5 的覆盖边界 = §9.2 台账 C5 行及必要依赖（§9.2 决定 4、§4 三出口表与"大范围"要点、§9.5 批处理导出行、§9.6 任务持久化划线、§5.1 daemon 写操作纪律、§11 红线、§3.1/§3.3 spec 与指纹契约、§8 相关事实）。用户明确范围边界："台账之外不做——C6 的 io_chunks 分块、TUI 界面改动都不在本 change"。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
|---|---|---|---|---|---|---|
| S1：§9.2 台账 C5 行 | complete | 服务端批处理导出 + GEE 任务状态映射 + jobs 最小持久化；验收要点：>64M 像素 AOI 可提交/可查询；daemon 重启后可恢复任务追踪。原文目的地 `toCloudStorage` | spec.md 提交/状态/恢复场景 | A1、A2、A3 | covered | 当前有效需求；目的地按 D10 裁决以 `toDrive` 落地（GCS 需绑卡不可用，用户 2026-10-06 确认） |
| S2：§9.2 决定 4 | complete | 服务端长任务不能因 daemon 重启丢本地追踪；jobs 最小持久化并入 C5，不再留在 P3 | spec.md 持久化与恢复场景 | A3、A5 | covered | 当前有效需求 |
| S3：§4 三出口表 + "大范围"要点 | complete | `getDownloadURL` 上限约 64M 像素，现有 file 出口超限报错路径保留；更大走服务端批处理导出 | spec.md 提交与零回归场景 | A1、A4 | covered | 当前有效需求；同 S1 的 D10 目的地修订 |
| S4：§9.5 批处理导出行 + §9.6 任务持久化划线 | complete | 大范围走服务端批处理导出；jobs 最小持久化并入本项（~~任务持久化~~ → 提前并入 C5） | spec.md 全部场景 | A1–A5 | covered | 当前有效需求；同 S1 的 D10 目的地修订 |
| S5：§5.1 daemon 端点 + "所有写操作都走 daemon" | complete | 导出任务的提交/查询/取消经 daemon（/mcp + /rpc + /events），TUI 不直接跑 GEE | spec.md 调用面场景 | A6 | covered | 必要依赖（架构纪律） |
| S6：§11 红线 1/2/3/5/6/8 | complete | 不建私有 ee 计算图（走 `source.build_image`）；网格 `compute_grid()` 定；像素输出不变（`PROCESSING_VERSION` 保持 2）；红线 6 串行试点（先 1 个小任务跑通再放大）；新字段指纹纪律 | spec.md 约束与零回归场景 | A4、A5 | covered | 必要依赖（实现约束） |
| S7：§3.1 ArtifactSpec 字段 + §3.3 指纹规则 | complete | 指纹 = 显式 payload 白名单 + `PROCESSING_VERSION`；导出参数归属经用户裁决 = job 提交参数（D3），spec.py 零改动 | spec.md 提交与零回归场景 | A4、A5 | covered | 必要依赖（设计依据） |
| S8：§8.1 踩坑 #2/#5 + §2.2/2.3 代码地图 | complete | region EPSG:4326 是 `getDownloadURL` 的约束（是否外推实现时核实，D8）；GEO_TIFF 固定写 Int32 的量化事实；jobs/daemon/emit 现状结构 | spec.md 约束场景 | — | background | 背景事实，支撑实现与排查，不单设验收 |

## 交付内容

1. `gis/export.py`（新文件）：kind="export" 任务实现——前置校验（spec 必填同 file 出口：crs/scale/aoi）、`source.build_image(spec)` 构建计算图、`compute_grid(spec)` 定网格、`ee.batch.Export.image.toDrive` 提交（description=`geocode-{job_id}`，folder 默认 `gexports`、提交参数可覆盖，fileNamePrefix 默认 `{slug}.{指纹8位}`，fileFormat 默认 GeoTIFF，maxPixels 按网格估算 + 余量）、task id 记录进 job；GEE 六态 → jobs 五态映射函数与进度喂送。
2. `gis/jobstore.py`（新文件）：`.cache/jobs.json` 最小持久化——仅覆盖 kind="export"；提交后 / 每次状态变化 / 终态写盘；daemon 启动时加载，未终态任务回 registry 并由后台轮询向 GEE 重查推进（task id 直连）。
3. `daemon.py` 接线：`job_submit` 支持 kind="export"（可选参数 folder / file_prefix / file_format / shard_size / file_dimensions / max_pixels）；启动时加载持久化；后台轮询非终态 export 任务（固定间隔查 `task.status()`，SSE 照常推送）；`job_cancel` 对 export job 联动 `task.cancel()`。
4. 离线单测（进 `tests/unit` 基线）：状态映射六→五、持久化保存/加载/恢复、取消联动判定、导出参数校验（folder 默认与透传、file_format/shard_size/file_dimensions/max_pixels 非法值拒绝）——不导入 ee、不联网、秒级完成。
5. 既有三出口（file/array/map）与 `tests/unit` 离线基线零回归；`spec.py` / `emit.py` / `source.py` / `grid.py` 零改动。

# 非目标

- C6 的 xee `io_chunks` 分块（台账外，按需另行立项）
- TUI 界面改动（台账外；TUI 经既有 job_list/job_get 轮询自然看到新任务类型）
- toCloudStorage / GCS 目的地（D10：绑卡受阻，将来有支付方式可另立项）
- 产物从 Drive 到用户服务器 Garage 的下游同步（rclone，范围外）
- 分片产物本地拼接/合并（D6：验收到"提交 + 状态 + 产物落 Drive"；多文件清单进 job result）
- 不改 `source.py` / `grid.py` / `spec.py` / `emit.py`（红线 1/2 + C3/C4 冲突面）；`PROCESSING_VERSION` 保持 2，像素输出不变
- 不并行刷 GEE 批任务（红线 6：批任务占配额，只串行试点）

# 验收示例

1. **>64M 像素 AOI 可提交、可查询**：提交一个网格像素数超过 64M（`getDownloadURL` 路径会拒绝）的 spec 走 kind="export"，成功创建 GEE 服务端任务（拿到 task id），job 立即返回且状态为 queued/running；`job_get` 可查到 GEE 侧状态；不受 `MAX_DIRECT_PIXELS` 限制，且 file 出口的 64M 超限报错路径保持原样。
2. **小任务串行试点闭环**（红线 6）：先提交 1 个小范围任务，跑通"提交 → RUNNING → COMPLETED → 产物在 Drive"完整闭环；Google Drive 的 `gexports` 文件夹（或提交指定的 folder）中出现以 fileNamePrefix 命名的产物文件（分片时为多张 TIF）；job result 含 task id 与产物定位信息（folder + fileNamePrefix）；本地 DONE 仅在 GEE COMPLETED 后出现。
3. **daemon 重启恢复追踪**：重启前提交的未终态导出任务，重启 daemon 后仍可见，状态继续按 GEE 侧真实进度推进，不丢任务。
4. **三出口与基线不回退**：既有 exit=file/array/map 行为不变（含 file 出口 64M 超限报错路径）；`source.py` / `grid.py` / `spec.py` / `emit.py` 零改动；`PROCESSING_VERSION` 保持 2；`tests/unit` 全量回归全绿。
5. **映射与持久化有离线单测**：GEE 六态 → jobs 五态映射、持久化保存/加载/恢复、取消联动判定、导出参数校验（folder/file_format/shard_size/file_dimensions/max_pixels）的纯逻辑有离线单测（不导入 ee、不联网、秒级完成）。
6. **写操作走 daemon**：批处理导出的提交/查询/取消全部经 daemon 调用面（MCP / RPC / HTTP）暴露，TUI 与 client 不引入直接 GEE 调用。
7. **取消联动**：对未终态 export job 调 `job_cancel`，本地发协作取消且同步调用 GEE `task.cancel()`；GEE 侧 CANCELLED 映射回本地 cancelled 终态。

# Constraints and invariants

- 红线 1/2：`gis/export.py` 不自行构建 ee 对象（计算图只来自 `source.build_image`），网格只来自 `compute_grid()`
- 红线 3：任何改变像素输出的代码改动必须 `PROCESSING_VERSION += 1`——本 change 不改变像素输出，不 bump
- 红线 6：串行试点——先 1 个小任务跑通"提交 → RUNNING → COMPLETED → 产物在 Drive"，再做 >64M 提交/查询验证；不并行刷任务
- 红线 8：导出参数全部走 job 提交参数（D3），spec 无新字段，指纹零触碰
- 红线 5（`getDownloadURL` region 必须 EPSG:4326）是否外推到 Export 路径，实现时核实（Export 有独立 crs/scale 参数，初步判断不外推，以实测为准，结论记录进 D8）
- 环境前提：试点与 >64M 验证需要 GEE 网络 + 认证；**不需要信用卡、不需要 GCS bucket**（D10）——产物落用户自己的 Google Drive，注意 Drive 免费 15GB 配额（试点为小任务，不受影响）
- 与 C3/C4 并行：本 change 的 worktree 基于 main HEAD（0cc8b25），不含 C3/C4 改动；`daemon.py` 与 C3 有交叠（那边有未提交改动），集成冲突按仓库实际内容解决

# Decisions

- D1：~~bucket 名放 `geocode.json` 新键 `export.bucket`~~ **被 D10 取代**（2026-10-06：用户无可用信用卡，GCS 计费不可开通）
- D2：~~不做 toDrive fallback~~ **被 D10 取代**（toDrive 从"不做"升级为唯一目的地）
- D3：导出参数（folder / file_prefix / file_format / shard_size / file_dimensions / max_pixels）全部走 job 提交参数；调用面呈现为新任务类型 kind="export"（`job_submit` 的 kind enum 扩展），不新增 exit——spec.py / emit.py 零改动，指纹零触碰
- D4：状态映射——UNSUBMITTED→queued、READY→queued、RUNNING→running、COMPLETED→done、FAILED→failed、CANCELLED→cancelled；本地 DONE 仅以 COMPLETED 为准；GEE 侧进度/消息喂 job.pct / job.message；未知状态保持现状 + warning
- D5：job_cancel 对 export job 联动 GEE `task.cancel()`；GEE CANCELLED 映射回本地 cancelled
- D6：分片产物不拼接；多文件以 folder + fileNamePrefix 清单进 job result，需要单文件时后续另行立项
- D7：重启恢复 = 持久化保存 task id，daemon 启动后按 id 直连 GEE 重查推进、不做列表扫描。接口事实（ee 1.7.46 试点实测）：`ee.batch.Task(task_id)` 构造器要求 task_type/state 等必填参数，无法按 id 重建对象——等价的按 id 直连接口为 `ee.data.getTaskStatus`（查询）与 `ee.data.cancelTask`（取消）。持久化文件 `.cache/jobs.json`（JSON），写盘时机 = 提交后 / 每次状态变化 / 终态；持久化范围仅 kind="export"（describe/defaults/emit 是本地瞬时计算，重启丢失属预期）
- D8（已核实，2026-10-06 试点）：红线 5 **不外推**——`toDrive` 的 region 直接接受 spec.aoi 的 GeoJSON 经纬度 geometry，小（约 10.5 万像素）/大（约 1.15 亿像素）两个试点任务均创建成功；本管线 aoi 契约恒为 GeoJSON（经纬度），不会产生投影坐标 region
- D9：Supervisor 拆分检查——不拆分：交付物紧密相关（同一批新文件 + daemon 接线 + 测试），验收项无法独立分配给多个子任务，单 change 推进
- D10（2026-10-06 用户裁决）：**目的地 = `Export.image.toDrive`**。事实链：GCS 建桶需绑定信用卡（用户无可用卡）；GEE 导出写入由 Google 服务端执行，只能写真正的 GCS 桶，用户服务器上的自建 S3 兼容存储（Garage）不能作为目的地；toDrive 无需任何云支付，产物落用户 Google Drive（免费 15GB），任务模型（六态/task id/恢复/取消）与 toCloudStorage 完全同构。下游经 rclone 从 Drive 同步到 Garage，不在本 change 范围
- D11：Drive 目的地文件夹 folder 默认 `"gexports"`，提交参数可覆盖；不进 `geocode.json`（与部署环境无关，纯任务参数）

# Verification expectations

- 离线项：`tests/unit` 全量回归 + 新增离线单测（映射 / 持久化 / 取消判定 / 参数校验），断网秒级可验
- 联网项按红线 6 串行，**无绑卡依赖，可立即执行**：先 1 个小任务跑通"提交 → RUNNING → COMPLETED → 产物在 Drive"，再做 >64M 提交/查询、daemon 重启恢复实测与取消实测（顺带核实 D8 红线 5 与 D11 folder 行为）
- Drive 产物证据：GEE task COMPLETED + Drive 对应文件夹内出现 fileNamePrefix 命名的文件（网页可核）
