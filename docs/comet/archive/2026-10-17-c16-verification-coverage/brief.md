# Outcome

把"**离线全绿、真跑必挂**"的覆盖缺口补上，并收掉两处仓库卫生问题。

背景（2026-10-11 首次真实数据运行实测）：`COPERNICUS/DEM/GLO30` 预设从未被真跑过 —— 它在 GEE 里
是 26076 片 1° 瓦片的 ImageCollection，预设缺装载标志，按单景走直接报
`Asset 'COPERNICUS/DEM/GLO30' is not an Image`。它能潜伏至今的直接原因是：**在线冒烟
`smoke_presets.py` 的默认预设定只有 7 条，不含 DEM 与 GSW**，于是 257 条离线用例全绿而真跑第一枪就挂
（该装载缺陷已在提交 `691014b` 修掉，但覆盖缺口仍在）。

同时收两处卫生问题：`tests/unit/test_presets.py` 里存在一份 `make_p0_spec` / `P0_SPEC_DICT` 的本地
拷贝（与 `tests/unit/_helpers.py` 的单一事实源重复，属同类漂移隐患）；`gis/preflight.py` 缺少对本机
已实测崩溃的 numpy 相关矩阵路径（`np.cov` / `np.corrcoef` 原生致命退出）的探测。

# Scope

- **在线冒烟纳入 DEM 与 GSW**：`tests/smoke_presets.py` 的默认预设定加入
  `COPERNICUS/DEM/GLO30`（30m，单波段）与 `JRC/GSW1_4/GlobalSurfaceWater`（30m，三分波段），
  并为两者各写一种校验 check：
  - DEM：高程量纲与取值域（真实 AOI 上与 GLO-30 语义一致；非恒定值、非全 NaN，极值落在合理区间）；
  - GSW：`occurrence` 的取值域（0–100）等语义断言，避免"跑通但内容错"；
  两条预设都必须能单独点名复跑（`python tests/smoke_presets.py dem` / `gsw`）。
- **消除 `make_p0_spec` 重复**：`tests/unit/test_presets.py` 的本地 `P0_SPEC_DICT` / `make_p0_spec`
  改为从 `tests/unit/_helpers.py` 取值（该文件自述为"金指纹与 P0 样本的单一事实源"），全量用例保持绿。
- **preflight 增加 numpy 相关矩阵可用性检查**：探测 `np.cov` / `np.corrcoef` 是否可用，**必须在子进程
  里探测**（该路径在本机会让父进程原生崩溃，退出码 127、无 traceback），失败时检查项给出人话原因与
  已验证的规避写法（手算 z-score 公式 / `scipy.stats.pearsonr`）。

## 目录结构

### 新建

无

### 修改

- `tests/smoke_presets.py` — 新增 DEM / GSW 两条预设项与各自语义 check 分支（`check_dem` / `check_gsw`），并支持 `dem` / `gsw` 短名独立点名复跑；既有 7 条的校验语义不动。
- `tests/unit/test_presets.py` — 移除文件内的 `P0_SPEC_DICT` / `make_p0_spec` 拷贝（第 34–57 行），改从 `tests/unit/_helpers.py` 导入；全量用例数量不减少。
- `gis/preflight.py` — 新增一条环境检查（子进程探测 numpy 相关矩阵路径），失败时给出人话原因与已验证的规避写法；纳入 `probe_env()` 消费链。

### 删除

无（`test_presets.py` 的本地 P0 拷贝是文件内定义的移除，计入「修改」）。

### 明确不建

- 不改 `tests/verify_all.py` 的 RUN 层口径（另有 change c17 处理）；
- 不修改 conda 环境本身（numpy/OpenBLAS 的安装问题不在本仓库范围内，本 change 只做探测与提示）。

# Non-goals

- 不调整 DEM / GSW 预设的分辨率、时间窗口或波段语义（本次只补覆盖与校验）；
- 不新增网络/在线检查进 `verify_all`，不引入 `--online` 开关；
- 不修 numpy 环境（不在仓库范围内），也不把 geocode 的代码改成"绕开 numpy"；
- 不改既有 7 条预设的校验语义。

# Acceptance examples

- A1: `tests/smoke_presets.py` 的默认清单包含 DEM 与 GSW，且两条都能按短名单独复跑
  （`python tests/smoke_presets.py dem` / `gsw` 只跑该条）；三出口在真实 GEE 数据上全部通过。
- A2: DEM 冒烟校验数值语义而非仅"跑通"：断言高程量纲与取值域（非恒定值、非全 NaN、极值落在合理区间），
  且与 GLO-30 的高程语义一致（可复用 2026-10-11 实测：泰安泰山玉皇顶一带极值 ≈ 1531.9 m）。
- A3: GSW 冒烟校验取值域语义（如 `occurrence` ∈ [0, 100]），并断言三出口指纹一致。
- A4: `tests/unit/test_presets.py` 不再包含 `P0_SPEC_DICT` / `make_p0_spec` 的本地拷贝（从
  `tests/unit/_helpers.py` 取值），全量离线用例保持全绿（数量不少于 change 开始时）。
- A5: `gis/preflight.py` 新增的检查能识别本机环境（`np.cov`/`np.corrcoef` 不可用）并输出人话原因与
  规避写法；探测走子进程，**父进程不得崩溃**；在正常环境（可用时）该检查报通过。
  - 探测用例必须是**浮点数组**（如 `np.cov(np.random.rand(2, 200))`）：整数/list 输入在本机不触发崩溃，
    用它探测会得到假阴性；
  - 本机当前期望结果：退出码 127 + 无 traceback → 检查项报失败并给出规避写法（手算 z-score / `scipy.stats.pearsonr`）；
  - 口径已定（D7）：检查项如实反映子进程探测结果，环境修复后自动转为通过态。
