# 工站 flow 映射确认表

## 当前结论

- 配置来源表：`QMS.dbo.station_directory_config`
- Web 配置页面：`http://127.0.0.1:8088/station-config`
- 工站字段统一为：`flow`
- 文件路径字段统一为：`filePath`

上传链路字段名统一，按有值才提交：

```text
multipart/form-data
  file = Excel 文件
  flow = 配置表中的 flow，可选
  filePath = 文件完整路径，可选
```

## 真实目录映射表

| ID | 目录类型 | 工站名称 | 当前 flow | 目录状态 | 备注 |
|---:|---|---|---|---|---|
| 13 | 半成品 | AFC | AFC | 存在 | HALF-AFC |
| 14 | 半成品 | AFX | AFX | 存在 | HALF-AFX |
| 15 | 半成品 | JXN | JXN | 存在 | HALF-JXN |
| 2 | 半成品 | LXD | LXD | 存在 | HALF-LXD |
| 16 | 半成品 | ZGL | ZGL | 存在 | HALF-ZGL |
| 17 | CP 阻抗 | AFC | AFC | 存在 | CP-AFC |
| 18 | CP 阻抗 | AFX | AFX | 存在 | CP-AFX |
| 19 | CP 阻抗 | JXN | JXN | 存在 | CP-JXN |
| 20 | CP 阻抗 | LXD | LXD | 存在 | CP-LXD |
| 21 | CP 阻抗 | ZGL | ZGL | 存在 | CP-ZGL |
| 22 | 半成品 | OUTER | OUTER | 存在 | HALF-OUTER |
| 23 | CP 阻抗 | OUTER | OUTER | 存在 | CP-OUTER |

## 查询 SQL

```sql
SELECT id,
       flow,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;
```

## 更新 SQL 模板

```sql
UPDATE QMS.dbo.station_directory_config
SET flow = N'最终代码',
    updated_by = N'web-confirm',
    updated_at = SYSDATETIME()
WHERE id = 13;
```
