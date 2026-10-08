# 发布面 Specs 索引与 supersession 台账

> 本文件是**发布面索引**，不是正式 Spec。正式 Spec 一律位于 `specs/<capability>/spec.md`
> （Runtime 只认这个路径；`specs/` 下的其他文件不会被当作正式规格）。
>
> 建立于 2026-10-08 的 **c13-spec-consistency**：跨 change 审阅（C1–C12）发现发布面同时存在互斥或
> 陈旧的「当前行为」陈述，本文件把**条款级取代关系**显式登记，并把四条发布面规范固定下来。
> 逐条修订方案见 `docs/comet/changes/c13-spec-consistency/spec-revision-list.md`；条目级修订由
> `tests/unit/test_comet_spec_consistency.py` 机械守卫。

## 一、条款级 supersession 台账

被取代的条款**原文保留不删**，各自在条款旁带 `> ⚠️ …` 注记指向本表。新增 change 若改动既有
capability 的行为，必须在此**追加一行**并给对方 spec 加注记。

| 被取代/被修订的条款 | 取代/修订方 | 日期 | 说明 |
|---|---|---|---|
| `p1b-arcgis-addin`（C9）：`gis/preflight.py` 探测项判据「**6530 端口是否监听（占用可见）**」 | `c12-preflight-endpoint-probe`（C12，`3c66c65` / `b160644`） | 2026-10-08 | 判据改为**端点身份匹配**：`GET /` 须 200 + 合法 JSON + `name == "geocode-pro"`；`listening` 降为诊断字段；端口被别的进程占用时报独立失败码 `pro-port-occupied-by-other` |
| `dockpane`（C11）：「`gis/preflight.py` **零改动**（`check_pro_addin` 的 installed/deployed/listening 三探测语义不变）」 | 同上 | 2026-10-08 | 该句仅约束 C11 范围；三探测语义已被 C12 修订（`ok` 改以端点为准） |
| `core-contract-unit-tests`（C1）：「`tests/smoke_*.py` **保持原样**；`gis/` **无行为性修改**」 | `c10-review-patches`（C10，`d091bff`）＋ `c12-preflight-endpoint-probe`（C12） | 2026-10-08 | C10 更新了 `smoke_array_chunking.py` / `smoke_map_renderers.py` / `smoke_timeseries.py`；C12 更新了 `gis/preflight.py` 的探测行为 |
| `p1a-arcpy-bridge`（C2）：「优先复用 P0 缓存产物，**指纹 `c9243efd`**」 | `p2-presets`（C4，`ce40e45`，`PROCESSING_VERSION` 2→3）＋ `c10-review-patches`（C10，指纹须随时代取值） | 2026-10-08 | 缓存文件名含指纹（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`），`c9243efd` 是 PV=2 历史值；当代金指纹为 `b91c09c9c6451c16`。**按指纹指名缓存/写期望值必须随时代取值** |

**就地订正（非跨 change 取代，仅格式/措辞对齐实现）**：

| spec | 订正内容 | 日期 |
|---|---|---|
| `c12-preflight-endpoint-probe`（C12） | ①A16 场景「进程内起假服务器」→「**子进程承载**的假服务器」（`tests/unit` 受离线守卫约束不得导入 `socket`/`http`/`urllib`）；②Scenario 验收引用移入标题并改用 Runtime 验收编号 A9–A17（原先写在标题外独立行、混用 brief 编号） | 2026-10-08（C13） |
| `dockpane`（C11） | H1 由 `# Capability：c11-dockpane …` 改为 `# Capability：dockpane …`（capability 名对齐目录名，change 名在正文点明） | 2026-10-08（C13） |
| `p2-presets`（C4）、`p2-batch-export`（C5） | H1 补 `Capability：<目录名> —— ` 前缀（此前为裸标题） | 2026-10-08（C13） |
| `p3-skill-knowledge`(C7) / `p3-osm-overpass`(C8) / `p1b-arcgis-addin`(C9) / `c10-review-patches`(C10) / `dockpane`(C11) | 各 Scenario 标题补 `（验收：Ax）`（共 40 条：5+8+8+9+10），映射见 `spec-revision-list.md` §F6 | 2026-10-08（C13） |

## 二、发布面四条规范

1. **capability 命名 = 发布面目录名**：H1 必须形如 `# Capability：<目录名> —— <标题>`。
   （Runtime 按 `specs/<capability>/spec.md` 落库；名字不符会让「capability ↔ 文件」失去唯一对应。）
2. **每个 `### Scenario:` 标题必须带 `（验收：Ax）`**：引用写在标题内，不接受标题外的独立引用行。
   编号用该 change 的验收集编号（Verifier 看到的同一套 ID）；Scenario 与 acceptance 不要求 1:1，但必须可追溯。
3. **按指纹指名缓存或写期望值必须随时代取值**：指纹进缓存文件名（`{slug}.{指纹8位}.tif`），
   `PROCESSING_VERSION` 变化会改变文件名与期望值；不得把某时代的常量当作跨时代判据
   （单一事实源：`tests/unit/_helpers.py::GOLDEN_FINGERPRINTS`；口径来源：`c10-review-patches` A1/A2）。
4. **双副本逐字节一致**：任何 spec 修订必须同时改发布面 `docs/comet/specs/<cap>/spec.md` 与归档面
   `docs/comet/archive/<change-dir>/specs/<cap>/spec.md`，两者必须逐字节相同。

## 三、机械守卫

`tests/unit/test_comet_spec_consistency.py` 检查规范 1、2、4 与归档产物完整性（离线、只读文件）：

- 发布面 spec 存在且数量合理（≥12）；
- H1 前缀与目录名一致（规范 1）；
- 发布面 spec 在归档面有逐字节相同副本，且无孤儿 capability（规范 4）；
- 每个 Scenario 带标题内引用、且无标题外独立引用行（规范 2）；
- 每个归档 change 目录含 `brief.md` / `comet-state.yaml` / `verification.md` / `specs/*/spec.md`。

规范 3 与语义级取代关系无法自动判定，靠本文件的人工台账 + 审阅。
