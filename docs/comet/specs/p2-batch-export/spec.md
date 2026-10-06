# p2-batch-export —— GEE 服务端批处理导出与任务持久化（完整规格）

本规格描述该 capability 归档后的完整行为：在既有"一份计算图、三出口共享"架构上，新增 GEE 服务端批处理导出（`ee.batch.Export.image.toDrive`，目的地裁决见 brief D10——GCS 因绑卡受阻不可用，toDrive 同为服务端长任务且无支付依赖），把服务端长任务的生命周期映射进现有 `jobs.py` 五态任务模型，并为这些任务提供跨 daemon 重启的最小持久化。

## 定位与边界

- **新任务类型，不是第四出口**：批处理导出以 `kind="export"` 任务类型暴露（MCP `job_submit` 的 kind enum 由 `{emit, describe, defaults}` 扩展为含 `export`）；`exit` 概念、`EXITS` / `_EXIT_REQUIRES` / `ArtifactSpec` / 指纹 payload 均保持不变（`spec.py`、`emit.py` 零改动）。
- **导出是既有计算图上的新去向**：ee 计算图只来自 `source.build_image(spec)`（红线 1），网格只来自 `compute_grid(spec)`（红线 2）；导出路径不构建任何 ee 对象、不算网格。
- **像素输出不变**：本能力只改变"产物去哪"，不改变"算什么"；`PROCESSING_VERSION` 保持 2（红线 3 不触发）。
- **实现落点**：`gis/export.py`（提交 / 状态映射 / 取消）+ `gis/jobstore.py`（持久化）+ `daemon.py` 接线；`geoenv.py`、`source.py`、`grid.py`、`spec.py`、`emit.py` 零改动。
- **写操作走 daemon**：提交 / 查询 / 取消全部经 daemon 调用面（`/mcp`、`/rpc`、HTTP 路由）；TUI 与 client 不引入任何直接 GEE 调用。

## 调用面

### 提交（`job_submit`，kind="export"）

请求体：

```json
{
  "kind": "export",
  "spec": { ... },           // 必带，或省略用 daemon 当前 spec
  "folder": "gexports",      // 可选：Google Drive 目标文件夹名（不存在时由 GEE 创建）；默认 "gexports"
  "file_prefix": "...",      // 可选：文件名前缀；默认 "{spec.slug}.{spec.fingerprint()[:8]}"
  "file_format": "GeoTIFF",  // 可选：导出文件格式；默认 "GeoTIFF"
  "shard_size": 256,         // 可选：分片尺寸（像素）；缺省交由 GEE 自动
  "file_dimensions": "...",  // 可选：单文件尺寸；缺省交由 GEE 自动
  "max_pixels": 1000000000   // 可选：maxPixels；默认按 compute_grid 估算像素数 + 余量
}
```

- 目的地是用户自己的 Google Drive（D10，无支付依赖）；folder 为任务级参数（D11），不进 `geocode.json`。
- spec 校验要求与 file 出口相同：`asset`、`crs`、`scale`、`aoi` 必填（缺项报错消息写清怎么修）。
- 提交成功立即返回 `job_id`；此时 job 状态为 queued，result 记录 GEE task id 与产物定位（folder + file_prefix）。

### 查询（`job_get` / `job_list` / SSE）

export job 与既有 job 走同一套查询与事件流：`to_dict` 包含 status / phase / pct / message / created_at / started_at / finished_at / spec_id / spec_fingerprint / task_id，result 含产物定位信息。

### 取消（`job_cancel`）

对未终态 export job：本地协作取消照常发出，并同步调用 GEE `task.cancel()`；之后按状态映射收敛到本地 cancelled 终态。对非 export job 行为不变。

## 提交行为

1. 前置校验：spec 必填项检查；提交参数校验（folder 非空、file_format ∈ {GeoTIFF, TFRecord}、shard_size / max_pixels 为正整数、file_dimensions 为正整数或正整数列表）。
2. `build_image(spec)` 得到 ee.Image（唯一计算图）。
3. `compute_grid(spec)` 得到网格；按 `grid.width × grid.height` 估算像素数，**不受 `MAX_DIRECT_PIXELS`（64M）限制**——这正是本能力相对 `getDownloadURL` 路径的存在意义。
4. 构造 `ee.batch.Export.image.toDrive`：`image`、`description="geocode-{job_id}"`、`folder`（默认 `gexports`）、`fileNamePrefix`（默认 `{slug}.{指纹8位}`）、`region` = spec.aoi 对应 `ee.Geometry`、`scale` = `grid.scale`、`crs` = `grid.crs`、`fileFormat`、`maxPixels`，可选 `shardSize` / `fileDimensions` 透传。
5. `task.start()` 提交；task id 写入 job 与持久化；job 进入 queued。

> 红线 5 核实结论（D8，2026-10-06 试点）：**不外推**——`toDrive` 的 region 直接接受 spec.aoi 的 GeoJSON 经纬度 geometry，小（约 10.5 万像素）/大（约 1.15 亿像素）两个试点任务均创建成功。

## 状态映射（GEE 六态 → jobs 五态）

