---
generated_from_state_version: 12
---

# 验证

## 当前结果

- 结果: **已归档**
- 验证情况: **已完成检查，验证结果已确认**
- 目标周期: 1
- 迭代: 1
- 验证器尝试次数: 1
- 完成时间: 2026-10-07T12:57:14.392Z
- 摘要: 作为独立只读 Verifier 对 p3-osm-overpass 全部 8 项验收做了独立判定，不采信 Builder 自评。核查方式：①亲跑离线基线 212 用例全绿（3.293s）；②通读 gis/osm.py、gis/aoi.py、gis/spec.py（OverlaySpec/fingerprint）、emit.py 与双 bridge diff、三个新测试文件与指纹守卫测试；③亲跑 smoke overlay-qgis（.qgz 独立 zip 解析 gdal=1+ogr=2）与 overlay-arcpy（overlays=2 errors=None），并用像素统计（零 token）证明矢量渲染进 layout PNG；④对 A8 既有证据做独立复核：GPKG 读回与 sidecar 一致、admin_aoi(110101) 真实链路复算 spec 指纹 2ba8b78c 与产物命名精确匹配、endpoint 镜像覆盖生效、退避路径由假 transport 测试覆盖；⑤git status/diff 确认改动面与 D1 一致、source.py 零改动、无 ee 引入、geocode.json skip-worktree 隐藏；⑥核 docs/README.md 主工作区四处更新（§2.2 代码地图 115-116 行、§8 踩坑 #18/#19、§9.1 374 行、§9.2 389 行）。8 项全部 passed，verdict=pass；未修改任何 git 跟踪文件（仅测试/smoke 产生的 gitignored 产物）。

## 验收

