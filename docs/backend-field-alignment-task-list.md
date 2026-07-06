# 后端字段全项目统一改造任务清单

## 1. 改造目标

后端导入接口已明确字段：

| 字段 | 含义 | 是否必传 | 项目统一要求 |
|---|---|---:|---|
| `file` | Excel 文件 | 是 | 保持现状，作为 multipart 文件字段 |
| `flow` | 工站代码/工站标识 | 否 | 全项目唯一工站字段名 |
| `filePath` | 文件完整路径 | 否 | 全项目唯一文件路径字段名 |

本次改造要求是全项目统一字段，不做兼容层，不保留新旧字段映射，不保留可配置字段名。

结论：

- [ ] 删除 `station_code` 命名，统一改为 `flow`。
- [ ] 删除 `source_dir` 命名，日志和过程对象统一使用 `filePath` 表示完整文件路径。
- [ ] 删除 `upload.station_field_name`、`upload.send_station_code` 等兼容配置。
- [ ] 上传表单固定发送 `file`，`flow`、`filePath` 有值才发送。
- [ ] 配置、数据库、Web 页面、日志、历史记录、去重 key、测试用例、文档全部统一到 `flow`、`filePath`。

## 2. 字段命名规则

- [ ] Python 数据对象字段也统一使用 `flow`、`filePath`，不再使用 `station_code`、`source_dir`。
- [ ] JSON 配置字段统一使用 `flow`、`dir`：

```json
{
  "scan": {
    "targets": [
      {
        "flow": "A557",
        "dir": "半成品\\AFC",
        "enabled": true
      }
    ]
  }
}
```

- [ ] 数据库配置表字段统一使用 `flow`：

```text
station_directory_config.flow
```

- [ ] 上传请求字段名统一为：

```text
multipart/form-data
  file = Excel 文件
  flow = 工站代码，可选，有值才提交
  filePath = 文件完整路径，可选，有值才提交
```

- [ ] 日志和历史记录中不再出现 `station_code`、`source_dir`。
- [ ] 项目代码中不允许新增兼容字段、别名字段或自动映射逻辑。

## 3. 模块覆盖范围

本清单必须覆盖三个业务模块：自动上传模块、监听模块、自主配置工站模块。任何一个模块如果仍保留旧字段，均视为改造未完成。

### 3.1 自动上传模块

自动上传模块负责扫描、解析、去重、上传、记录日志和生成上传汇总，必须统一使用 `flow`、`filePath`。

- [ ] 入口脚本：
  - [ ] `run_upload.py`
  - [ ] `zk_impedance_upload/cli.py`

- [ ] 核心流程：
  - [ ] `zk_impedance_upload/runner.py`
  - [ ] `zk_impedance_upload/scanner.py`
  - [ ] `zk_impedance_upload/parser.py`
  - [ ] `zk_impedance_upload/dedupe.py`
  - [ ] `zk_impedance_upload/fingerprint.py`
  - [ ] `zk_impedance_upload/uploader.py`
  - [ ] `zk_impedance_upload/log_store.py`

- [ ] 自动上传日志和历史记录：
  - [ ] `upload_log_*.jsonl` 中只允许出现 `flow`、`filePath`。
  - [ ] `uploaded_file_fingerprints*.json` 中只允许出现 `flow`、`filePath`。
  - [ ] `upload_summary_*.json` 中只允许出现 `flow`、`filePath`。

- [ ] 自动上传配置：
  - [ ] `config.example.json`
  - [ ] `config.dry_run.small.json`
  - [ ] 生产 `config.json`
  - [ ] `scan.targets[].flow` 是唯一工站配置字段。

- [ ] 自动上传测试：
  - [ ] `tests/test_config.py`
  - [ ] `tests/test_scanner.py`
  - [ ] `tests/test_parser.py`
  - [ ] `tests/test_dedupe.py`
  - [ ] `tests/test_fingerprint.py`
  - [ ] `tests/test_uploader.py`
  - [ ] `tests/test_runner.py`
  - [ ] `tests/test_project_structure.py`

### 3.2 监听模块

监听模块负责常驻扫描目录变化、记录监听日志、生成监听汇总。虽然监听模块不上传文件，也必须在涉及工站和路径的地方统一字段。

- [ ] 入口脚本：
  - [ ] `run_watcher.py`
  - [ ] `zk_impedance_upload/cli.py`

- [ ] 核心流程：
  - [ ] `zk_impedance_upload/watcher.py`
  - [ ] `zk_impedance_upload/station_config.py`
  - [ ] `zk_impedance_upload/log_store.py`

- [ ] 监听配置来源：
  - [ ] watcher 启动时使用与自动上传一致的有效配置构建逻辑。
  - [ ] watcher 使用 `scan.targets[].flow`。
  - [ ] watcher 从数据库读取配置时使用 `flow` 字段。

