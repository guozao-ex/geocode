# 目标

为核心契约模块建立**离线单元测试基线**（开发文档 §9.2 Change 台账 C1）：覆盖 `gis/spec.py`（ArtifactSpec / RenderSpec 校验与指纹）、`gis/grid.py`（确定性网格）、`gis/crs_rules.py`（CRS 纪律）。测试不碰网络、不触发 GEE 认证、秒级完成，作为后续所有 change（C2–C8）的 Verifier 回归地基。

三个被测模块均只依赖 Python 标准库（已核实 import），离线可测性成立。

# 范围

## Source coverage

需求来源：`docs/README.md`（用户 2026-10-06 指定为项目开发文档）。C1 的覆盖边界 = 文档中与 C1 直接相关的条目及其必要依赖（被测契约的定义章节）：

| 来源条目与位置 | 读取状态 | 需要保留的内容 | Spec 位置 | 验收 ID | 覆盖状态 | 理由或替代关系 |
|---|---|---|---|---|---|---|
| S1：§9.2 台账 C1 行 | complete | spec/grid/指纹/crs_rules 离线单测；不碰网络、秒级完成；覆盖红线关键断言（含指纹稳定性与向后兼容） | spec.md 定位 + 全部场景 | A1、A2、A3、A4、A5 | covered | 当前有效需求 |
| S2：§9.2 决定 1（单测基线先行） | complete | C1 作为后续所有 change 的 Verifier 回归基线 | spec.md 定位 | A1 | covered | 当前有效需求 |
| S3：§9.2 决定 3（指纹向后兼容） | complete | 新增 spec 字段不得改变旧 spec 指纹；C1 提供单测断言 | spec.md 指纹向后兼容守卫场景 | A4 | covered | 当前有效需求 |
| S4：§3.3 指纹与缓存（含 2026-10-06 向后兼容段） | complete | 指纹 = 决定输出因素的白名单哈希 + PROCESSING_VERSION；元信息字段排除 | spec.md 指纹稳定性场景 | A3、A4 | covered | 必要依赖（被测契约的定义） |
| S5：§11 红线 1/2/3/8 | complete | 红线 2（网格唯一来源）/ 3（PROCESSING_VERSION 纪律）/ 8（指纹兼容）做机器断言 | spec.md 网格、指纹场景 | A3、A4、A5 | covered | 必要依赖；红线 1 属运行时架构约束，离线单测只能覆盖其"三出口网格一致"侧面（由 A5 网格测试间接保障），该侧面之外标记 background |

## 交付内容

新增 `tests/unit/` 离线测试套件（与现有 smoke 平行），覆盖：

1. `ArtifactSpec.validate(exit=...)`：array / file / map 三出口必填项（`_EXIT_REQUIRES`）检查与报错消息的可读性（含修复提示）
2. `ArtifactSpec` 基础行为：dtype / reducer / time_range / aoi 校验、`with_` 不可变更新、`to_dict` / `from_dict` JSON 往返、`slug`
3. 指纹稳定性：仅 `note` / `tags`（及 `id` / `render`）不同的 spec 指纹相同；重复计算稳定；`PROCESSING_VERSION` 变化 → 指纹变化
4. 指纹向后兼容守卫：ArtifactSpec 的 dataclass 字段全集必须被「指纹白名单 ∪ 显式排除名单」覆盖，未决定归属的新字段导致守卫测试失败
5. `grid.compute_grid()`：同一 spec 多次计算结果一致（crs / transform / shape 相同）；`Grid.matches()` 判定
6. `crs_rules`：PCS / GCS 判定与 CGCS2000 关键映射

# 非目标

- 不修改 `gis/` 生产代码行为；如测试暴露生产缺陷，只做最小修复并逐条记录，凡改变像素输出的修复必须 `PROCESSING_VERSION += 1`（红线 3）
- 不改动现有 `tests/smoke_*.py`
- 不引入任何网络、GEE 认证或外部服务依赖
- 不为 emit / daemon / tui 等 I/O 层写测试（后续 change 按需）

# 验收示例

