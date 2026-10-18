---
generated_from_state_version: 14
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 3
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-18T07:41:17.898Z
- 摘要: 独立复核（fresh 上下文，未改任何被跟踪文件）：A1–A10 全部 passed，verdict=pass。核心数字：候选提交 3ab6d39 上 369 用例全绿（父提交 2511389 实测 352，同日同步 main 口径一致）、ruff 零告警、verify_all RUN 4/4 PASS；S2 真彩色/NDVI/10m 真彩色三组现状 float64 样本落 float32 后逐块全量比对 max|Δ| 分别为 2.975e-08 / 2.980e-08 / 5.951e-08（≤1e-6，DEM 两组 changed=False、Δ=0）；旧 spec 的 to_dict 与 fingerprint 相对父提交逐字节不变（b91c09c9c6451c16 / c9243efd40318c85 双双复算命中）；量纲守卫在写盘前以可读 SpecError 拦下「0–1 小数 + 整数容器」，绕过契约层后守卫仍生效；缓存命中经真实 emit_file/emit_array 入口归一 float64→float32 并留痕，容器一致时零字节重写。PROCESSING_VERSION 仍为 3、normalize_nodata_to_nan 等既存函数体相对父提交逐字节未变、docs/README.md 未在主工作区就地改动。残留风险均为未离线可达路径与工作树卫生类，见 risks。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: 同一 spec 的 `emit_file`（GeoTIFF）与 `emit_array`（NetCDF）容器 dtype 一致，且等于按 Q1 选定 语义推导出的期望值（例如 `container_dtype=float32` 时两边都是 float32）。 | 两出口共用 gis/container.py::resolve_container 单源解析。独立离线实测（自建 spec）：显式 float32 → GeoTIFF ds.dtypes=['float32'] 且 NetCDF B4=float32；显式 float64 → ['float64'] 且 float64；缺省不声明 → 两边 float32（且 to_dict 不带该键）。时序堆叠路径离线跑通 _merge_stack(container='float32')：输出 ['float32','float32']、nodata=NaN、值 0.125/0.5 保持，container=None 时仍为历史 float64。未执行：GeoTIFF 分块拼接（emit.py:793 由首个 tile 继承容器，tile 已在 _fetch_tif 落契约）与 NetCDF 分块写入（emit.py:1471 np.dtype(container)）为代码审查，需 GEE。 |
| A2 | passed | brief.md | A2: 量纲守卫生效：对"数据为 0–1 小数、却声明整数容器"的 spec，产物不得被静默量化 —— 必须报出可读错误（或按选定语义降级为浮点并明确告警），且有离线用例覆盖该判定。 | 自建破坏性输入（不读测试名）：guard_container_capacity([[0.0695,0,1],[0.5,nan,0.25]],'uint16') 抛 SpecError，消息含首个越界样值 0.0695、越界像元计数与「改法：float32/float64」；含 NaN + int32 亦拒；浮点容器与「整数数据+整数容器」放行（不误伤）。真实写盘路径：spec(dtype=uint16, container_dtype=uint16)（过静态校验）在 _apply_container_to_geotiff 抛 SpecError，被测文件 sha 与 mtime 不变、无 .part 残留＝写盘前拦下。monkeypatch 绕过契约层（resolve_container→'uint16'）后采样守卫仍拦下同一输入，证明拦阻来自实测采样而非只看声明。静态层另行拒 dtype=float32+container=uint16 的自相矛盾声明。 |
| A3 | passed | brief.md | A3: 既有 P0 样本的像素值不因本 change 变化（数值域校验：min/max/mean 与改动前一致， 容差 ≤ 1e-6）。Shape 已确认 Q2=b ⇒ 本 change 不 bump `PROCESSING_VERSION`、不预注册金指纹切换， A3 只按"数值域不变 + 金指纹不回退"判。实测必须打在 **S2 真彩色**那条（现状 GeoTIFF float64 → 契约 float32 才是真验证）；DEM（现状已 float32）与 WorldCover（同样 float32）只能作旁证，不得单独充数。 | 打在现状确为 float64 的 S2 真彩色与 NDVI（主工作区基线只读复制到 .cache，用本 change 的 rewrite_geotiff_container 落 float32 后逐块全量比对）：taian_s2_truecolor.ff2f0ca1（1769×936×3）max\|Δ\|=2.975e-08，Δmin=0、Δmax≤1.83e-08、Δmean≤1.27e-11；taian_s2_truecolor_10m.824afc80（17680×9355×3）max\|Δ\|=5.951e-08、Δmean≤6.02e-11；taian_s2_ndvi.4e5dc772 max\|Δ\|=2.980e-08。旁证（本就 float32，changed=False、Δ=0.0）：taian_dem_city.26f57c12 / taian_dem_county.3227ec35。五组 .nc 基线全为 float32＝契约，无归一动作。全部 \|Δ\| ≤ 1e-6（实测上界 5.951e-08），非有限像元计数不变。 |
| A4 | passed | brief.md | A4: 文档收敛：README §9.7 的"已知边界"条目不再声称 dtype 不可控，改为写清当前语义与取值规则； dev doc 的对应章节同步。 | 入库件 README.md 新增容器契约条目（默认 float32、dtype=数据语义提示、两出口按同一契约、容器不进指纹、整数容器被拒、缓存命中归一并留痕）；父提交 README.md 本来就没有「容器 dtype 不可控」的表述（git show 2511389:README.md 无 dtype/容器字样），需要收敛的「已知边界」原文只在 gitignored 的 docs/README.md §9.7，按 D5 以 local-changes.md 清单交付（§9.7 整段改写 + §3.1 字段表加行 + §11 判例注记）。主工作区 docs/README.md mtime 仍为 2026-10-11 22:12，未被就地改动。 |
| A5 | passed | brief.md | A5: 回归：离线用例全绿（含容器 dtype 与量纲守卫的新用例）、`uvx ruff@0.17.0 check` 零告警、 `tests/verify_all.py` 离线层 RUN 全 PASS。 | 独立复跑：python -m unittest discover -s tests/unit -t . → Ran 369 tests, OK (skipped=10)，含容器契约与量纲守卫新用例；uvx --offline ruff@0.17.0 check → All checks passed!；tests/verify_all.py 自跑一轮（先确认 127.0.0.1:6531 空闲）→ overall=pass，RUN 4 / PASS 4 / FAIL 0 / SKIP 9（跳过项均为需网络/GEE/前置产物，属离线层设计口径），报告 logs/verify_all_report.json。 |
| A6 | passed | brief.md | A6: 附条件 1 —— 旧产物容器不一致被**显式处置**：缓存命中时既有产物的容器 dtype 与当前契约不符 （如 S2 真彩色 .tif 为 float64、契约 float32）会走一次性归一（沿用 `normalize_nodata_to_nan` 的 .part + 原子替换先例）并留下可读进度记录；不接受"默认无视"。旧缓存不被删除，也不另造基线。 | 走真实出口入口（离线可达）实测：emit_file 缓存命中 float64 的 s2_beijing_test.b91c09c9.tif → 产物变 float32，留痕两条「既有产物容器不符契约（band1–3 float64 != 契约 float32）」「既有产物容器归一：容器 float64 → float32（按 container_dtype 契约）」，逐像元 max\|Δ\|=2.975e-08，无 .part，返回体指纹仍 b91c09c9c6451c16；再跑一次容器已一致 ⇒ sha/mtime 零变化、不再报归一（仅『已存在，跳过下载』）。.nc 侧走真实 emit_array：float64 的 .nc 归一为 float32 并留痕（B4/B3 float64→float32），已一致的 float32 基线 .nc 不重写。旧缓存未删除、未改名、未另造基线。 |
| A7 | passed | brief.md | A7: 附条件 3 —— 判例写进文档：`docs/README.md` §11 红线 3 下补注记，写明「容器精度截断 （float64→float32 等）若数值域在 1e-6 容差内不变，不视为改变像素输出；nodata/掩膜语义的归一化 改写同理（c15 判例）」。该文件是 gitignored 本地件，以**待执行差异清单**形式交付（四列：现状 / 改为 / 依据 / 回退），由归档轮在主工作区就地执行。 | local-changes.md 三项差异各含现状/改为/依据/回退四列，现状为逐字全文并带执行时行号。独立核对主工作区 docs/README.md：§9.7「已知边界」恰为 506–508 行、§3.1 dtype 行为 174、§11 红线 3 为 526（其下紧接红线 4，插入位明确），三处引文与磁盘逐字节相同。回退列给出可逆动作（还原整段 / 删新增行 / 删插入行），并在执行备忘里给出「先核行号再改」与备份建议。 |
| A8 | passed | brief.md | A8: 回归基线按同步 main 后的口径留档：全量离线用例 ≥ 352 条全绿（不得低于 352）， 并附 change 开始时的实测条数。 | 交付口径 369 条全绿（OK, skipped=10）≥ 352。基线口径独立复核：抽取父提交 2511389 完整树在 .cache 内跑同一命令 → Ran 352 tests, OK (skipped=10)，与 brief/spec 记载的 352 一致；增量 +17 条（test_container_dtype 15 + test_export_chunks 1 + test_spec_fingerprint 1），只增不减。 |
| A9 | passed | brief.md | A9: `container_dtype` 序列化按红线 8：仅在值 ≠ 默认 `float32` 时落键；旧 spec（未写该字段） 指纹逐字节不变，金指纹 `b91c09c9c6451c16` / `c9243efd40318c85` 不回退。 | 候选与父提交的 gis/spec.py 各自独立加载后比对同一 P0 spec（tests/unit/_helpers.py 本 change 零改动）：to_dict() 的 JSON 字节在 sort_keys 与插入序两种序列化下都完全一致（sha256 前 16 位 9e66a89759a7e150 / 324c199ba165155b 两边相同），container_dtype 键缺席；fingerprint() 两边都是 b91c09c9c6451c16＝金值，PV 置 2 时为 c9243efd40318c85＝金值，均不回退。显式 container_dtype='float64' 时 to_dict 落键、指纹不变、from_dict 往返不丢；fingerprint() 函数体不含 container_dtype。EXCLUDED_FIELDS 含 container_dtype 且不在 FINGERPRINT_FIELDS，两者并集恰好覆盖 dataclass 全部字段且无交叠。 |
| A10 | passed | brief.md | A10: 附条件 2 —— `collapse_mask_bands`（`gis/export_chunks.py`）补齐整数 value band → float32 提升，与 `normalize_nodata_to_nan` 口径统一：对整数容器 + nodata=NaN 的组合不再硬失败， 且有离线用例覆盖该判定（当前实现会抛 rasterio 越界 ValueError）。 | 破坏性自证：先复现 c15 失败形态（rasterio 以 dtype=int32 + nodata=nan 建文件 → ValueError 'nodata value, nan, is beyond the valid range of its data type, int32'）；再对 int32 两波段（值+掩膜）跑 collapse_mask_bands(path,1) → 返回 dtype=int32 / out_dtype=float32，落盘 ['float32']、nodata=NaN，掩膜=0 处为 NaN、值 3.0/1.0 保留，无 .part 残留；浮点输入行为不变（仍 float32，值 0.5 与 NaN 正确）。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| 离线单测全量（含容器契约与量纲守卫用例） | -m unittest discover -s tests/unit -t . | . | passed | 0 | 20511 ms |
| ruff 门禁（零告警） | --offline ruff@0.17.0 check | . | passed | 0 | 189 ms |
| verify_all 离线层（RUN 项全 PASS；需端口 6531 空闲） | tests/verify_all.py | . | passed | 0 | 27922 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- unit: passed — python -m unittest discover -s tests/unit -t . 369 tests OK (skipped=10)
- ruff: passed — uvx --offline ruff@0.17.0 check All checks passed!
- verify_all: passed — python tests/verify_all.py RUN 4 / PASS 4 / FAIL 0，SKIP 9（离线层）
- a3-effective-values: passed — python .cache/c18_a3_evidence.py 5 组 max|diff| ≤ 5.951e-08 ≤ 1e-6，报告 logs/c18_a3_container_effective_values.json
- 已知限制: A3/A6 的实测在 worktree 本地副本上做（主工作区 data/derived 只读复用）；主工作区基线未被本 change 改动。
- 已知限制: A3 是逐块全量读比对（非逐像素 sha256）；复现脚本 .cache/c18_a3_evidence.py 按项目纪律不入库。
- 已知限制: NetCDF 容器归一（_rewrite_ncdf_container）走 dask 流式写，本机未用 1.98 GB 级的 taian_s2_truecolor_10m.824afc80.nc 实测（只验证了小块 .nc）。
- 已知限制: collapse_mask_bands 的整数提升用合成 int32 输入自证；该形态在真实 GEE 下载件上当前不可达（source.build_image 恒 toFloat，c15 已记录）。