- [ ] 监听日志和汇总：
  - [ ] `watch_log_*.jsonl` 如记录工站字段，只允许使用 `flow`。
  - [ ] `watch_log_*.jsonl` 如记录文件路径，只允许使用 `filePath`。
  - [ ] `watch_summary_*.json` 不允许出现 `station_code`、`source_dir`。

- [ ] 监听测试：
  - [ ] `tests/test_watcher.py`
  - [ ] `tests/test_log_store.py`
  - [ ] `tests/test_project_structure.py`
  - [ ] `tests/test_runner.py` 中生成监听汇总的用例。

### 3.3 自主配置工站模块

自主配置工站模块负责维护数据库中的“目录 -> 工站 flow”关系，是本次字段统一的源头模块，必须从数据库、Web 表单、模板、测试到文档全部使用 `flow`。

- [ ] 数据库配置读取：
  - [ ] `zk_impedance_upload/station_config.py`
  - [ ] `StationDbConfig.table` 只配置表名，不配置字段名。
  - [ ] SQL 固定读取 `flow`、`directory_path`。

- [ ] Web 配置工具：
  - [ ] `station_config_web/config.py`
  - [ ] `station_config_web/repository.py`
  - [ ] `station_config_web/app.py`
  - [ ] `station_config_web/templates/station_config_list.html`
  - [ ] `station_config_web/templates/station_config_form.html`
  - [ ] `station_config_web/static/style.css` 如有字段文案也同步检查。

- [ ] Web 配置文件：
  - [ ] `web_config.example.json`
  - [ ] 生产 `web_config.json`

- [ ] SQL 脚本：
  - [ ] `docs/sql/create_station_directory_config.sql`
  - [ ] `docs/sql/seed_station_directory_config.sql`
  - [ ] `docs/sql/update_flow_from_station_name.sql`

- [ ] 自主配置工站测试：
  - [ ] `tests/test_station_config.py`
  - [ ] `tests/test_station_config_web_config.py`
  - [ ] `tests/test_station_config_web_repository.py`
  - [ ] `tests/test_station_config_web_app.py`

## 4. 数据库修改任务

当前截图中的配置表仍是：

```text
QMS.dbo.station_directory_config.station_code
```

这与全项目统一字段目标不一致。数据库表必须改成：

```text
QMS.dbo.station_directory_config.flow
```

数据库层是自主配置工站模块的数据源，也是自动上传和监听模块读取工站配置的源头；因此不能只在代码里映射，必须直接修改表字段。

### 4.1 最终表结构

`QMS.dbo.station_directory_config` 最终字段要求如下：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGINT IDENTITY | 是 | 主键 |
| `flow` | NVARCHAR(50) | 是 | 工站代码，和后端导入接口 `flow` 字段完全一致 |
| `station_name` | NVARCHAR(100) | 否 | 工站显示名称，仅用于人工查看 |
| `directory_path` | NVARCHAR(500) | 是 | 相对 `share.root` 的扫描目录 |
| `enabled` | BIT | 是 | 是否启用 |
| `sort_order` | INT | 是 | 排序 |
| `remark` | NVARCHAR(500) | 否 | 备注 |
| `created_by` | NVARCHAR(50) | 否 | 创建人 |
| `created_at` | DATETIME2(0) | 是 | 创建时间 |
| `updated_by` | NVARCHAR(50) | 否 | 更新人 |
| `updated_at` | DATETIME2(0) | 是 | 更新时间 |

最终建表 SQL 应改为：

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

### 4.2 迁移前检查 SQL

执行迁移前，先确认当前表里是否仍存在 `station_code`，以及是否已经存在 `flow`：

```sql
SELECT COLUMN_NAME,
       DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH,
       IS_NULLABLE
FROM QMS.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'station_directory_config'
  AND COLUMN_NAME IN ('station_code', 'flow')
ORDER BY COLUMN_NAME;
```

检查当前启用数据：

```sql
SELECT id,
       station_code,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       created_by,
       created_at,
       updated_by,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;
```

检查是否有空工站值：

```sql
SELECT id,
       station_code,
       station_name,
       directory_path
FROM QMS.dbo.station_directory_config
WHERE station_code IS NULL
   OR LTRIM(RTRIM(station_code)) = N'';
```

如果上面有结果，先补齐 `station_code`，再改名为 `flow`。

### 4.3 迁移前备份 SQL

字段改名属于破坏式统一改造，执行前先备份当前配置表：

```sql
SELECT *
INTO QMS.dbo.station_directory_config_backup_before_flow_20260703
FROM QMS.dbo.station_directory_config;
```

备份后确认行数一致：

