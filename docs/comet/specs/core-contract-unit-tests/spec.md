# Capability：core-contract-unit-tests —— 核心契约离线单元测试基线

## 定位

`tests/unit/` 下的离线单元测试套件，验证三出口共享的产物契约层（spec / grid / 指纹 / crs_rules）的行为。它是后续所有 change（C2–C8）的 Verifier 回归基线：任何触碰契约层的改动，先过这套测试。

被测模块：`gis/spec.py`、`gis/grid.py`、`gis/crs_rules.py`（三者均只依赖 Python 标准库；测试代码不得导入 `ee` 或任何网络库）。

## 行为规格

### Scenario: 离线运行全绿（验收：A1）

在 geo env（`C:\ProgramData\miniforge3\envs\geo\python.exe`）、断网条件下执行单测套件（`python -m unittest discover -s tests/unit` 或等价 pytest 命令），全部用例通过。测试代码只导入标准库、被测的 gis 模块与 pyproj（D7 授权的 CRS 元数据查询，且为 `compute_grid` 生产实现的既有依赖）；**不导入 ee 或任何网络库**。

### Scenario: 运行时长（验收：A2）

全套用例在本机 geo env 下运行时长 < 10 秒。

### Scenario: 指纹稳定性（验收：A3）

- 仅 `note` / `tags` / `id` / `render` 不同的两个 `ArtifactSpec`，`fingerprint()` 返回值相同；
- 同一 spec 重复调用 `fingerprint()` 结果一致；
- `PROCESSING_VERSION` 变化（以等价手段模拟版本变化）后指纹变化。

### Scenario: 指纹向后兼容守卫（验收：A4）

守卫测试显式声明两组名单：指纹白名单（asset / band_expr / crs / scale / aoi / dtype / bands / time_range / reducer，外加版本分量 `_processing_version`）与排除名单（id / note / tags / render / nodata——nodata 与其余元信息字段一样被 `spec.fingerprint()` 的 payload 现状排除；若未来认定 nodata 影响像素输出，须按红线 8 移入白名单并评估历史缓存影响），并断言 `ArtifactSpec` 的 dataclass 字段全集被两名单之并集覆盖。未来新增字段而未显式决定其指纹归属时，守卫测试失败，报错消息提示「决定入指纹白名单或加入排除名单」。

### Scenario: 契约行为覆盖（验收：A5）

- `validate(exit=...)`：array / file 出口要求 crs + scale + aoi，map 出口仅要求 aoi；缺失时报错消息含缺失字段名与修复提示；非法 dtype / reducer / time_range / aoi 均被拒绝；
- `with_()` 返回新实例且原 spec 不变；`to_dict` / `from_dict` JSON 往返还原全部字段；`slug` 输出安全文件名；
- `compute_grid`：同一 spec 多次计算结果一致（crs / transform / shape 相同），`Grid.matches()` 对一致参数返回真、不一致参数返回假；
- `crs_rules`：PCS / GCS 判定与 CGCS2000 关键映射正确。

### Scenario: 现有资产保护（验收：A6）

`tests/smoke_*.py` 保持原样；`gis/` 无行为性修改。若测试暴露生产缺陷，最小修复须逐条记录于 Builder 交接，且改变像素输出的修复必须 `PROCESSING_VERSION += 1`（红线 3）。
> ⚠️ 本条为 C1 交付时的范围声明，已被后续 change 修订：`tests/smoke_array_chunking.py`、`tests/smoke_map_renderers.py`、`tests/smoke_timeseries.py` 经 `c10-review-patches`（2026-10-08）更新；`gis/preflight.py` 的探测行为经 `c12-preflight-endpoint-probe`（2026-10-08）更新。见 `docs/comet/specs/README.md`。
