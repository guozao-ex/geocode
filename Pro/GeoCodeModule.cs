// GeoCode add-in：ArcGIS Pro 3.7 活会话接入。
// 红线：本目录下所有触碰 Pro API 的方法一律经 QueuedTask.Run 编组进 Pro UI 线程；
// 后台 HttpListener 线程只做协议解析与 JSON 组装（D3 硬纪律）。
using System;
using System.Threading.Tasks;
using ArcGIS.Desktop.Framework.Contracts;

namespace GeoCodePro
{
    /// <summary>add-in 模块：负责在 Pro 启动后拉起 MCP server（Module1.cs 惯例入口）。</summary>
    internal class GeoCodeModule : Module
    {
        private static GeoCodeModule? _this;
        private McpServerHost? _host;

        public static GeoCodeModule Current => _this ?? throw new InvalidOperationException("模块未初始化");

        public GeoCodeModule()
        {
            _this = this;
        }

        /// <summary>Pro 加载 Module 后回调：后台线程起 HTTP MCP server（零 Pro API 直调）。
        /// 起监听失败（如端口被占用）不抛异常——只记录状态，避免中断 Pro 启动。</summary>
        protected override bool Initialize()
        {
            McpServerHost.Shared.Start();
            return true;
        }

        protected override void Uninitialize()
        {
            McpServerHost.Shared.Stop();
        }
    }
}
