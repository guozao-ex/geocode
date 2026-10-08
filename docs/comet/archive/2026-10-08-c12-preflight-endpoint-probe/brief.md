# 目标

把 `gis/preflight.py` 的 ArcGIS Pro add-in 探测从「6530 端口上有没有监听者」升级为**端点级探测**：判定它是否真的是**本 add-in 的 MCP 端点**，而不是任意原始监听者占着端口。

现状缺口（C11 归档时记录的已知局限，README §8.6 #30）：`_port_listening()` 是 TCP `connect_ex` 零字节探测——任何进程只要在 6530 上 accept，`pro_addin` 探针就报 `listening: true` 且 `ok: true`、reason「Pro MCP add-in 就绪」。于是：
- agent/人会把「端口有人在接」误判成「add-in 就绪」，进而拿到难以定位的失败；
- C11 的 A7 验收里「注入端口占用」用的正是一个原始 socket 占用者——同一场景下 preflight 会给出假阳性。

本 change 兑现 §8.6 #30 的立项：让探针回答「这是不是我们的端点」。

# 范围

**实现面**

- `gis/preflight.py`
  - 新增端点级探测 `_mcp_endpoint_alive(port, timeout)`（本机 HTTP，零外网）：`GET http://127.0.0.1:<port>/` 必须 **200**、body 可解析为 **JSON**、且 `name == "geocode-pro"`（add-in 的稳定身份字段，见 `Pro/McpServerHost.cs` 的 `GET /` info）。
  - `check_pro_addin()` 的 `ok` 判定由 `installed and deployed and listening` 改为 `installed and deployed and endpoint_alive`。
  - `value` 保留既有 `listening`（向后兼容与诊断），新增端点字段（`endpoint_alive`、`endpoint_name`、`endpoint_error` 之类，命名以实现自定为准）。
  - 新增失败码：端口**有**监听但不是本 add-in 端点 → 端口被别的进程占用；reason 给可执行中文排查（netstat 看 PID / 关闭占用者 / 或改 `GEOCODE_PRO_PORT`）。
  - 既有失败码（`pro-not-installed` / `pro-addin-not-deployed` / `pro-mcp-not-listening`）的语义与文案保持不回退。
- `tests/unit/`
  - 新增离线用例文件，覆盖：无监听 / 原始监听者（不回 HTTP）/ 返回 JSON 但身份不匹配 / 模拟本 add-in 端点 / 半开黑洞监听者（超时预算内返回）/ 端口覆盖。
  - 更新 `tests/unit/test_pro_addin.py` 中受 `ok` 语义变化影响的断言。
  - 新增**契约守卫**静态断言：add-in 源码的 `GET /` info 仍声明 `name = "geocode-pro"`（防止探测基准与 add-in 静默漂移）。
- 文档（按 D9 以「待执行差异清单」交付，不在本 change 改 README 正文）：§8.6 #30 改为「已由 C12 修复」；§9.1/§9.2 追加 C12 台账行。

**不改动**

- 不改 `Pro/**`（add-in 侧零改动：`GET /` 已提供稳定身份字段）。
- 不改 `_port_listening()` 本身（它就是一个端口探测，命名与语义都正确）；端点判断作为独立函数叠加。
- 不改 6530/6531 端口契约；不改 `probe_all()` 的键名结构（只在 `pro_addin.value` 内增字段）；不改 `summarize()`。
- 不改 `gis/daemon.py` 的健康载荷（它不消费 `pro_addin`）。
- 不 bump `PROCESSING_VERSION`、不动金指纹、不动 `geocode.json`。

## 交付内容（工作分解）

1. `gis/preflight.py`：端点探测函数 + `check_pro_addin` 接线 + 新失败码/文案 + `value` 字段。
2. `tests/unit/test_preflight_pro_endpoint.py`（新）：假端点服务器与假原始监听者驱动的离线用例。
3. `tests/unit/test_pro_addin.py`：更新受影响断言 + 新增契约守卫断言。
4. 本地件差异清单（README §8.6 #30 收口 + §9.1/§9.2 台账）。

# 非目标

- **不做完整 MCP `initialize` 握手**：`GET /` 身份校验已覆盖本 change 的目标缺口（原始监听者 / 异类 HTTP 服务）；握手需构造 JSON-RPC POST、更重、并与 MCP 会话语义纠缠。若将来要排除「冒充同名身份的 MCP 服务」，另立 change。
- **不扩展到 daemon（6531）或 GEE 网络探测**：前者不被 preflight 以端口方式探测，后者无此缺口。
- **不要求 Pro 会话**：验收全部离线可测（假服务器即可覆盖）；真实端点旁证可选、不作门槛。
- **不改 preflight 的 CLI 退出码与摘要行**：`summarize()` 与 `__main__` 的失败段落本就不聚合 `pro_addin`，本 change 不改变这一点。

