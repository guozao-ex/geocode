# Capability：c12-preflight-endpoint-probe —— Pro add-in 端点级探测（修正 preflight 端口假阳性）

## 定位

C11 归档时把「`gis/preflight.py::_port_listening` 是 TCP-connect 探针、任意原始监听者都会让它报 true」记为已知局限（README §8.6 #30）并承诺另立 change。本 Spec 定义该 change 的完整目标行为：让 `pro_addin` 探针回答「**这是不是本 add-in 的 MCP 端点**」，而不是「端口上有没有人接」。

边界与不变量：
- **仅本机**：只访问 `127.0.0.1`，零外网、零凭证、零代理依赖。
- **不改 add-in**：`Pro/**` 零 diff。身份基准取自 add-in 既有的 `GET /` 响应字段 `name`，其值 `"geocode-pro"` 由 `Pro/McpServerHost.cs` 的 `GET /` info 声明。
- **不动引擎契约**：`PROCESSING_VERSION` 不 bump、金指纹不回调、`geocode.json` 不动、6530/6531 端口契约不变、`probe_all()` 键名结构不变。
- **有界时延**：单次 `check_pro_addin()` 的端点探测部分在秒级内返回，半开监听者不得挂住探针。

需求来源：README §8.6 #30（2026-10-08 C11 归档）+ 本 change 的 `brief.md`。

## 行为规格

### Scenario: 端口无人监听（基线不回退）

`check_pro_addin()` 在 add-in 已安装、已部署、但目标端口没有任何监听者时：`ok=False`，`code="pro-mcp-not-listening"`，reason 保持既有可执行文案（提示打开 ArcGIS Pro / 检查 Add-In Manager），`value["listening"] is False`，端点判定字段为 False。既有失败码 `pro-not-installed`、`pro-addin-not-deployed` 的判定优先级与文案不变。

（验收：A1）

### Scenario: 端口被非 add-in 进程占用（本 change 的核心修正）

目标端口有监听者，但 `GET http://127.0.0.1:<port>/` 不构成本 add-in 的端点时——包括：连接后不回 HTTP 响应、非 HTTP 协议应答、HTTP 状态非 200、body 不是合法 JSON、JSON 中 `name != "geocode-pro"`——探针必须：
- `ok=False`；
- 报**新的占用类失败码**（与 `pro-mcp-not-listening` 可区分，命名以实现为准）；
- reason 说明「端口有监听但不是本 add-in 端点」并给出可执行动作（`netstat -ano` 查 PID / 结束占用者 / 或用 `GEOCODE_PRO_PORT` 换端口）；
- 保留诊断信息：`value["listening"] is True`，端点判定字段为 False，且不得报「就绪」。

（验收：A2、A3）

### Scenario: 真实本 add-in 端点（就绪判定）

在 `installed and deployed` 成立、且 `GET http://127.0.0.1:<port>/` 返回 200 + 合法 JSON + `name == "geocode-pro"` 时：`ok=True`，reason 表示 add-in 就绪，端点判定字段为 True。本 change 不修改该 GET 路由的响应体形状，只把 `name` 作为身份基准读取。

（验收：A4）

### Scenario: 半开 / 黑洞监听者不得挂住探针

监听者 accept 连接后永不响应（或持续挂起）时，端点探测必须在有界时延内（连接 + 读取合计约 2 秒量级）返回 False，并按占用类失败码处理；探针不得无限等待。该场景是「端口被占用」的一种退化形态，不是崩溃路径。

（验收：A5）

### Scenario: 端口覆盖沿用既有语义

`GEOCODE_PRO_PORT` 覆盖或显式 `port=` 入参时，端点探测与端口探测使用同一端口：`value["port"]` 与探测目标一致；未设置时回退 `6530`（`PRO_DEFAULT_PORT`）。

（验收：A6）

### Scenario: 身份基准的契约守卫

探测依赖 add-in `GET /` 的 `name == "geocode-pro"`。必须有静态断言锁住该事实：若 `Pro/McpServerHost.cs` 中该字段被改名或删除，测试立即失败，提示同步更新探测基准与本文档。该断言只读源码文本，不需 Pro 会话。

（验收：A7）

### Scenario: 离线回归与改动面

- `python -m unittest discover -s tests/unit` 与 `python -m unittest tests.unit.test_spec_basics` 两条入口全绿；新增用例计入总数。
- `probe_all(network=False)` 键面不变（仍含 `env` / `gee_local` / `pro_addin`），`summarize()` 不因新增字段异常。
- 改动面限定：`gis/preflight.py` + `tests/unit/**`（新增与更新）+ 本地件差异清单载体；`Pro/**`、`geocode.json`、`PROCESSING_VERSION` 零 diff。

（验收：A8）

### Scenario: 测试全部离线且不污染本机

新增用例通过**进程内起假服务器**（绑定 `127.0.0.1:0` 由系统分配端口后注入 `port=`）或**假原始监听者**覆盖各分支；不依赖 Pro 是否安装/运行、不占用固定 6530/6531、用例结束即释放监听，可在无 Pro 的环境下全绿。

（验收：A1–A6）

### Scenario: 文档收口（D9 惯例）

`docs/README.md` 为 gitignored 本地文档，本 change 不在其工作副本内直接改动，而以「待执行差异清单」交付：§8.6 #30 由「已知局限」改为「已由 C12 修复」（保留净结论与回归方式），并在 §9.1/§9.2 追加 C12 台账行。清单四列（现状/改为/依据/回退）齐备、逐条可逆。

（验收：A8 的改动面部分）
