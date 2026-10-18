# Outcome

让产物的**容器 dtype 可预期、可控**。

现状（项目自 2026-10-06 起记录在 docs/README §9.7）：产物容器 dtype **不由 `spec.dtype` 决定**，
而由 GEE 导出路径决定 —— 声明 `uint16` 的 S2 样本实落 `float64`（P0 产物
`s2_beijing_test.b91c09c9.tif` 4.44 MB / 860×784 / 3 波段），声明 `uint8` 的 WorldCover 实落
`float32`；NetCDF 侧（xee）则按 float32 落盘。

2026-10-11 首次真实数据运行给出了可直接量化的数字（同一 4.6M 像素网格）：

| 产物 | GeoTIFF | NetCDF |
|---|---|---|
| 泰安市 DEM 60m（1 波段） | 6.66 MB | 17.58 MB |
| 泰安市 NDVI 60m（1 波段） | 15.48 MB | 17.58 MB |
| 泰安市 S2 真彩色 100m（3 波段） | 5.39 MB | 18.99 MB |

同一份数据、同一网格，两个出口的字节占用差 2–3 倍，且声明值与实际值不符 —— 下游（论文附件、
ArcGIS/QGIS 工程、后续栅格代数）无法按声明预期规划存储与精度。

**关键风险（必须在 Shape 阶段定清）**：若简单地"按 `spec.dtype` 落盘"，S2 地表反射率的
物理量纲是 0–1 之间的小数（如 0.0695），按 `uint16` cast 会**量化成 0**，属于静默数据损坏；
即"声明即容器"只有在声明与数据量纲一致时才安全。

# Scope

Q1=b / Q2=b 已由用户拍板，范围按此收敛（结论见 Decisions D1）：

- **契约层**：新增 `ArtifactSpec.container_dtype`（默认 `"float32"`），按 D6 序列化（只在值 ≠ 默认时落键）；
  `dtype` 语义收敛为"数据语义提示"，字段注释与两个出口的 docstring 都要写清
  「`dtype` = 数据语义提示（当前不影响落盘）/ `container_dtype` = 落盘容器契约」；
- **出口层**：`emit_file`（GeoTIFF：直写 / 分块 / 时序堆叠三条路径）与 `emit_array`
  （NetCDF：直接 / 分块两条路径）的**写盘容器**按 `container_dtype` 落，同一 spec 两出口容器一致；
- **防线（附条件 2）**：量纲 ↔ 容器一致性守卫 + `collapse_mask_bands` 的整数 value band 提升补齐
  （同一语义域，见 D7/D8 与 A2/A10）；
- **版本与缓存**：容器 dtype 不进指纹、不 bump `PROCESSING_VERSION`（Q2=b）；缓存命中时既有容器按 D2
  就地归一（沿用 C15 先例），不另造基线、不删除既有缓存；
- **文档**：顶层 `README.md`（入库）的 §9.7 边界条目收敛为已定义语义；`docs/README.md`（gitignored 本地件）
  按 D5 走"本地件待执行差异清单"，不就地改主工作区。

## 目录结构

### 新建

- `tests/unit/test_container_dtype.py` — 容器 dtype 契约与量纲守卫的离线用例（含破坏性自证）；
- `docs/comet/changes/c18-container-dtype/local-changes.md` — `docs/README.md`（本地件、不入库）的
  待执行差异清单，四列（现状 / 改为 / 依据 / 回退），沿用 C13 载体：归档轮在主工作区就地执行。

### 修改

- `gis/spec.py` — 新增 `container_dtype` 字段与取值校验；`to_dict` 按 D6 条件序列化；
  `fingerprint()` 维持不含容器（两个序列化点都按红线 8 处理，旧 spec 指纹逐字节不变）；
- `gis/emit.py` — GeoTIFF 与 NetCDF 两侧落容器 dtype；缓存命中时的容器归一（衔接既有
  `_reuse_cached_raster` 的 nodata 归一）与守卫接线；
- `gis/export_chunks.py` — `collapse_mask_bands` 补整数 value band → float32 提升（附条件 2 前半）；
- `tests/unit/` — 既有用例按新字段复核（金指纹断言按同步 main 后的 352 用例口径回归）；
- `README.md` — §9.7 已知边界条目收敛为"已定义"（入库件）。

