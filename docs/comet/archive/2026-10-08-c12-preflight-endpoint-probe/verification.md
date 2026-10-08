---
generated_from_state_version: 8
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 1
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-08T14:58:49.947Z
- 摘要: 独立只读验收 17/17 通过：独立 harness（真 socket，20/20）验证端点级探测对半开/黑洞/非 HTTP/404/非 JSON/身份不匹配判 False 且有界、对真 add-in 形状判 True；无监听仍 pro-mcp-not-listening，占用态报独立码 pro-port-occupied-by-other 且 reason 可执行；ok 以 endpoint_alive 为准、value 兼留旧字段；GEOCODE_PRO_PORT 覆盖有效；两条入口 246/20 全绿；Pro/、geocode.json 零 diff、PV=3；A16 离线守卫与内核分配端口合规；A17 五条现状引用块与 README L558/L544/L380/L375/L398 逐字节一致、四列齐备。verdict=pass。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | **A1（离线）端口无人监听** → `check_pro_addin` 报 `pro-mcp-not-listening`、`ok=False`、`value["listening"] is False`、端点字段为 False。 | 独立 harness：无监听端口 -> ok=False、code=pro-mcp-not-listening、listening=False、endpoint_alive=False、endpoint_error='无监听者' 且不发 HTTP（_mcp_endpoint_alive 未被调用，见 tests/unit/test_preflight_pro_endpoint.py::CheckProAddinWiringTest.test_A1_not_listening_reports_baseline_code）。证据：%TEMP%/c12-verifier/probe_harness.py 'no-listener' PASS。 |
| A2 | passed | brief.md | **A2（离线）原始 socket 监听者占住端口**（accept 后不回 HTTP）→ `ok=False`、报**新的占用类失败码**（与 `pro-mcp-not-listening` 可区分）、reason 含可执行排查动作（netstat/PID 或换端口）、`value["listening"] is True` 且端点字段为 False。 | 独立 harness 起真原始/非 HTTP 监听者：ok=False、code=pro-port-occupied-by-other（!= pro-mcp-not-listening）、listening=True（诊断保留）、endpoint_alive=False、reason 以「症状：」开头且含 netstat -ano\|findstr:<port> 与 GEOCODE_PRO_PORT 换端口两条处置。证据：probe_harness.py 'occupied(non-http)'、'raw-only-listen' PASS。 |
| A3 | passed | brief.md | **A3（离线）HTTP 返回 200 + 合法 JSON 但 `name != "geocode-pro"`** → 与 A2 同判（不是本 add-in 端点），不得报就绪。 | 独立 harness：HTTP 200 + 合法 JSON 但 name='other-svc' -> alive=False、name 记录为 other-svc、err 含该值，不报就绪。另有非 HTTP、404、非 JSON body、JSON 数组分支均 False。证据：probe_harness.py 'mode=wrongname'/'badjson'/'listjson'/'status404' PASS。 |
| A4 | passed | brief.md | **A4（离线）模拟本 add-in 的 `GET /`**（200 + `{"name":"geocode-pro","version":…,"routes":["/mcp"],"hint":…}`）→ 在 `installed`/`deployed` 成立的前提下 `ok=True`、端点字段为 True。 | 独立 harness：真子进程假端点回 {"name":"geocode-pro","version":...,"routes":["/mcp"]} + 真 _port_listening -> endpoint_alive=True、endpoint_name=='geocode-pro'、installed+deployed 成立时 ok=True、code==''。证据：probe_harness.py 'mode=good'、'good endpoint -> ok True' PASS。 |
| A5 | passed | brief.md | **A5（离线）半开/黑洞监听者**（accept 后永不响应）→ 探测在超时预算内返回 False，不挂死（用例带耗时上限断言）。 | 独立 harness 实测半开（只 listen 不应答）0.83s、黑洞（accept 后永不响应）0.84s 均在有界时延内返回 False（timeout=0.8）。证据：probe_harness.py 前两行 PASS；测试侧另有 elapsed<6.0s 断言。 |
| A6 | passed | brief.md | **A6（离线）`GEOCODE_PRO_PORT` 覆盖**（如 6999）→ 端点探测打在该端口，`value["port"]` 与之一致。 | 独立 harness：设 GEOCODE_PRO_PORT=<内核端口> + port=None -> value['port'] 与该端口一致且对同一端口探测就绪；显式 port= 入参同样生效；未设时回退 PRO_DEFAULT_PORT=6530。证据：probe_harness.py 'GEOCODE_PRO_PORT override' PASS。 |
| A7 | passed | brief.md | **A7（契约）** add-in 源码仍声明身份基准 `name = "geocode-pro"`（静态断言）；一旦 add-in 改名，测试立即失败，提示同步更新探测基准。 | tests/unit/test_pro_addin.py::ProAddinPreflightTest.test_addin_endpoint_identity_contract 断言 preflight.PRO_ENDPOINT_NAME=='geocode-pro' 且 Pro/McpServerHost.cs 源码含 '["name"] = "geocode-pro"'（GET / 路由，第 115 行），把 add-in GET / 身份与 preflight 基准常量钉在一起；add-in 改名即失败。证据：git diff 该断言 + McpServerHost.cs 直读。 |
| A8 | passed | brief.md | **A8（回归）** `python -m unittest discover -s tests/unit` 与 dotted-path 入口全绿；`probe_all()` 键面不变（`pro_addin` 仍在）且 `summarize()` 正常；除 `gis/preflight.py`、新增/更新的测试与本地件差异清单外无其他改动（`Pro/**`、`geocode.json`、`PROCESSING_VERSION` 零 diff）。 | 独立复跑：discover -s tests/unit -> Ran 246 OK(16.0s)；tests.unit.test_spec_basics -> Ran 20 OK。probe_all() 键面 env/gee_local/pro_addin、summarize() 返回 str 不崩。改动面：git diff --name-only 仅 gis/preflight.py + tests/unit/test_pro_addin.py，另有 change 目录未跟踪件；Pro/ 与 geocode.json 零 diff；gis/spec.py 的 PROCESSING_VERSION = 3 未改。证据：%TEMP%/c12-verifier/git-status-start.txt + 复跑输出。 |
| A9 | passed | specs/c12-preflight-endpoint-probe/spec.md | 端口无人监听（基线不回退） `check_pro_addin()` 在 add-in 已安装、已部署、但目标端口没有任何监听者时：`ok=False`，`code="pro-mcp-not-listening"`，reason 保持既有可执行文案（提示打开 ArcGIS Pro / 检查 Add-In Manager），`value["listening"] is False`，端点判定字段为 False。既有失败码 `pro-not-installed`、`pro-addin-not-deployed` 的判定优先级与文案不变。 （验收：A1） | Spec 场景 1（基线不回退）与 A1 同一判据：无监听 -> pro-mcp-not-listening、listening=False、端点字段 False，且 pro-not-installed / pro-addin-not-deployed 优先级与文案不变（独立 harness 已分别验证三个失败码优先级）。 |
| A10 | passed | specs/c12-preflight-endpoint-probe/spec.md | 端口被非 add-in 进程占用（本 change 的核心修正） 目标端口有监听者，但 `GET http://127.0.0.1:<port>/` 不构成本 add-in 的端点时——包括：连接后不回 HTTP 响应、非 HTTP 协议应答、HTTP 状态非 200、body 不是合法 JSON、JSON 中 `name != "geocode-pro"`——探针必须： - `ok=False`； - 报**新的占用类失败码**（与 `pro-mcp-not-listening` 可区分，命名以实现为准）； - reason 说明「端口有监听但不是本 add-in 端点」并给出可执行动作（`netstat -ano` 查 PID / 结束占用者 / 或用 `GEOCODE_PRO_PORT` 换端口）； - 保留诊断信息：`value["listening"] is True`，端点判定字段为 False，且不得报「就绪」。 （验收：A2、A3） | Spec 场景 2（核心修正）与 A2+A3 同一判据：独立 harness 覆盖连接后不回 HTTP（raw/blackhole）、非 HTTP 协议应答（garbage）、状态非 200（404）、body 非合法 JSON（badjson/listjson）、name 不匹配（wrongname）全部 -> ok=False、独立占用类码、reason 含 netstat/PID 与换端口处置、listening=True 且端点字段 False。 |
| A11 | passed | specs/c12-preflight-endpoint-probe/spec.md | 真实本 add-in 端点（就绪判定） 在 `installed and deployed` 成立、且 `GET http://127.0.0.1:<port>/` 返回 200 + 合法 JSON + `name == "geocode-pro"` 时：`ok=True`，reason 表示 add-in 就绪，端点判定字段为 True。本 change 不修改该 GET 路由的响应体形状，只把 `name` 作为身份基准读取。 （验收：A4） | Spec 场景 3（就绪判定）与 A4 同一判据：GET / 返回 200 + 合法 JSON + name==geocode-pro 时 ok=True（需 installed+deployed 成立），未改 add-in GET / 响应体形状，只读 name 作身份基准。 |
| A12 | passed | specs/c12-preflight-endpoint-probe/spec.md | 半开 / 黑洞监听者不得挂住探针 监听者 accept 连接后永不响应（或持续挂起）时，端点探测必须在有界时延内（连接 + 读取合计约 2 秒量级）返回 False，并按占用类失败码处理；探针不得无限等待。该场景是「端口被占用」的一种退化形态，不是崩溃路径。 （验收：A5） | Spec 场景 4（有界时延）与 A5 同一判据：半开与黑洞两态均在 timeout 预算内（实测 ~0.84s，< 约 2s 量级）有界返回 False，探针不挂死。 |
| A13 | passed | specs/c12-preflight-endpoint-probe/spec.md | 端口覆盖沿用既有语义 `GEOCODE_PRO_PORT` 覆盖或显式 `port=` 入参时，端点探测与端口探测使用同一端口：`value["port"]` 与探测目标一致；未设置时回退 `6530`（`PRO_DEFAULT_PORT`）。 （验收：A6） | Spec 场景 5（端口覆盖）与 A6 同一判据：GEOCODE_PRO_PORT 覆盖与显式 port= 入参使端点探测与端口探测共用同一 port 变量，value['port'] 与探测目标一致；未设时回退 PRO_DEFAULT_PORT=6530（未改端口契约）。 |
| A14 | passed | specs/c12-preflight-endpoint-probe/spec.md | 身份基准的契约守卫 探测依赖 add-in `GET /` 的 `name == "geocode-pro"`。必须有静态断言锁住该事实：若 `Pro/McpServerHost.cs` 中该字段被改名或删除，测试立即失败，提示同步更新探测基准与本文档。该断言只读源码文本，不需 Pro 会话。 （验收：A7） | Spec 场景 6（契约守卫）与 A7 同一判据：静态断言只读 Pro/McpServerHost.cs 源码文本、不需 Pro 会话，锁住 name==geocode-pro；改名/删字段会立即失败并提示同步更新探测基准与文档。 |
| A15 | passed | specs/c12-preflight-endpoint-probe/spec.md | 离线回归与改动面 - `python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics` 两条入口全绿；新增用例计入总数。 - `probe_all(network=False)` 键面不变（仍含 `env` / `gee_local` / `pro_addin`），`summarize()` 不因新增字段异常。 - 改动面限定：`gis/preflight.py` + `tests/unit/**`（新增与更新）+ 本地件差异清单载体；`Pro/**`、`geocode.json`、`PROCESSING_VERSION` 零 diff。 （验收：A8） | Spec 场景 7（离线回归与改动面）与 A8 同一判据：两条入口全绿（246 / 20）、probe_all/summarize 不回退、改动限定 gis/preflight.py + tests/unit/** + change 目录清单，Pro/**、geocode.json、PROCESSING_VERSION 零 diff。 |
| A16 | passed | specs/c12-preflight-endpoint-probe/spec.md | 测试全部离线且不污染本机 新增用例通过**进程内起假服务器**（绑定 `127.0.0.1:0` 由系统分配端口后注入 `port=`）或**假原始监听者**覆盖各分支；不依赖 Pro 是否安装/运行、不占用固定 6530/6531、用例结束即释放监听，可在无 Pro 的环境下全绿。 （验收：A1–A6） | 独立 AST 扫描 tests/unit/test_preflight_pro_endpoint.py：顶层 import 仅 gis/json/os/pathlib/subprocess/sys/tempfile/time/unittest，无 socket/http/urllib 等 BANNED；假服务器/假监听者由子进程（subprocess + sys.executable -c）承载，端口 bind('127.0.0.1',0) 内核分配，__exit__ terminate+wait+cleanup 释放监听；测试用例不依赖 Pro（涉及 ok 的断言以 installed/deployed 为条件）。test_offline_guard 独立复跑 OK。注：Spec A16 措辞为「进程内起假服务器」，实现改用子进程（因离线守卫禁止 tests/unit 导入 socket），实质要求（离线、不占固定端口、用例结束释放、无 Pro 可跑）均满足。 |
| A17 | passed | specs/c12-preflight-endpoint-probe/spec.md | 文档收口（D9 惯例） `docs/README.md` 为 gitignored 本地文档，本 change 不在其工作副本内直接改动，而以「待执行差异清单」交付：§8.6 #30 由「已知局限」改为「已由 C12 修复」（保留净结论与回归方式），并在 §9.1/§9.2 追加 C12 台账行。清单四列（现状/改为/依据/回退）齐备、逐条可逆。 （验收：A8 的改动面部分） | 独立脚本从 local-changes.md 抽取 5 个「现状逐字」块与主工作区 docs/README.md 对应行逐字节比较：L558/L544/L380/L375/L398 全部 exact=True（长度 287/48/434/432/215 全等），无省略号；5 条差异（§8.6 #30 行、§8.6 标题、§9.1 台账追加行、§9.1 line375 下一步行、§9.2 台账追加行）均四列齐备（现状/改为/依据/回退），逐条可逆。证据：%TEMP%/c12-verifier/check_readme.py + 输出。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| unit-discover | -m unittest discover -s tests/unit | . | passed | 0 | 17731 ms |
| unit-dotted-path | -m unittest tests.unit.test_spec_basics | . | passed | 0 | 287 ms |
| endpoint-suite | -m unittest tests.unit.test_preflight_pro_endpoint | . | passed | 0 | 9618 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- offline-unit-discover: passed — geo env：discover -s tests/unit → Ran 246 tests, OK（233 基线 + 12 新 + 1 契约守卫）
- offline-unit-dotted-path: passed — geo env：-m unittest tests.unit.test_spec_basics → Ran 20 tests, OK
- new-endpoint-suite: passed — -m unittest tests.unit.test_preflight_pro_endpoint -v → 12 条全 ok（含 2 条真打真连的子进程假服务器用例）
- offline-guard: passed — test_offline_guard.py 的 AST 扫描通过：新测试文件未导入 socket/http/urllib 等禁用库
- zero-diff-invariants: passed — Pro/ 零 diff、geocode.json 零 diff、PROCESSING_VERSION = 3 未改；改动面仅 gis/preflight.py + tests/unit/** + change 目录
- stale-zip-restored: passed — 主工作区 zip 为 C11 之前产物致 5 条 zip 依赖用例失败；package_pro_addin.py build 重建后全绿（未部署、未改 Pro/ 源码）
- 已知限制: 端点身份基准依赖 add-in 的 GET / 字段 name=="geocode-pro"（Pro/McpServerHost.cs）。该耦合由静态契约守卫钉住（add-in 改名会立刻失败），但改名时须同步更新 preflight 常量与本地件清单。
- 已知限制: 本 change 不做完整 MCP initialize 握手（非目标）：一个「自称 name=geocode-pro」的冒充服务仍会被判为本端点；若将来要排除这种情形，另立 change。
- 已知限制: 端口被「不响应型」监听者占用时，端点探测必然消耗到 timeout（默认 1.5s）才判 False——这是有界但非零的代价；`check_pro_addin` 在该情形下由毫秒级变为秒级。
- 已知限制: 测试必须跑在 conda env geo 下（系统 Python312 缺 pyproj）；zip 依赖用例（PackageStructureTest / DamlValidityTest / DockpaneDamlTest）需 Pro/GeoCodePro.addin.zip 存在且为当前源码构建，未构建时这些用例被 skipUnless 跳过。
- 已知限制: 本轮为就地 current 工作区（无独立分支/合并提交），归档轮需在主工作区执行 README 差异清单并回填提交号。

## 阻塞项

_无。_

## 风险与跳过的工作

- 端点身份基准耦合 add-in GET / 的 name 字段；由静态契约守卫钉住（A7/A14），但 add-in 改名时须同步更新 preflight 常量与本地件清单——已由实现者记录为已知局限。
- 本 change 不做完整 MCP initialize 握手（非目标）：一个自称 name=geocode-pro 的冒充服务仍会被判为本端点。
- 端口被不响应型监听者占用时，探测必然消耗到 timeout（默认 1.5s；测试传 0.6-1.0s）才判 False——有界但非零代价。
- 主工作区 Pro/GeoCodePro.addin.zip 在 Build 期被按用例前提重建（gitignored，不属 diff 面）。该动作未改 Pro/ 源码、未部署，不影响本 change 任何判据；但归档时若需 zip 与源码一致，应知悉该重建来自 C11 之前的旧产物。
- Spec A16 原文「进程内起假服务器」与实现的子进程方案措辞不符（由离线守卫禁止 tests/unit 导入 socket 所致）；实质验收要求满足，仅措辞偏差。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 1 | pass | — | 独立只读验收 17/17 通过：独立 harness（真 socket，20/20）验证端点级探测对半开/黑洞/非 HTTP/404/非 JSON/身份不匹配判 False 且有界、对真 add-in 形状判 True；无监听仍 pro-mcp-not-listening，占用态报独立码 pro-port-occupied-by-other 且 reason 可执行；ok 以 endpoint_alive 为准、value 兼留旧字段；GEOCODE_PRO_PORT 覆盖有效；两条入口 246/20 全绿；Pro/、geocode.json 零 diff、PV=3；A16 离线守卫与内核分配端口合规；A17 五条现状引用块与 README L558/L544/L380/L375/L398 逐字节一致、四列齐备。verdict=pass。 | 2026-10-08T14:58:49.947Z |



## 结论

独立只读验收 17/17 通过：独立 harness（真 socket，20/20）验证端点级探测对半开/黑洞/非 HTTP/404/非 JSON/身份不匹配判 False 且有界、对真 add-in 形状判 True；无监听仍 pro-mcp-not-listening，占用态报独立码 pro-port-occupied-by-other 且 reason 可执行；ok 以 endpoint_alive 为准、value 兼留旧字段；GEOCODE_PRO_PORT 覆盖有效；两条入口 246/20 全绿；Pro/、geocode.json 零 diff、PV=3；A16 离线守卫与内核分配端口合规；A17 五条现状引用块与 README L558/L544/L380/L375/L398 逐字节一致、四列齐备。verdict=pass。