| 编号 | 结果 | 来源 | 验收项 | 原因 |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1 离线基线不回退：现有 172 用例全绿；新增用例并入 tests/unit，秒级完成、不碰网络；查询构造纯函数确定性断言。 | 亲跑 PYTHONPATH=. C:/ProgramData/miniforge3/envs/geo/python.exe -m unittest discover -s tests/unit → Ran 212 tests in 3.293s, OK（172 原有 + 40 新增，秒级离线）。查询构造纯函数确定性断言在位：tests/unit/test_osm.py QueryBuildTest 五测（字节级同参同串、tag 键归一化、多值正则排序、bbox 换序与非法值拒绝、selector/nwr 校验）。fixture tests/unit/fixtures/osm_water_recorded.json 实测 145019 字节（<500KB）、25 要素（≤200）、真实录制响应（含 osm3s.timestamp_osm_base）。 |
| A2 | passed | brief.md | A2 Overpass 客户端离线完备：transport 可注入；用入库 fixture（真实录制响应、小型、≤200 要素、<500KB，可为中国非边界要素）断言：way→面/线、带洞 relation 装配、skipped 计数、osm id 确定性排序、CRS=4326。 | gis/osm.py Transport 可注入（osm.py:56 类型别名、query_osm(transport=...)）；ParseAssembleTest 用真实 fixture 断言：21 闭合 way 全部→Polygon、开放 way→LineString、relation outer/inner 装配含洞（test_relation_with_hole 断言 interiors==1）、skipped 三种原因留痕（way_without_geometry/relation_without_outer/relation_unclosed_outer，test_skipped_counted_not_silent 断言 len==3 且不静默）、(类型序, osm id) 确定性排序、CRS to_epsg()==4326。拉取侧 FetchRetryTest：429 退避后成功（sleeps==[2.0]）、超限抛 OverpassError 且消息含『镜像/缩小查询』、504 先同端点退避 MAX_RETRIES 次再落镜像（calls 序列断言）、400 不重试并带响应体。endpoint 覆盖（_endpoints() 读 geocode.json osm.endpoints）、_default_transport 调 geoenv.apply_proxy_env()（osm.py:164）、GEOCODE_OSM_REFRESH 强刷（_refresh_forced）均有实现与测试。 |
| A3 | passed | brief.md | A3 GPKG 交付：geopandas 读回图层与要素数一致；文件名/sidecar 符合 D5；幂等复用成立。 | GpkgDeliverTest（交付目录隔离到临时目录）断言：sidecar 含 query/endpoint/osm3s_timestamp/feature_count/skipped/hash8/hash_input/cache_digest/vector_version 九键、geopandas 读回 25 要素且 CRS==4326、同输入重复导出 reused=True 且 transport 调用数不变（幂等复用）、文件名 {id}.{hash8}.gpkg。hash8 组件确定性测试（deliver_hash：数据时戳进 hash、AOI 摘要进 hash、cache_digest 不含时戳）。VECTOR_VERSION=1 独立常量（gis/osm.py:37），进 sidecar 与命名、不进 spec 指纹（spec.py fingerprint payload 无此键）。亲验 worktree data/deliver/smoke_osm_water.a28d341a.json sidecar 键完整、hash8=a28d341a 与文件名一致。 |
| A4 | passed | brief.md | A4 行政区 AOI 进契约：`admin_aoi(adcode)` 返回值通过 `spec.validate`，`compute_grid(spec)` 离线可算出网格；`_ref` 缺失报错可读且指向恢复程序。 | tests/unit/test_aoi.py AdminAoiTest：110101/110100/110000 命中（admin_tiny fixture 注入路径）、aoi 写进 ArtifactSpec 后 spec.validate('map') 通过且 compute_grid 离线出正网格、adcode 唯一键破坏（admin_dup fixture）报 RuntimeError『唯一键』、缺失目录报 FileNotFoundError 且消息含 docs/knowledge/README.md 与『出处』。我另行亲验真实链路：geocode.json aoi.admin_data_dir=D:/DEV/geocode/_ref/contributions/china-admin-boundaries/skill/data，admin_aoi('110101') 返回 MultiPolygon GeoJSON dict，compute_grid(spec) 得 60x116 @100m。osm_boundary_aoi 返回物化 geometry dict，osm3s_timestamp 只进 meta/save_aoi_note（D4：test 断言几何 dict 内无时戳键）。 |
| A5 | passed | brief.md | A5 矢量进 map 出口（离线+需网络）：同一 OverlaySpec 下 .qgz 含栅格+N 个矢量图层（读回断言），arcpy renderer 出 PDF/PNG 含矢量；两 bridge 样式参数同源（禁止私有布局参数的守卫与 LayoutSpec 同款）。 | 亲跑 tests/smoke_osm.py overlay-qgis（6.5s）→ PASS: .qgz 含栅格 1 + 矢量 2 图层；我再用 zipfile+ET 独立解析 data/deliver/s2_beijing_test.b91c09c9.qgz：provider gdal=1（rgb8.tif）+ ogr=2（smoke_osm_aoi.geojson、smoke_osm_water.a28d341a.gpkg），与 2 个 OverlaySpec 一致。亲跑 overlay-arcpy（27.0s）→ PASS: arcpy overlays=2 errors=None，PDF 4.7MB/PNG 2.4MB 产出；对 layout.png 做像素统计（不读图）：#e05252 县界色 624px、#7aa7ff 水系填充色 662px，矢量要素实证被渲染。两 bridge 样式同源守卫：test_overlay_spec.py BridgeSameSourceGuardTest 断言 write_qgz/write_aprx 签名含 overlays 且 AST 扫描 emit_map 两个分发点均传 spec.overlays；bridge 侧均为 OverlaySpec.to_dict() 契约透传（qgis_bridge.py/arcpy_bridge.py diff 确认，无私造参数）。.png 纯栅格口径已在 emit_map docstring 文档化（emit.py diff：『矢量可见性由 .qgz 工程与 arcpy PDF/PNG 承载』）。 |
| A6 | passed | brief.md | A6 呈现层不进指纹：overlays 缺席与在场指纹逐位相同；金指纹 `b91c09c9c6451c16` 不回退；PV 保持 3。 | gis/spec.py fingerprint() payload（spec.py:565-586）结构上永不含 overlays 键——缺席与在场指纹逐位相同（强于『缺省整键缺席』判据）。tests/unit/test_spec_fingerprint.py：EXCLUDED_FIELDS 含 'overlays'（:36）、test_meta_fields_do_not_change_fingerprint 含 overlays 缺席/单层/双层不同内容三变体断言指纹等于 base、GOLDEN_FINGERPRINTS[3]='b91c09c9c6451c16'（:45-48）且金指纹测试断言 make_p0_spec().fingerprint() 命中、FingerprintForwardCompatGuardTest 强制全字段归属。实证：亲跑 overlay-qgis/arcpy 打印 fingerprint: b91c09c9c6451c16（带 2 个 overlays 的 spec）——金指纹与 PV=3 双双不回退。 |
| A7 | passed | brief.md | A7 合规守卫：代码库内不存在 OSM 中国边界查询路径/示例/文档表述；中国边界数据消费点唯一（本地 `_ref`，adcode）。 | test_osm.py ComplianceGuardTest 三测全绿：gis/osm.py 无 adcode/china-admin-boundaries/china_county/china_city/china_province 任何指示物、gis/ 下引用 china-admin-boundaries 的模块仅 gis/aoi.py、fixture 无 boundary=administrative 要素。country=CN 拒绝路径真实存在：gis/aoi.py:36 _CN_MARKERS={'cn','chn','156','中国','中华人民共和国'} → ComplianceError（守卫先于任何网络行为），test_aoi.py test_china_country_rejected_compliance 对 5 个标识逐一断言拒绝。我另行 grep gis/osm.py、tests/unit/test_osm.py、tests/smoke_osm.py、.cache/make_qgz.py、.cache/make_aprx.py：不存在任何『OSM 查询中国边界』的查询构造路径或示例；中国边界消费点唯一（admin_aoi ← 本地 _ref + adcode）。 |
| A8 | passed | brief.md | A8 端到端实测（需网络，串行）：小范围 OSM 要素拉取→GPKG 读回→`admin_aoi` 选一个小组行政区（如东城区 110101）@100m 走三出口 mini smoke，证明 OSM/边界矢量确实进入 spec 与三出口链路；代理经 geocode.json 生效；429/504 退避路径至少验证一次（可用假 transport 离线覆盖）。 | A8① 证据独立复核：data/deliver/smoke_osm_live.1e82f641.{gpkg,json}——sidecar 端点为 kumi.systems（geocode.json osm.endpoints 四镜像列表首位，覆盖生效）、osm3s_timestamp=2026-10-07T12:18:05Z、feature_count=6/skipped=0/vector_version=1/query 完整；我用 geopandas 独立读回 GPKG：6 要素、CRS=4326、Polygon，与 sidecar 一致。A8② 证据独立复算：我按 mini 同参数（admin_aoi('110101') 真实 _ref 边界 + smoke_osm_water GPKG 叠加 + @100m）重建 spec，spec.validate 通过、fingerprint=2ba8b78c15082dd0 与产物命名 c8_mini_dongcheng.2ba8b78c.{tif,nc,qgz,png,rgb8.tif} 精确匹配（file/map 出口同指纹命名=三出口指纹一致的产物级证据），compute_grid=60x116；独立解析 c8_mini_dongcheng.2ba8b78c.qgz：gdal=1+ogr=1（smoke_osm_water.gpkg）与 spec.overlays 一致。429/504 退避路径由 FetchRetryTest 假 transport 离线覆盖（212 全绿内）。未做网络重跑（Overpass 公共服务今日限流严重，踩坑 #18 记录主站连 3 次 504）；既有证据（文件+sidecar+独立指纹复算+GPKG 读回）自洽，采信既有证据判 passed。代理链路：geocode.json gee.proxy/use_proxy 在位，apply_proxy_env() 注入 HTTP(S)_PROXY 后 urllib 生效（osm.py:159-171）。 |