### 删除

无

### 明确不建

- 不改像素值语义（不做重采样、不引入 scale/offset 变换）；
- 不改指纹算法本身（容器 dtype 按 Q2=b 不进指纹，不碰 `PROCESSING_VERSION`）；
- 不做压缩策略优化（GeoTIFF 的 deflate/predictor 调优是独立话题）；
- 不改 C15 已验收机制的行为（`normalize_nodata_to_nan` 的归一/提升逻辑零改动，见 D8）；
- 不作废旧缓存、不重生成既有基线产物（见 D2）；
- 不改 GEE 侧的导出路径选择、不做跨平台适配。

# Non-goals

- 不追求"让所有产物体积最小"（本 change 只解决 dtype 的**可预期性**与**一致性**，不是压缩优化）；
- 不改 GEE 侧的导出路径选择（`getDownloadURL` / `computePixels` 的取舍属出口层另一话题，
  分块下载见 c15）；
- 不改既有无行为变更的预设语义（S2 / Landsat 的缩放口径不动）；
- 不做跨平台适配。

# Acceptance examples

- A1: 同一 spec 的 `emit_file`（GeoTIFF）与 `emit_array`（NetCDF）容器 dtype 一致，且等于按 Q1 选定
  语义推导出的期望值（例如 `container_dtype=float32` 时两边都是 float32）。
- A2: 量纲守卫生效：对"数据为 0–1 小数、却声明整数容器"的 spec，产物不得被静默量化 ——
  必须报出可读错误（或按选定语义降级为浮点并明确告警），且有离线用例覆盖该判定。
- A3: 既有 P0 样本的像素值不因本 change 变化（数值域校验：min/max/mean 与改动前一致，
  容差 ≤ 1e-6）。Shape 已确认 Q2=b ⇒ 本 change 不 bump `PROCESSING_VERSION`、不预注册金指纹切换，
  A3 只按"数值域不变 + 金指纹不回退"判。实测必须打在 **S2 真彩色**那条（现状 GeoTIFF float64 → 契约
  float32 才是真验证）；DEM（现状已 float32）与 WorldCover（同样 float32）只能作旁证，不得单独充数。
- A4: 文档收敛：README §9.7 的"已知边界"条目不再声称 dtype 不可控，改为写清当前语义与取值规则；
  dev doc 的对应章节同步。
- A5: 回归：离线用例全绿（含容器 dtype 与量纲守卫的新用例）、`uvx ruff@0.17.0 check` 零告警、
  `tests/verify_all.py` 离线层 RUN 全 PASS。
- A6: 附条件 1 —— 旧产物容器不一致被**显式处置**：缓存命中时既有产物的容器 dtype 与当前契约不符
  （如 S2 真彩色 .tif 为 float64、契约 float32）会走一次性归一（沿用 `normalize_nodata_to_nan` 的
  .part + 原子替换先例）并留下可读进度记录；不接受"默认无视"。旧缓存不被删除，也不另造基线。
- A7: 附条件 3 —— 判例写进文档：`docs/README.md` §11 红线 3 下补注记，写明「容器精度截断
  （float64→float32 等）若数值域在 1e-6 容差内不变，不视为改变像素输出；nodata/掩膜语义的归一化
  改写同理（c15 判例）」。该文件是 gitignored 本地件，以**待执行差异清单**形式交付（四列：现状 /
  改为 / 依据 / 回退），由归档轮在主工作区就地执行。
- A8: 回归基线按同步 main 后的口径留档：全量离线用例 ≥ 352 条全绿（不得低于 352），
  并附 change 开始时的实测条数。
- A9: `container_dtype` 序列化按红线 8：仅在值 ≠ 默认 `float32` 时落键；旧 spec（未写该字段）
  指纹逐字节不变，金指纹 `b91c09c9c6451c16` / `c9243efd40318c85` 不回退。