```sql
SELECT 'source' AS table_name, COUNT(*) AS row_count
FROM QMS.dbo.station_directory_config
UNION ALL
SELECT 'backup' AS table_name, COUNT(*) AS row_count
FROM QMS.dbo.station_directory_config_backup_before_flow_20260703;
```

### 4.4 字段改名迁移 SQL

推荐在维护窗口执行：

```sql
BEGIN TRANSACTION;

IF COL_LENGTH('QMS.dbo.station_directory_config', 'flow') IS NOT NULL
BEGIN
    THROW 51000, 'flow column already exists, stop migration.', 1;
END;

IF COL_LENGTH('QMS.dbo.station_directory_config', 'station_code') IS NULL
BEGIN
    THROW 51001, 'station_code column does not exist, stop migration.', 1;
END;

EXEC QMS.sys.sp_rename
  'dbo.station_directory_config.station_code',
  'flow',
  'COLUMN';

COMMIT TRANSACTION;
```

如果 DBeaver 当前连接已经选中 `QMS` 数据库，也可以执行：

```sql
BEGIN TRANSACTION;

EXEC sys.sp_rename
  'dbo.station_directory_config.station_code',
  'flow',
  'COLUMN';

COMMIT TRANSACTION;
```

### 4.5 索引改名 SQL

字段改名后，旧索引名 `IX_station_directory_config_station_code` 仍可能保留，需要同步改成 `IX_station_directory_config_flow`。

先检查索引：

```sql
SELECT i.name AS index_name,
       c.name AS column_name
FROM QMS.sys.indexes AS i
INNER JOIN QMS.sys.index_columns AS ic
  ON i.object_id = ic.object_id
 AND i.index_id = ic.index_id
INNER JOIN QMS.sys.columns AS c
  ON ic.object_id = c.object_id
 AND ic.column_id = c.column_id
WHERE i.object_id = OBJECT_ID('QMS.dbo.station_directory_config')
ORDER BY i.name, ic.key_ordinal;
```

如果旧索引存在，执行：

```sql
EXEC QMS.sys.sp_rename
  'dbo.station_directory_config.IX_station_directory_config_station_code',
  'IX_station_directory_config_flow',
  'INDEX';
```

如果索引改名失败，则删除旧索引后重建：

```sql
DROP INDEX IX_station_directory_config_station_code
ON QMS.dbo.station_directory_config;

CREATE INDEX IX_station_directory_config_flow
ON QMS.dbo.station_directory_config (flow);
```

### 4.6 字段说明更新 SQL

为避免后续在 DBeaver 或数据库字典里继续看到旧含义，建议补充或更新扩展属性：

```sql
EXEC QMS.sys.sp_addextendedproperty
  @name = N'MS_Description',
  @value = N'后端导入接口 flow 字段值，表示工站代码/工站标识',
  @level0type = N'SCHEMA', @level0name = N'dbo',
  @level1type = N'TABLE', @level1name = N'station_directory_config',
  @level2type = N'COLUMN', @level2name = N'flow';
```

如果属性已存在，则使用：

```sql
EXEC QMS.sys.sp_updateextendedproperty
  @name = N'MS_Description',
  @value = N'后端导入接口 flow 字段值，表示工站代码/工站标识',
  @level0type = N'SCHEMA', @level0name = N'dbo',
  @level1type = N'TABLE', @level1name = N'station_directory_config',
  @level2type = N'COLUMN', @level2name = N'flow';
```

### 4.7 迁移后验收 SQL

迁移后，检查字段：

```sql
SELECT COLUMN_NAME,
       DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH,
       IS_NULLABLE
FROM QMS.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'station_directory_config'
ORDER BY ORDINAL_POSITION;
```

预期：

- [ ] 存在 `flow`。
- [ ] 不存在 `station_code`。
- [ ] `flow` 为 `NVARCHAR(50) NOT NULL`。

检查数据：

```sql
SELECT id,
       flow,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       created_by,
       created_at,
       updated_by,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;
```

检查旧字段是否彻底消失：

```sql
SELECT COLUMN_NAME
FROM QMS.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'station_directory_config'
  AND COLUMN_NAME = 'station_code';
```

预期返回 0 行。

### 4.8 迁移后查询模板

后续所有配置查询统一改为：

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
WHERE enabled = 1
ORDER BY sort_order ASC, id ASC;
```

Python 读取配置时统一映射为：

```python
ScanTargetConfig(
    flow=row.flow,
    dir=row.directory_path,
    enabled=True,
)
```

### 4.9 配置数据更新模板

以后更新工站代码时，必须更新 `flow`：

```sql
UPDATE QMS.dbo.station_directory_config
SET flow = N'A557',
    updated_by = N'web-confirm',
    updated_at = SYSDATETIME()
