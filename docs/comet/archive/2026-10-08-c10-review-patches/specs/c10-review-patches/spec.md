# Capability：c10-review-patches —— 审阅问题全量补丁（测试断言 / 归档 Spec 正文 / 文档 / 本地配置）

## 定位

C1–C9 的归档 brief/spec/verification 与仓库实际状态逐一比对后，本 capability 交付的**补丁面**：修掉审阅发现的可修问题，使「代码行为、测试断言、归档 Spec 正文、开发文档实际状态」四处重新自洽。它不新增产品行为：不改任何栅格像素输出、不改三出口语义、不改 `spec.py` 指纹、不新增字段、不动预设表、不新增依赖。

本 capability 覆盖三类载体，交付时必须分开列明：

- **入库文件**：`tests/`（断言与入口）、`docs/comet/specs/**` 与 `docs/comet/archive/**/specs/**`（归档 Spec 正文，两处同步且逐文件一致）；
- **本地文档**：`docs/README.md`（被 `.gitignore` 的 `/docs/*` 忽略；只存在于主工作区；**本 change 的 worktree 内不改动**，按 D9 在归档轮于主工作区就地执行）；
- **本机配置**：`geocode.json`（skip-worktree 本地件；同样按 D9 在归档轮于主工作区就地执行）。

需求来源：C1–C9 交付物的只读审阅结论（12 条，其中 S6/S7 经 2026-10-08 磁盘与代码复核后撤销；有效项 S1–S5、S8–S12）+ S13（C9 归档后的台账收口）。

## 行为规格

### Scenario: SMOKE-A3 指纹断言按时代取值

验收：A1

`tests/smoke_array_chunking.py` 的指纹判定不再以常量字符串 `c9243efd` 作为通过条件。期望值从"按 `PROCESSING_VERSION` 登记的金指纹"这一单一事实源取得（当前 PV=3 ⇒ `b91c09c9c6451c16`），或在无法读取登记表时与本次 daemon 返回的 `spec.fingerprint()` 自洽比较。该文件的打印文案同步更新，不再断言"期望 c9243efd…"。

`tests/unit/_helpers.py` 的指纹注释与 `make_p0_spec` docstring 标注时代：`c9243efd40318c85` 为 PV=2 时代值，`b91c09c9c6451c16` 为 PV=3 现行值；任一注释都不再把 PV=2 值表述为"现状金指纹"。

新增离线用例：断言"指纹期望值取自 `PROCESSING_VERSION` 对应登记项"（例如对 `GOLDEN_FINGERPRINTS[PROCESSING_VERSION]` 存在且非空、且与 `make_p0_spec().fingerprint()` 相等的守护），使该断言在任何一次版本 bump 后自动指向正确值，而非依赖人工修改常量。

### Scenario: SMOKE-B1 离线地图冒烟自足

验收：A2

`tests/smoke_map_renderers.py` 的模块说明与实际运行前提一致，必须写明：

- 该冒烟使用的栅格缓存文件名带**当前时代指纹**（`gis/emit.py::_output_path` → `{slug}.{指纹8位}.tif`；PV3 现行 `b91c09c9`）——**不得**表述为「默认离线命中 PV2 时代的 `c9243efd` 缓存」或「新指纹 spec 可复用旧栅格」（指纹进文件名，跨时代不通用）；
- **离线命中的条件**：目标缓存文件已存在且 >4096B（`gis/emit.py::_ensure_raster` 的复用分支）；
- 缓存缺失时**不静默跳过**：走联网路径现场生成（GEE 拉取，需网络与认证）；且写明主工作区现存的 P0 产物是 PV2 时代 `s2_beijing_test.c9243efd.tif`，在当前 PV 下不命中——故当前实际走联网，先在当代 PV 下生成一次当代缓存，之后即可离线复跑；
- 「`c9243efd` 是 P0 历史指纹（PV2 时代），当代金指纹见 `tests/unit/_helpers.py` 的按 PROCESSING_VERSION 时代登记表」。