- A10: 附条件 2 —— `collapse_mask_bands`（`gis/export_chunks.py`）补齐整数 value band → float32
  提升，与 `normalize_nodata_to_nan` 口径统一：对整数容器 + nodata=NaN 的组合不再硬失败，
  且有离线用例覆盖该判定（当前实现会抛 rasterio 越界 ValueError）。

# Constraints and invariants

- **红线 3（本次口径，Q2=b）**：容器 dtype 判定为"不影响像素值"（与 render/layout 同类），
  故**不进指纹、不 bump `PROCESSING_VERSION`**；但 A3 仍要求既有 P0 样本像素值不因本 change 变化
  （min/max/mean 与改动前一致，容差 ≤ 1e-6），并给出**实测数字**而非声称；
  ⚠ 若实现中判断仍需 bump PV：会与并行推进的 c16 / c17 的"金指纹不得回退"断言撞车 ——
  **立刻停下报告，不要自己决定**；
- **红线（C15 机制边界）**：`gis/export_chunks.py` 的 `normalize_nodata_to_nan()` 会把整数容器
  提升为 float32，`gis/emit.py` 的 `_reuse_cached_raster()` 会在**复用既有缓存时就地改写产物** ——
  两者与 `container_dtype` 同属一个语义域，必须显式处置（D2 归一化 / D7 拒绝 / D8 不动它）；
  若要改 `normalize_nodata_to_nan` 的行为，**先停下问**（属 C15 已验收语义）；
- 红线：三出口共享同一计算图与网格（本 change 不得为此另建网格）；不做压缩策略优化、
  不改 GEE 导出路径选择、不做跨平台适配；
- 金指纹 `b91c09c9c6451c16`（PV 3）与 `c9243efd40318c85`（PV 2）的登记纪律见
  `tests/unit/_helpers.py`（单一事实源），指纹字面量受 `test_fingerprint_literals.py` 结构守卫约束；
  `make_p0_spec` 现支持 `render` 参数（c16 改动），改前先读最新版；
- `tests/unit` 受离线守卫约束；写盘层改动需保证离线可测（不依赖 GEE）；
- **归档确认口径**：本项目 `.comet/config.yaml` 的 `native.archive_confirmation` = `automatic`
  （归档预检通过即自动归档）、且 worktree 隔离 `finish=null`；按本 change 的 Shape 约束，
  归档必须**先停下问用户选 `--finish keep|merge|push|pull-request`**，不自行选定；
- **回归基线（2026-10-18 同步 main 后实测口径）**：全量离线用例 **352 条**（不是 c18 立项时的 257 条）；
  A3 / 回归口径一律按 352 留档；
- **基线产物在盘可直接用（主工作区只读）**：`D:/DEV/geocode/data/derived/`（53 件），taian 五组为
  `taian_dem_city.26f57c12` / `taian_dem_county.3227ec35` / `taian_s2_ndvi.4e5dc772` /
  `taian_s2_truecolor.ff2f0ca1` / `taian_s2_truecolor_10m.824afc80`（各 .tif + .nc）；
  **不要另造基线，也不要删除既有缓存**；S2 真彩色 10m 那组 .nc 约 1.98 GB，只按需读元数据；
- **共享资源纪律**：`tests/verify_all.py` / `smoke_all.py` / `smoke_tui.py` 会自行启停
  `127.0.0.1:6531` daemon（无引用计数），跑前先确认端口空闲（`netstat -ano | grep 6531`），
  占用中等待、不并发；`tests/unit` 离线单测不启 daemon，可随时跑；
- **本机环境事实**：必须用 geo 环境 `C:/ProgramData/miniforge3/envs/geo/python.exe`
  （numpy 2.5.3 / ee 1.7.46 / python 3.12.14）；arcpy 渲染在本机 **117–121 s/轮**（机器状态所致，
  与代码无关），跑渲染类检查要预留时间，别当超时或挂死；
- **worktree 隔离**：本 change 的一切读写都在
  `D:/DEV/geocode/.worktrees/c18-container-dtype` 内；`data/` 被 gitignore，产物根缺省指向
  worktree 自己的空目录，A3 的对照基线只读复用主工作区路径（见 D9）；
  提交前确认 `git status` 里没有过程脚本（c17 曾把 handoff JSON 留在仓库根导致归档被 blocked）。