## 检查

| 检查 | 命令 | 工作目录 | 状态 | 退出码 | 耗时 |
| --- | --- | --- | --- | ---: | ---: |
| tests/unit 全量离线基线（212 用例） | -m unittest discover -s tests/unit | . | passed | 0 | 5375 ms |

### Builder 报告的证据

以下为 Builder 报告，不等同于 Runtime 检查凭据或独立验收结果。

- tests/unit 全量离线基线（212 用例）: passed — 3.8s 全绿（172 基线 + 40 新增），含新增指纹归属守卫
- smoke_osm overlay-qgis（A5）: passed — .qgz 读回 gdal:1+ogr:2；P0 PV3 缓存经 GEE 首建 4.4MB（A5 标注的需网络部分）
- smoke_osm overlay-arcpy（A5）: passed — .aprx + PDF/PNG；overlays=2、overlay_errors=None
- smoke_osm network-fetch（A8①）: passed — 真实拉取 6 要素，hash8=1e82f641，osm3s=2026-10-07T12:18:05Z，GPKG 读回一致
- smoke_osm mini-three-exits（A8②）: passed — 三出口指纹一致 2ba8b78c15082dd0；.qgz 读回 gdal:1+ogr:1
- 已知限制: geocode.json 为本地 skip-worktree 件：worktree 内改动（osm.endpoints 镜像池 + aoi.admin_data_dir 指向主工作区 _ref）不随本 change 提交，已用 git update-index --skip-worktree 隐藏
- 已知限制: A2 真实 fixture（北京水系 25 要素）本身 0 skipped（数据干净）；skipped 留痕路径由测试内联畸形要素覆盖（way 无 geometry / relation 无 outer / outer 不闭合 / inner 不被包含）
- 已知限制: A8② 的 .qgz 中水系叠加层与东城区范围基本不相交（水系 GPKG bbox 偏西）——『矢量进入链路』由 .qgz 图层读回断言承载，视觉可见性由 A5（P0 AOI 与水系 bbox 相交）承载
- 已知限制: docs/README.md 为本地件不入库，已在主工作区就地更新四处（§2.2 代码地图 8619 行、§8 踩坑 #18/#19、§9.1 台账、§9.2 C8 行）；§9.1 的独立验收结论措辞待 Verify 后定稿
- 已知限制: test_offline_guard 的 AST 扫描目标不含 gis/osm.py / gis/aoi.py（urllib 是其功能本体，与 emit→urllib.request 既有先例同权）；tests/unit 自身无网络库 import，守卫继续全绿
- 已知限制: qgis/arcpy 的 label_field 标注为最佳努力实现（CIM/PyQGIS 标注引擎差异大），失败 WARN 留痕不阻塞出图；主体样式（颜色/线宽/透明度/填充）双 bridge 同源 OverlaySpec

