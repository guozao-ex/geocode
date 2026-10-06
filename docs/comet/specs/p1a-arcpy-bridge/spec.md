# Capability：p1a-arcpy-bridge —— arcpy 出版级出图 + LayoutSpec 制图契约

## 定位

把「出版级制图」从两个 bridge 各写一套的隐患变成共享契约：`spec.py` 定义 `LayoutSpec`（呈现规格，与 `render` 对称），`qgis_bridge` 与 `arcpy_bridge` 共同消费；新增 `arcpy_bridge` 让 ArcGIS Pro headless arcpy 产出可直接进论文的 `.aprx` + PDF/PNG。`emit_map` 以 `renderer` 参数选择出口，默认 `qgis` 保持现状兼容。

## 行为规格

### Scenario: 同一 GeoTIFF 双出图（验收：A1）

给定同一 spec（含 LayoutSpec）与其 GeoTIFF（优先复用 P0 缓存产物，指纹 `c9243efd`；缺失时经 emit_file 现场生成）：`emit_map(renderer="qgis")` 与 `emit_map(renderer="arcpy")` 各产出一张图，均成功落盘 `data/deliver/`；qgis 路径产出 `.qgz` + PNG（现状格式），arcpy 路径产出 `.aprx` + PDF + PNG。

### Scenario: arcpy 出版图五要素（验收：A2）

arcpy 路径产出的 layout 包含标题 / 比例尺 / 指北针 / 图例 / 图廓五要素（arcpy 程序化列元素名断言）；`.aprx` 可被 arcpy 打开，PDF 与 PNG 文件存在、尺寸合理（dpi 遵循 LayoutSpec，默认 300），人工可读、可直接进论文。

### Scenario: LayoutSpec 契约共享（验收：A3）

`LayoutSpec` 为 frozen dataclass，含 `to_dict` / `from_dict` JSON 往返保真；`qgis_bridge` 与 `arcpy_bridge` 均从 `ArtifactSpec.layout` 读取呈现规格，不允许各自私有的布局参数定义；单测覆盖构造、默认值（四要素开、graticule 关、dpi 300、scalebar_length_cm 4.0、formats pdf+png）与往返。

### Scenario: renderer 纪律（验收：A4）

`emit_map` 的 `renderer` 接受 `"qgis"` 与 `"arcpy"`；默认 `"qgis"`；非法值抛出可读错误（列出合法值）。`renderer="qgis"` 且无 layout 时行为与现状完全一致（现有输出不回归）。**nolayout 语义统一**：`layout` 缺席时两 renderer 都不创建布局——arcpy 路径产 map-only `.aprx`（无布局、无 PDF/PNG 导出），qgis 路径维持 P0 三件套。

### Scenario: C1 回归基线（验收：A5）

`C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit` 在仓库根全部通过（含 LayoutSpec 新用例与更新后的指纹守卫），运行时长 < 10 秒，全程无网络访问。

### Scenario: 指纹与资产保护（验收：A6）

新增 `layout` 字段后，旧 spec（不含 layout）的 `fingerprint()` 保持不变（守卫名单更新 + 回归断言）；`source.py` / `grid.py` 零改动；`PROCESSING_VERSION` 保持 2；`arcgispro-py3` 环境不被安装任何新包（subprocess + 文件交换，红线 7）。