# Verification expectations

- A2 的守卫必须有**破坏性自证**（构造"0–1 数据 + 整数容器"的用例，证明会被拦下，而不是恰好通过）；
- A3 的数值域比对需在真实产物上做（复用 2026-10-11 泰安市三份产物与指纹
  `26f57c12` / `4e5dc772` / `ff2f0ca1` 作为对照基线），且**必须打在 S2 真彩色**（现状 float64）；
  报告要给逐组 min/max/mean 的实测数字与 |Δ| 上界；
- A3 需要在**改动前后**各测一次：读旧产物 + 契约容器下的新产物，差值按逐像素读回比对
  （分块读，避免整份 4.6M 像素 × 3 波段一次性入内存）；
- 若涉及 PV bump，需给出"版本号替换回旧值即复现旧指纹"的证据（与 C4 的既有做法一致）；
- A6 的归一化要在**复制的副本**上证明（把既有产物复制到 worktree 本地再触发缓存命中），
  同时证明复制品容器 dtype 变化前后一致、只变 dtype 不改数值；
- A7 的清单必须逐条可逆（现状 / 改为 / 依据 / 回退四列，现状为逐字全文）；
- 验收由**独立 Verifier** 执行，实现方不自己宣布通过；
- 离线证据与在线证据分开留档：`tests/unit` 与 ruff 属离线层，真实产物数值域比对属在线层；
- 本轮 Shape 确认前**不做任何实现写入**（含不碰 `gis/`、`tests/`）。

# Decisions

- **D1（2026-10-18 用户拍板，Q1=b / Q2=b；已定结论，不再回头提问）**：
  `spec.dtype` = **数据语义提示**（当前不影响落盘）；新增 `container_dtype`（默认 `float32`）
  = **落盘容器契约**。理由：`dtype` 已参与指纹序列化（`gis/spec.py` 的 `fingerprint()` 与
  `to_dict()` 两处），选 (a)"声明即容器"必然触发全量指纹变更与缓存作废；且容器不应与计算语义耦合。
  字段注释与 docstring 必须显式写清这条语义分工。
- **D2（Q1/Q2 的必然推论）**：容器 dtype **不进指纹**、**不 bump `PROCESSING_VERSION`**
  （与 render/layout 同类：不改物理像素值）⇒ 旧 spec 指纹与缓存键原样保留；盘上"旧容器"与
  "新契约容器"共用同一指纹，两者不可由指纹区分 —— 这正是附条件 1 的来源，处置见 D4。
  实测（2026-10-18，geo 环境）：盘上既有产物 GeoTIFF 容器的现状是
  **S2 真彩色 `float64`（`taian_s2_truecolor.ff2f0ca1` 3 波段）、NDVI `float64`、
  DEM `float32`（`taian_dem_city.26f57c12`）、WorldCover `float32`**，NetCDF 侧统一 float32。
- **D3（默认值取 float32 的依据）**：默认与 NetCDF/xee 侧既有落盘一致（float32），
  故"未声明 `container_dtype`"等价于历史 NetCDF 行为；GeoTIFF 侧则由 float64 收敛到 float32，
  字节占用随之下降（本 change 只取"可预期"，不把体积下降当目标）。
- **D4（附条件 1 的处置：选 (i) 容器归一化）**：缓存命中的既有产物若容器 dtype 与契约不符，
  走**一次性归一化**（沿用 C15 `normalize_nodata_to_nan` 的 `.part` + 原子替换先例）并留痕；
  不删缓存、不另造基线、不重生成既有产物（(ii) 作废旧缓存会与"既有缓存保留不动"冲突）。
  归一化前先判容器相同则整体跳过（不重写，避免无谓的字节变化）。
- **D5（`docs/README.md` 是 gitignored 本地件，只存在于主工作区）**：附件条件 3 的判例注记
  **不就地改主工作区**（违反 worktree 隔离），而是交付 `local-changes.md` 待执行差异清单
  （四列：现状 / 改为 / 依据 / 回退），由归档轮在主工作区就地执行 —— 沿用 C13 已归档的载体先例
  （`docs/comet/archive/2026-10-08-c13-spec-consistency/local-changes.md`）。入库件 `README.md` 的 §9.7 直接改。