| GEE state | jobs 状态 | 说明 |
|---|---|---|
| UNSUBMITTED | queued | 已构造未 start（start 后立即查询，短暂存在） |
| READY | queued | 已提交未开跑——语义是"在排队" |
| RUNNING | running | 服务端计算中；GEE 进度信息喂 `job.pct` / `job.message` |
| COMPLETED | done | 本地 DONE 的唯一依据 |
| FAILED | failed | error 记录 GEE 返回的错误信息（含 Drive 配额满等） |
| CANCELLED | cancelled | 本地发起取消或 GEE 侧被取消 |

未知状态：保持本地现状不动，并记 warning（诚实策略，不猜）。

daemon 以固定间隔后台轮询未终态 export 任务的 `task.status()`，状态变化写盘并经 SSE 推送；轮询失败不误标终态，连续失败在 job.message 中如实报错。

## 持久化与重启恢复

- 文件：`.cache/jobs.json`（JSON；与既有 `.cache/daemon.json` 同目录同风格）。
- 覆盖范围：**仅 kind="export"**。describe / defaults / emit 是本地瞬时计算，重启丢失属预期，不入档。
- 记录内容：job_id、task_id、description、spec（dict）、folder / file_prefix、status、phase/pct/message、created_at / started_at / finished_at、error / warning、GEE 侧字段。
- 写盘时机：提交成功后、每次状态变化、进入终态。
- daemon 启动时：加载文件 → 未终态 export 任务回到 registry（状态先按存档呈现）→ 后台轮询按 task id 直连 GEE（`ee.data.getTaskStatus`；ee 1.7.46 无法按 id 重建 Task 对象，试点实测）重查真实状态并推进——重启前提交的任务，重启后状态继续推进，不丢追踪。
- task id 缺失或直连查询失败的记录：保留现场、如实标记，不伪造状态。

## 错误行为

- 提交参数非法（folder 为空、file_format 不支持、shard_size / max_pixels 非正整数等）：提交即报可执行错误（422 风格，写清怎么修）。
- GEE 提交失败（配额 / 认证 / 参数）：job 进入 failed，error 含 GEE 原始错误。
- Drive 侧失败（配额满、文件夹异常）：提交后任务在 GEE 侧 FAILED——按状态映射正常推进到本地 failed，error 可读。

## 场景

### Scenario: 提交批处理导出（验收：A1）

给定一份网格像素数超过 64M 的 spec（如大范围 AOI @ 10m；`getDownloadURL` 路径对该网格会拒绝），通过 daemon 提交 `kind="export"`：前置校验通过时，成功创建 GEE 服务端任务并拿到 task id；job 立即返回（job_id + queued 状态）；`job_get` 能查到 GEE 侧状态。同一 spec 走 `exit="file"` 仍在 64M 像素处报既有的"网格太大"错误——两条路径边界互不影响。

### Scenario: 小任务串行试点闭环（验收：A2）

按红线 6 先提交 1 个小范围任务（网格远小于 64M）：任务经 queued / running 推进，GEE 侧 COMPLETED 后本地进入 done；Google Drive 的 `gexports` 文件夹（或提交指定的 folder）中出现以 fileNamePrefix 命名的产物文件（分片时为多张 TIF）；job result 含 task id 与产物定位信息（folder + file_prefix）；全程不并行提交第二个任务。

### Scenario: 持久化与重启恢复（验收：A3）

给定一个重启前提交、尚未终态的 export 任务（task id 已在 `.cache/jobs.json`）：重启 daemon 后 `job_list` / `job_get` 仍能看到该任务；daemon 用 task id 直连 GEE 重查真实状态并继续推进（如 GEE 已 RUNNING 则本地回到 running，GEE 已 COMPLETED 则收敛到 done）；追踪不丢失。describe / defaults / emit 任务不持久化、重启后不出现。

### Scenario: 三出口与既有行为零回归（验收：A4）

`spec.py` / `emit.py` / `source.py` / `grid.py` 无改动；`PROCESSING_VERSION` 保持 2；既有 exit=file/array/map 的行为（含 file 出口 64M 超限报错路径、`_ensure_raster` 缓存复用、三出口对齐判据）不变；`tests/unit` 全量回归通过。

### Scenario: 映射与持久化的离线单测（验收：A5）

`tests/unit` 新增离线用例覆盖纯逻辑：GEE 六态 → 五态映射表逐项断言（含未知状态不误判）；`jobs.json` 保存 / 加载 / 未终态恢复往返保真；取消联动判定（export + task id 存在才触发 GEE 取消）；导出参数校验（folder 默认 `gexports` 与透传、file_format / shard_size / file_dimensions / max_pixels 非法值拒绝）。全部用例不导入 ee、不联网、秒级完成，纳入既有离线基线一并回归。

### Scenario: 写操作走 daemon（验收：A6）

批处理导出的提交 / 查询 / 取消仅经 daemon 暴露：MCP `job_submit(kind="export")`、RPC `job.submit`、HTTP 路由行为一致；TUI 与 client 侧无任何直接 GEE 调用路径；任务状态变化经既有 SSE 事件流推送。

### Scenario: 取消联动（验收：A7）

对未终态 export job 调 `job_cancel`：本地协作取消发出，同步调用 GEE `task.cancel()`；GEE 侧进入 CANCELLED 后本地收敛到 cancelled 终态。对已终态 job 取消请求被拒绝（与既有行为一致）；对非 export job 不产生 GEE 调用。