说明文字更正不改变脚本的判定逻辑与产物；缓存存在且 >4096B 时离线跑 qgis 分支应为 PASS（缓存缺失则走联网路径）。

### Scenario: SMOKE-C1 测试入口稳健性

验收：A3

`tests/unit` 与 `tests/smoke_timeseries.py` 的共享构造（`_helpers.py`）不依赖运行方注入 `sys.path`：

- `python -m unittest discover -s tests/unit` 全绿（保持现状兼容）；
- `python -m unittest tests.unit.test_spec_basics` 等 dotted-path 形式同样全绿（当前报 `ModuleNotFoundError: _helpers`，本场景要求消除）；
- 实现方式优先"新增 `tests/unit/__init__.py` + 统一包路径导入"；若两种入口无法同时满足，以两种入口都可用为验收底线，允许调整 `_helpers.py` 的位置/名称，但必须同步全部引用点；
- `docs/README.md` §12 命令速查写明两种入口（dotted-path 若仍需 `-t tests/unit`，明确写出）。

### Scenario: C3 spec 正文与实现一致

验收：A4

`docs/comet/specs/p2-timeseries/spec.md` 与其归档副本 `docs/comet/archive/2026-10-06-p2-timeseries/specs/p2-timeseries/spec.md` 的正文修正为与实现一致：

- A3 场景的 `emit_file` 时序实现描述改为**逐期 `getDownloadURL` 拉取 + 本地合并**（实现落点 `gis/emit.py` 的 `_download_stack_to`），并保留实测依据：`toBands()` 单请求 54,613,440B 超 GEE 50,331,648B 上限被 400 拒，逐期请求与单期同限；该路径属已授权的等价实现，产物形态与对齐判据不变；
- 修正只触及正文表述：验收 ID、场景标题、场景数量、`Acceptance:`/`验收：` 引用均不变；两份文件除这些修正外与归档版本逐行一致。

### Scenario: README 文档订正

验收：A5

主工作区 `docs/README.md`（本地文档，gitignored；按 D9 在归档轮于主工作区就地执行，本 change 的 worktree 内不改该文件）按实际状态订正：

- **§9.6** C8 行不再是裸待办：改为删除线 + ✅ 归档（提交 `2361082`），与 §9.1/§9.2 的 C8 状态一致；不得再引用不存在的模块名；
- **§11 红线 2** 补充 C3 确立的约束："时序不改变网格语义（`compute_grid()` 仍是网格唯一来源）"；
- **§13** 参考表的交叉引用由"（§9.3）"更正为"（§9.4）"；
- **§9.2 C1 行**的"覆盖红线 1/2/3 关键断言"更正为"覆盖红线 2/3/8 关键断言"（与 C1 brief/spec 实际断言一致）；
- **§9.1 余量**措辞由"C4 分支清理"更正为"worktree/分支残留清理"（C4 已并入 main）；
- **§8** 新增一条踩坑记录：时序期窗口推导（以 `time_range[0]` 为起点、月/年步进用年月加法并对月末钳制、日/周用 `timedelta`、末段可越界至多一个步长、期数上限保护）；
- **§8 #18** 关于 Overpass 镜像池的表述与本机实际配置自洽（见 A6）；
- **§2.4** 目录树含 `_ref/`（不入库的上游知识快照）。

### Scenario: 本地配置补齐 OSM 镜像池

验收：A6

主工作区 `geocode.json`（skip-worktree 本地件；按 D9 在归档轮于主工作区就地执行）增加 `osm.endpoints` 镜像池（至少 2 个 endpoint；主站与镜像的序位按 README 记录的实测可用顺序）。要求：

- `gis.osm._endpoints()` 读回该列表（`gis/osm.py` 已在 `_endpoints()` 中读取 `geocode.json` 的 `osm.endpoints`，本 change 不改其实现）；
- `gee` / `gdal` / `server` 段保持原值不变；
- 文件仍为 skip-worktree 入库状态（本地件，不入库）；
- README §8 #18 的描述与该实配一致。

