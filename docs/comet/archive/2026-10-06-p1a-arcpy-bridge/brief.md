# 目标

与 `qgis_bridge.py` 对称新增 `gis/arcpy_bridge.py`，并把出版级制图要素契约化：`spec.py` 新增 `LayoutSpec`（图廓 / 比例尺 / 指北针 / 图例 / 标题），两个 bridge 共同消费；`emit_map` 增加 `renderer` 选项（`qgis` / `arcpy`）；arcpy 出口产出 `.aprx` + 出版级 PDF/PNG，可直接进论文。对应开发文档 §9.2 台账 C2 / §9.3。

# 范围

## Source coverage

需求来源：`docs/README.md`（用户 2026-10-06 指定为本项目开发文档）。C2 的覆盖边界 = 台账 C2 行、§9.3 全部内容及必要依赖（环境纪律与红线）：

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
|---|---|---|---|---|---|---|
| S1：§9.2 台账 C2 行 | complete | `arcpy_bridge.py` + LayoutSpec 契约 + `emit_map` renderer 选项 + 出版级布局 + PDF/PNG 导出；两 bridge 共享同一 LayoutSpec；不依赖 add-in | spec.md 全部场景 | A1–A4 | covered | 当前有效需求 |
| S2：§9.3 P1a「要做的事」1–5 | complete | LayoutSpec 契约先行；arcpy_bridge 定位 arcgispro-py3、subprocess 调 arcpy、生成 .aprx；出版级布局；导出 PDF+PNG；emit_map 支持 renderer | spec.md 对应场景 | A1–A4 | covered | 当前有效需求 |
| S3：§9.3 验收判据 | complete | 同一 GeoTIFF，QGIS 与 arcpy 各出一图；arcpy 图带完整图廓要素可直接进论文；两 bridge 消费同一 LayoutSpec | spec.md 双出图、五要素、契约共享场景 | A1、A2、A3 | covered | 当前有效需求 |
| S4：§11 红线 1/2/3/7/8 | complete | arcpy_bridge 不建 ee 计算图、不算网格（只消费 GeoTIFF）；像素输出不变则 PROCESSING_VERSION 不动；geo 与 arcgispro-py3 不合并；新字段指纹归属显式化 | spec.md 指纹与资产保护场景 | A5、A6 | covered | 必要依赖（实现约束） |
| S5：§6 环境事实 + §9.3 认知修正记录 | complete | arcgispro-py3 = `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`（arcpy 3.7 / ArcInfo / 六扩展 Available，headless 已实测），不需要 add-in | spec.md 双出图场景 | A1、A2 | covered | 必要依赖（环境事实） |

## 交付内容

1. `spec.py` 新增 `LayoutSpec`（frozen dataclass，含 `to_dict` / `from_dict`）：`title`（标题）、图廓 `frame`、比例尺 `scalebar`、指北针 `north_arrow`、图例 `legend`（四要素默认开启）、经纬网 `graticule`（默认关）、`dpi`（默认 300）、`page_size` / `orientation`、`formats`（默认 `("pdf", "png")`）、比例尺条长 `scalebar_length_cm`（默认 4.0cm，2026-10-06 验收轮修订新增）。作为 `ArtifactSpec.layout: LayoutSpec | None = None` 新字段——呈现规格，与 `render` 对称。
2. 指纹守卫同步（红线 8）：`layout` 入 EXCLUDED_FIELDS（呈现层，不影响像素值），C1 守卫名单更新 + 「新增字段后旧 spec 指纹不变」回归断言。
3. `emit_map` 增加 `renderer` 参数：`"qgis"`（默认，现状路径）/ `"arcpy"`；非法值报错可读。
4. `gis/arcpy_bridge.py`：定位 `arcgispro-py3` 解释器 → subprocess 调 arcpy 脚本 → 生成 `.aprx`（map + layout 五要素）→ 导出 PDF + PNG 到 `data/deliver/`。
5. `qgis_bridge.py` 重构：布局参数消费 LayoutSpec；无 layout 时保持现状输出兼容。
6. C1 单测扩展：LayoutSpec 校验 / 序列化用例 + 守卫名单更新；全量回归保持全绿。

# 非目标

