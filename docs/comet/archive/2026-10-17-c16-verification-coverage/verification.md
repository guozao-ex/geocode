---
generated_from_state_version: 15
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 2
- 迭代: 2
- 验证器尝试次数: 2
- 完成时间: 2026-10-17T17:58:39.575Z
- 摘要: 6 项验收全部 passed，verdict=pass。A4/A5 离线：268 tests OK（≥257）、test_presets 本地拷贝已删改走 _helpers、check_numpy_linalg 子进程+浮点数组探测本机返回 3228369023 并给两条规避写法且父进程不崩。A1/A2/A3 联网：dem 与 gsw 均短名单点跑通 1 条 × 3 出口，DEM min=24.45/max=95.57/mean=51.04、有效 74209/75194，指纹 bcfc1a7ea425d205；GSW occurrence[0,89]/seasonality[1,12]/max_extent[0,1] 全部在域内，指纹 e5eeac3849643dd4。A6：ruff All checks passed、verify_all RUN 3 PASS 3 FAIL 0（6531 空闲已核验）。GSW TIF 8.8KB 的体积疑点已用 rasterio/xarray 逐波段掩膜比对排除，为 1.2% 稀疏有效像素所致，三波段掩膜与 NC 100% 吻合。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: `tests/smoke_presets.py` 的默认清单包含 DEM 与 GSW，且两条都能按短名单独复跑 （`python tests/smoke_presets.py dem` / `gsw` 只跑该条）；三出口在真实 GEE 数据上全部通过。 | PRESETS 末尾含 dem/gsw 两条（tests/smoke_presets.py:66-79），selected() 按 name 短名匹配、未知名 exit 2 并列可选清单（:336-345）。实跑 python tests/smoke_presets.py dem → 「✅ 全部通过：1 条预设 × 3 出口」DEM_EXIT=0；python tests/smoke_presets.py gsw → 「✅ 全部通过：1 条预设 × 3 出口」GSW_EXIT=0。真实 GEE 联网，三出口 file/array/map 全过。 |
| A2 | passed | brief.md | A2: DEM 冒烟校验数值语义而非仅"跑通"：断言高程量纲与取值域（非恒定值、非全 NaN、极值落在合理区间）， 且与 GLO-30 的高程语义一致（可复用 2026-10-11 实测：泰安泰山玉皇顶一带极值 ≈ 1531.9 m）。 | check_dem() 断言四项语义（非全 NaN、非恒定值、极值落在 [-500,9000]、与 GLO-30 语义一致），非仅跑通。实测输出「DEM 高程：min=24.45 max=95.57 mean=51.04 有效像素=74209/75194」+「✅ 高程取值域合理（[-500.0, 9000.0] 内）、非恒定、有有效像素」；三出口指纹一致 bcfc1a7ea425d205。数值与量纲合理（北京 AOI 数十米量级）。 |
| A3 | passed | brief.md | A3: GSW 冒烟校验取值域语义（如 `occurrence` ∈ [0, 100]），并断言三出口指纹一致。 | check_gsw() 按全域语义域断言而非绑定本 AOI 极值：occurrence [0,89]⊂[0,100] ✅、seasonality [1,12]⊂[0,12] ✅、max_extent [0,1]⊂[0,1] ✅；「✅ 3 个波段的取值域全部合理」；三出口指纹一致 e5eeac3849643dd4。 |
| A4 | passed | brief.md | A4: `tests/unit/test_presets.py` 不再包含 `P0_SPEC_DICT` / `make_p0_spec` 的本地拷贝（从 `tests/unit/_helpers.py` 取值），全量离线用例保持全绿（数量不少于 change 开始时）。 | git diff HEAD -- tests/unit/test_presets.py 显示本地 P0_SPEC_DICT 与 make_p0_spec 定义（32 行）已全部删除，改为 from tests.unit._helpers import (GOLDEN_FINGERPRINTS, expected_p0_fingerprint, make_p0_spec)。离线全量 python -m unittest discover -s tests/unit -t . → Ran 268 tests in 17.5s, OK (skipped=10)，268 ≥ 257（change 起点），数量未减少。 |
| A5 | passed | brief.md | A5: `gis/preflight.py` 新增的检查能识别本机环境（`np.cov`/`np.corrcoef` 不可用）并输出人话原因与 规避写法；探测走子进程，**父进程不得崩溃**；在正常环境（可用时）该检查报通过。 - 探测用例必须是**浮点数组**（如 `np.cov(np.random.rand(2, 200))`）：整数/list 输入在本机不触发崩溃， 用它探测会得到假阴性； - 本机当前期望结果：退出码 127 + 无 traceback → 检查项报失败并给出规避写法（手算 z-score / `scipy.stats.pearsonr`）； - 口径已定（D7）：检查项如实反映子进程探测结果，环境修复后自动转为通过态。 | ①探测走子进程：subprocess.run([python,'-c',_NUMPY_PROBE_SRC], capture_output, timeout=60)；②探测输入为浮点数组：rng.random((2,200)) 再 np.cov/np.corrcoef（注释明写「浮点数组：本机崩溃的必要条件」），非整数/list。实跑 check_numpy_linalg() → ok=False code=numpy-linalg-broken returncode=3228369023（=0xC06D007F），reason 含 z-score:True、pearsonr:True 两条规避写法；父进程正常退出（PYEXIT=0，全量 268 tests 亦 OK），证明未波及父进程。离线守卫未破坏：tests.unit.test_offline_guard Ran 1 test OK。 |
| A6 | passed | brief.md | A6: 回归：`uvx ruff@0.17.0 check` 零告警；`tests/verify_all.py` 离线层 RUN 项全 PASS；新增的在线 检查项在联网环境下"单独复跑"通过（留档）。 | uvx ruff@0.17.0 check → 「All checks passed!」 exit 0。6531 端口核验无 LISTENING（仅 TIME_WAIT 残留）后跑 python -u tests/verify_all.py → 「== 汇总：RUN 3（PASS 3 / FAIL 0） · SKIP 9 ==」「== verify_all 全部通过（含 SKIP） ==」VERIFY_ALL_EXIT=0；preflight 维度 tests-unit=pass。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| 离线单测全量（geo 环境） | -m unittest discover -s tests/unit -t . | . | passed | 0 | 19322 ms |
| ruff 门禁 | ruff@0.17.0 check | . | passed | 0 | 215 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- offline-unit: passed — python -m unittest discover -s tests/unit -t . → Ran 268 tests, OK (skipped=10)
- ruff: passed — uvx ruff@0.17.0 check → All checks passed!
- smoke_presets-dem-gsw-online: passed — 单点名 dem / gsw 各 3 出口全过；默认全量 9 条 × 3 出口全过（真实 GEE 联网）
- verify_all-offline: passed — RUN 3（PASS 3 / FAIL 0）· SKIP 9 · EXIT=0
- 已知限制: 在线项（smoke_presets dem/gsw）依赖真实 GEE 网络与认证；本 worktree 的 geocode.json 版本库内是占位符 YOUR_GEE_PROJECT，验证时用 GEE_PROJECT 环境变量注入真实 project id，未写入任何被跟踪文件。
- 已知限制: COPERNICUS/DEM/GLO30 已被 GEE 标记 deprecated（官方指向 GLO30_2024_1）；本 change 按 brief 非目标不改预设资产，运行时会有 DeprecationWarning。
- 已知限制: 本机 numpy linalg 崩溃仍未修复（属 conda 环境问题，brief 非目标）；preflight 检查项当前报失败是如实反映。
- 已知限制: Runtime 检查必须用 geo 环境的绝对解释器路径（C:/ProgramData/miniforge3/envs/geo/python.exe）；系统 Python 3.12.10 缺 geopandas/ee/xarray，直接跑 tests/unit 会有 40 个 ModuleNotFoundError。

