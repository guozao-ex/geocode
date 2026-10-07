<comet-ambient-resume>
<!-- Managed by Comet. Edits inside this block may be replaced by comet init/update. -->
<!-- Contract: comet.resume_probe.v2 -->

## Comet Ambient Resume

在这个仓库中，开始处理需要改动或调查的任务前，如果可能存在活跃 Comet workflow，把当前用户请求传入只读探针：`comet resume-probe . --stdin --json`。

- 如果用户通过宿主明确调用任意 Comet Skill（例如 `@comet`、`/comet`、`@comet-native` 或 `/comet-hotfix`），显式调用优先于本恢复协议；不要运行 resume probe，直接进入被调用的 Skill。
- 如果用户通过宿主明确调用的是非 Comet 的 Skill 或斜杠命令，任务意图已由该调用明确：不要运行 resume probe，直接执行该 Skill。
- 如果你正在 Comet 流程内（包括正在等待用户回复你在流程中提出的问题），不要运行 resume probe；把这类回复（例如方案/选项选择）当作当前 change 的继续，直接按用户的选择推进。
- 只信任返回的 `workflow`、`skill` 和 `entrySource`；它们只由项目配置或无配置兼容回退决定。不得扫描或切换另一套 workflow。
- 如果 probe 返回 `auto_resume`，简短说明选中的 active change，并进入 `nextCommand` 指向的永久入口。不要把状态命令当作恢复入口直接推进。
- 如果 probe 返回 `ask_user`，只问一个简短问题并等待用户回复。
- 如果当前请求未明确调用 Comet Skill，且 probe 返回 `out_of_scope` 或 `none`，不要进入 Comet workflow。
- `out_of_scope` 或 `none` 只表示不要因为这个新请求进入 Comet workflow；它绝不表示要暂停或退出一个已在进行的 Comet 流程。
- 如果配置或状态无效且没有 `nextCommand`，停止并报告原因；不要猜测另一个 workflow。
- 不能只因为存在 active change 就把无关任务挂到该 change。Native 的未提交改动由 Native 入口检查，不由探针自动归因。
</comet-ambient-resume>

## 图片读取纪律 —— 大图隔离（仅供应商 commandcode）

**背景（2026-10-05 实录）**：commandcode 的网关是 Cloudflare Worker，按单次请求的体量与 CPU 时间设限，而图片以 base64 随上下文在每一次请求里全量重发。当晚 10 张截图累计 ~21MB（base64）+ 48.7 万 token 文本，请求在限额边缘走钢丝，负载一高即 `Error 1102` / `Stream ended without finish_reason`，原样重试必然复现。token 只占窗口一半也可能死 —— 字节先顶到网关限额。

**触发条件**：供应商为 commandcode（模型 id 形如 `deepseek/deepseek-v4.1-flash`）时本节生效。

- 单张 ≥ 0.5MB 的图不读进主会话 —— 开 delegate（fresh）子代理去读，把文件路径交给它；主会话只收文字结论（尺寸/判读/异常），结论里禁止再贴图。
- 多张图复用同一个子代理，但设批次帽：最多 3 张或文件合计 ≤ 3MB（先到为准）。到帽主动收尾汇报，剩余图新开代理接手 —— 别等报错才分家。
- 子代理报 `Stream ended without finish_reason` 等流中断 ＝ 单请求体量到顶：新开子代理，只领剩余未处理的图，且批次减半（3→2→1）。禁止原样重派 —— 那是在复制主会话昨晚的重试死循环。
- 先缩再读：UI / 渲染目检用宽 ≤ 800px 的 JPEG（单张 ~100–200KB），绝大多数验证根本到不了第 1 条的线。
- 能出数字就不看图：波段 min/max/mean、唯一色数、工程 XML 检查等结构化验证用工具做 —— 零 token、零字节、可复现。

## 领域知识库（GeoCode-Release Skill 集市收录，C7）

涉及 GIS/GEE 工作流、制图投影选择、中国行政区划边界、专题制图规范等领域问题时，先读知识索引 **`docs/knowledge/README.md`**，再按需读 `_ref/contributions/<skill>/skill/SKILL.md` 及其 `references/`（路径均相对仓库根；`_ref/` 为本地不入库目录，遵守 .gitignore 的搜索工具可能跳过它——请按字面路径直接读取；`_ref/` 缺失时按知识索引「出处」节或 `_ref/PROVENANCE.md` 记录的上游 commit 重新抓取）。

收录技能：gee-scripting（GEE 脚本工作流）、thematic-map（专题制图规范）、projection-selection（投影选择）、china-admin-boundaries（中国行政区划边界数据）、china-statistics-data（国家统计局数据获取）。

注意：上游 SKILL.md 面向 GeoCode 客户端 agent，其中的工具指令（RunGeeScript、Playwright MCP、Cartopy/frykit 栈、`geocode` 包）**不适配本项目**，按索引中的适配注记理解；本项目红线（ee 计算图只在 source.py 构建、compute_grid 唯一网格、指纹向后兼容、三出口共享契约）优先。
