// 三个 MCP 工具：pro_get_view_aoi / pro_add_layer / pro_export_view。
// 线程纪律（D3 硬纪律）：每个触碰 Pro API 的方法体一律包在 QueuedTask.Run 闭包内；
// 本文件之外（McpServerHost.cs / GeoCodeModule.cs）零 Pro API 触碰。
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;

namespace GeoCodePro
{
    /// <summary>工具表与分发（后台线程可见的静态元数据 + QueuedTask.Run 编组的执行）。</summary>
    internal static class ProTools
    {
        private static readonly List<Dictionary<string, object?>> ToolList = new()
        {
            new Dictionary<string, object?>
            {
                ["name"] = "pro_get_view_aoi",
                ["description"] = "取当前活动地图视图范围，转 EPSG:4326，返回 GeoJSON Polygon dict（可直接写进 spec.aoi）。",
                ["inputSchema"] = new Dictionary<string, object?> { ["type"] = "object", ["properties"] = new Dictionary<string, object?>() },
            },
            new Dictionary<string, object?>
            {
                ["name"] = "pro_add_layer",
                ["description"] = "把本地 GeoTIFF（.tif）或 GPKG（.gpkg）加进活动地图，返回图层名与图层计数。",
                ["inputSchema"] = new Dictionary<string, object?>
                {
                    ["type"] = "object",
                    ["properties"] = new Dictionary<string, object?>
                    {
                        ["path"] = new Dictionary<string, object?> { ["type"] = "string", ["description"] = "本地文件绝对路径（.tif / .gpkg）" },
                    },
                    ["required"] = new[] { "path" },
                },
            },
            new Dictionary<string, object?>
            {
                ["name"] = "pro_export_view",
                ["description"] = "导出当前活动地图视图为 PNG（入参输出路径，默认落 data/deliver/）。",
                ["inputSchema"] = new Dictionary<string, object?>
                {
                    ["type"] = "object",
                    ["properties"] = new Dictionary<string, object?>
                    {
                        ["out_path"] = new Dictionary<string, object?> { ["type"] = "string", ["description"] = "输出 PNG 绝对路径；缺省落 data/deliver/（相对仓库根）" },
                    },
                },
            },
        };

        public static IReadOnlyList<Dictionary<string, object?>> Tools => ToolList;

        public static object Call(string name, Dictionary<string, object?> args)
        {
            return name switch
            {
                "pro_get_view_aoi" => GetViewAoi(args),
                "pro_add_layer" => AddLayer(args),
                "pro_export_view" => ExportView(args),
                _ => throw new KeyNotFoundException($"未知工具：{name}"),
            };
        }

        // ------------------------------------------------------------------
        // pro_get_view_aoi：视图 extent → EPSG:4326 → GeoJSON Polygon dict
        // QueuedTask.Run 内触碰 Pro API（MapView.Active / extent / SR 转换）。
        // ------------------------------------------------------------------

        private static object GetViewAoi(Dictionary<string, object?> args)
        {
            return QueuedTask.Run(() =>
            {
                var view = MapView.Active ?? throw new InvalidOperationException("没有活动地图视图。请先在 Pro 打开一个地图。");
                var extent = view.Extent ?? throw new InvalidOperationException("活动视图没有 extent。");

                // 视图坐标系 → WGS84（EPSG:4326）
                var wgs84 = SpatialReferenceBuilder.CreateSpatialReference(4326);
                var env = GeometryEngine.Instance.Project(extent, wgs84) as Envelope
                          ?? throw new InvalidOperationException("extent 投影到 EPSG:4326 失败。");

                double xmin = env.XMin, ymin = env.YMin, xmax = env.XMax, ymax = env.YMax;
                // GeoJSON Polygon：外环闭合，左上角起逆时针为外环惯例；取左下起顺时针到左下闭合
                var ring = new List<List<double>>
                {
                    new() { xmin, ymin },
                    new() { xmin, ymax },
                    new() { xmax, ymax },
                    new() { xmax, ymin },
                    new() { xmin, ymin },
                };
                return new Dictionary<string, object?>
                {
                    ["type"] = "Polygon",
                    ["coordinates"] = new object[] { ring },
                };
            }).Result;
        }

        // ------------------------------------------------------------------
        // pro_add_layer：本地 .tif / .gpkg 加进活动地图，返回图层名与计数
        // QueuedTask.Run 内触碰 Pro API（LayerFactory / Map）。
        // ------------------------------------------------------------------