WHERE id = 13;
```

不再允许写：

```sql
UPDATE QMS.dbo.station_directory_config
SET station_code = N'AFC'
WHERE id = 13;
```

### 4.10 SQL 文件修改清单

- [ ] 修改建表 SQL：`docs/sql/create_station_directory_config.sql`
  - [ ] 将 `station_code` 字段改为 `flow`。
  - [ ] 将索引 `IX_station_directory_config_station_code` 改为 `IX_station_directory_config_flow`。
  - [ ] 字段说明改为“工站代码/后端 flow 字段值”。

- [ ] 新增一次性迁移 SQL：`docs/sql/migrate_station_directory_config_flow.sql`。
  - [ ] 包含迁移前检查。
  - [ ] 包含备份表创建。
  - [ ] 包含字段改名。
  - [ ] 包含索引改名或重建。
  - [ ] 包含迁移后验收查询。

- [ ] 修改种子数据 SQL：`docs/sql/seed_station_directory_config.sql`
  - [ ] 插入字段从 `station_code` 改为 `flow`。

- [ ] 修改更新脚本：
  - [ ] `docs/sql/update_station_code_from_station_name.sql` 重命名为 `docs/sql/update_flow_from_station_name.sql`。
  - [ ] SQL 内所有 `station_code` 改为 `flow`。

- [ ] 修改 `docs/station-directory-code-mapping.md` 里的所有数据库查询和更新 SQL。
- [ ] 修改 `docs/station-directory-config-phase2-requirement.md` 里的表结构、查询 SQL、字段说明。

## 5. 配置文件修改任务

- [ ] 修改 `config.example.json`：
  - [ ] `scan.targets[].station_code` 改为 `scan.targets[].flow`。
  - [ ] 删除 `upload.send_station_code`。
  - [ ] 删除 `upload.station_field_name`。

- [ ] 修改生产 `config.json`：
  - [ ] `scan.targets[].station_code` 改为 `scan.targets[].flow`。
  - [ ] 删除 `upload.send_station_code`。
  - [ ] 删除 `upload.station_field_name`。

- [ ] 修改配置示例为：

```json
{
  "upload": {
    "url": "http://YOUR_SERVER/service-qms/file/importImpedanceData",
    "dry_run": false,
    "timeout_seconds": 300,
    "retry_count": 2
  },
  "scan": {
    "targets": [
      {
        "flow": "A557",
        "dir": "ExampleStationDirectoryA",
        "enabled": true
      }
    ]
  }
}
```

- [ ] `station_config.db.table` 仍可保留表名配置，但读取字段固定为 `flow`，不做字段名配置。

## 6. Python 核心代码修改任务

- [ ] 修改 `zk_impedance_upload/config.py`：
  - [ ] `UploadConfig` 删除 `send_station_code`。
  - [ ] `UploadConfig` 删除 `station_field_name`。
  - [ ] `ScanTargetConfig.station_code` 改为 `ScanTargetConfig.flow`。
  - [ ] `_optional_scan_targets()` 只解析 `flow`，不解析 `station_code`。
  - [ ] `flow` 字段名统一，允许暂时为空；非字符串或非法字符仍需报错。
  - [ ] 不允许 `station_code` 继续通过配置校验。

- [ ] 修改 `zk_impedance_upload/station_config.py`：
  - [ ] SQL 查询字段从 `station_code` 改为 `flow`。
  - [ ] `ScanTargetConfig(station_code=...)` 改为 `ScanTargetConfig(flow=...)`。
  - [ ] 校验函数从 `_STATION_CODE_PATTERN` 改为 `_FLOW_PATTERN`。
  - [ ] 错误信息统一使用 `flow`。

- [ ] 修改 `zk_impedance_upload/scanner.py`：
  - [ ] `CandidateFile.station_code` 改为 `CandidateFile.flow`。
  - [ ] 删除或替换 `source_dir` 字段。
  - [ ] `CandidateFile.filePath` 固定保存完整文件路径。
  - [ ] 扫描结果、缺失目录、失败目录中的工站字段统一为 `flow`。

- [ ] 修改 `zk_impedance_upload/parser.py`：
  - [ ] `ParsedFile.station_code` 改为 `ParsedFile.flow`。
  - [ ] `ParsedFile.source_dir` 改为 `ParsedFile.filePath`。
  - [ ] `parse_candidate()` 从 `CandidateFile.flow`、`CandidateFile.filePath` 继承字段。

- [ ] 修改 `zk_impedance_upload/fingerprint.py`：
  - [ ] 上传历史记录写入 `flow`。
  - [ ] 上传历史记录写入 `filePath`。
  - [ ] 不再写入 `station_code`、`source_dir`。

- [ ] 修改 `zk_impedance_upload/dedupe.py`：
  - [ ] fallback key 从 `station_code + region + normalized_name + size + mtime` 改为 `flow + region + normalized_name + size + mtime`。
  - [ ] 旧 key 不做兼容匹配。

- [ ] 修改 `zk_impedance_upload/uploader.py`：
  - [ ] `upload_file()` 参数从 `station_code` 改为 `flow`。
  - [ ] 删除 `send_station_code` 参数。
  - [ ] 删除 `station_field_name` 参数。
  - [ ] 增加必传参数 `filePath`。
  - [ ] `_build_upload_data()` 固定返回：

```python
{
    "flow": flow,
    "filePath": filePath,
}
```

- [ ] 修改 `zk_impedance_upload/runner.py`：
  - [ ] 所有日志字段从 `station_code` 改为 `flow`。
  - [ ] 所有日志字段从 `source_dir` 改为 `filePath`。
  - [ ] 调用 `upload_file()` 时传入 `flow=parsed_file.flow`。
  - [ ] 调用 `upload_file()` 时传入 `filePath=parsed_file.filePath`。
  - [ ] 删除 `upload_station_field`、`send_station_code` 相关日志字段。

- [ ] 修改 `zk_impedance_upload/watcher.py`：
  - [ ] 所有配置对象和日志字段统一使用 `flow`、`filePath`。
  - [ ] 确认 watcher 不再引用 `station_code`。

- [ ] 修改 `zk_impedance_upload/cli.py` 和 `diag_scan.py`：
  - [ ] 配置检查输出统一使用 `flow`。
  - [ ] 诊断输出统一使用 `flow`、`filePath`。

## 7. Web 配置工具修改任务

- [ ] 修改 `station_config_web/repository.py`：
  - [ ] `StationDirectoryRow.station_code` 改为 `flow`。
  - [ ] `StationDirectoryInput.station_code` 改为 `flow`。
  - [ ] SQL 字段全部从 `station_code` 改为 `flow`。
  - [ ] 校验函数改为 `validate_flow` 或等价命名。

- [ ] 修改 `station_config_web/app.py`：
  - [ ] 表单参数 `station_code` 改为 `flow`。
  - [ ] 模板上下文 `station_code` 改为 `flow`。
  - [ ] 页面提示 `flow` 为可选，确认真实工站代码后填写。

- [ ] 修改模板：
  - [ ] `station_config_web/templates/station_config_list.html`
  - [ ] `station_config_web/templates/station_config_form.html`
  - [ ] 表单 `name="station_code"` 改为 `name="flow"`。
  - [ ] 列标题从“工站代码/station_code”改为“flow”。

- [ ] 修改 `station_config_web/README.md`：
  - [ ] 表结构说明使用 `flow`。
  - [ ] 页面说明使用 `flow`。

## 8. 测试修改任务

- [ ] 全局重命名测试字段：
  - [ ] `station_code` 改为 `flow`。
  - [ ] `source_dir` 改为 `filePath`。
  - [ ] 测试函数名中的 `station_code` 改为 `flow`。

- [ ] 修改 `tests/test_config.py`：
  - [ ] 覆盖 `scan.targets[].flow`。
  - [ ] 覆盖缺少 `flow` 时报错。
  - [ ] 覆盖旧字段 `station_code` 不再被接受。
  - [ ] 覆盖 `UploadConfig` 不再包含 `send_station_code`、`station_field_name`。

- [ ] 修改 `tests/test_station_config.py`：
  - [ ] DB repository 返回 `flow`。
  - [ ] 校验空 `flow` 报错。
  - [ ] 校验非法 `flow` 报错。
  - [ ] 错误消息不再出现 `station_code`。

- [ ] 修改 `tests/test_scanner.py`：
  - [ ] 候选文件带正确 `flow`。
  - [ ] 候选文件带完整 `filePath`。

- [ ] 修改 `tests/test_parser.py`：
  - [ ] `ParsedFile.flow` 来自 `CandidateFile.flow`。
  - [ ] `ParsedFile.filePath` 来自 `CandidateFile.filePath`。
  - [ ] fallback key 有 `flow` 时包含 `flow`，无 `flow` 时使用 `filePath` 兜底。

- [ ] 修改 `tests/test_uploader.py`：
  - [ ] multipart 表单有 `flow` 时包含 `flow`。
  - [ ] multipart 表单有 `filePath` 时包含 `filePath`。
  - [ ] 不再测试字段名配置或关闭发送开关。

- [ ] 修改 `tests/test_runner.py`：
  - [ ] dry-run 日志包含 `flow`、`filePath`。
  - [ ] 上传成功日志包含 `flow`、`filePath`。
  - [ ] 历史成功记录包含 `flow`、`filePath`。

- [ ] 修改 Web 测试：
  - [ ] `tests/test_station_config_web_repository.py`
  - [ ] `tests/test_station_config_web_app.py`
  - [ ] `tests/test_station_config_web_config.py`
  - [ ] 全部断言改为 `flow`。

- [ ] 执行全量测试：

```powershell
python -m unittest discover -s tests -v
```

## 9. 文档修改任务

- [ ] 修改 `README.md`：
  - [ ] 删除 `station_code` 描述。
  - [ ] 删除 `upload.station_field_name` 描述。
  - [ ] 删除 `send_station_code` 描述。
  - [ ] 新增 `flow`、`filePath` 字段说明。

- [ ] 修改 `docs/station-directory-binding-requirement.md`：
  - [ ] `station_code` 全部替换为 `flow`。
  - [ ] `source_dir` 全部替换为 `filePath`。
  - [ ] 删除“后端字段未确认”相关说明。

- [ ] 修改 `docs/station-directory-config-phase2-requirement.md`：
  - [ ] 配置表字段改为 `flow`。
  - [ ] 查询 SQL 改为 `flow`。
  - [ ] 删除可配置上传字段名说明。

- [ ] 修改 `docs/station-directory-code-mapping.md`：
  - [ ] 文档标题可改为“工站 flow 映射确认表”。
  - [ ] 表格列 `当前 station_code` 改为 `当前 flow`。
  - [ ] SQL 全部改为 `flow`。

- [ ] 全局检查文档中是否仍有旧字段：

```powershell
rg -n "station_code|source_dir|station_field_name|send_station_code" README.md docs station_config_web zk_impedance_upload tests config.example.json
```

预期：除迁移说明文档中必要提及外，不应再出现旧字段。

## 10. 全项目兜底审查任务

三大业务模块覆盖后，还需要对项目内其余文件做兜底检查。部分文件理论上不需要改，但必须确认没有残留旧字段、旧配置或旧文档说明。

### 10.1 需要确认无字段残留的非核心文件

- [ ] `zk_impedance_upload/__init__.py`
- [ ] `zk_impedance_upload/share_auth.py`
- [ ] `zk_impedance_upload/exceptions.py`
- [ ] `zk_impedance_upload/date_window.py`
- [ ] `station_config_web/__init__.py`
- [ ] `requirements.txt`
- [ ] `notes.md`
- [ ] `web_config.json`
- [ ] `config.json`

如果这些文件出现 `station_code`、`source_dir`、`station_field_name`、`send_station_code`，必须判断是：

- [ ] 应删除的旧字段。
- [ ] 应改成 `flow` / `filePath` 的字段。
- [ ] 迁移说明里允许保留的旧字段名称。

除迁移说明外，不允许继续保留旧字段。

### 10.2 需要确认无字段残留的非核心测试

- [ ] `tests/test_date_window.py`
- [ ] `tests/test_share_auth.py`
- [ ] `tests/test_log_store.py`
- [ ] `tests/test_project_structure.py`

这些测试不一定直接涉及工站字段，但如果测试夹具、示例配置或断言里出现旧字段，也必须同步改成 `flow`、`filePath`。

### 10.3 全项目旧字段扫描

执行：

```powershell
rg -n "station_code|source_dir|station_field_name|send_station_code|upload_station_field|stationCode" .
```

预期：

- [ ] `zk_impedance_upload/` 下不出现旧字段。
- [ ] `station_config_web/` 下不出现旧字段。
- [ ] `tests/` 下不出现旧字段。
- [ ] `config.example.json`、`config.dry_run.small.json`、`web_config.example.json` 下不出现旧字段。
- [ ] SQL 建表、种子、更新脚本中不出现旧字段，迁移脚本除外。
- [ ] README 和旧需求文档如继续保留历史说明，必须明确标注为“历史字段/迁移前字段”，不能作为当前方案。

### 10.4 全项目新字段扫描

执行：

```powershell
rg -n "\bflow\b|filePath" zk_impedance_upload station_config_web tests docs config.example.json config.dry_run.small.json web_config.example.json README.md
```

预期：

- [ ] 自动上传链路能看到 `flow`、`filePath`。
- [ ] 监听链路如记录工站或文件路径，使用 `flow`、`filePath`。
- [ ] 自主配置工站 Web 和 SQL 使用 `flow`。
- [ ] 测试用例覆盖 `flow`、`filePath`。
- [ ] 文档和示例配置只描述当前统一字段。

### 10.5 文件覆盖验收清单

改造完成前，下面命令列出的文件都必须被审查过：

```powershell
rg --files
```

执行人必须把 `rg --files` 输出的每个文件逐一归类，审查结果只允许分成三类：

- [ ] 已修改：文件原本使用旧字段，已改为 `flow`、`filePath`。
- [ ] 无需修改：文件与工站字段、上传字段、路径日志无关。
- [ ] 迁移保留：仅数据库迁移说明中保留旧字段名，用于从旧结构迁移到新结构。

任何未归类文件都视为漏审，不能进入联调。

当前项目文件审查表如下，后续新增文件也必须追加到此清单或重新生成清单：

| 文件 | 分类 | 审查要求 |
|---|---|---|
| `README.md` | 已修改 | 当前说明只描述 `flow`、`filePath` |
| `notes.md` | 无需修改/已修改 | 如保留历史内容，必须标注为历史记录 |
| `config.example.json` | 已修改 | 删除旧上传开关，`scan.targets[].flow` |
| `config.dry_run.small.json` | 已修改 | 删除旧上传开关，`scan.targets[].flow` |
| `web_config.example.json` | 无需修改/已修改 | 如涉及表字段说明，必须使用 `flow` |
| `requirements.txt` | 无需修改 | 确认无旧字段文本 |
| `run_upload.py` | 无需修改/已修改 | 自动上传入口不出现旧字段 |
| `run_watcher.py` | 无需修改/已修改 | 监听入口不出现旧字段 |
| `diag_scan.py` | 已修改 | 诊断输出使用 `flow`、`filePath` |
| `zk_impedance_upload/__init__.py` | 无需修改 | 确认无旧字段文本 |
| `zk_impedance_upload/cli.py` | 已修改 | 配置检查和入口逻辑不出现旧字段 |
| `zk_impedance_upload/config.py` | 已修改 | 配置模型统一 `flow`，删除旧上传配置 |
| `zk_impedance_upload/date_window.py` | 无需修改 | 确认无旧字段文本 |
| `zk_impedance_upload/dedupe.py` | 已修改 | 去重 key 使用 `flow` |
| `zk_impedance_upload/exceptions.py` | 无需修改 | 确认无旧字段文本 |
| `zk_impedance_upload/fingerprint.py` | 已修改 | 历史记录使用 `flow`、`filePath` |
| `zk_impedance_upload/log_store.py` | 无需修改/已修改 | 日志写入不引入旧字段 |
| `zk_impedance_upload/parser.py` | 已修改 | `ParsedFile` 使用 `flow`、`filePath` |
| `zk_impedance_upload/runner.py` | 已修改 | 上传日志和上传调用使用 `flow`、`filePath` |
| `zk_impedance_upload/scanner.py` | 已修改 | `CandidateFile` 使用 `flow`、`filePath` |
| `zk_impedance_upload/share_auth.py` | 无需修改 | 确认无旧字段文本 |
| `zk_impedance_upload/station_config.py` | 已修改 | 数据库读取固定 `flow` |
| `zk_impedance_upload/uploader.py` | 已修改 | multipart 固定发送 `flow`、`filePath` |
| `zk_impedance_upload/watcher.py` | 已修改 | 监听配置和日志使用 `flow`、`filePath` |
| `station_config_web/__init__.py` | 无需修改 | 确认无旧字段文本 |
| `station_config_web/app.py` | 已修改 | 表单和上下文使用 `flow` |
| `station_config_web/config.py` | 无需修改/已修改 | 如涉及字段说明，必须使用 `flow` |
| `station_config_web/repository.py` | 已修改 | SQL 和数据类使用 `flow` |
| `station_config_web/README.md` | 已修改 | Web 配置说明使用 `flow` |
| `station_config_web/static/style.css` | 无需修改 | 确认无旧字段文本 |
| `station_config_web/templates/station_config_form.html` | 已修改 | input name 使用 `flow` |
| `station_config_web/templates/station_config_list.html` | 已修改 | 列表字段使用 `flow` |
| `docs/backend-field-alignment-task-list.md` | 迁移保留 | 允许出现旧字段作为迁移说明 |
| `docs/station-directory-binding-requirement.md` | 已修改/迁移保留 | 当前方案使用 `flow`，历史字段需标注 |
| `docs/station-directory-code-mapping.md` | 已修改/迁移保留 | 查询和更新 SQL 使用 `flow` |
| `docs/station-directory-config-phase2-requirement.md` | 已修改/迁移保留 | 表结构和配置说明使用 `flow` |
| `docs/sql/create_station_directory_config.sql` | 已修改 | 建表字段使用 `flow` |
| `docs/sql/seed_station_directory_config.sql` | 已修改 | 插入字段使用 `flow` |
| `docs/sql/update_station_code_from_station_name.sql` | 已修改/迁移保留 | 应重命名为 `update_flow_from_station_name.sql` |
| `tests/test_config.py` | 已修改 | 配置测试使用 `flow` |
| `tests/test_date_window.py` | 无需修改 | 确认无旧字段文本 |
| `tests/test_dedupe.py` | 已修改 | 去重测试使用 `flow` |
| `tests/test_fingerprint.py` | 已修改 | 历史记录测试使用 `flow`、`filePath` |
| `tests/test_log_store.py` | 无需修改/已修改 | 如有日志夹具，使用 `flow`、`filePath` |
| `tests/test_parser.py` | 已修改 | 解析测试使用 `flow`、`filePath` |
| `tests/test_project_structure.py` | 无需修改/已修改 | 示例配置断言无旧字段 |
| `tests/test_runner.py` | 已修改 | 上传流程测试使用 `flow`、`filePath` |
| `tests/test_scanner.py` | 已修改 | 扫描测试使用 `flow`、`filePath` |
| `tests/test_share_auth.py` | 无需修改 | 确认无旧字段文本 |
| `tests/test_station_config.py` | 已修改 | 数据库配置测试使用 `flow` |
| `tests/test_station_config_web_app.py` | 已修改 | Web 表单测试使用 `flow` |
| `tests/test_station_config_web_config.py` | 无需修改/已修改 | 如有表字段说明，使用 `flow` |
| `tests/test_station_config_web_repository.py` | 已修改 | Web repository 测试使用 `flow` |
| `tests/test_uploader.py` | 已修改 | multipart 测试固定 `flow`、`filePath` |
| `tests/test_watcher.py` | 已修改 | 监听测试如涉及工站/路径，使用 `flow`、`filePath` |

文件覆盖验收失败条件：

- [ ] `rg --files` 出现了表中没有归类的新文件。
- [ ] 任一“已修改”文件仍包含旧字段且不是迁移说明。
- [ ] 任一“无需修改”文件包含旧字段。
- [ ] 任一“迁移保留”文件没有明确说明旧字段仅用于迁移前/历史说明。
- [ ] `rg -n "station_code|source_dir|station_field_name|send_station_code|upload_station_field|stationCode" .` 的结果没有逐条解释。

## 11. 联调测试任务

- [ ] 使用接口：

```text
POST /service-qms/file/importImpedanceData
Content-Type: multipart/form-data

