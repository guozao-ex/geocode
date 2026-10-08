# C10 本地件待执行差异清单（A5 / A6 / A9；交付形态与回退见 A8）

> **来历（2026-10-08 由 `c13-spec-consistency` 回收）**：本文件是 C10 归档时的四列差异清单原件，
> 原落在主工作区 gitignored 的 `logs/acceptance/c10-local-changes.md`（不入库、不在归档产物内）。
> 为兑现「清单载体须 git 跟踪、随归档入库」的一致性口径，本文逐字复制进归档面；**正文一字未改**。
> 位置说明：本文件放在**本 change worktree 的 `logs/`**（gitignored，不入库；change 目录
> `docs/comet/changes/c10-review-patches/` 除 `brief.md`/`children.yaml`/`specs/*/spec.md`
> 外由 Runtime 专有，agent 不可写）。同一内容的要点已随 builder-handoff 提交并随归档留存。

本 change 的**本地件（不入库）**改动不在 worktree 内执行（D9 决定），由**归档轮在主工作区就地执行**：

- `docs/README.md`：被 `.gitignore` 的 `/docs/*` 忽略（`!/docs/comet/` 例外），只存在于主工作区；
- `geocode.json`：`skip-worktree` 本地件（主工作区 `git ls-files -v geocode.json` 显示 `S`）。

每条给出：位置 / 现状 / 改为 / 依据 / 回退。

---

## 一、`docs/README.md`（A5 文档订正 + A9 C9 归档台账收口；共 11 条）

### 1. §9.6 的 C8 行（S9）— 裸待办 → 归档
- 现状：`- OSM 工具（Overpass）作为矢量数据源（C8）`（与 §9.1/§9.2 的 ✅ 已归档自相矛盾）
- 改为（与 C7 行同格式：删除线 + ✅ + 提交号）：
  `- ~~OSM 工具（Overpass）作为矢量数据源~~ → ✅ **已交付（2026-10-07，提交 `2361082`）**：Overpass 矢量源接入（`gis/osm.py` QL/退避/装配 + `gis/aoi.py` 边界 + OverlaySpec 双 bridge）`
- 依据：S9。原判的「本行引用不存在的模块名 `gis/osmtools.py`」经 2026-10-08 复核不成立（全仓无该字样），已撤销、不再提。
- 回退：还原为该单行。

### 2. §11 红线 2（S8 ②）— 补 C3 的时序约束
- 现状：`2. **网格必须由 compute_grid() 定**——不允许出口各自算`
- 改为：追加半句 → `2. **网格必须由 compute_grid() 定**——不允许出口各自算；**时序不改变网格语义**（C3：期维度只增加时间/波段维，网格仍由 `compute_grid()` 唯一决定）`
- 依据：C3 spec 的 Constraints。回退：删去追加的半句。

### 3. §13 参考表两处（S8 ③ + 路径用语）
- `| Knight60/ArcGIS-Pro-MCP | P1b add-in 技术要点来源（§9.3） |` → 交叉引用改为 `（§9.4）`
- （同表）zzhonglei 行的「P3 时读其 `contributions/` SKILL.md」→ 明确为**本地**路径：`` P3 起读 `_ref/contributions/<skill>/skill/SKILL.md`（上游 `contributions/` 经 sparse-checkout 收录）``
- 依据：S8 ③；路径用语与磁盘及 `_ref/PROVENANCE.md` 一致（S7 撤销后的正向表述）。回退：还原两处文字。

### 4. §9.2 台账 C1 行（S8 ④）
- 现状：`覆盖红线 1/2/3 关键断言` → 改为：`覆盖红线 2/3/8 关键断言`（与 C1 实际断言一致）。回退：还原。

### 5. §9.1「下一步」行：余量措辞 + C9 收口（S8 ⑤ + S13；A5+A9）
- 现状（尾段）：`…C8 OSM/Overpass 已于 2026-10-07 立项交付（见下行）；余量：C9 add-in（条件性）、C4 分支清理 | ✅ |`
- 改为：`` …C8 OSM/Overpass 已交付并归档（`2361082`）；C9 add-in 已交付并归档（`2817da6` / `a76a1f1`，**已推送**）——路线图 **C1–C9 全部交付、清账**；余量仅 **dockpane（已拆出另行立项，范围要点见 §9.4）** 与 worktree/分支残留清理 | ✅ | ``
- 依据：S13 + S8 ⑤（原「C4 分支清理」易误读：C4 早已并入 main，残留的是 worktree/分支）。回退：还原原尾段。

### 6. §8 新增一条踩坑（S8 ①）
- 现状：§8 表缺「时序期窗口推导」条目 → 按该表「现象 / 根因 / 结论」三列追加一行，**落在 §8.5「架构层」**（期窗口属于 `gis/spec.py` 契约层推导），**编号 29**（§8 各表当前末号为 28；C9 已占用 #27/#28，在 §8.6）：
  - 现象：自定义月/年步长的期窗口推导（`time_periods`）边界行为无文档；
  - 根因：期窗口 = 以 `time_range[0]` 为起点按步长推进的半开区间集合；月/年用年月加法并**对月末钳制**（1/31 + 1 月 → 2/28 或 2/29），日/周用 `timedelta`；末段允许越界至多一个步长；期数有上限保护；
  - 结论：推导规则与上限写进实现注释与 C3 Spec Constraints；改动期窗口逻辑须同步这两处。
- 依据：S8 ①。回退：删去该行。

