# Capability：p3-skill-knowledge —— GeoCode-Release 领域知识集成（Skill 集市 → agent 会话可读）

## 定位

把上游 zzhonglei/GeoCode-Release Skill 集市（`contributions/`）中的 GIS/GEE 领域知识以"原样收录 + 适配注记"方式集成进本项目：素材落在不入库的 `_ref/`（仿 `_src/` 先例），tracked 层是一份知识索引 `docs/knowledge/README.md`（收录清单、说明、适配注记、出处）加 AGENTS.md 指针段，使全新 agent 会话凭 AGENTS.md 指针能定位知识文件并据此正确回答领域问题。零管线改动：不碰 `gis/`、daemon.py、jobs.py、emit.py、spec.py；PROCESSING_VERSION、指纹体系、三出口行为零变更。

需求来源：docs/README.md §9.2 C7 行、§9.6（素材来源经 2026-10-07 事实核验修正——`_src/` v0.9.6 快照不含 `contributions/`，改由上游仓库补齐，用户已确认）。

## 行为规格

### Scenario: 素材落位与出处（验收：A1）

验收：A1

对上游仓库 github.com/zzhonglei/GeoCode-Release 以 sparse-checkout 只取 `contributions/`，检出上游 main（checkout 时锁定实际 commit hash）：

- `_ref/contributions/<skill>/` 下 5 个收录技能结构完整、与上游原样一致：manifest/meta.json、manifest/README.md、skill/SKILL.md，及其 references/、templates/、scripts/、data/（含数据文件：china-admin-boundaries 3 份 GeoJSON 共 ~18.7MB、thematic-map 底图 gpkg 6.5MB）；
- `_ref/` 根含出处标注文件：上游仓库 URL、commit hash、抓取日期；上游 LICENSE 与 NOTICE 原文随收（或 `_ref/` 内等效出处文件承载同等信息）；
- `_ref/` 加入 .gitignore（不入库）；`_src/` 零改动；
- 网络访问仅限该上游公开仓库，不触发任何 GEE 任务。

### Scenario: 筛选边界（验收：A2）

验收：A2

收录范围 = 已确认清单（gee-scripting、thematic-map、projection-selection、china-admin-boundaries、china-statistics-data，共 5 个）；被弃技能 docx-reader、pdf、xlsx、hello-geocode、update-test 不出现在 `_ref/contributions/` 的收录结果与索引收录表中。索引记录筛选理由：docx/pdf/xlsx 为 K-Dense Inc. 第三方办公文档技能（非 GIS 领域），hello-geocode/update-test 为 deprecated 样例与一次性测试技能。

### Scenario: 指针与索引（验收：A3）

验收：A3

- AGENTS.md 保留 comet-ambient-resume 托管块与图片纪律节原文，新增"领域知识库"指针段：知识库位置（`_ref/` + 索引路径）、何时读（涉及 GIS/GEE 工作流、制图投影、行政区划边界、专题制图等领域问题时）、收录技能清单；指针段只含指针与清单，不含知识正文摘录；
- `docs/knowledge/README.md`（tracked；.gitignore 增加 `!/docs/knowledge/` 例外）为知识索引：每技能一句话说明 + 适配注记——不适用段落及对应本项目模块：
  - gee-scripting 的 RunGeeScript 工具与 `from geocode import ...` → 本项目用 gis/source.py 计算图与 daemon 管线，不引入该工具面；
  - china-statistics-data 的 Playwright MCP 开启流程 → 本项目无浏览器工具面，仅保留 NBS 平台结构等领域知识部分；
  - thematic-map 的 Cartopy/frykit/matplotlib 强制栈 → 本项目制图走 QGIS/arcpy 双 bridge（LayoutSpec 契约），其 references 的制图规范（图例/比例尺/指北针/经纬网/配色）仍适用作设计依据；
  - 各技能中的"GeoAgent/GeoCode 客户端"身份表述 → 本项目会话语境，不改变知识内容本身；
- `.zcode/skills/` 下既有 Comet 技能不变。

### Scenario: 新会话可用性（验收：A4）

验收：A4

以全新 agent 会话实测（无本次 change 的对话历史、无人工补充提示）：仅凭 AGENTS.md，会话能定位知识索引与相关知识文件，并正确回答至少一个领域问题。候选问题（命中其一即达标；回答须与知识文件内容一致，且不得给出与本项目 red lines 冲突的操作指令）：

- 中国区域制图应选什么投影坐标系（projection-selection：变形性质四分类、中国制图投影坐标系规范）；
- 中国省/市/县行政区划边界数据从哪获取、怎么选单元（china-admin-boundaries：Tianditu 合规数据、adcode 选择纪律、WGS84/EPSG:4326）；
- 专题图的图例/比例尺/指北针/经纬网规范要点（thematic-map references）。

### Scenario: 管线零改动守护（验收：A5）

验收：A5

- git diff（相对基线 a35c48b）不含 gis/、daemon.py、jobs.py、emit.py、spec.py 及任何管线代码文件；改动仅限：.gitignore（`_ref/` 排除 + `!/docs/knowledge/` 例外）、docs/knowledge/README.md（新增索引）、AGENTS.md（新增指针段）、`_ref/`（不入库）、docs/comet/（本 change 产物）；docs/README.md 的台账更新在主工作区就地完成（本地文件不入库）；
- tests/unit 全绿（离线 94 用例，命令见 Verification expectations）；
- smoke 不回退：client 类 smoke 端口写死 6531，被并行会话（C5/C6）占用时以"零管线改动 + tests/unit 全绿 + 索引/指针静态核查"作为等效守护并在验收报告注明；端口可用时在本工作区实测通过。

## Constraints

- 上游素材保留 MIT License（Copyright (c) 2025 opencode / (c) 2026 zzhonglei）与 NOTICE 原文；索引与适配注记为自有产出，须同样标注知识来源，不得把上游知识当作自有产出。
- `_src/` 只读；不 select/resume p2-batch-export（C5）与 p2-array-chunking（C6），不动其 worktree。
- 非目标重申：不做技能商店/安装流程、不引入 GeoCode 客户端工具依赖、不碰 C8（OSM Overpass）。
