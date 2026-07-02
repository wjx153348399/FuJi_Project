# 工站目录代码映射确认表

本文档用于先完成“目录位置对应工站代码”的整理工作。后端上传字段名暂未确认时，先不影响目录和工站关系确认；后续只需要把最终字段名配置到 `config.json` 的 `upload.station_field_name`，并把最终工站代码写入 `QMS.dbo.station_directory_config.station_code`。

## 当前结论

- 配置来源表：`QMS.dbo.station_directory_config`
- Web 配置页面：`http://127.0.0.1:8088/station-config`
- 当前真实目录数量：12 条
- 保留测试目录：`ExampleStationDirectoryA`
- 当前问题：真实目录的 `station_code` 仍为 `UNKNOWN`，还不能作为最终上传工站代码使用

上传链路已经支持随文件一起提交工站代码：

```text
multipart/form-data
  file = Excel 文件
  station_code = 配置表中的 station_code
```

如果后端最终字段名不是 `station_code`，只需要修改：

```json
{
  "upload": {
    "station_field_name": "后端确认的字段名"
  }
}
```

## 真实目录映射表

| ID | 目录类型 | 工站名称 | 当前 station_code | 建议临时 station_code | 最终上传工站代码 | 目录状态 | 备注 |
|---:|---|---|---|---|---|---|---|
| 13 | 半成品 | AFC | UNKNOWN | AFC | 待确认 | 存在 | HALF-AFC |
| 14 | 半成品 | AFX | UNKNOWN | AFX | 待确认 | 存在 | HALF-AFX |
| 15 | 半成品 | JXN | UNKNOWN | JXN | 待确认 | 存在 | HALF-JXN |
| 2 | 半成品 | LXD | UNKNOWN | LXD | 待确认 | 存在 | HALF-LXD |
| 16 | 半成品 | ZGL | UNKNOWN | ZGL | 待确认 | 存在 | HALF-ZGL |
| 17 | CP 阻抗 | AFC | UNKNOWN | AFC | 待确认 | 存在 | CP-AFC |
| 18 | CP 阻抗 | AFX | UNKNOWN | AFX | 待确认 | 存在 | CP-AFX |
| 19 | CP 阻抗 | JXN | UNKNOWN | JXN | 待确认 | 存在 | CP-JXN |
| 20 | CP 阻抗 | LXD | UNKNOWN | LXD | 待确认 | 存在 | CP-LXD |
| 21 | CP 阻抗 | ZGL | UNKNOWN | ZGL | 待确认 | 存在 | CP-ZGL |
| 22 | 半成品 | OUTER | UNKNOWN | OUTER | 待确认 | 存在 | HALF-OUTER |
| 23 | CP 阻抗 | OUTER | UNKNOWN | OUTER | 待确认 | 存在 | CP-OUTER |

## 目录明细

| ID | 工站名称 | 目录路径 |
|---:|---|---|
| 13 | AFC | `ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\LXD & AFX & JXN\AFC` |
| 14 | AFX | `ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\LXD & AFX & JXN\AFX` |
| 15 | JXN | `ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\LXD & AFX & JXN\JXN` |
| 2 | LXD | `ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\LXD & AFX & JXN\LXD` |
| 16 | ZGL | `ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\LXD & AFX & JXN\ZGL` |
| 17 | AFC | `ผลิตภัณฑ์สำเร็จรูปCP-阻抗\LXD & AFX & JXN\AFC` |
| 18 | AFX | `ผลิตภัณฑ์สำเร็จรูปCP-阻抗\LXD & AFX & JXN\AFX` |
| 19 | JXN | `ผลิตภัณฑ์สำเร็จรูปCP-阻抗\LXD & AFX & JXN\JXN` |
| 20 | LXD | `ผลิตภัณฑ์สำเร็จรูปCP-阻抗\LXD & AFX & JXN\LXD` |
| 21 | ZGL | `ผลิตภัณฑ์สำเร็จรูปCP-阻抗\LXD & AFX & JXN\ZGL` |
| 22 | OUTER | `ผลิตภัณฑ์กึ่งสำเร็จรูป图形后(半成品)\OUTER` |
| 23 | OUTER | `ผลิตภัณฑ์สำเร็จรูปCP-阻抗\OUTER` |

## 测试目录

| ID | 工站名称 | 当前 station_code | 状态 | 目录路径 | 备注 |
|---:|---|---|---|---|---|
| 1 | V-CUT | A10 | 停用 | `ExampleStationDirectoryA` | 测试目录，保留用于验证 |

## 待业务确认项

1. 后端最终字段名是什么。
   - 当前配置：`station_code`
   - 待确认示例：可能是 `stationCode`、`station_code` 或其他字段名

2. 最终上传工站代码是什么。
   - 如果后端接受目录名代码，可以直接使用建议临时值：`AFC`、`AFX`、`JXN`、`LXD`、`ZGL`、`OUTER`
   - 如果后端要求类似领导示例中的 `A10`、`A50`，需要业务提供每个目录对应的真实代码

3. 半成品和 CP 阻抗是否使用同一套工站代码。
   - 例如半成品 AFC 和 CP-AFC 是否都传 `AFC`
   - 或者需要区分为两个不同代码

## 后续更新 SQL 模板

如果确认临时使用工站名称作为上传代码，可以执行：

```sql
UPDATE QMS.dbo.station_directory_config
SET station_code = station_name,
    updated_by = N'web-confirm',
    updated_at = SYSDATETIME()
WHERE enabled = 1
  AND station_code = N'UNKNOWN'
  AND station_name IS NOT NULL;
```

如果业务给出类似 `A10`、`A50` 的最终代码，按 ID 精准更新更安全：

```sql
UPDATE QMS.dbo.station_directory_config
SET station_code = N'最终代码',
    updated_by = N'web-confirm',
    updated_at = SYSDATETIME()
WHERE id = 13;
```

更新后可用下面 SQL 检查：

```sql
SELECT id,
       station_code,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;
```