## 阻塞项

_无。_

## 风险与跳过的工作

- 演示数据几何错位（非判据违规）：水系 fixture bbox 北界 39.9511 与 P0 AOI 南界 39.95 仅微小压线，shapely 实算交集面积 0.0——水系叠加层在 A5/A8② 主视野外，视觉演示效果依赖县界层；A8② 叠加层与东城区范围不相交为 Builder 已声明的 known_limit。渲染链路本身由像素统计（#1f6feb 系 662px、#e05252 624px）与 bridge 明细（overlays=2, errors=None）证明工作正常。
- test_offline_guard.py 的 TARGETS 未纳入 gis/osm.py 与 gis/aoi.py（Builder known_limit 已声明）。已核两模块顶层导入仅标准库+gis 内部（urllib/geopandas 均函数内懒加载），现状不违规且 osm 本就是网络客户端模块；但守卫清单与新模块不同步，后续给 aoi.py 等纯离线模块扩守卫时需记得补录。
- A8② 的 array 出口为内存返回无落盘产物，三出口指纹一致断言在 smoke 脚本内执行且无保留日志；以 file/map 产物同指纹 2ba8b78c 命名 + 本 verifier 独立复算指纹精确匹配间接闭合，非直接日志证据。
- 任务包引用的 Runtime unit-baseline 日志 logs/checks/448faab3-*.log 在 worktree logs/ 下不存在（logs/ 仅 qgis_render.png）；不影响判定——我已亲跑 212 用例全绿（3.293s），结论与 Runtime 声明一致。
- .cache/make_qgz.py(+94)/make_aprx.py(+98) 为 git 跟踪文件修改，超出 D1 字面『五处+tests/』清单，但内容是双 bridge overlays 消费的 QGIS/arcpy 进程内实现（与 bridge diff 配套同一功能面），判定为 D1 的合理延伸。
- label_field 标注为 CIM/Arcade 最佳努力（arcpy_bridge._style_overlay try/except WARN 降级留痕），OverlaySpec 契约中本为可选字段，可接受。
- Overpass 公共服务限流频发（踩坑 #18：主站连 3 次 504），后续任何网络重跑（network-fetch/mini-three-exits）都可能 504/429——镜像池与退避已实现并测试，属环境风险非本候选缺陷。

