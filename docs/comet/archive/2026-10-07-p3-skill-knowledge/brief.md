# 目标

把上游 zzhonglei/GeoCode-Release Skill 集市（`contributions/`）中的 GIS/GEE 领域知识集成进本项目，使 agent 会话能够发现并读取使用：凭项目指令文件 AGENTS.md 中的指针定位知识文件，并据此正确回答领域问题（如中国区域制图的投影选择、行政区划边界数据获取、专题制图规范）。所有收录内容保留 MIT License 与 NOTICE 出处标注，不冒充自有产出。

对应台账：docs/README.md §9.2 C7 行、§9.6（见范围·来源覆盖）。

# 范围

- 素材获取：对上游仓库 github.com/zzhonglei/GeoCode-Release 做 sparse-checkout，只取 `contributions/`（版本对齐上游 main，checkout 时锁定实际 commit hash 记入出处）。
- 技能筛选（已确认清单）：收录 5 个 GIS/GEE 领域技能——gee-scripting、thematic-map、projection-selection、china-admin-boundaries、china-statistics-data（数据文件随收录）；弃用 5 个——docx-reader、pdf、xlsx（K-Dense 第三方办公文档技能）、hello-geocode、update-test（deprecated 样例/测试技能）。
- 集成形态：原样收录 + 适配注记——上游 SKILL.md 原文不动，每技能在索引中加适配注记，标明不适用本项目 red lines 的段落（RunGeeScript、Playwright MCP、Cartopy/frykit 栈、geocode 包）及对应本项目模块（gis/source.py、daemon 管线、QGIS/arcpy 双 bridge 与 LayoutSpec 契约）。
- 知识存放：知识正文落 `_ref/contributions/<skill>/`（`_ref/` 加入 .gitignore 不入库，仿 `_src/` 先例）；tracked 层为索引 `docs/knowledge/README.md`（含收录清单、一句话说明、适配注记、出处；.gitignore 加 `!/docs/knowledge/` 例外）；AGENTS.md 新增领域知识库指针段（只加指针与清单，不塞知识正文）。
- 台账 C7 状态更新：docs/README.md 属主工作区本地文件（.gitignore 忽略），按既有先例交付时在主工作区就地更新。

## Source coverage

来源：docs/README.md（主工作区本地文件，被 .gitignore 忽略不入库；worktree 内不存在，以下行号以主工作区当前内容为准）。

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
| --- | --- | --- | --- | --- | --- | --- |
| S1：§9.2 Change 台账 C7 行（第 382 行） | complete | 读 GeoCode-Release 的 SKILL.md 作领域知识；验收要点"领域知识可被 agent 会话读取使用" | specs/p3-skill-knowledge/spec.md 全部场景 | A1–A5 | covered | 素材来源经 2026-10-07 事实核验修正：`_src/` v0.9.6 快照不含 `contributions/`，改由上游仓库补齐（用户已核实并指定此前提） |
| S2：§9.6 P3 第一条（第 444 行） | complete | Skill 集市集成（C7）：读 contributions/ 下的 SKILL.md 作为领域知识 | specs/p3-skill-knowledge/spec.md 全部场景 | A1–A5 | covered | 同 S1：路径修正为上游 contributions/ |
| S3：§13 参考表 GeoCode-Release 行（第 533 行） | complete | 上游仓库标识（github.com/zzhonglei/GeoCode-Release，快照 v0.9.6） | specs/p3-skill-knowledge/spec.md 出处标注场景 | A1 | covered | 必要依赖：S1/S2 素材来源仓库的唯一标识 |

# 非目标

- 不碰 `gis/` 目录与任何管线代码：daemon.py / jobs.py（C5 在改）、emit.py（C6 在改）、spec.py（契约层）均不修改。
- PROCESSING_VERSION、指纹体系、三出口行为零变更。
- C8（OSM Overpass 矢量源）不在本 change。
- 不引入 GeoCode 客户端工具依赖（RunGeeScript、Playwright MCP 等）；不触发任何 GEE 任务。
- 不把上游技能改造为可执行管线代码；不做技能商店/安装流程。
- 不改 `.zcode/skills/` 下既有 Comet 技能。

# Constraints and invariants