1. 离线全绿：在 geo env 下运行单测套件（如 `python -m unittest discover -s tests/unit` 或等价 pytest 命令）全部通过；测试代码不导入 `ee` 或任何网络库，断网环境可运行。
2. 秒级：全套用例在本机（geo env）运行时长 < 10 秒。
3. 指纹行为断言存在：仅 note/tags（及 id/render）不同的两个 spec 指纹相同；同一 spec 重复计算指纹稳定；PROCESSING_VERSION 变化导致指纹变化。
4. 指纹向后兼容守卫存在：dataclass 字段全集必须被指纹白名单或显式排除名单覆盖，新增未决定字段时守卫测试失败并给出处理提示。
5. 覆盖矩阵完整：交付内容 1–6 每类至少一个用例，能列出测试文件与用例名对照。
6. 现有资产不受影响：`tests/smoke_*.py` 未被修改或删除；`gis/` 无行为性修改（最小修复须逐条记录并满足红线 3）。

# Constraints and invariants

- 被测契约 = docs/README.md §11 红线 2/3/8 与 §3.3 指纹规则；测试断言必须与之一致，不得为实现方便放松契约。
- 指纹断言只锁行为性质（相等 / 不等 / 随 PROCESSING_VERSION 变化），不锁哈希位数、具体哈希值或文件名截取细节。

# Decisions

- D1：测试框架在 stdlib `unittest` 与 pytest 之间按 geo env 实际安装情况选型（实现选择，不影响验收结果）。
- D2：测试目录 `tests/unit/`，与现有 smoke 平行。
- D3：工作区隔离 = current（用户 2026-10-06 选择 A），实现直接落在 main 分支。
- D4：指纹向后兼容守卫采用「字段全集 ⊆ 白名单 ∪ 排除名单」的清单式断言，以 `spec.py` 现有 fingerprint 实现为基线，不重构指纹实现。

2026-10-06 验收轮修订（用户要求修复 Verifier 列出的四条风险后再接受结果）：

- D5（R1）：nodata 归入指纹排除名单，spec.md A4 场景的排除名单文字同步更新为 id / note / tags / render / nodata，与 `spec.fingerprint()` 实现现状一致；"nodata 是否应入指纹"作为契约议题留给后续 change。
- D6（R2）：离线守卫的 AST 扫描覆盖 `tests/unit/` 下全部测试文件**与 `_helpers.py`**；docstring 如实描述传递链——ee 为 `geoenv.py` 函数内延迟导入（实测不加载），传递导入的网络相关模块仅 emit→urllib.request（stdlib，仅 import 无调用）。
- D7（R3）：CGCS2000 用例升级为**中央经线一致性属性校验**：对覆盖中国范围的多个经度，验证 `cgcs2000_3deg_epsg` 返回的 EPSG 其名称中的 CM 与 `3*round(lon/3)` 一致；表为空（PROJ 数据库缺失）时断言 `suggest_crs` 落到 UTM 兜底分支。不硬编码 EPSG 码位，跨 PROJ 版本稳健。
- D8（R4）：`Grid.matches` 的容差语义用显式测试固化：容差内的小偏移**不报警**（文档化 rtol=1e-3 相对容差的现状），超容差偏移必须报警；不修改生产代码的容差默认值——若未来要收紧，属生产语义变更，另立 change。

2026-10-06 第 2 轮验收后修订（用户要求修复两条轻微残余风险）：

- D9（残余 1）：守卫 docstring 措辞精确化——「测试导入链仅发生 import、不触发网络调用；urlopen 位于 `emit._download` 函数体内，仅下载路径才执行」，替换原先压缩的「仅 import 无调用」表述；并在守卫注释中显式注明 pyproj 为 D7 授权的允许导入。
- D10（残余 2）：spec.md A1 场景文字更新为「只导入标准库、被测的 gis 模块与 pyproj（D7 授权的 CRS 元数据查询）；不导入 ee 或任何网络库」，消除 A1 字面表述与 D7 的冲突。测试代码无需改动（pyproj 已是惰性导入）。