file=<Excel 文件>
flow=<工站代码>
filePath=<文件完整路径>
```

- [ ] 使用配置检查确认字段统一：

```powershell
python run_upload.py --config config.json --check-config
```

- [ ] 使用诊断扫描确认输出统一：

```powershell
python diag_scan.py --config config.json
```

- [ ] 选择 1 个小文件真实上传。
- [ ] 在后端日志或接口工具中确认实际 multipart 字段只有：
  - [ ] `file`
  - [ ] `flow`
  - [ ] `filePath`
- [ ] 确认请求中不再出现：
  - [ ] `station_code`
  - [ ] `source_dir`
  - [ ] `stationFieldName`
- [ ] 确认后端能按 `flow` 查询导入结果。

## 12. 上线步骤

- [ ] 第一步：备份当前数据库表和生产配置。
- [ ] 第二步：执行数据库字段迁移，将 `station_code` 改为 `flow`。
- [ ] 第三步：更新生产 `config.json`，将 `scan.targets[].station_code` 改为 `scan.targets[].flow`。
- [ ] 第四步：部署代码。
- [ ] 第五步：执行配置检查。
- [ ] 第六步：执行 dry-run 或诊断扫描，确认日志字段为 `flow`、`filePath`。
- [ ] 第七步：执行单文件真实上传。
- [ ] 第八步：确认后端收到 `flow` 和 `filePath`。
- [ ] 第九步：恢复正常定时任务或 watcher。

## 13. 回滚方案

本次目标是不保留兼容代码，因此回滚只能走版本回退和数据库备份恢复。

- [ ] 回滚代码到改造前版本。
- [ ] 恢复改造前 `config.json`。
- [ ] 如果数据库字段已改名，需要执行反向迁移：

```sql
EXEC sp_rename
  'dbo.station_directory_config.flow',
  'station_code',
  'COLUMN';
```

- [ ] 恢复旧索引名或重建旧索引。
- [ ] 回滚后重新执行原版本配置检查和 dry-run。

## 14. 验收标准

- [ ] 代码中不再出现 `station_code`。
- [ ] 代码中不再出现 `source_dir`。
- [ ] 配置文件中不再出现 `station_code`。
- [ ] 日志和历史记录中不再出现 `station_code`、`source_dir`。
- [ ] 数据库配置表使用 `flow` 字段。
- [ ] Web 配置工具使用 `flow` 字段。
- [ ] 上传请求固定包含 `file`，`flow`、`filePath` 有值才提交。
- [ ] 项目不再包含 `upload.station_field_name`、`upload.send_station_code`。
- [ ] 全量单元测试通过。
- [ ] 后端联调确认可按 `flow` 正常接收和查询。
