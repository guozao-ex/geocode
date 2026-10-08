// 工具结果注册表：C11 面板与 6530 HTTP 路径共用的「每工具最近一次结果」。
// 线程纪律（D3）：锁保护，UI 线程与后台 HTTP 线程均可读写；只存字符串快照，
// 不触碰 Pro API。
using System;
using System.Collections.Generic;
using System.Text.Json;

namespace GeoCodePro
{
    /// <summary>每工具最近一次结果（全局单例，两执行路径统一写入）。</summary>
    internal static class ResultRegistry
    {
        private static readonly object _lock = new();
        private static readonly Dictionary<string, string> _recent = new();
        private static long _toolCalls;

        /// <summary>
        /// 本会话累计工具执行次数：HTTP 路径与面板路径**合计**（两者都经 Record 汇合）。
        /// A6 计数语义：从面板按钮发起的工具执行同样计入，故「计数随工具执行增长」
        /// 对两条执行路径均成立；与 McpServerHost.Requests（只数 HTTP 请求）互补而互不冒充。
        /// </summary>
        public static long ToolCalls => System.Threading.Interlocked.Read(ref _toolCalls);

        /// <summary>登记一次工具执行，返回可直接展示的文本行。</summary>
        public static string Record(string tool, bool success, string? summary, string? error, int elapsedMs)
        {
            var ts = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            var sb = new System.Text.StringBuilder();
            sb.Append($"[{tool}] {ts} · {(success ? "成功" : "失败")}");
            if (elapsedMs > 0) sb.Append($" · {elapsedMs} ms");
            sb.AppendLine();
            if (summary != null) sb.AppendLine(summary);
            if (error != null) sb.AppendLine(error);
            var text = sb.ToString().TrimEnd();
            System.Threading.Interlocked.Increment(ref _toolCalls);
            lock (_lock) { _recent[tool] = text; }
            return text;
        }

        /// <summary>HTTP 路径执行完成后登记（McpServerHost 调用，避免反向依赖）。</summary>
        public static void RecordHttpCall(string tool, object? result, Exception? error)
        {
            int ms = 0;
            bool ok = error == null;
            var summary = ok ? Summarize(tool, result) : null;
            Record(tool, ok, summary, error == null ? null : $"{error.GetType().Name}: {error.Message}", ms);
        }

        /// <summary>读取某工具最近结果（面板打开时回填）。</summary>
        public static string? Get(string tool) { lock (_lock) { return _recent.TryGetValue(tool, out var v) ? v : null; } }

        /// <summary>只含正在 Pro/ 这个进程内可用工具。</summary>
        public static IReadOnlyList<string> KnownTools { get; } = new[] { "pro_get_view_aoi", "pro_add_layer", "pro_export_view" };

        // JSON 输出与摘要（System.Text.Json，属性名原样）
        private static readonly JsonSerializerOptions _json = new()
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };

        public static string ToJson(object? o) => JsonSerializer.Serialize(o, _json);

        /// <summary>工具结果的短摘要（面板展示用）。</summary>
        public static string Summarize(string tool, object? result)
        {
            try
            {
                if (result is Dictionary<string, object?> d)
                {
                    if (d.TryGetValue("coordinates", out var c) && c is object[] rings && rings.Length > 0)
                    {
                        var ring = rings[0] as System.Collections.IEnumerable;
                        if (ring != null)
                        {
                            int n = 0; double xmin = double.MaxValue, ymin = double.MaxValue, xmax = double.MinValue, ymax = double.MinValue;
                            foreach (var pt in ring)
                            {
                                var arr = pt as System.Collections.IEnumerable;
                                if (arr == null) continue;
                                var list = new List<double>();
                                foreach (var x in arr) list.Add(Convert.ToDouble(x));
                                if (list.Count >= 2)
                                {
                                    xmin = Math.Min(xmin, list[0]); xmax = Math.Max(xmax, list[0]);
                                    ymin = Math.Min(ymin, list[1]); ymax = Math.Max(ymax, list[1]);
                                }
                                n++;
                            }
                            return $"bbox=[{Fmt(xmin)}, {Fmt(ymin)}, {Fmt(xmax)}, {Fmt(ymax)}] · ring 顶点数 {n}";
                        }
                    }
                    if (d.TryGetValue("layer_name", out var ln))
                        return $"图层 {ln} · 当前图层数 {(d.TryGetValue("layer_count", out var lc) ? lc : (object)"?")} · added={(d.TryGetValue("added", out var ad) ? ad : (object)"?")}";
                    if (d.TryGetValue("out_path", out var op))
                        return $"PNG 已导出：{op} · exported={(d.TryGetValue("exported", out var ex) ? ex : (object)"?")}";
                }
                return ToJson(result) ?? "";
            }
            catch (Exception e) { return $"(摘要失败：{e.Message})"; }
        }

        private static string Fmt(double v) => v.ToString("0.####");
    }
}
