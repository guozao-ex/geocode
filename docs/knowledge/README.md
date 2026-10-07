# 领域知识库索引 —— GeoCode-Release Skill 集市收录

> 涉及 GIS/GEE 工作流、制图投影选择、中国行政区划边界、专题制图规范等领域问题时，先读本索引，再按需读对应技能的 `skill/SKILL.md` 及其 `references/`。
>
> 知识正文在 `_ref/contributions/<skill>/`（本地目录，不入库；出处与抓取方式见 `_ref/PROVENANCE.md`）。本索引与 AGENTS.md 指针随版本库走。

## 出处

- 上游仓库：https://github.com/zzhonglei/GeoCode-Release （main @ `6e3534f7af3675b19bd3c5d54c94022959dccdd2`，2026-10-07 抓取）
- 许可证：MIT（`_ref/LICENSE`，©2025 opencode / ©2026 zzhonglei；项目关系见 `_ref/NOTICE`）
- 收录形态：**原样收录 + 适配注记**——上游原文不改写；不适配本项目的段落见下表注记，不改知识内容本身。

## 收录技能（5）

| 技能 | 版本 | 内容 | 适配注记（不适用段落 → 本项目对应模块） |
| --- | --- | --- | --- |
| gee-scripting | 0.1.0 | GEE 脚本工作流：脚本模式选择、编写规范，references 含影像合成 / 分类 / 变化检测，附单期影像模板 | RunGeeScript 工具（inline/file 模式）与 `from geocode import init_gee, ...` → **不适用**；本项目经 `gis/source.py` 构建 ee 计算图、daemon 管线执行（红线 1）。其工作流经验（合成顺序、去云纪律、边界文件本地预备）仍适用 |
| thematic-map | 0.3.1 | 专题制图规范：底图、投影、图例、比例尺与指北针、经纬网、研究区边界、栅格/矢量数据，附脚本与底图数据 | Cartopy / matplotlib / frykit 强制栈与"只能用 Python 代码出图" → **不适用**；本项目制图走 QGIS / arcpy 双 bridge（`LayoutSpec` 契约，两 bridge 不各写一套布局参数）。其 references 的制图规范（图例/比例尺/指北针/经纬网/配色）作为 LayoutSpec 设计依据适用 |
| projection-selection | 0.1.0 | 投影选择知识框架：变形性质四分类、UTM/高斯-克吕格分带、圆锥投影标准纬线，附《中国制图投影坐标系规范》 | 客户端耦合最少，几乎整体适用；其"先确定研究区经纬范围"的前置纪律与本项目 `compute_grid(spec)` 唯一确定网格的思路一致 |
| china-admin-boundaries | 0.1.0 | 天地图合规的中国行政区划边界（省 34 / 市 375 / 县 2891，WGS84/EPSG:4326，GeoJSON），含 adcode 选择纪律 | 数据在 `_ref/contributions/china-admin-boundaries/skill/data/`；本项目管线消费时注意 `adcode` 唯一键纪律。明确禁止从 OSM / Natural Earth / GADM 取中国边界（表述不合规）——与 C8（OSM Overpass）并行存在时，OSM 仅用于非边界要素 |
| china-statistics-data | 0.1.1 | 国家统计局主题统计数据查找与下载指南（NBS 平台结构、指标导航） | Playwright MCP 开启流程与"GeoCode 状态按钮" → **不适用**（本项目无浏览器工具面）；NBS 平台结构、指标体系等领域知识部分适用 |

## 弃用技能（5，不收录）

| 技能 | 弃用理由 |
| --- | --- |
| docx-reader / pdf / xlsx | K-Dense Inc. 第三方办公文档技能（vendored 自 scientific-agent-skills），与 GIS/GEE 领域无关 |
| hello-geocode | deprecated 样例技能（上游自标 deprecated: true） |
| update-test | deprecated 一次性测试技能（验证上游商店升级流程用） |

## 使用注意

1. 上游 SKILL.md 写给 GeoCode 客户端 agent，其中出现 RunGeeScript、Playwright MCP、`geocode` 包、GeoAgent/GeoCode 客户端身份等表述时，按上表适配注记理解，**不要**在本项目会话中照做工具指令。
2. 本项目红线不受上游知识影响：ee 计算图只在 `source.py` 构建、网格由 `compute_grid(spec)` 唯一确定、指纹向后兼容、三出口共享契约（docs/README.md §11）。
3. `_ref/` 不入库（遵守 .gitignore 的搜索工具可能跳过它，请按字面路径直接读取）；换机器后按本索引「出处」节或 `_ref/PROVENANCE.md` 记录的上游 commit 重新 sparse-checkout 抓取。