## 阻塞项

_无。_

## 风险与跳过的工作

- GSW TIF 仅 8.8 KB 而 NC 0.92 MB：已独立核实为稀疏特性而非内容缺失 —— rasterio 读 TIF 与 xarray 读 NC 逐波段比对，occurrence 有效 901/75194=1.2%、seasonality 805/75194=1.1%、max_extent 74209/75194=98.7%，三波段掩膜与 NC 逐像素完全一致（differ=0），有效像素最大差 3.815e-06（occurrence，float32 精度），另两波段 0。文件小的原因是 occurrence/seasonality 大面积 -inf nodata 高度可压缩。
- TIF rasterio 的 masked 读法用 np.isfinite(tn.filled(nan)) 比较会因 NaN!=NaN 误报 masks_equal=False；已改用 np.isfinite(raw) 原值比对确证一致，非产物问题。
- verify_all 的 RUN 层口径未改动（3 RUN / 9 SKIP），多数 smoke 项仍为 SKIP 而非实际在线执行；A6 的「新增在线检查项单独复跑」由 A1 的 dem/gsw 单点名实跑覆盖，不是 verify_all 自身跑出的。
- presets 维度在 verify_all 中 tests-unit=pass, smoke-presets=skip —— 全量 9 条 × 3 出口未在本轮复跑，仅 dem/gsw 两条单点名实跑（brief 要求的正是这两条）。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-17T17:30:15.169Z |
| 2 | 1 | 0 | recovery | — | Builder handoff Runtime checks failed: offline-unit | 2026-10-17T17:47:53.841Z |
| 2 | 2 | 1 | execution-error | — | 独立 Verifier subagent（209366db-0015-4aff-8a06-0fab231f8093）在提交结果前执行失败，未留下任何收尾消息，Runtime 侧无 verifier-started 之外的进度记录，stateVersion 仍停在 10 / next_action=await-verifier-result。 | 2026-10-17T17:54:39.000Z |
| 2 | 2 | 2 | pass | — | 6 项验收全部 passed，verdict=pass。A4/A5 离线：268 tests OK（≥257）、test_presets 本地拷贝已删改走 _helpers、check_numpy_linalg 子进程+浮点数组探测本机返回 3228369023 并给两条规避写法且父进程不崩。A1/A2/A3 联网：dem 与 gsw 均短名单点跑通 1 条 × 3 出口，DEM min=24.45/max=95.57/mean=51.04、有效 74209/75194，指纹 bcfc1a7ea425d205；GSW occurrence[0,89]/seasonality[1,12]/max_extent[0,1] 全部在域内，指纹 e5eeac3849643dd4。A6：ruff All checks passed、verify_all RUN 3 PASS 3 FAIL 0（6531 空闲已核验）。GSW TIF 8.8KB 的体积疑点已用 rasterio/xarray 逐波段掩膜比对排除，为 1.2% 稀疏有效像素所致，三波段掩膜与 NC 100% 吻合。 | 2026-10-17T17:58:39.575Z |



## 结论

6 项验收全部 passed，verdict=pass。A4/A5 离线：268 tests OK（≥257）、test_presets 本地拷贝已删改走 _helpers、check_numpy_linalg 子进程+浮点数组探测本机返回 3228369023 并给两条规避写法且父进程不崩。A1/A2/A3 联网：dem 与 gsw 均短名单点跑通 1 条 × 3 出口，DEM min=24.45/max=95.57/mean=51.04、有效 74209/75194，指纹 bcfc1a7ea425d205；GSW occurrence[0,89]/seasonality[1,12]/max_extent[0,1] 全部在域内，指纹 e5eeac3849643dd4。A6：ruff All checks passed、verify_all RUN 3 PASS 3 FAIL 0（6531 空闲已核验）。GSW TIF 8.8KB 的体积疑点已用 rasterio/xarray 逐波段掩膜比对排除，为 1.2% 稀疏有效像素所致，三波段掩膜与 NC 100% 吻合。