        private static object AddLayer(Dictionary<string, object?> args)
        {
            var path = args.TryGetValue("path", out var p) ? p?.ToString() : null;
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException("缺少入参 path（本地 .tif / .gpkg 绝对路径）。");
            path = Path.GetFullPath(path);
            if (!File.Exists(path))
                throw new FileNotFoundException($"文件不存在：{path}");
            var ext = Path.GetExtension(path).ToLowerInvariant();
            if (ext != ".tif" && ext != ".tiff" && ext != ".gpkg")
                throw new ArgumentException($"只支持 .tif / .gpkg，收到：{ext}");
            // GPKG 可选入参 layer：指定子图层名；缺省按 <file>.gpkg\layer 惯例尝试
            var layerName = args.TryGetValue("layer", out var lv) ? lv?.ToString() : null;

            return QueuedTask.Run(() =>
            {
                var map = MapView.Active?.Map ?? throw new InvalidOperationException("没有活动地图。请先在 Pro 打开一个地图。");
                var before = map.Layers.Count;
                Layer? layer = ext == ".gpkg"
                    ? CreateGpkgLayer(path, layerName, map)
                    : LayerFactory.Instance.CreateLayer(new Uri(path), map);
                var name = layer?.Name ?? Path.GetFileName(path);
                var count = map.Layers.Count;
                return new Dictionary<string, object?>
                {
                    ["layer_name"] = name,
                    ["layer_count"] = count,
                    ["added"] = count > before,
                };
            }).Result;
        }

        /// <summary>
        /// GPKG 加图层。ArcGIS 的 GPKG 要素类路径惯例是 &lt;file.gpkg&gt;\&lt;schema&gt;.&lt;layer&gt;
        /// （默认 schema 为 main），裸文件路径会报“无法添加数据”。
        /// 依次尝试：显式 layer 的 main. 复合路径 → 显式 layer 裸复合 → 枚举 gpkg_contents。
        /// </summary>
        private static Layer? CreateGpkgLayer(string path, string? layerName, Map map)
        {
            var candidates = new List<string>();
            void Add(string cand) { if (!candidates.Contains(cand)) candidates.Add(cand); }

            if (!string.IsNullOrWhiteSpace(layerName))
            {
                Add(layerName.Contains('.') ? $@"{path}\{layerName}" : $@"{path}\main.{layerName}");
                Add($@"{path}\{layerName}");
            }
            foreach (var t in GpkgTableNames(path))
                Add($@"{path}\main.{t}");

            Exception? last = null;
            foreach (var cand in candidates)
            {
                try
                {
                    var layer = LayerFactory.Instance.CreateLayer(new Uri(cand), map);
                    if (layer != null) return layer;
                }
                catch (Exception e) { last = e; }
            }
            throw last ?? new InvalidOperationException($"无法添加 GPKG：{path}（未找到要素图层）");
        }

        /// <summary>读 GPKG（sqlite）的 gpkg_contents 列出要素图层名；无 sqlite 依赖时返回空。</summary>
        private static IEnumerable<string> GpkgTableNames(string path)
        {
            var names = new List<string>();
            try
            {
                using var conn = new System.Data.SQLite.SQLiteConnection($"Data Source={path};Read Only=True;");
                conn.Open();
                using var cmd = conn.CreateCommand();
                cmd.CommandText = "SELECT table_name FROM gpkg_contents WHERE data_type='features'";
                using var r = cmd.ExecuteReader();
                while (r.Read()) names.Add(r.GetString(0));
            }
            catch { /* 无 sqlite 或非 GPKG：退化为只试显式复合路径 */ }
            return names;
        }

        // ------------------------------------------------------------------
        // pro_export_view：当前视图导出 PNG（默认落 data/deliver/）
        // QueuedTask.Run 内触碰 Pro API（MapView.Export / map.GetPath）。
        // ------------------------------------------------------------------

        private static object ExportView(Dictionary<string, object?> args)
        {
            var outPath = args.TryGetValue("out_path", out var o) ? o?.ToString() : null;

            return QueuedTask.Run(() =>
            {
                var view = MapView.Active ?? throw new InvalidOperationException("没有活动地图视图。请先在 Pro 打开一个地图。");
                if (string.IsNullOrWhiteSpace(outPath))
                {
                    // 默认落 <map 所在盘的仓库根>/data/deliver/：优先用当前工程路径推断
                    var projPath = Project.Current?.URI ?? throw new InvalidOperationException("没有活动工程，且未指定 out_path。");
                    var root = Path.GetDirectoryName(projPath) ?? ".";
                    outPath = Path.Combine(root, "data", "deliver", $"pro_view.{DateTime.Now:yyyyMMdd_HHmmss}.png");
                }
                outPath = Path.GetFullPath(outPath);
                var dir = Path.GetDirectoryName(outPath);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

                var png = new PNGFormat { Resolution = 96, Width = view.GetViewSize().Width, Height = view.GetViewSize().Height, OutputFileName = outPath };
                view.Export(png);
                return new Dictionary<string, object?>
                {
                    ["out_path"] = outPath,
                    ["exported"] = File.Exists(outPath),
                };
            }).Result;
        }
    }
}