# 约束与不变量

- 仅访问 `127.0.0.1`：零外网、零凭证、零代理依赖（preflight 是快速体检）。
- 探测有界时延：连接 + 读取合计不超过约 2 秒；半开/黑洞监听者不得让探针挂住。
- `probe_all(network=False)` 的既有键与语义不回退（`pro_addin` 仍在其中）；`summarize()` 不因新增字段异常。
- 既有 `check_pro_addin(addin_dir=..., port=...)` 的注入式调用（单测 mock 路径）继续可用。
- 携带 `GEOCODE_PRO_PORT` 覆盖：端点探测与 `listening` 使用同一个 `port` 变量。

# 关键决定

1. **身份基准 = `GET /` 返回的 `name == "geocode-pro"`**（而不是「能返回 JSON 就算」）：该字段是 add-in 的稳定常量、不随版本变化；据此可同时拒绝原始监听者与非本 add-in 的 HTTP 服务。用静态契约断言防止两边漂移。
2. **`ok` 以端点为准，`listening` 降为诊断字段**：既修复假阳性，又保留「端口上是否有进程接」的信息，便于区分「没人听」与「别人占着」。
3. **新增独立失败码而不是复用 `pro-mcp-not-listening`**：占用与未监听是两种不同的处置（一个要清理占用者，一个要打开 Pro），必须可区分、且 reason 给出对应动作。
4. **端点探测叠加在 `_port_listening` 之后**：先做零字节 connect（快、无需等 HTTP），只有端口有人接时才发 HTTP 请求——既省时又避免对空端口做无谓等待。

# 验收示例

- **A1（离线）端口无人监听** → `check_pro_addin` 报 `pro-mcp-not-listening`、`ok=False`、`value["listening"] is False`、端点字段为 False。
- **A2（离线）原始 socket 监听者占住端口**（accept 后不回 HTTP）→ `ok=False`、报**新的占用类失败码**（与 `pro-mcp-not-listening` 可区分）、reason 含可执行排查动作（netstat/PID 或换端口）、`value["listening"] is True` 且端点字段为 False。
- **A3（离线）HTTP 返回 200 + 合法 JSON 但 `name != "geocode-pro"`** → 与 A2 同判（不是本 add-in 端点），不得报就绪。
- **A4（离线）模拟本 add-in 的 `GET /`**（200 + `{"name":"geocode-pro","version":…,"routes":["/mcp"],"hint":…}`）→ 在 `installed`/`deployed` 成立的前提下 `ok=True`、端点字段为 True。
- **A5（离线）半开/黑洞监听者**（accept 后永不响应）→ 探测在超时预算内返回 False，不挂死（用例带耗时上限断言）。
- **A6（离线）`GEOCODE_PRO_PORT` 覆盖**（如 6999）→ 端点探测打在该端口，`value["port"]` 与之一致。
- **A7（契约）** add-in 源码仍声明身份基准 `name = "geocode-pro"`（静态断言）；一旦 add-in 改名，测试立即失败，提示同步更新探测基准。
- **A8（回归）** `python -m unittest discover -s tests/unit` 与 dotted-path 入口全绿；`probe_all()` 键面不变（`pro_addin` 仍在）且 `summarize()` 正常；除 `gis/preflight.py`、新增/更新的测试与本地件差异清单外无其他改动（`Pro/**`、`geocode.json`、`PROCESSING_VERSION` 零 diff）。

# 验证预期

- 全部离线：假端点服务器（`http.server` 或手工 socket 应答）+ 假原始监听者 + 黑洞用例；无需 Pro 会话。
- 独立验收需复跑两条测试入口，并独立核 `probe_all()` 键面与 `summarize()` 不崩。
- 可选旁证（不作门槛）：把 `gis/preflight.py` 在内存里指向真实 6530（若本机 Pro 正开着），确认对真实 add-in 报就绪。

# 未决问题

（无 blocking。上述「关键决定」均可由仓库现状与 C11 归档记录可靠确定：身份字段已存在、`_port_listening` 语义正确、影响面仅 CLI `--json` 的 `pro_addin` 块。）
