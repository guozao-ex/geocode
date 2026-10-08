// MCP server：HTTP 型（127.0.0.1:6530），协议与 gis/daemon.py 一致
// （initialize protocolVersion 2025-06-18 → tools/list → tools/call）。
// 线程纪律（D3）：后台 HttpListener 线程只解析协议；每个触碰 Pro API 的调用
// 经 QueuedTask.Run 编组进 Pro UI 线程。本文件内零 Pro API 直调——Pro API
// 触碰只出现在 ProTools.cs 的 QueuedTask.Run 闭包内。
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace GeoCodePro
{
    /// <summary>HTTP 型 MCP server 宿主（单例）。</summary>
    internal sealed class McpServerHost
    {
        private static readonly Lazy<McpServerHost> _lazy = new(() => new McpServerHost());
        public static McpServerHost Shared => _lazy.Value;

        private const int DefaultPort = 6530;
        private HttpListener? _listener;
        private Thread? _thread;
        private volatile bool _running;
        private long _requests;

        public int Port { get; private set; } = DefaultPort;
        public bool Running => _running;
        public long Requests => Interlocked.Read(ref _requests);
        public long Errors => Interlocked.Read(ref _errors);
        private long _errors;

        private McpServerHost() { }

        public string? LastError { get; private set; }

        /// <summary>
        /// 起监听。端口被占用等失败时记录 LastError 并返回 false——绝不抛异常，
        /// 以免 add-in 初始化异常中断 Pro 启动（Initialize 在 Pro 启动路径上）。
        /// </summary>
        public bool Start()
        {
            if (_running) return true;
            var portEnv = Environment.GetEnvironmentVariable("GEOCODE_PRO_PORT");
            Port = int.TryParse(portEnv, out var p) && p > 0 ? p : DefaultPort;

            try
            {
                var listener = new HttpListener();
                // 127.0.0.1 精确绑定；仅本机访问
                listener.Prefixes.Add($"http://127.0.0.1:{Port}/");
                listener.Start();
                _listener = listener;
            }
            catch (Exception e)
            {
                LastError = $"{e.GetType().Name}: {e.Message}";
                _listener = null;
                return false;
            }
            _running = true;
            _thread = new Thread(Loop) { IsBackground = true, Name = "geocode-pro-mcp" };
            _thread.Start();
            return true;
        }

        public void Stop()
        {
            if (!_running) return;
            _running = false;
            try { _listener?.Stop(); } catch { /* 尽力关闭 */ }
        }

        private void Loop()
        {
            var listener = _listener!;
            while (_running)
            {
                HttpListenerContext ctx;
                try { ctx = listener.GetContext(); }
                catch { if (_running) continue; else break; }
                Interlocked.Increment(ref _requests);
                try { Handle(ctx); }
                catch (Exception e) { Interlocked.Increment(ref _errors); TrySendError(ctx, e); }
            }
        }

        private static void TrySendError(HttpListenerContext ctx, Exception e)
        {
            try { Send(ctx, 500, Encoding.UTF8.GetBytes(Json(JsonRpcError(ctx.Request, e)))); } catch { }
        }

        // ------------------------------------------------------------------
        // HTTP 处理（后台线程）
        // ------------------------------------------------------------------

        private void Handle(HttpListenerContext ctx)
        {
            var req = ctx.Request;
            var path = req.Url?.AbsolutePath?.TrimEnd('/') ?? "/";
            if (path == "") path = "/";

            if (req.HttpMethod == "OPTIONS")
            {
                ctx.Response.AddHeader("Allow", "GET, POST, OPTIONS");
                Send(ctx, 204, Array.Empty<byte>());
                return;
            }
            if (req.HttpMethod == "GET")
            {
                if (path == "/")
                {
                    var info = new Dictionary<string, object?> {
                        ["name"] = "geocode-pro",
                        ["version"] = "1.0.0",
                        ["routes"] = new[] { "/mcp" },
                        ["hint"] = $"MCP 客户端连 http://127.0.0.1:{Port}/mcp",
                    };
                    Send(ctx, 200, Encoding.UTF8.GetBytes(Json(info)));
                    return;
                }
                if (path == "/mcp")
                {
                    Send(ctx, 405, Encoding.UTF8.GetBytes("{\"error\":\"MCP 用 POST\"}"));
                    return;
                }
                Send(ctx, 404, Encoding.UTF8.GetBytes($"{{\"error\":\"没有这个路由：{path}\"}}"));
                return;
            }
            if (req.HttpMethod != "POST")
            {
                Send(ctx, 405, Encoding.UTF8.GetBytes("{\"error\":\"只支持 GET/POST\"}"));
                return;
            }

            string body;
            using (var reader = new StreamReader(req.InputStream, Encoding.UTF8))
                body = reader.ReadToEnd();

            // MCP 协议挂在 /mcp；其余路由 404
            if (path != "/mcp")
            {
                Send(ctx, 404, Encoding.UTF8.GetBytes($"{{\"error\":\"没有这个路由：{path}\"}}"));
                return;
            }

            Dictionary<string, object?>? msg;
            try { msg = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object?>>(body); }
            catch (Exception e)
            {
                Send(ctx, 400, Encoding.UTF8.GetBytes($"{{\"error\":\"请求体不是合法 JSON：{Escape(e.Message)}\"}}"));
                return;
            }
            if (msg == null)
            {
                Send(ctx, 400, Encoding.UTF8.GetBytes("{\"error\":\"空请求\"}"));
                return;
            }

            var resp = McpHandle(msg);
            if (resp == null) { Send(ctx, 202, Array.Empty<byte>()); return; }
            Send(ctx, 200, Encoding.UTF8.GetBytes(Json(resp)));
        }

        private static void Send(HttpListenerContext ctx, int code, byte[] body)
        {
            ctx.Response.StatusCode = code;
            ctx.Response.ContentType = "application/json; charset=utf-8";
            ctx.Response.ContentLength64 = body.Length;
            ctx.Response.AddHeader("Cache-Control", "no-store");
            try { ctx.Response.OutputStream.Write(body, 0, body.Length); } catch { }
            ctx.Response.Close();
        }

        // ------------------------------------------------------------------
        // MCP 协议（与 gis/daemon.py mcp_handle 对齐）
        // ------------------------------------------------------------------

        /// <summary>返回 null 表示这是通知，不需要响应。</summary>
        private Dictionary<string, object?>? McpHandle(Dictionary<string, object?> msg)
        {
            var id = msg.TryGetValue("id", out var idv) ? idv : null;
            var method = (msg.TryGetValue("method", out var mv) ? mv?.ToString() : "") ?? "";
            Dictionary<string, object?>? parms = null;
            if (msg.TryGetValue("params", out var pv) && pv is System.Text.Json.JsonElement je && je.ValueKind == System.Text.Json.JsonValueKind.Object)
                parms = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object?>>(je.GetRawText());

            Dictionary<string, object?> Ok(object? result) =>
                new() { ["jsonrpc"] = "2.0", ["id"] = id, ["result"] = result };

            if (method is "notifications/initialized" or "notifications/cancelled") return null;

            if (method == "initialize")
            {
                return Ok(new Dictionary<string, object?> {
                    ["protocolVersion"] = Str(parms, "protocolVersion") ?? "2025-06-18",
                    ["capabilities"] = new Dictionary<string, object?> { ["tools"] = new Dictionary<string, object?> { ["listChanged"] = false } },
                    ["serverInfo"] = new Dictionary<string, object?> { ["name"] = "geocode-pro", ["version"] = "1.0.0" },
                });
            }
            if (method == "ping") return Ok(new Dictionary<string, object?>());
            if (method == "tools/list") return Ok(new Dictionary<string, object?> { ["tools"] = ProTools.Tools });
            if (method == "tools/call")
            {
                var name = Str(parms, "name") ?? "";
                object? args = null;
                if (parms != null && parms.TryGetValue("arguments", out var av))
                    args = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object?>>(((System.Text.Json.JsonElement)av).GetRawText());
                try
                {
                    var result = ProTools.Call(name, args as Dictionary<string, object?> ?? new Dictionary<string, object?>());
                    return Ok(new Dictionary<string, object?> {
                        ["content"] = new object[] { new Dictionary<string, object?> { ["type"] = "text", ["text"] = Json(result) } },
                        ["isError"] = false,
                    });
                }
                catch (Exception e)
                {
                    Interlocked.Increment(ref _errors);
                    return Ok(new Dictionary<string, object?> {
                        ["content"] = new object[] { new Dictionary<string, object?> { ["type"] = "text", ["text"] = $"{e.GetType().Name}: {e.Message}" } },
                        ["isError"] = true,
                    });
                }
            }
            if (id == null) return null;
            return new() { ["jsonrpc"] = "2.0", ["id"] = id, ["error"] = new Dictionary<string, object?> { ["code"] = -32601, ["message"] = $"未实现的方法：{method}" } };
        }

        private static Dictionary<string, object?> JsonRpcError(HttpListenerRequest req, Exception e) =>
            new() { ["error"] = $"{e.GetType().Name}: {e.Message}" };

        // ------------------------------------------------------------------
        // JSON 帮手（System.Text.Json 输出，属性名原样）
        // ------------------------------------------------------------------

        internal static string Json(object? obj) =>
            System.Text.Json.JsonSerializer.Serialize(obj, new System.Text.Json.JsonSerializerOptions {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            });

        internal static string Escape(string s) => Json(s);

        private static string? Str(Dictionary<string, object?>? d, string key)
        {
            if (d == null || !d.TryGetValue(key, out var v)) return null;
            if (v is System.Text.Json.JsonElement je) return je.ValueKind == System.Text.Json.JsonValueKind.String ? je.GetString() : je.GetRawText();
            return v?.ToString();
        }
    }
}
