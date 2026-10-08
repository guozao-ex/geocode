# fixtures/ 数据归属与来源

## osm_water_recorded.json

| 项 | 值 |
| --- | --- |
| 数据来源 | **OpenStreetMap**，经 **Overpass API** 录制（`generator` 字段：`Overpass API 0.7.62.11 87bfad18`） |
| 版权与许可 | © OpenStreetMap contributors，**ODbL**（Open Database License）——数据文件内 `osm3s.copyright` 原文自带该声明 |
| 录制时间（数据快照） | `osm3s.timestamp_osm_base` = **2026-10-07T11:55:51Z** |
| 查询范围 | 北京一带水域要素（外接框约 lon 116.2887–116.7848 / lat 39.7591–39.9511，EPSG:4326） |
| 内容 | 25 个要素：21 个 `way` + 4 个 `relation`（multipolygon），全部 `natural=water`（含 `water=river/pond/basin/lake` 等细分）；含名称者如玉渊潭、八一湖、天鹅湖、水獭池、翠池、北展后湖 |
| 文件大小 | 145,019 B |
| 用途 | **仅作离线测试 fixture**（如 `tests/unit/test_osm.py` 解析与边界校验）；不参与任何联网路径、不作为交付数据 |
| 记录形式 | 冻结的录制响应（录制即离线复用的目的），**正文不随代码改动**；需要更新时按同样方式重新录制并同步本说明的录制时间 |

## admin_dup/ 、admin_tiny/

行政区边界测试用的小型几何样本（C8 边界消费路径的离线 fixture）。同属测试数据，
不参与交付。

## 说明

- 本目录文件被测试**解析消费**（JSON 结构、几何坐标都被断言引用），因此**不要手工编辑**正文；
  需要变更时新增文件并在测试中显式引用。
- OSM 数据的使用须遵守 ODbL：分发衍生数据时保留上述归属与许可声明。
