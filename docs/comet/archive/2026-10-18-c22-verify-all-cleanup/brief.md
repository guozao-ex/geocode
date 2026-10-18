# 目标

把 c19–c21 三轮验收累积下来的 **8 条遗留**一次性收口，不再各自单独立项。其中一条（入口控制台横幅丢失）已在 Shape 阶段定位到**根因并用最小实验证明修法**；其余为文档/措辞/测试健壮性与**一条需要口径裁决的规格断言**。

条目清单（编号沿用 c21 第四轮 Verifier 的 risks 编号）：

| # | 问题 | 性质 |
|---|---|---|
| 3 | 入口在重定向/管道下运行时，**daemon 窗口之前打印的内容全部丢失**（横幅 + 「启动 daemon…」+「daemon 就绪」） | **真 bug**，根因已定位 |
| 4 | `smoke-map-renderers-*` 的 SKIP 文案没像 rescan-big 那样限定「本次执行根下」 | 措辞 |
| 2 | `tests/unit/test_verify_report_tools.py` 模块级硬 import 两个工具 → 工具缺失时整个 tests-unit 红 | 测试健壮性 |
| 5 | `tools/README.md` 写「linked worktree **没有** `data/`」，实际有空的 data/ 目录树、缺的是 `data/derived/` 产物 | 文档 |
| 1 | spec「离线层零网络通过」声称「全程对外网请求为零」是**硬断言**，但实测 arcpy 渲染时 `arcgispro-py3` 子进程会回连 Esri（R1） | **口径裁决（Q1）** |
| 6 | spec 说「成功产物哈希不漂移」，但 `.aprx`/`.layout.pdf` 含时间戳、跨轮必然不同 | 判据口径 |
| 7 | spec A13 写「tests/ 下 9 个 smoke」，盘上实为 10 个（含 `smoke_all.py`） | spec 文本 |
| 8 | `shape_confirmation_hash` 无法只读复核 | 记录 |

# 范围

## 目录结构

### 新建

- `docs/comet/changes/c22-verify-all-cleanup/specs/verify-all/spec.md` —— `verify-all` 能力的**完整规格**（含本次修订）。Shape 确认前落盘，并与发布面 + 3 份归档副本逐字节一致。

### 修改

- `tests/verify_all.py` —— **#3**：两处模块级 `TextIOWrapper` 加 `write_through=True`（一行 ×2，根因与修法见「决策」）；**#4**：渲染两项的 SKIP 文案对齐 rescan-big 的「本次执行根下」口径。
- `tests/unit/test_verify_report_tools.py` —— **#2**：把两个工具的 import 改为**惰性**（在用例内导入）+ 工具缺失时以 `skipUnless` 归 SKIP，而不是让整个模块 import 失败。
- `tools/README.md` —— **#5**：「主工作区 / worktree 的差异」一节措辞校正（worktree 有空的 `data/` 目录树，缺的是 `data/derived/` 下的产物）。
- `docs/comet/specs/verify-all/spec.md` —— **#1（按 Q1 裁决）/ #6 / #7**：收窄「零外网」断言的覆盖范围并写明第三方渲染栈可能回连；明确「字节可复现」判据为「生产路径零 diff」；A13 的 smoke 数量就地订正为 10 并注明 C14 时代为 9。
- `docs/comet/archive/2026-10-11-c14-…/specs/verify-all/spec.md`、`…/2026-10-18-c17-…`、`…/2026-10-18-c21-…` —— 上述规格的 3 份归档副本，逐字节同步（不变量 2）。
- `docs/comet/specs/README.md` —— 台账追加一行（就地订正表），登记本次的 spec 修订。

### 删除

无

### 明确不建

- **不改 `gis/**`**（除 Q1 选 (b) 给 arcpy 加离线约束这种情形；那属另一个量级的改动，默认不做）；
- 不改 `tools/` 两个工具的**算法与退出码语义**（只改 `tools/README.md` 的措辞）；
- 不改入口的检查项集合、层位判定与失败语义（`report-selfcheck` 的行为不动）；
- 不新增检查项、不新增覆盖率矩阵模块、不建 CI；
- 不动 `PROCESSING_VERSION` 与金指纹。

# 非目标

- 不顺手修其它缺陷（发现即记录并报告）；
- 不重构 `tests/verify_all.py`（只做定点修改）；
- 不追求「让 arcpy 完全离线」——除非 Q1 明确选 (b)；
- 不改 `docs/README.md` 这类 gitignored 本地件。

# 验收示例

