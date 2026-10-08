using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;

namespace GeoCodePro
{
    /// <summary>
    /// 功能区「Status Panel」按钮（DAML id=GeoCodePro_ShowDockpane）。
    /// 虚方法同步 OnClick()（踩坑 #20）；只做 Find+Activate，不碰 Pro 编辑栈。
    /// </summary>
    internal class ShowDockpaneButton : Button
    {
        protected override void OnClick()
        {
            GeoCodeDockpaneViewModel.Show();
        }
    }
}
