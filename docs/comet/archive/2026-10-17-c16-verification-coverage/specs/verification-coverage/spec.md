# Capability：verification-coverage —— 在线冒烟覆盖缺口与仓库卫生

GeoCode 的验证面由两层构成：离线层（`tests/unit`，受 AST 禁网守卫约束）与在线层（`tests/smoke_*.py`，
需真实 GEE 网络与认证）。本 capability 规定：**每一个可在 GEE 上取数的预设都必须有在线冒烟覆盖**——
否则"离线全绿、真跑必挂"的缺陷会持续潜伏（2026-10-11 的 DEM 装载缺陷即为此类）。同时规定两处仓库
卫生：P0 样本的单一事实源方向、以及环境探测对已知崩溃路径的覆盖。

## 在线预设覆盖

### Scenario: 默认冒烟清单覆盖全部可取数预设（验收：A1）

验收：A1

`tests/smoke_presets.py` 的默认预设定必须包含 DEM（`COPERNICUS/DEM/GLO30`）与 GSW
（`JRC/GSW1_4/GlobalSurfaceWater`），与既有 7 条预设一同三出口执行。新增条目必须同时支持按短名
单独点名（`dem` / `gsw`），以符合"先串行试点一条再全跑"的既有纪律。

### Scenario: DEM 冒烟校验高程语义（验收：A2）

验收：A2

DEM 项的校验不得停留在"三出口跑通"：须断言产物的高程语义——存在有效像素、非恒定值、
极值落在合理区间，且三出口（file/array/map）指纹一致。

校验跑在默认清单共用的北京小 AOI（116.30–116.40E / 39.95–40.02N）上，该 AOI 的 GLO-30 实测
极值为 min ≈ 24.45 m / max ≈ 95.57 m / mean ≈ 51.05 m（2026-10-18 实测），故合理区间断言取
[-500, 9000]（覆盖地球陆地高程域，能抓住量纲错误与"跑通但内容错"）。GLO-30 的高程语义另以
2026-10-11 泰安实测值最高 ≈ 1531.9 m 作旁证（2026-10-18 在本机复现为 1531.93 m），该 AOI 不进入
默认清单，仅作为锚点合理性依据。

### Scenario: GSW 冒烟校验取值域语义（验收：A3）

验收：A3

GSW 项的校验须断言 `occurrence` 的取值域（0–100）与三出口指纹一致，避免"接口跑通但内容错"。
若某分波段在该 AOI 上语义受限（如 `seasonality` 取值稀疏），以可稳定复现的断言为准并在
smoke 输出中说明。

取值域断言按各波段的**全域**书写，不绑定本 AOI 的观测极值（本 AOI 实测：`occurrence` 0–89、
`seasonality` 1–12、`max_extent` 0–1），以免换个 AOI 就产生假失败；`max_extent` 是二值掩膜
（0/1），一并断言其取值域。GSW 在 GEE 上是单景 `Image`，走 `ee.Image(asset)` 单景分支，
不需要也不得补 `collection_only`（与 DEM 的 26076 片集合不同）。

## 单一事实源

### Scenario: P0 样本只有一处定义（验收：A4）

验收：A4

`tests/unit/test_presets.py` 不得再持有 `P0_SPEC_DICT` / `make_p0_spec` 的本地拷贝，一律从
`tests/unit/_helpers.py` 取值（该文件是 P0 样本与金指纹的单一事实源）。全量离线用例保持全绿，
且数量不少于本 change 开始时。

## 环境探测覆盖

### Scenario: preflight 覆盖 numpy 相关矩阵崩溃路径（验收：A5）

验收：A5

`gis/preflight.py` 新增检查：`np.cov` / `np.corrcoef` 在本机是否可用。探测**必须在子进程**中执行
（该路径在本机触发原生致命退出 0xc06d007f、退出码 127、无 traceback），父进程不得崩溃。
不可用时检查项报失败并给出：现象（原生退出码）、影响（任何计算相关矩阵的分析脚本会静默死）、
已验证的规避写法（手算 z-score 公式或 `scipy.stats.pearsonr`）。可用时检查项通过。

**探测输入必须是浮点数组**（如 `np.cov(np.random.rand(2, 200))`）：2026-10-18 实测，本机崩溃仅在
浮点 ndarray 输入下复现（3/3 次退出码 127），而整数 ndarray 与 Python list 输入正常返回 —— 用后两者
探测会得到假阴性，使检查项在本机误报通过。

检查项**如实反映子进程探测结果**（2026-10-18 用户决定）：当前环境崩溃则报失败并给规避写法，
环境修复后自动报通过；不保留"即使可用也固定告警"的历史语义。

## 回归

### Scenario: 门禁与离线基线不回退（验收：A6）

验收：A6

实现后 `uvx ruff@0.17.0 check` 零告警；`tests/verify_all.py` 离线层 RUN 项全 PASS；
新增的两条在线预设项在联网环境下单独复跑通过并留档。`tests/unit` 的离线守卫不被破坏
（preflight 的探测不得引入 ee / requests / socket 依赖到 tests/unit）。