- A1: 入口在**输出被重定向到文件/管道**时，daemon 窗口之前打印的内容（横幅、「启动 daemon…」、「daemon 就绪」）**不再丢失**，与交互式终端运行一致；给出最小复现脚本的前后对照（现版本丢、修后不丢）与入口实跑的文件头证据。
- A2: `smoke-map-renderers-qgis` / `-arcpy` 在缓存缺失时的 SKIP 文案明确限定「本次执行根下」（与 rescan-big 同口径），且仍如实说明「联网跑一次后本项自动转 RUN」与单独复跑方式。
- A3: `tools/verify_facts_check.py` 缺失时，`tests/unit` **不再整片失败**（改为该模块相关用例 skip 或惰性导入后的单点失败），其余用例照常通过；工具存在时，该文件的 41 个用例行为与现在完全一致（全绿）。
- A4: `verify-all` 规格的「离线层零网络通过」不再把**第三方渲染栈**的对外回连算作本入口违约：改写后的断言范围与 Shape 裁决的口径一致，且**能被机械核对**（断言只覆盖入口自身发起的请求 / 或明确列出不受约束的第三方组件）。
- A5: 规格明确「字节可复现」判据为「**生产路径零 diff**」，并点明 `.aprx` / `.layout.pdf` 因内嵌时间戳而非字节可复现；对 `.png` / `.qgz` 等的既有表述按实测校正。
- A6: 规格里 smoke 的数量与盘上一致（10 个，含 `smoke_all.py` 汇总器），并注明 C14 时代为 9；台账有对应的就地订正登记行。
- A7: 回归与纪律：`tests/unit` 全量全绿、`uvx --offline ruff@0.17.0 check` 零告警、入口在 worktree 内一条命令跑通且 `report-selfcheck` PASS；**五份副本逐字节一致**（发布面 1 + 归档面 3 + change 暂存 1）；`gis/**`、`Pro/**`、`scripts/**`、`geocode.json`、`PROCESSING_VERSION` 与金指纹零 diff。

# 约束与不变量

- **发布面纪律**：原文零删除（`#7` 的数字属「就地订正」，台账登记；其余一律追加 ⚠️ 注记）；发布面 ↔ 归档面双副本逐字节一致；
- **只改必要处**：#3 只动两行关键字参数；#4 只动两条文案；#2 只动 import 形态；其余为文档/规格；
- **#3 的证据必须双向**：现版本「丢」的证据 + 修后「不丢」的证据，且最小复现脚本可复跑；
- **离线**：本 change 不引入任何网络导入；
- **不改验收口径之外的东西**：`report-selfcheck` 的层位/失败语义、渲染两项的条件项判据、ruff 项的 probe 都不动。

# 决策

- **#3 根因（已实验确认）**：`tests/verify_all.py` 模块级把 `sys.stdout` 包成 `TextIOWrapper` 并保活；`tui-timeseries-probe` 复用的 `tests/smoke_all.py` 在第 26 行**再包一层** `sys.stdout` —— 旧 wrapper 里缓冲的横幅从此没人 flush，永久丢失。最小实验（三模式对照）：默认 `write_through=False` + 保活 → 横幅丢；`write_through=True` → 保留；二次包装前显式 `flush()` → 保留。**取 `write_through=True`**（对任何未来的再次包装都免疫，且不需要在别处埋 flush 点）。
- **#4**：文案对齐 rescan-big 的既有口径（「本次执行根下 …」），不改断言语义；
- **#2**：惰性 import + 工具缺失时 skip —— 让「工具缺失」表现为「相关用例跳过」而不是「整个 tests-unit 红」；
- **#6**：判据改为「生产路径零 diff」并点明哪些产物含时间戳；
- **#7**：就地订正数量为 10 并注明沿革（台账登记），不删原文；
- **#8**：不写代码，只在规格/文档中说明 `shape_confirmation_hash` 是 Runtime 内部状态、不属可只读复核的产物；
- **Q1=(a) R1 收口**：spec 的「离线层零网络通过」断言**收窄为「入口自身发起的对外请求为零」**（python 主进程 + 入口自带 daemon 探针 + 既有 smoke/单测，均只访问 127.0.0.1 且探针禁代理）；并**写明** arcpy/QGIS 渲染子进程属第三方运行时、可能回连 Esri 许可/basemap 服务、不计入本断言（实测：命中态观测到 443/80 出站约 12 s+，qgis 侧未观测到）。**不改代码**；
- **#8 的落点**：`shape_confirmation_hash` 是 Comet Runtime 的内部状态，不写进产品规格（那不属于 verify-all 的能力行为），只在本次交接的 known_limits 里记录「无法只读复核」这一事实。

# 待解决问题

无 —— 本轮唯一的待决项 Q1（R1 的断言口径）已由用户裁决为 (a)，结论记入「决策」。实现期间若出现会改变用户可见结果的新歧义，在此新增 `[blocking]` 项并停下提问。

# 验证预期

- **A1 必须给前后对照**：现版本丢横幅的文件头证据 + 修后不丢的文件头证据 + 最小复现脚本（三模式对照）可复跑；
- **A4/A5/A6 用规格 diff 自证**：逐条指出改在哪行、改前改后各是什么，以及台账的登记行；
- **A7 用哈希与零 diff 对照**：四份副本 sha256 相同；`gis/**` 等零 diff；
- **入口实跑两处**：worktree（无缓存 → 渲染项 SKIP）与（若需要）带缓存的副本（验命中态）；
- **独立验收**：由新的只读 Verifier 独立判断全部验收项，Builder 不自行宣布通过。