- **D6（序列化规则，红线 8）**：`to_dict()` 只在 `container_dtype != "float32"` 时写入该键；
  `from_dict()` 缺省即 float32。`fingerprint()` 的 payload **完全不加**该键。
  旧 spec 的 `to_dict` 输出与指纹逐字节不变（用 `b91c09c9c6451c16` 当场验证）。
- **D7（附条件 2 的实现选择：**拒绝**非法组合 + 补齐 collapse 提升）**：两条路都要 ——
  (1) 守卫在 `container_dtype` 为整数时**拒绝**（整数容器与 `nodata=NaN` 语义互斥，
      rasterio 会抛 "nodata value, nan, is beyond the valid range of its data type"）；
  (2) `collapse_mask_bands` 补整数 value band → float32 提升，封住 C15 记录在案的防御缺口。
  一并覆盖 `spec.dtype` 声明浮点却要求整数容器这类**自相矛盾声明**（静态校验），
  以及"实测数据含小数却要求整数容器"这类**实测证据**（写盘前有界采样校验）。
  ⚠ (2) 的语义是"封住 C15 已存在的缺陷路径"，不是"允许整数容器"：该路径处理的是 GEE 下载件、
  恒为浮点，提升只是让掩膜折叠不再硬失败；与 (1) 不冲突。
- **D8（不改 C15 已验收语义）**：`normalize_nodata_to_nan` 本身**零改动** —— 它已是
  "整数容器 → float32 提升"的正确侧，与"显式声明整数容器必须被拒绝"的方向相反但**不重叠**：
  前者处理 GEE 的整数哨兵，后者是用户在契约层显式声明整数容器时的合法性问题。
  按红线补充的授权边界，若最终评估认为必须改它的行为，**先停下问用户**。
- **D9（数据面隔离）**：本 worktree 的产物根缺省（`data/` 被 gitignore）指向 worktree 自己的空
  `data/`，因此 A3 的对照基线落在**主工作区只读复用**（`D:/DEV/geocode/data/derived/`，53 件，
  含 taian 五组），一切写操作走 worktree 本地；核对既有产物容器时**先复制到本地再动它**，
  不在主工作区就地归一化。
- **D10（不提问的理由）**：D5 的载体、D7 的两条路、D9 的隔离方式都在用户给定的授权范围内
  （"要么补齐提升、要么在守卫里拒绝该组合，二选一" + "既有缓存保留不动" + worktree 隔离），
  属实现选择；无新增用户决策项。

- **D11（Spec 验收引用的承载形态：标题内 → 正文独占行，实证后调整）**：
  Shape 首轮 `prepare-shape-confirmation` 生成了 **20 条**验收项 —— brief 的 A1–A10 之外，
  spec 的 10 个 Scenario 各被当作独立验收项（A11–A20），与 brief 的 A1–A10 **重复**。
  查 Runtime 实现（`native-acceptance.js` 的 `deriveSpecAcceptanceCriteria`）确认引用只在
  **正文行**上匹配：`/^(?:Acceptance|验收)\s*[:：]\s*(.*)$/`，识别后写入 `briefAcceptanceRef`
  并与 brief 条目合并；写在 `### Scenario:` **标题内**的 `（验收：A1）` 形态**不被识别**。
  故本 change 起把 spec 的引用改为正文独占行 `Acceptance: A<n>`，编号与 brief **互不重叠**
  （brief A1–A10 / spec A11–A20，沿用 c17 已建立的编号纪律）；
  `tests/unit/test_comet_spec_consistency.py` 的结构守卫（发布面规范 2）同步接受该形态，
  但仍禁止历史异类形态（正文独占一行的 `（验收：…）`）。属 `tests/unit` 的门禁对齐，
  不是"绕过守卫"：两种形态语义等价，Runtime 契约优先。

# Open questions

（无）

Q1 / Q2 已于 2026-10-18 由用户拍板（Q1=b、Q2=b，含三条附条件），结论见 Decisions D1–D10。
