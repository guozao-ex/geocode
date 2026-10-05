# GeoCode

把 Google Earth Engine 的**免费数据与算力**接进本地 GIS 引擎（QGIS / ArcGIS Pro），
由 coding agent 驱动。一份产物契约，同时服务三种消费者：**人看 / 我算 / 下游接**。

## 核心设计

**一份 `ee` 计算图 + 一份 `ArtifactSpec` 契约 + 三个物化出口。**

```
Layer 0  认证/环境      earthengine-api / GDAL / conda envs
Layer 1  计算图         ee 对象（filter → mask → reduce → clip）   ← 唯一真相源
Layer 2  产物契约 ★     ArtifactSpec + Grid                       ← 三出口共享
Layer 3  三出口
         ├─ emit_file  → GeoTIFF / COG      服务「下游接」
         ├─ emit_array → xarray / NetCDF    服务「我算」
         └─ emit_map   → .qgz / .png        服务「人看」
Layer 4  服务层         HTTP daemon（/mcp + /rpc + /events）+ TUI
```

- `ArtifactSpec`：frozen dataclass，CRS / 分辨率 / AOI(GeoJSON) / 波段 / 时间 / 渲染全部显式声明；
  指纹（spec 字段 + 处理逻辑版本）进产物文件名，缓存命中可解释、可作废。
- 网格由 `compute_grid()` 独家裁定，三出口逐像素对齐可校验
  （`ALIGN_TOLERANCE = 0.5` 量化 GEE GEO_TIFF 强制 Int32 的已知差异）。
- 「人看」不依赖 MCP：`.qgz` 为程序化生成的工程文件，双击即看。

## 状态

P0 完成并实测验收（spec 指纹 `c9243efd`，Sentinel-2 北京真彩色）：
三出口产物逐像素一致（容差 0.5），QGIS 4.2.2 读回渲染验证通过。
路线图：P1a arcpy 出版级制图（headless）→ P1b ArcGIS Pro add-in（按需）→ P2 批量导出 → P3 工程化。

## 快速开始

```bash
# conda env geo：python 3.12 + ee / xee / geedim / xarray / rioxarray / geopandas / textual
python -m gis.preflight --network          # 环境探测（6 类失败码 + 可执行提示）
python -m gis.daemon                       # HTTP 服务（127.0.0.1:6531）
python -m gis.tui                          # 终端界面
PYTHONPATH=. python tests/smoke_three_exits.py
```

复制 `geocode.json` 填入**自己的** GEE project id 与代理设置。

## MCP 接入（agent 宿主）

HTTP 型 server：`http://127.0.0.1:6531/mcp`（initialize → tools/list → tools/call）。
工具 9 个：`gee_status` / `gee_describe` / `spec_defaults` / `spec_get` / `spec_set` /
`job_submit` / `job_list` / `job_get` / `job_cancel`。

## 说明

- 开发文档（完整架构、**17 条踩坑记录**、路线图与进度台账）在 `docs/README.md`，
  **本地维护、不入库**——所以你在仓库里看不到它。
- 核心依赖许可：earthengine-api / xee / geedim（Apache-2.0）、geemap（MIT）、
  geopandas（BSD-3）。本项目 License 未定。