- A6: 回归：`uvx ruff@0.17.0 check` 零告警；`tests/verify_all.py` 离线层 RUN 项全 PASS；新增的在线
  检查项在联网环境下"单独复跑"通过（留档）。

# Constraints and invariants

- `tests/unit` 受离线守卫约束（AST 禁网），因此 preflight 的 numpy 探测必须走**子进程**
  且不得引入 ee / requests / socket；
- 在线冒烟依赖 `geocode.json`（本地件，含真实 GEE project id）与真实网络；DEM 三出口需要
  DEM 预设的 `tile_mosaic` 装载路径（已由 `691014b` 提供）；
- smoke_presets 的三出口校验与既有 check 同构（指纹一致 + 语义断言），不引入新框架；
- 金指纹 `b91c09c9c6451c16` 与 P0 样本产物不得回退。
- 验证入口纪律（2026-10-18 实测）：`tests/verify_all.py` / `smoke_all.py` / `smoke_tui.py` 自行启停
  127.0.0.1:6531 的 daemon 且无引用计数，跑前须确认端口空闲（本次已核：空闲）；离线单测与
  `smoke_presets.py <短名>` 不启 daemon，可随时跑。
- Python 环境：必须用 geo 环境 `/c/ProgramData/miniforge3/envs/geo/python.exe`（numpy 2.5.3 / ee 1.7.46 /
  python 3.12.14）；系统 Python 3.12.10 未装 ee，跑冒烟会直接 ImportError。
- GEE 认证：`~/.config/earthengine/credentials` 存在且有效；但 `geocode.json` 是**被 git 跟踪**的文件且
  版本库里是占位符 `YOUR_GEE_PROJECT`（16 字符），真实 project id（22 字符）只在本机工作树中。
  故本 worktree 里直接跑 GEE 会报 `Project 'projects/YOUR_GEE_PROJECT' not found`；联网验证时用
  `GEE_PROJECT` 环境变量注入（`geoenv.gee_project()` 优先读环境变量），**不得把真实 project id 写进任何被跟踪的文件**。
- 离线基线（本次 change 开始时实测）：`python -m unittest discover -s tests/unit -t .` → 257 tests，OK（10 skipped）。
- 本 worktree 落后 main 7 个提交（HEAD=691014b7，main=acc6c16）；经核实这 7 个提交与本次三个目标文件
  （`tests/smoke_presets.py` / `tests/unit/test_presets.py` / `gis/preflight.py`）**零重叠**，无同步冲突风险。

# Decisions

- D1：DEM / GSW 的校验采用「取值域 + 语义断言」而非仅"跑通"，因为本次缺陷正是"跑得通但装载方式错"；
- D2：preflight 的 numpy 探测放**子进程**执行 —— 该路径在本机直接杀掉进程，父进程内探测无法收尾；
- D3：`test_presets.py` 的 P0 样本改从 `_helpers` 取，而不是让 `_helpers` 反向依赖 —— 保持单一事实源方向。
- D4（2026-10-18 Shape 核实）：两条预设**共用既有北京小 AOI**（116.30–116.40E / 39.95–40.02N，与 `tests/smoke_presets.py:34`
  的 `AOI` 一致），不新增地理锚点。DEM 锚点改用本 worktree 实测值而非泰安：北京 AOI 上 GLO-30 实测
  `min≈24.45 m / max≈95.57 m / mean≈51.05 m`（合理区间断言 = 存在有效像素、非恒定、极值落在 [-500, 9000]）；
  泰安 1531.9 m 的记载已在本机复现（`max=1531.93`，AOI 117.06–117.16E / 36.22–36.29N），但换 AOI 会改动
  smoke 的既有地理约定，留作 A2 的旁证而不进默认清单。
- D5（2026-10-18 Shape 核实）：GSW 在 GEE 上是**单景 Image**（`ee.data.getInfo` → `type=IMAGE`），
  而 DEM 是 `IMAGE_COLLECTION`（26076 片）。故 GSW 预设**不应**补 `collection_only` —— 现状走 `ee.Image(asset)`
  单景分支即正确，无需装载改动。这同时解释了为什么只有 DEM 曾报 `is not an Image`。
- D6（2026-10-18 Shape 核实）：GSW 三波段在本 AOI 的实测取值域为 `occurrence 0–89`、`seasonality 1–12`、
  `max_extent 0–1`（occurrence / seasonality 是 int8、max_extent 是 uint8；计算图统一 `toFloat()` 后落浮点）。
  A3 的取值域断言按**全域**写（`occurrence ∈ [0,100]`、`max_extent ∈ [0,1]`），不绑定本 AOI 的观测极值，
  避免换个 AOI 就假失败。
- D7（2026-10-18 用户决定，Q1=A）：preflight 的 numpy 检查**如实反映子进程探测结果** —— 当前环境实测崩溃即报
  失败并给规避写法，将来环境修复则自动报通过；不保留「即使可用也固定告警」的历史语义。探测输入强制用
  **浮点数组**（整数 / list 输入在本机不触发崩溃，会让检查项假阴性误报通过）。

# Verification expectations

- A2 / A3 的校验必须在**真实 GEE 联网**条件下留档（这正是本次缺口所在），不接受仅离线 mock；
- A5 的探测需要在**本机现状**（已崩溃环境）下实测：检查项应报可用性失败 + 规避写法，且父进程正常退出；
- 覆盖缺口闭环的证据：DEM / GSW 两条在独立点名复跑与全量默认清单两种方式下都通过。

# Open questions

（无）

Q1 已于 2026-10-18 由用户决定，结论见 Decisions D7。
