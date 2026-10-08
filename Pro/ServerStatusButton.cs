// ServerStatusButton：DAML 声明的按钮（查看 6530 MCP server 状态）。
// 线程纪律（D3）：不触碰 Pro API（零 QueuedTask 需求）；只读 McpServerHost 状态。
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;

namespace GeoCodePro
{
    internal class ServerStatusButton : Button
    {
        protected override void OnClick()
        {
            var host = McpServerHost.Shared;
            string msg;
            if (host.Running)
                msg = $"GeoCode Pro MCP server 运行中\n端口：{host.Port}\n请求数：{host.Requests}\n错误数：{host.Errors}";
            else if (host.LastError != null)
                msg = $"GeoCode Pro MCP server 未运行\n起监听失败：{host.LastError}\n（端口 {host.Port} 可能被占用）";
            else
                msg = "GeoCode Pro MCP server 未运行";
            ArcGIS.Desktop.Framework.Dialogs.MessageBox.Show(msg, "GeoCode Pro MCP");
        }
    }
}
