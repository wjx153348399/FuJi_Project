# 工站目录配置数据库需求

## 目标

工站目录配置表作为自动上传、监听和 Web 自主配置工站模块的统一数据源。字段必须与后端导入接口一致，使用 `flow` 表示工站代码。

## 表结构

```sql
CREATE TABLE dbo.station_directory_config (
  id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_station_directory_config PRIMARY KEY,
  flow NVARCHAR(50) NOT NULL,
  station_name NVARCHAR(100) NULL,
  directory_path NVARCHAR(500) NOT NULL,
  enabled BIT NOT NULL CONSTRAINT DF_station_directory_config_enabled DEFAULT (1),
  sort_order INT NOT NULL CONSTRAINT DF_station_directory_config_sort_order DEFAULT (0),
  remark NVARCHAR(500) NULL,
  created_by NVARCHAR(50) NULL,
  created_at DATETIME2(0) NOT NULL CONSTRAINT DF_station_directory_config_created_at DEFAULT (SYSDATETIME()),
  updated_by NVARCHAR(50) NULL,
  updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_station_directory_config_updated_at DEFAULT (SYSDATETIME())
);

CREATE UNIQUE INDEX UX_station_directory_config_directory_path
  ON dbo.station_directory_config (directory_path);

CREATE INDEX IX_station_directory_config_flow
  ON dbo.station_directory_config (flow);

CREATE INDEX IX_station_directory_config_enabled_sort
  ON dbo.station_directory_config (enabled, sort_order, id);
```

## 查询约定

```sql
SELECT flow,
       station_name,
       directory_path,
       enabled,
       sort_order
FROM dbo.station_directory_config
WHERE enabled = 1
ORDER BY sort_order ASC, id ASC;
```

Python 读取后转换为：

```python
ScanTargetConfig(
    flow=row.flow,
    dir=row.directory_path,
    enabled=True,
)
```

## 配置来源

`station_config.source` 支持：

| 值 | 含义 |
|---|---|
| `json` | 使用 `scan.targets` |
| `db` | 只使用数据库配置表 |
| `db_then_json` | 优先数据库，失败或为空时回退 JSON |

## 验收标准

- 数据库表使用 `flow` 字段。
- Web 配置工具写入 `flow` 字段。
- 自动上传和监听模块读取 `flow` 字段。
- SQL 脚本、README、测试均使用 `flow`。