- 不做 P1b add-in（操作活会话 / dockpane / 当前视图取 AOI）——C2 落地后再评估（台账 C9）
- 不在 `arcgispro-py3` 安装任何 GEE / geo 栈（红线 7，subprocess + 文件交换）
- 不改动 `source.py` / `grid.py` 的计算与网格路径（红线 1/2）；不改变像素输出（`PROCESSING_VERSION` 保持 2）
- 不改 qgis 现有「拉伸烘焙进 8bit RGB」渲染路径（踩坑 #9 结论不动）

# 验收示例

1. 同一 GeoTIFF 双出图：同一 spec（含 LayoutSpec）分别以 `renderer=qgis` 与 `renderer=arcpy` 出图，两张图均成功落盘 `data/deliver/`（GeoTIFF 来源：优先复用 P0 缓存产物——同指纹命中 `_ensure_raster` 缓存则断网可验；缺失时经 emit_file 现场生成，需 GEE 网络）。
2. arcpy 出版图五要素齐备：`.aprx` 可打开，导出的 PDF/PNG 存在且尺寸合理；程序化断言 layout 含标题 / 比例尺 / 指北针 / 图例 / 图廓元素（arcpy 列元素名核验），并人工可读。
3. LayoutSpec 契约共享：两 bridge 消费同一 LayoutSpec；`to_dict` / `from_dict` 往返保真；单测覆盖（C1 套件扩展）。
4. renderer 参数纪律：`emit_map` 接受 `qgis` / `arcpy`，非法值报错可读；`qgis` 路径与现状兼容（无 layout 时输出不变）。
5. C1 回归基线全绿：`unittest discover -s tests/unit` 全部通过（含 LayoutSpec 新用例与守卫更新），运行时长仍 < 10 秒。
6. 契约与资产保护：新增 `layout` 字段不改变旧 spec 指纹（守卫 + 回归断言）；`source.py` / `grid.py` 零改动；`PROCESSING_VERSION` 保持 2。

# Constraints and invariants

- 红线 1/2：`arcpy_bridge` 不建 ee 计算图、不算网格，只消费 emit 链产出的 GeoTIFF
- 红线 7：`geo` 与 `arcgispro-py3` 不合并，subprocess + 文件交换
- 红线 3/8：任何影响像素输出的改动必须 `PROCESSING_VERSION += 1`；`layout` 呈现字段不得参与指纹
- 环境事实：`arcgispro-py3` 解释器 = `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`（arcpy 3.7 / ArcInfo / 六扩展 Available，headless 已实测可用）

# Decisions

- D1：`LayoutSpec` 挂在 `ArtifactSpec`（`layout` 字段，与 `render` 对称），按红线 8 入指纹排除名单——C1 守卫将先拦截该新字段，属预期行为，随本 change 更新守卫名单
- D2：arcpy 集成方式 = subprocess 调 `arcgispro-py3` 解释器执行独立脚本（与 `qgis_bridge` 的 `python-qgis.bat` 子进程同模式），不写 add-in
- D3：`renderer` 默认 `"qgis"`，保证现状兼容
- D4：验收用 GeoTIFF 优先复用 P0 缓存产物（断网可验），缺失时才联网生成
- D5：工作区隔离 = current（同 C1），实现落 main 分支

2026-10-06 验收轮修订（用户要求修复 Verifier 列出的 5 条残余风险）：

- D6（残余 1）：QGIS 路径经纬网用 `QgsLayoutItemMapGrid` 实现（经纬度间隔按图层范围取 1/2/5 整值），消除与 arcpy（GRID surround）的不对称。
- D7（残余 2）：`LayoutSpec` 新增 `scalebar_length_cm`（默认 4.0，校验 0 < x ≤ 30），arcpy 自绘比例尺按其取目标长度；单测补默认值/校验/往返断言。
- D8（残余 3）：**nolayout 语义统一**——`layout` 缺席时两 renderer 都不创建布局：qgis 不建布局（P0 现状），arcpy 产 map-only `.aprx`（无布局、无 PDF/PNG 导出）。
- D9（残余 4）：arcpy 消费 `frame=False`——通过 CIM 关闭地图框边框（实现前先探针定位 CIM 字段）；QGIS 路径已支持（setFrameEnabled）。
- 残余 5（调试 PDF 残留）已在验收后清理，无代码改动。