### 6bis. §9.4 标题与 §10 第 3 行的「条件性」字样（Verifier 风险 2）
- 现状：§9.4 标题 `### 9.4 P1b —— ArcGIS Pro add-in（change C9，条件性）`；§10 第 3 行 `| 3 | add-in 是否真需要 | ✅ **条件性**——C2（P1a）落地后再评估，对应 change C9 |`。C9 已交付归档，「条件性」已过期。
- 改为：§9.4 标题 → `### 9.4 P1b —— ArcGIS Pro add-in（change C9，已交付 2026-10-08）`；§10 第 3 行 → `| 3 | add-in 是否真需要 | ✅ **已交付**——C2（P1a）落地后评估通过并立项，C9 已于 2026-10-08 归档（`2817da6` / `a76a1f1`） |`
- 依据：Verifier 2026-10-08 风险 2（与 A9 的路线图收口同一事实）。
- 回退：还原两处文字。

### 7. §8 的 Overpass 镜像池条目（S10；与 A6 联动）
- 现状：声称镜像池已配置（kumi / mail.ru / private.coffee 实测可用），与主工作区 `geocode.json` 无 `osm` 键的事实不符。
- 改为：按 **A6 落地后的实配**写成「已落地」并列出实际 endpoint 清单与顺序；若 A6 暂缓执行，则改为「**待落地**（本条即 S10 的登记）」，不得继续声称已配置。
- 依据：S10；实测无 `osm` 键时 `gis.osm._endpoints()` 回退单点主站。

### 8. §2.4 目录树（S8 ⑤）
- 现状：树中没有 `_ref/` → 追加一行：`├── _ref/            # 上游知识快照（C7；本地不入库，索引见 docs/knowledge/README.md）`。回退：删去该行。

### 9. §9.4 落定 dockpane 立项范围要点（S13 / A9）
- 现状：仅在「headless 做不到的三件事」里点名 dockpane，无立项范围。
- 改为：该段之后追加一段：
  `**dockpane（已拆出另行立项）**：范围要点 = add-in 内的 Pro Dockpane 面板，进程内展示 6530 服务状态与三工具（pro_get_view_aoi / pro_add_layer / pro_export_view）的入口与最近结果；前提 = 可复用 C9 已交付的 add-in 骨架、打包部署脚本（.esriAddInX）与 Pro 会话取证流程；**本项不在 C10 范围内实现**。`
- 依据：S13（2026-10-08 用户指定并入 C10 落台账）。回退：删去该段。

### 10. §12 命令速查：补两种测试入口（S4 的文档面）
- 现状：`# 测试` 段只有 `smoke_three_exits` 一条。
- 改为：追加（**实测：均须在仓库根执行；dotted-path 不再需要 `-t`**）：
  ```bash
  # 离线单测（两种入口等价，仓库根执行）
  PYTHONPATH=. python -m unittest discover -s tests/unit
  PYTHONPATH=. python -m unittest tests.unit.test_spec_basics   # dotted-path
  ```
- 依据：S4（C10 前 dotted-path 报 `ModuleNotFoundError: _helpers`；本 change 以 `tests/`+`tests/unit/` 包 + `tests.unit._helpers` 包路径导入修复，两种入口实测全绿）。回退：删去追加行。

---

## 二、`geocode.json`（A6）

- 现状（主工作区）：三键 `gee` / `gdal` / `server`，**无 `osm` 键**；`_endpoints()` 回退默认单点 `https://overpass-api.de/api/interpreter`。
- 改为：新增 `osm` 段（**其余键值一字不改**）：
  ```json
    "osm": {
      "endpoints": [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.private.coffee/api/interpreter"
      ]
    }
  ```
  - 序位：主站排首位；后三条是 README §8 #18 记录为「实测可用」的 kumi / mail.ru / private.coffee 三个镜像的规范 endpoint（把 §8 #18 记录的三个镜像**全部**补回，配置与文档记录一一对应）。C8 当时的配置落在已删除的 worktree 内、未回主工作区——本项即补回。
  - **离线纪律下未联网复测**这些 URL 的连通性；如需变更以实测为准。
- 验证（离线读回）：`python -c "import sys; sys.path.insert(0,'.'); from gis.osm import _endpoints; print(_endpoints())"` → 应打印上述三条。
- 回退：删除 `osm` 键即回默认单点。纪律：保持 skip-worktree（`S`），**不入库**。

---

## 三、交付形态与回退（A8）

| 载体 | 文件 | 入库 | 回退方式 |
|---|---|---|---|
| 入库改动 | `tests/**`（`unit/_helpers.py` 金值表与 `expected_p0_fingerprint`、`smoke_array_chunking.py`、`smoke_map_renderers.py`、`smoke_timeseries.py`、`tests/__init__.py`、`tests/unit/__init__.py`、10 处 `tests.unit._helpers` 导入、`unit/fixtures/README.md`）、`docs/comet/specs/p2-timeseries/spec.md` 与 archive 副本 | ✅ | `git diff main` 逐项核对；单文件 `git checkout -- <path>`；整体丢弃分支 |
| 本地文档 | `docs/README.md`（第一节 11 条） | ❌ gitignored | 按每条「回退」还原 |
| 本机配置 | `geocode.json`（第二节） | ❌ skip-worktree | 删除 `osm` 键 |

- `docs/comet/archive/*/verification.md` 与各 `comet-state.yaml` **零修改**。
- 入库改动路径面核查：`git diff --name-only main` 只应出现 `tests/`、`docs/comet/specs/`、`docs/comet/archive/*/specs/`、`docs/comet/changes/c10-review-patches/`；不得出现 `gis/`、`Pro/`、`scripts/`、`docs/comet/changes/p1b-arcgis-addin/`。