## 阻塞项

_无。_

## 风险与跳过的工作

- 5 条写盘路径中 3 条未离线执行（GeoTIFF 分块拼接、NetCDF 分块写入、GEE 下载本身），仅代码审查：前两条分别依赖 tile 已在 _fetch_tif 落契约（emit.py:793 继承首个 tile 的 dtype）与 np.dtype(container)（emit.py:1471），逻辑上收敛于同一契约，但没有运行证据。
- NetCDF 容器归一（_rewrite_ncdf_container）只在合成小块 .nc 上实测；1.98 GB 级的 taian_s2_truecolor_10m.824afc80.nc 未做归一跑（Builder 的 known_limits 亦有同样声明）。
- .cache/ 未被 .gitignore（只忽略 daemon.json/jobs.json 等固定三项），工作树里留有约 40 个未跟踪的过程脚本与 JSON（c18_*.py / c18_*.json / a3、a6 数据副本）；候选提交 3ab6d39 的树内干净（13 文件全为正式产物），不含这些文件 —— 但归档若按「工作树必须干净」判定需注意。
- Builder handoff 的 A3 note 写「逐波段 mean 逐位相同」与实测不符：实测 Δmean 最大 1.27e-11（其自己的 logs/c18_a3_container_effective_values.json 也记了 mean_baseline ≠ mean_contract）；验收判据是 |Δ| ≤ 1e-6，不影响结论，仅措辞过强。
- 主工作区 s2_beijing_test.b91c09c9.tif/.nc 的 mtime 是 2026-10-18 14:41/14:54（早于本候选提交 15:25，贴近 main 合流 14:37 与 c17 归档 14:47）；其容器仍为 float64＝c18 记录的「改前」状态，taian 五组与 docs/README.md 保持 10-11 未动 —— 无法归因到 c18 Builder，但主工作区 P0 两件确实在今日被动过。
- _merge_stack 的整数容器场景由 rasterio.open 的 ValueError 先失败（仍在写盘前，无产物落地），公开路径上可读报错来自 resolve_container；即该函数内的采样守卫对整数容器不可达（防御性），不构成 A2 失败。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-18T07:00:33.649Z |
| 2 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-18T07:26:10.903Z |
| 3 | 1 | 1 | pass | — | 独立复核（fresh 上下文，未改任何被跟踪文件）：A1–A10 全部 passed，verdict=pass。核心数字：候选提交 3ab6d39 上 369 用例全绿（父提交 2511389 实测 352，同日同步 main 口径一致）、ruff 零告警、verify_all RUN 4/4 PASS；S2 真彩色/NDVI/10m 真彩色三组现状 float64 样本落 float32 后逐块全量比对 max\|Δ\| 分别为 2.975e-08 / 2.980e-08 / 5.951e-08（≤1e-6，DEM 两组 changed=False、Δ=0）；旧 spec 的 to_dict 与 fingerprint 相对父提交逐字节不变（b91c09c9c6451c16 / c9243efd40318c85 双双复算命中）；量纲守卫在写盘前以可读 SpecError 拦下「0–1 小数 + 整数容器」，绕过契约层后守卫仍生效；缓存命中经真实 emit_file/emit_array 入口归一 float64→float32 并留痕，容器一致时零字节重写。PROCESSING_VERSION 仍为 3、normalize_nodata_to_nan 等既存函数体相对父提交逐字节未变、docs/README.md 未在主工作区就地改动。残留风险均为未离线可达路径与工作树卫生类，见 risks。 | 2026-10-18T07:41:17.898Z |



## 结论

独立复核（fresh 上下文，未改任何被跟踪文件）：A1–A10 全部 passed，verdict=pass。核心数字：候选提交 3ab6d39 上 369 用例全绿（父提交 2511389 实测 352，同日同步 main 口径一致）、ruff 零告警、verify_all RUN 4/4 PASS；S2 真彩色/NDVI/10m 真彩色三组现状 float64 样本落 float32 后逐块全量比对 max|Δ| 分别为 2.975e-08 / 2.980e-08 / 5.951e-08（≤1e-6，DEM 两组 changed=False、Δ=0）；旧 spec 的 to_dict 与 fingerprint 相对父提交逐字节不变（b91c09c9c6451c16 / c9243efd40318c85 双双复算命中）；量纲守卫在写盘前以可读 SpecError 拦下「0–1 小数 + 整数容器」，绕过契约层后守卫仍生效；缓存命中经真实 emit_file/emit_array 入口归一 float64→float32 并留痕，容器一致时零字节重写。PROCESSING_VERSION 仍为 3、normalize_nodata_to_nan 等既存函数体相对父提交逐字节未变、docs/README.md 未在主工作区就地改动。残留风险均为未离线可达路径与工作树卫生类，见 risks。