### Scenario: OSM fixture 归属标注

验收：A7

`tests/unit/fixtures/` 下新增说明文件（如 `README.md`），载明 `osm_water_recorded.json` 的来源与许可：数据来自 OpenStreetMap / Overpass API（经 Overpass 录制），© OpenStreetMap contributors，许可 ODbL；并记录录制时间（`osm3s.timestamp_osm_base`）、查询范围与用途（仅测试 fixture）。fixture 正文不改；`tests/unit/test_osm.py` 仍全绿。

### Scenario: 交付形态与可回退性

验收：A8

交付清单按三类载体分开列明，且可逐项核对：

1. **入库改动**：`git diff --name-only main` 只含 `tests/`、`docs/comet/specs/`、`docs/comet/archive/*/specs/`、`docs/comet/changes/c10-review-patches/`；不含 `gis/`、`Pro/`、`scripts/`、`docs/comet/changes/p1b-arcgis-addin/`；
2. **本地文档改动**：列出 `docs/README.md` 的具体章节与改动要点，并给出回退方式；
3. **本机配置改动**：列出 `geocode.json` 的确切键与值，并给出回退方式（删除 `osm` 键即回默认单点）；
4. `docs/comet/archive/*/verification.md` 与 `comet-state.yaml` 零修改（归档结论不被补丁触碰）。

### Scenario: C9 归档与路线图收口台账

验收：A9

主工作区 `docs/README.md`（本地文档，gitignored；按 D9 在归档轮于主工作区就地执行，本 change 的 worktree 内不改该文件）按 C9 归档后的实际状态收口：

- **§9.1「下一步」行**：写明 C1–C9 全部交付、路线图清账；余量仅剩 dockpane（拆出另行立项）；引用 C9 归档提交 `2817da6` / `a76a1f1` 与已推送状态；
- **§9.2 台账**：C9 行状态列与归档提交号自洽，保留「dockpane 拆出，另行立项」注记；如新增本 change（C10）行，按同一格式登记；
- **§9.4 P1b 节**：落定 dockpane 立项的范围要点（GUI 状态面板：6530 状态与三工具入口的进程内展示、操作入口边界）与前提（可复用 C9 的 add-in 骨架、打包部署与 Pro 取证流程）；
- 全篇不再出现「C9 add-in（条件性）」等过期余量表述（与 A5 的 §9.1 措辞订正同一处，合并核验）。

## Constraints

- **红线 1/2**：不引入 ee 对象、不改 `source.py` 计算图、不改 `compute_grid()` 语义；本 capability 是测试/文档/配置补丁。
- **红线 3**：`PROCESSING_VERSION` 保持 3，不 bump；本 capability 不改任何像素输出。
- **红线 8**：不新增 `ArtifactSpec` 字段，指纹白名单/排除名单不变。
- **归档 Spec 修正边界**：只改正文，不改验收 ID、场景标题与场景数量；每处修正须有实现或磁盘事实支撑（S6/S7 两条因前提与磁盘/代码相反而撤销，即为此纪律的结果）；`docs/comet/specs/**` 与 `docs/comet/archive/**/specs/**` 两处同步且逐文件一致。
- **不改 C9**：`Pro/`、`gis/preflight.py`、`scripts/package_pro_addin.py`、`tests/unit/test_pro_addin.py`、`docs/comet/changes/p1b-arcgis-addin/` 一律不动。
- **不实现 dockpane**：本 capability 只落台账与未来立项的范围要点（A9），不新增 `Pro/` 侧实现、不新增 Pro 会话取证依赖、不新增验收运行依赖。
- **本地件纪律**：`docs/README.md`（gitignored）与 `geocode.json`（skip-worktree）只就地更新，不入库；入库改动与本地件改动在交付中分开。
- **离线纪律**：`tests/unit` 保持离线（不 import `ee`、不发网络请求），本 capability 全程不触发 GEE/Overpass。
- **工作区**：worktree `comet/c10-review-patches`（已同步至 main `2817da6`，含 C9 归档）。
