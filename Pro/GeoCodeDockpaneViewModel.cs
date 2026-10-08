using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;

namespace GeoCodePro
{
    /// <summary>
    /// 状态面板 VM（DAML dockPane 的 className）。
    /// 契约要求：继承 Contracts.DockPane 且 protected 构造（Esri ProGuide DockPanes）。
    /// 自身零 Pro API：工具调用一律经 <see cref="ProTools.CallAsync"/>（QueuedTask.Run 编组），
    /// 服务状态读 <see cref="McpServerHost"/> 静态属性（后台 HttpListener 线程维护，只读安全）。
    /// </summary>
    internal class GeoCodeDockpaneViewModel : DockPane
    {
        private const string DockPaneId = "GeoCodePro_Dockpane";

        /// <summary>最近一次 pro_get_view_aoi 的 GeoJSON 原文（供复制按钮）。</summary>
        private string? _lastAoiGeoJson;

        protected GeoCodeDockpaneViewModel()
        {
        }

        /// <summary>功能区按钮 / Alt+Q 打开面板：Find 按需创建单例，Activate 显示并激活。</summary>
        public static void Show()
        {
            var pane = FrameworkApplication.DockPaneManager.Find(DockPaneId);
            pane?.Activate();
        }

        /// <summary>
        /// 服务状态快照：(状态文本, 详情文本, 是否显示重试按钮)。
        /// 只读 McpServerHost 静态属性，UI 线程安全（零 Pro API）。
        /// </summary>
        public Tuple<string, string, bool> GetStatusSnapshot()
        {
            var host = McpServerHost.Shared;
            // 端口取实际值：GEOCODE_PRO_PORT 覆盖后随之变化，不写死 6530（A6 判据）。
            var port = host.Port;
            if (host.Running)
            {
                return Tuple.Create(
                    string.Format("{0} 服务：正常", port),
                    string.Format(
                        "监听端口 {0}（GEOCODE_PRO_PORT 可覆盖）。HTTP 请求 {1} 次（失败 {2} 次）；工具执行 {3} 次（HTTP + 面板）。",
                        port, host.Requests, host.Errors, ResultRegistry.ToolCalls),
                    false);
            }

            var lastError = host.LastError ?? "(无详细错误)";
            return Tuple.Create(
                string.Format("{0} 服务：未监听", port),
                string.Format("MCP 端点未在监听。最近错误：{0}", lastError),
                true);
        }

        /// <summary>
        /// 重试监听：Stop 后重新 Start（纯 .NET，无需 QueuedTask）。
        /// Start() 约定不抛异常（踩坑 #26），异常兜底记注册表；返回刷新后的状态快照。
        /// </summary>
        public Tuple<string, string, bool> RetryListen()
        {
            var host = McpServerHost.Shared;
            try
            {
                host.Stop();
                host.Start();
            }
            catch (Exception ex)
            {
                ResultRegistry.RecordHttpCall("__panel_retry_listen__", null, ex);
            }

            return GetStatusSnapshot();
        }

        /// <summary>
        /// 面板侧工具调用：经 ProTools.CallAsync（内部 QueuedTask.Run 编组，D3 加严），
        /// 结果写共享注册表（与 HTTP 路径同源），返回人类可读摘要文本。
        /// 必须在 UI 线程 await（CallAsync 内 ConfigureAwait(true) 回 UI 上下文）。
        /// </summary>
        public async Task<string> RunToolAsync(string tool, Dictionary<string, object?> args)
        {
            var sw = Stopwatch.StartNew();
            try
            {
                var result = await ProTools.CallAsync(tool, args).ConfigureAwait(true);
                var summary = ResultRegistry.Summarize(tool, result);
                ResultRegistry.Record(tool, true, summary, null, (int)sw.ElapsedMilliseconds);
                if (tool == "pro_get_view_aoi")
                {
                    _lastAoiGeoJson = ResultRegistry.ToJson(result);
                }

                return summary;
            }
            catch (Exception ex)
            {
                ResultRegistry.RecordHttpCall(tool, null, ex);
                return string.Format("{0} 调用失败：{1}", tool, ex.Message);
            }
        }

        /// <summary>复制按钮：返回最近 AOI GeoJSON 原文（未取过时返回 null）。</summary>
        public string? GetLastAoiGeoJson()
        {
            return _lastAoiGeoJson;
        }
    }
}
