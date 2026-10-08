using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Microsoft.Win32;

namespace GeoCodePro
{
    /// <summary>
    /// 状态面板视图（DAML dockPane content）。code-behind 只做事件转发与文本渲染；
    /// 全部逻辑在 <see cref="GeoCodeDockpaneViewModel"/>（框架会把 DataContext 绑到 VM）。
    /// </summary>
    public partial class GeoCodeDockpaneView : UserControl
    {
        /// <summary>
        /// 服务状态区周期刷新计时器（spec A6：面板可见期间由 UI 线程计时器刷新）。
        /// DispatcherTimer 的 Tick 在 UI 线程派发，读取的是 McpServerHost 的纯 .NET 静态属性，
        /// 不触碰 Pro API，因此无需 QueuedTask 编组。
        /// </summary>
        private readonly DispatcherTimer _statusTimer;

        public GeoCodeDockpaneView()
        {
            InitializeComponent();
            _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            _statusTimer.Tick += (s, e) => RefreshStatus();
            Loaded += OnViewLoaded;
            Unloaded += OnViewUnloaded;
            IsVisibleChanged += OnViewIsVisibleChanged;
        }

        private GeoCodeDockpaneViewModel? Vm => DataContext as GeoCodeDockpaneViewModel;

        private void OnViewLoaded(object sender, RoutedEventArgs e)
        {
            RefreshStatus();
            _statusTimer.Start();
        }

        private void OnViewUnloaded(object sender, RoutedEventArgs e)
        {
            _statusTimer.Stop();
        }

        /// <summary>只在可见期间走表：面板被隐藏/关闭时停表，避免后台空转。</summary>
        private void OnViewIsVisibleChanged(object sender, DependencyPropertyChangedEventArgs e)
        {
            if (IsVisible)
            {
                RefreshStatus();
                _statusTimer.Start();
            }
            else
            {
                _statusTimer.Stop();
            }
        }

        private void RefreshStatus()
        {
            RenderStatus(Vm?.GetStatusSnapshot());
        }

        // ---------------- 服务状态区 ----------------

        private void OnRetryListen(object sender, RoutedEventArgs e)
        {
            RenderStatus(Vm?.RetryListen());
        }

        private void RenderStatus(Tuple<string, string, bool>? snap)
        {
            if (snap == null)
            {
                return;
            }

            StatusText.Text = snap.Item1;
            DetailText.Text = snap.Item2;
            RetryListenButton.Visibility = snap.Item3 ? Visibility.Visible : Visibility.Collapsed;
        }

        // ---------------- 三工具区 ----------------

        private async void OnGetAoi(object sender, RoutedEventArgs e)
        {
            AppendResult(await RunSafeAsync("pro_get_view_aoi", new Dictionary<string, object?>()));
        }

        private void OnCopyGeo(object sender, RoutedEventArgs e)
        {
            var geo = Vm?.GetLastAoiGeoJson();
            try
            {
                Clipboard.SetText(geo ?? "(尚未取得 AOI)");
            }
            catch (Exception ex)
            {
                AppendResult("复制失败：" + ex.Message);
                return;
            }

            AppendResult(geo == null ? "(尚未取得 AOI，无内容可复制)" : "已复制最近 AOI GeoJSON 到剪贴板。");
        }

        private async void OnAddLayer(object sender, RoutedEventArgs e)
        {
            var path = (AddLayerPathBox.Text ?? string.Empty).Trim();
            var layer = (AddLayerSublayerBox.Text ?? string.Empty).Trim();
            if (path.Length == 0)
            {
                AppendResult("pro_add_layer：请先填入 .tif / .gpkg 绝对路径。");
                return;
            }

            var args = new Dictionary<string, object?> { ["path"] = path };
            if (layer.Length > 0)
            {
                args["layer"] = layer;
            }

            AppendResult(await RunSafeAsync("pro_add_layer", args));
        }

        private void OnBrowseLayer(object sender, RoutedEventArgs e)
        {
            var dlg = new OpenFileDialog
            {
                Title = "选择 .tif 或 .gpkg",
                Filter = "栅格/矢量文件 (*.tif;*.tiff;*.gpkg)|*.tif;*.tiff;*.gpkg|全部文件 (*.*)|*.*",
                CheckFileExists = true,
            };
            if (dlg.ShowDialog() == true)
            {
                AddLayerPathBox.Text = dlg.FileName;
            }
        }

        private async void OnExportView(object sender, RoutedEventArgs e)
        {
            var outPath = (ExportPathBox.Text ?? string.Empty).Trim();
            var args = new Dictionary<string, object?>();
            if (outPath.Length > 0)
            {
                args["out_path"] = outPath;
            }

            AppendResult(await RunSafeAsync("pro_export_view", args));
        }

        // ---------------- 公共 ----------------

        /// <summary>统一工具调用入口：VM 已捕获异常并写注册表，这里只做文本渲染。</summary>
        private async Task<string> RunSafeAsync(string tool, Dictionary<string, object?> args)
        {
            if (Vm == null)
            {
                return "(面板未就绪)";
            }

            var text = await Vm.RunToolAsync(tool, args).ConfigureAwait(true);
            return string.Format("[{0:HH:mm:ss}] {1}", DateTime.Now, text);
        }

        private void AppendResult(string text)
        {
            ResultText.Text = text;
        }
    }
}