- `_src/` 只读不动；补齐素材放独立目录 `_ref/`，仿照 `_src/` 先例加入 .gitignore（不入库）。
- 收录内容保留 MIT License 与 NOTICE 出处（上游仓库 URL、commit hash、抓取日期、原始路径），不得当作自有产出。上游根目录自带 LICENSE（MIT，Copyright (c) 2025 opencode / (c) 2026 zzhonglei）与 NOTICE（GeoCode-Release 为 OpenCode 桌面 fork）。
- worktree 隔离：分支 comet/p3-skill-knowledge（基于 main HEAD a35c48b）；不 select/resume p2-batch-export（C5）与 p2-array-chunking（C6），不动其工作区。
- AGENTS.md 只加指针不塞正文；AGENTS.md 当前为主工作区未跟踪文件，本 change 将其首次入库（保留 comet-ambient-resume 托管块与图片纪律节原文），归档合并时需处理主工作区同名未跟踪文件的碰撞。
- 网络访问仅限拉取上游公开仓库素材（github.com/zzhonglei/GeoCode-Release），不触发 GEE。

# Decisions

- D1（Q1）：素材获取 = sparse-checkout 只取 `contributions/`，不带 assets/、scripts/ 等无关目录。
- D2（Q2）：版本对齐 = 上游 main（2026-10-07 观测 HEAD 6e3534f7af3675b19bd3c5d54c94022959dccdd2），checkout 时锁定实际 commit hash 记入出处；不用 v0.9.6 标签——两个中国数据技能仅存在于 main，thematic-map 亦以 main 版（v0.3.1）更新。
- D3（Q3）：筛选清单 = 留 gee-scripting / thematic-map / projection-selection / china-admin-boundaries / china-statistics-data（含各自 references、data、scripts 与数据文件）；弃 docx-reader / pdf / xlsx（K-Dense Inc. 第三方办公文档技能，非 GIS 领域）、hello-geocode / update-test（deprecated 样例与一次性测试技能）。
- D4（Q4）：集成形态 = 原样收录 + 适配注记——原文保真、出处清晰；客户端特定段落经注记声明不适配，避免改写失真。
- D5（Q5）：知识存放 = 正文 `_ref/`（不入库）+ tracked 索引 `docs/knowledge/README.md`（.gitignore 加例外）+ AGENTS.md 指针；不注册 `.zcode/skills/`（避免污染技能自动触发面）。
- D6（Q6）：验收判据 = A1–A5 建议基线（见验收示例）；smoke 在端口 6531 被并行会话占用时以等效守护代替并注明。

# Verification expectations

- 管线零改动：git diff 范围核查，本 change 不出现 gis/、daemon.py、jobs.py、emit.py、spec.py 等管线文件改动。
- tests/unit 基线全绿（离线 94 用例；C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit）。
- 现有 smoke 不回退：本 change 不改管线代码；client 类 smoke 端口写死 6531，并行会话可能占用该端口（连到别的 worktree 的 daemon，证据无效）——端口被占时以"零管线改动 + tests/unit 全绿 + 知识文件静态核查"作为等效守护，并在验收报告中注明。
- 新会话可用性判据：以独立全新会话实测（无本对话历史），仅凭 AGENTS.md 指针定位知识文件并正确回答至少一个领域问题。
- 网络访问仅限拉取上游公开仓库素材，不触发 GEE。

# 验收示例

- A1 素材落位与出处：`_ref/contributions/<skill>/` 下 5 个收录技能结构完整（manifest/meta.json、manifest/README.md、skill/SKILL.md 及 references/data/scripts 按上游原样）；`_ref/` 含出处标注（上游 URL + commit hash + 抓取日期）并保留上游 LICENSE 与 NOTICE；`_ref/` 加入 .gitignore；`_src/` 零改动。
- A2 筛选边界：收录范围与确认清单一致；被弃技能（docx-reader、pdf、xlsx、hello-geocode、update-test）不出现在收录结果与索引收录表中；筛选理由记录于索引。
- A3 指针与索引：AGENTS.md 含领域知识库指针段（位置、何时读、收录清单），保留既有托管块原文，无大段知识正文；索引 `docs/knowledge/README.md` 列出每个收录技能的一句话说明与适配注记（不适用段落 + 对应本项目模块）。
- A4 新会话可用性：全新 agent 会话（无本对话历史）仅凭 AGENTS.md 指针能定位知识索引与知识文件，并正确回答至少一个领域问题（如：中国区域制图选什么投影坐标系；中国省/市/县边界数据从哪获取；专题图图例/比例尺/指北针规范要点）。
- A5 守护判据：git diff 无管线文件改动；tests/unit 94 用例全绿；smoke 判定按 Verification expectations（端口冲突时等效守护并注明）。