## 之前的迭代

| 目标周期 | 迭代 | 尝试 | 结果 | 未解决项 | 摘要 | 完成时间 |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 1 | 1 | pass | — | 作为独立只读 Verifier 对 p3-osm-overpass 全部 8 项验收做了独立判定，不采信 Builder 自评。核查方式：①亲跑离线基线 212 用例全绿（3.293s）；②通读 gis/osm.py、gis/aoi.py、gis/spec.py（OverlaySpec/fingerprint）、emit.py 与双 bridge diff、三个新测试文件与指纹守卫测试；③亲跑 smoke overlay-qgis（.qgz 独立 zip 解析 gdal=1+ogr=2）与 overlay-arcpy（overlays=2 errors=None），并用像素统计（零 token）证明矢量渲染进 layout PNG；④对 A8 既有证据做独立复核：GPKG 读回与 sidecar 一致、admin_aoi(110101) 真实链路复算 spec 指纹 2ba8b78c 与产物命名精确匹配、endpoint 镜像覆盖生效、退避路径由假 transport 测试覆盖；⑤git status/diff 确认改动面与 D1 一致、source.py 零改动、无 ee 引入、geocode.json skip-worktree 隐藏；⑥核 docs/README.md 主工作区四处更新（§2.2 代码地图 115-116 行、§8 踩坑 #18/#19、§9.1 374 行、§9.2 389 行）。8 项全部 passed，verdict=pass；未修改任何 git 跟踪文件（仅测试/smoke 产生的 gitignored 产物）。 | 2026-10-07T12:57:14.392Z |



## 结论

作为独立只读 Verifier 对 p3-osm-overpass 全部 8 项验收做了独立判定，不采信 Builder 自评。核查方式：①亲跑离线基线 212 用例全绿（3.293s）；②通读 gis/osm.py、gis/aoi.py、gis/spec.py（OverlaySpec/fingerprint）、emit.py 与双 bridge diff、三个新测试文件与指纹守卫测试；③亲跑 smoke overlay-qgis（.qgz 独立 zip 解析 gdal=1+ogr=2）与 overlay-arcpy（overlays=2 errors=None），并用像素统计（零 token）证明矢量渲染进 layout PNG；④对 A8 既有证据做独立复核：GPKG 读回与 sidecar 一致、admin_aoi(110101) 真实链路复算 spec 指纹 2ba8b78c 与产物命名精确匹配、endpoint 镜像覆盖生效、退避路径由假 transport 测试覆盖；⑤git status/diff 确认改动面与 D1 一致、source.py 零改动、无 ee 引入、geocode.json skip-worktree 隐藏；⑥核 docs/README.md 主工作区四处更新（§2.2 代码地图 115-116 行、§8 踩坑 #18/#19、§9.1 374 行、§9.2 389 行）。8 项全部 passed，verdict=pass；未修改任何 git 跟踪文件（仅测试/smoke 产生的 gitignored 产物）。
