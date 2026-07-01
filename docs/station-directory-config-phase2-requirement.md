# 工站目录配置第二阶段开发需求文档

## 1. 文档目的

本文档用于指导“工站目录绑定需求”的第二阶段开发。

第一阶段已经完成：Python 程序可以在 `config.json` 中通过 `scan.targets` 配置“工站代码 + 扫描目录”，扫描、解析、上传、日志、去重记录都可以带上 `station_code`。

第二阶段的目标是：在不依赖后端业务导入字段最终名称的前提下，先把 Python 侧的“工站目录配置来源”设计完整，使后续可以从数据库配置表读取工站目录绑定关系，同时保留 JSON 配置作为兜底。

## 2. 当前已知前提

1. 当前项目是 Python 采集上传程序，不是后端服务项目。
2. 第一阶段内部统一字段为 `station_code`。
3. 后端上传接口最终接收工站字段名暂不确定。
4. 当前已经支持通过配置控制上传字段：

```json
{
  "upload": {
    "send_station_code": true,
    "station_field_name": "station_code"
  }
}
```

5. 如果后端最终字段不是 `station_code`，只需要改 `upload.station_field_name`，例如：

```json
{
  "upload": {
    "send_station_code": true,
    "station_field_name": "stationCode"
  }
}
```

6. 如果后端暂时不接收工站字段，可以设置：

```json
{
  "upload": {
    "send_station_code": false
  }
}
```

此时 Python 本地日志、去重记录、扫描结果仍然保留 `station_code`，只是上传请求不发送该字段。

## 3. 第二阶段目标

第二阶段要解决的问题不是“后端业务表怎么存上传结果”，而是“Python 程序从哪里读取工站目录绑定配置”。

第二阶段完成后，用户可以选择：

1. 继续从 `config.json` 读取工站目录配置。
2. 从数据库新表读取工站目录配置。
3. 优先从数据库读取，如果数据库不可用或配置为空，则回退使用 `config.json`。

从用户角度看，第二阶段要达到：

1. 运维或实施人员可以把工站目录绑定关系维护到数据库表中。
2. Python 程序启动或执行任务时自动读取有效配置。
3. 数据库配置异常时可以清楚报错或自动回退，不影响已有 JSON 配置方案。
4. 后续如果再做 Web 配置页面，可以直接维护这张配置表。

## 4. 第二阶段不做的内容

第二阶段暂不做以下内容：

1. 不修改后端上传接口的业务处理逻辑。
2. 不修改后端“阻抗数据导入结果表”的字段。
3. 不新增后端查询接口。
4. 不新增前端配置页面。
5. 不从 Excel 内容中识别工站。
6. 不做工站主数据管理表。
7. 不把数据库密码写入公开示例配置。

这些内容可以作为第三阶段或后端联调阶段处理。

## 5. 用户使用流程

### 5.1 当前 JSON 模式

用户继续维护 `config.json`：

```json
{
  "scan": {
    "targets": [
      {
        "station_code": "A10",
        "dir": "ExampleStationDirectoryA",
        "enabled": true
      }
    ]
  },
  "station_config": {
    "source": "json"
  }
}
```

程序行为：

1. 只读取 `scan.targets`。
2. 不连接数据库。
3. 行为与第一阶段一致。

### 5.2 数据库模式

用户把配置写入数据库表：

```sql
INSERT INTO station_directory_config
  (station_code, station_name, directory_path, enabled, sort_order, remark)
VALUES
  ('A10', 'V-CUT', 'ExampleStationDirectoryA', 1, 10, '示例目录'),
  ('A50', '阻抗', 'ExampleStationDirectoryB', 1, 20, '示例目录');
```

`config.json` 设置为：

```json
{
  "station_config": {
    "source": "db",
    "db": {
      "enabled": true,
      "driver": "sqlserver",
      "odbc_driver": "ODBC Driver 17 for SQL Server",
      "host": "127.0.0.1",
      "port": 1433,
      "database": "QMS",
      "username": "sa",
      "password": "password",
      "table": "station_directory_config",
      "connect_timeout_seconds": 5,
      "query_timeout_seconds": 10
    }
  }
}
```

程序行为：

1. 连接数据库。
2. 查询 `station_directory_config` 表。
3. 只读取 `enabled = 1` 的配置。
4. 把数据库记录转换成第一阶段已经支持的 `ScanTargetConfig`。
5. 后续扫描、解析、上传、日志逻辑不需要关心配置来自 JSON 还是数据库。

### 5.3 数据库优先、JSON 兜底模式

推荐上线初期使用该模式：

```json
{
  "station_config": {
    "source": "db_then_json",
    "on_db_error": "fallback_to_json"
  }
}
```

程序行为：

1. 优先读取数据库。
2. 如果数据库连接失败，回退使用 `scan.targets`。
3. 如果数据库查询成功但没有有效配置，也回退使用 `scan.targets`。
4. 日志中记录本次实际使用的配置来源。

## 6. 数据库新表设计

### 6.1 表名

推荐表名：

```text
station_directory_config
```

中文含义：

```text
工站目录绑定配置表
```

### 6.2 建表 SQL

推荐 SQL Server 建表语句如下：

```sql
CREATE TABLE station_directory_config (
  id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_station_directory_config PRIMARY KEY,
  station_code NVARCHAR(50) NOT NULL,
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
  ON station_directory_config (directory_path);

CREATE INDEX IX_station_directory_config_station_code
  ON station_directory_config (station_code);

CREATE INDEX IX_station_directory_config_enabled_sort
  ON station_directory_config (enabled, sort_order, id);

EXEC sys.sp_addextendedproperty
  @name = N'MS_Description',
  @value = N'工站目录绑定配置表',
  @level0type = N'SCHEMA', @level0name = N'dbo',
  @level1type = N'TABLE', @level1name = N'station_directory_config';

GO

CREATE TRIGGER TR_station_directory_config_set_updated_at
ON station_directory_config
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;

  UPDATE target
  SET updated_at = SYSDATETIME()
  FROM station_directory_config AS target
  INNER JOIN inserted AS source
    ON target.id = source.id;
END;
```

### 6.3 字段说明

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---:|---:|---|---|
| `id` | BIGINT | 是 | `1` | 主键，自增 |
| `station_code` | VARCHAR(50) | 是 | `A10` | 工站代码，Python 内部统一使用该字段 |
| `station_name` | VARCHAR(100) | 否 | `V-CUT` | 工站名称，方便人工查看，不参与核心逻辑 |
| `directory_path` | VARCHAR(500) | 是 | `ExampleStationDirectoryA` | 相对 `share.root` 的目录路径 |
| `enabled` | BIT | 是 | `1` | `1` 启用，`0` 停用 |
| `sort_order` | INT | 是 | `10` | 排序字段 |
| `remark` | VARCHAR(500) | 否 | `示例目录` | 备注 |
| `created_by` | VARCHAR(50) | 否 | `admin` | 创建人 |
| `created_at` | DATETIME | 是 | `2026-06-28 10:00:00` | 创建时间 |
| `updated_by` | VARCHAR(50) | 否 | `admin` | 更新人 |
| `updated_at` | DATETIME | 是 | `2026-06-28 10:00:00` | 更新时间 |

### 6.4 为什么目录路径要唯一

`directory_path` 建议唯一：

```sql
UNIQUE KEY uk_directory_path (directory_path)
```

原因：

1. 一个目录只能属于一个工站。
2. 如果同一个目录被绑定到多个工站，程序无法判断目录中的文件到底属于哪个工站。
3. 在数据库层加唯一索引，可以提前阻止错误配置。

允许的配置：

```text
A10 -> 目录A
A10 -> 目录B
A50 -> 目录C
```

不允许的配置：

```text
A10 -> 目录A
A50 -> 目录A
```

### 6.5 为什么不新建工站主表

第二阶段暂不建议新建工站主表。

原因：

1. 当前核心需求只是让 Python 知道“目录属于哪个工站”。
2. 后端现有系统是否已有工站表暂不确定。
3. 如果现在强行设计工站主表，可能和后端已有模型冲突。
4. `station_name` 已经能满足人工识别的基本需要。

后续如果后端确认需要统一工站主数据，可以再新增：

```text
station_info
```

或接入后端已有工站表。

## 7. 数据库初始化脚本

建议新增 SQL 文件：

```text
docs/sql/create_station_directory_config.sql
```

文件内容：

```sql
CREATE TABLE station_directory_config (
  id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_station_directory_config PRIMARY KEY,
  station_code NVARCHAR(50) NOT NULL,
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
  ON station_directory_config (directory_path);

CREATE INDEX IX_station_directory_config_station_code
  ON station_directory_config (station_code);

CREATE INDEX IX_station_directory_config_enabled_sort
  ON station_directory_config (enabled, sort_order, id);

GO

CREATE TRIGGER TR_station_directory_config_set_updated_at
ON station_directory_config
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;

  UPDATE target
  SET updated_at = SYSDATETIME()
  FROM station_directory_config AS target
  INNER JOIN inserted AS source
    ON target.id = source.id;
END;
```

示例数据可以单独放到：

```text
docs/sql/seed_station_directory_config.sql
```

文件内容：

```sql
INSERT INTO station_directory_config
  (station_code, station_name, directory_path, enabled, sort_order, remark, created_by)
VALUES
  ('A10', 'V-CUT', 'ExampleStationDirectoryA', 1, 10, '示例目录', 'system'),
  ('A50', '阻抗', 'ExampleStationDirectoryB', 1, 20, '示例目录', 'system');
```

## 8. 查询 SQL 约定

Python 程序读取配置时使用：

```sql
SELECT
  station_code,
  station_name,
  directory_path,
  enabled,
  sort_order
FROM station_directory_config
WHERE enabled = 1
ORDER BY sort_order ASC, id ASC;
```

读取后转换为：

```python
ScanTargetConfig(
    station_code=row["station_code"],
    dir=row["directory_path"],
    enabled=True,
)
```

注意：

1. `station_name` 只用于日志或调试，不影响扫描。
2. `directory_path` 对应第一阶段配置中的 `dir`。
3. `enabled = 0` 的记录不进入扫描。

## 9. 配置文件设计

### 9.1 新增配置节点

建议在 `config.json` 新增顶层节点：

```json
{
  "station_config": {
    "source": "json",
    "on_db_error": "fallback_to_json",
    "db": {
      "enabled": false,
      "driver": "sqlserver",
      "odbc_driver": "ODBC Driver 17 for SQL Server",
      "host": "127.0.0.1",
      "port": 1433,
      "database": "QMS",
      "username": "sa",
      "password": "password",
      "table": "station_directory_config",
      "connect_timeout_seconds": 5,
      "query_timeout_seconds": 10
    }
  }
}
```

### 9.2 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|---|
| `station_config.source` | string | 否 | `json` | 配置来源 |
| `station_config.on_db_error` | string | 否 | `raise` | 数据库异常处理方式 |
| `station_config.db.enabled` | boolean | 否 | `false` | 是否启用数据库配置 |
| `station_config.db.driver` | string | 否 | `sqlserver` | 数据库类型 |
| `station_config.db.odbc_driver` | string | 否 | `ODBC Driver 17 for SQL Server` | SQL Server ODBC 驱动名称 |
| `station_config.db.host` | string | db 模式必填 | 无 | 数据库地址 |
| `station_config.db.port` | int | db 模式必填 | `1433` | 数据库端口 |
| `station_config.db.database` | string | db 模式必填 | 无 | 数据库名 |
| `station_config.db.username` | string | db 模式必填 | 无 | 数据库用户名 |
| `station_config.db.password` | string | db 模式必填 | 无 | 数据库密码 |
| `station_config.db.table` | string | 否 | `station_directory_config` | 配置表名 |
| `station_config.db.connect_timeout_seconds` | int | 否 | `5` | 连接超时时间 |
| `station_config.db.query_timeout_seconds` | int | 否 | `10` | 查询超时时间 |

### 9.3 source 可选值

| 值 | 含义 | 推荐场景 |
|---|---|---|
| `json` | 只读取 `scan.targets` | 当前默认方式、最稳妥 |
| `db` | 只读取数据库配置表 | 数据库配置已经稳定后 |
| `db_then_json` | 优先数据库，失败或为空时回退 JSON | 第二阶段上线初期推荐 |

### 9.4 on_db_error 可选值

| 值 | 含义 |
|---|---|
| `raise` | 数据库异常时直接报错，中断本次任务 |
| `fallback_to_json` | 数据库异常时回退使用 `scan.targets` |

推荐：

1. 开发环境使用 `raise`，方便尽早暴露问题。
2. 生产上线初期使用 `fallback_to_json`，避免数据库配置异常导致任务完全不可用。

## 10. Python 结构设计

### 10.1 config.py 新增数据结构

建议新增：

```python
@dataclass(frozen=True)
class StationDbConfig:
    enabled: bool = False
    driver: str = "sqlserver"
    odbc_driver: str = "ODBC Driver 17 for SQL Server"
    host: str = ""
    port: int = 1433
    database: str = ""
    username: str = ""
    password: str = ""
    table: str = "station_directory_config"
    connect_timeout_seconds: int = 5
    query_timeout_seconds: int = 10


@dataclass(frozen=True)
class StationConfig:
    source: str = "json"
    on_db_error: str = "raise"
    db: StationDbConfig = field(default_factory=StationDbConfig)
```

`AppConfig` 新增：

```python
station_config: StationConfig = field(default_factory=StationConfig)
```

### 10.2 新增 station_config.py

建议新增文件：

```text
zk_impedance_upload/station_config.py
```

职责：

1. 根据 `station_config.source` 决定配置来源。
2. 把数据库记录转换为 `ScanTargetConfig`。
3. 做配置校验。
4. 输出最终有效的 `ScanConfig` 或 `list[ScanTargetConfig]`。

核心函数建议：

```python
def build_effective_scan_targets(
    app_config: AppConfig,
    repository: StationTargetRepository | None = None,
) -> list[ScanTargetConfig]:
    ...
```

### 10.3 Repository 协议

建议定义协议：

```python
class StationTargetRepository(Protocol):
    def load_targets(self, db_config: StationDbConfig) -> list[ScanTargetConfig]:
        ...
```

好处：

1. 单元测试可以用假的 repository，不需要真实数据库。
2. 后续可以替换 SQL Server、接口、文件等数据来源。
3. Python 主流程不直接依赖具体数据库库。

### 10.4 SQL Server 实现

建议新增：

```python
class SqlServerStationTargetRepository:
    def load_targets(self, db_config: StationDbConfig) -> list[ScanTargetConfig]:
        ...
```

依赖库建议：

```text
pyodbc
```

`requirements.txt` 增加：

```text
pyodbc
```

如果暂时不希望引入数据库依赖，可以先完成协议、假实现和配置逻辑，SQL Server 实现放在后续小步补充。

### 10.5 数据库读取伪代码

```python
def load_targets(self, db_config: StationDbConfig) -> list[ScanTargetConfig]:
    connection = pyodbc.connect(
        "DRIVER={%s};SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s;TrustServerCertificate=yes;"
        % (
            db_config.odbc_driver,
            db_config.host,
            db_config.port,
            db_config.database,
            db_config.username,
            db_config.password,
        ),
        timeout=db_config.connect_timeout_seconds,
    )
    try:
        sql = f"""
            SELECT station_code, directory_path
            FROM dbo.station_directory_config
            WHERE enabled = 1
            ORDER BY sort_order ASC, id ASC
        """
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
        return [
            ScanTargetConfig(
                station_code=row.station_code,
                dir=row.directory_path,
                enabled=True,
            )
            for row in rows
        ]
    finally:
        connection.close()
```

注意：

1. 表名不能从用户输入随意拼接到 SQL。
2. 需要校验 `db_config.table` 只能包含字母、数字、下划线。
3. 推荐默认固定表名 `station_directory_config`。

## 11. 配置合并与回退规则

### 11.1 json 模式

```text
source = json
```

规则：

1. 不连接数据库。
2. 使用 `config.scan.targets`。
3. 如果 `scan.targets` 为空，再按第一阶段兼容逻辑使用 `scan.target_dirs`。

### 11.2 db 模式

```text
source = db
```

规则：

1. 必须连接数据库。
2. 数据库连接失败，中断任务并报错。
3. 数据库查询失败，中断任务并报错。
4. 数据库查询结果为空，中断任务并报错。
5. 不回退 JSON。

适合数据库配置已经稳定后使用。

### 11.3 db_then_json 模式

```text
source = db_then_json
```

规则：

1. 先尝试读取数据库。
2. 数据库读取成功且返回至少一条有效配置，则使用数据库配置。
3. 数据库连接失败，回退 JSON。
4. 数据库查询失败，回退 JSON。
5. 数据库返回空配置，回退 JSON。
6. 回退时日志中必须记录原因。

适合第二阶段上线初期使用。

## 12. 校验规则

无论配置来自 JSON 还是数据库，都必须执行相同校验。

### 12.1 station_code 校验

规则：

1. 不能为空。
2. 去掉前后空格后不能为空。
3. 建议只允许字母、数字、下划线、短横线。

建议正则：

```text
^[A-Za-z0-9_-]+$
```

### 12.2 directory_path 校验

规则：

1. 不能为空。
2. 去掉前后空格后不能为空。
3. 必须是相对 `share.root` 的路径。
4. 不建议允许绝对路径。
5. 不允许重复绑定。

### 12.3 enabled 校验

规则：

1. JSON 配置中缺省时默认 `true`。
2. 数据库配置中只读取 `enabled = 1`。
3. `enabled = 0` 的记录不扫描。

### 12.4 重复目录校验

规则：

1. 同一个 `directory_path` 只能出现一次。
2. 如果出现重复，应直接报错。
3. 错误信息必须包含重复的目录路径。

示例错误：

```text
Duplicate station directory config: ExampleStationDirectoryA
```

### 12.5 同一工站多个目录

允许：

```text
A10 -> 目录A
A10 -> 目录B
```

这是正常业务场景，不应报错。

## 13. 与现有流程的集成点

### 13.1 run_upload.py

执行上传任务前：

1. 加载 `AppConfig`。
2. 根据 `station_config` 构建最终扫描目标。
3. 把最终扫描目标交给 scanner。

### 13.2 runner.py

建议在 runner 初始化或执行前拿到最终有效 targets。

运行日志建议增加：

```json
{
  "station_config_source": "db_then_json",
  "effective_station_config_source": "db",
  "station_target_count": 2
}
```

如果发生回退：

```json
{
  "station_config_source": "db_then_json",
  "effective_station_config_source": "json",
  "station_config_fallback_reason": "database connection failed"
}
```

### 13.3 watcher.py

监听模式启动时也要使用相同的有效配置构建逻辑。

规则：

1. watcher 启动时读取一次配置。
2. 第二阶段暂不要求运行中自动刷新数据库配置。
3. 如果要刷新配置，先重启 watcher。

### 13.4 diag_scan.py

诊断扫描工具也应该支持数据库配置来源。

验收方式：

```powershell
python diag_scan.py --config config.json
```

输出中应能看到最终使用的配置来源和扫描目录数量。

## 14. 日志要求

第二阶段必须保证问题可排查。

### 14.1 正常使用数据库

日志建议包含：

```json
{
  "event": "station_config_loaded",
  "source": "db",
  "target_count": 2
}
```

### 14.2 数据库失败后回退 JSON

日志建议包含：

```json
{
  "event": "station_config_fallback",
  "source": "db_then_json",
  "fallback_to": "json",
  "reason": "database connection failed"
}
```

### 14.3 数据库配置为空后回退 JSON

日志建议包含：

```json
{
  "event": "station_config_fallback",
  "source": "db_then_json",
  "fallback_to": "json",
  "reason": "database returned no enabled targets"
}
```

## 15. 异常处理

### 15.1 数据库连接失败

`source = db`：

```text
直接报错，中断任务。
```

`source = db_then_json`：

```text
记录日志，回退 JSON。
```

### 15.2 数据库表不存在

`source = db`：

```text
直接报错，中断任务。
```

`source = db_then_json`：

```text
记录日志，回退 JSON。
```

### 15.3 数据库字段不存在

如果 `station_directory_config` 缺少字段，例如 `directory_path`：

`source = db`：

```text
直接报错，中断任务。
```

`source = db_then_json`：

```text
记录日志，回退 JSON。
```

### 15.4 数据库配置重复

如果数据库中出现重复目录，虽然唯一索引理论上会拦住，但 Python 仍应校验。

无论什么模式，只要最终使用的配置存在重复目录，都应报错。

## 16. 测试用例设计

### 16.1 test_config.py

新增测试：

1. 能解析 `station_config.source = json`。
2. 能解析 `station_config.source = db`。
3. 能解析 `station_config.source = db_then_json`。
4. `station_config` 缺省时默认 `source = json`。
5. `db.port` 缺省时默认 `1433`。
6. `db.table` 缺省时默认 `station_directory_config`。
7. 非法 `source` 报错。
8. 非法 `on_db_error` 报错。

### 16.2 test_station_config.py

建议新增测试文件：

```text
tests/test_station_config.py
```

测试内容：

1. `json` 模式使用 `scan.targets`。
2. `json` 模式不调用 repository。
3. `db` 模式调用 repository。
4. `db` 模式 repository 返回配置后正常使用。
5. `db` 模式 repository 抛异常时任务报错。
6. `db` 模式 repository 返回空列表时报错。
7. `db_then_json` 模式数据库成功时使用数据库配置。
8. `db_then_json` 模式数据库异常时回退 JSON。
9. `db_then_json` 模式数据库为空时回退 JSON。
10. 重复 `directory_path` 报错。
11. 空 `station_code` 报错。
12. 空 `directory_path` 报错。

### 16.3 test_runner.py

补充测试：

1. runner 使用最终有效 targets。
2. 数据库配置返回的 targets 能进入扫描。
3. 回退 JSON 后仍能完成 dry-run。
4. 日志中包含配置来源。

### 16.4 test_watcher.py

补充测试：

1. watcher 启动时使用最终有效 targets。
2. `db_then_json` 回退时 watcher 仍能启动。

### 16.5 test_diag_scan.py

如果当前已有诊断脚本测试，可补充：

1. 诊断扫描显示配置来源。
2. 诊断扫描显示有效目录数量。

## 17. 开发步骤

建议按以下顺序开发。

### 步骤 1：补配置结构

修改：

```text
zk_impedance_upload/config.py
```

新增：

1. `StationDbConfig`
2. `StationConfig`
3. `AppConfig.station_config`

同时补测试：

```text
tests/test_config.py
```

### 步骤 2：新增配置来源模块

新增：

```text
zk_impedance_upload/station_config.py
```

先实现：

1. `StationTargetRepository` 协议。
2. `build_effective_scan_targets()`。
3. JSON 模式。
4. DB 模式的 repository 注入。
5. DB 失败回退 JSON。

先不一定要连真实 SQL Server。

### 步骤 3：补假 repository 测试

新增：

```text
tests/test_station_config.py
```

用假 repository 模拟：

1. 数据库返回配置。
2. 数据库抛异常。
3. 数据库返回空。

### 步骤 4：接入 runner

修改：

```text
zk_impedance_upload/runner.py
```

目标：

1. runner 使用最终有效 targets。
2. 扫描逻辑不需要知道配置来自哪里。
3. 日志记录配置来源。

### 步骤 5：接入 watcher

修改：

```text
zk_impedance_upload/watcher.py
```

目标：

1. watcher 启动时使用同一套配置来源逻辑。
2. 行为与 runner 保持一致。

### 步骤 6：接入 diag_scan.py

修改：

```text
diag_scan.py
```

目标：

1. 诊断扫描能验证数据库配置。
2. 输出有效 targets 数量。
3. 输出实际配置来源。

### 步骤 7：实现 SQL Server repository

修改或新增：

```text
zk_impedance_upload/station_config.py
```

或拆分：

```text
zk_impedance_upload/station_repository.py
```

实现真实 SQL Server 查询。

修改：

```text
requirements.txt
```

增加：

```text
pyodbc
```

### 步骤 8：更新示例配置

修改：

```text
config.example.json
```

增加：

```json
{
  "station_config": {
    "source": "json",
    "on_db_error": "fallback_to_json",
    "db": {
      "enabled": false,
      "driver": "sqlserver",
      "odbc_driver": "ODBC Driver 17 for SQL Server",
      "host": "127.0.0.1",
      "port": 1433,
      "database": "YOUR_DATABASE",
      "username": "YOUR_DB_USERNAME",
      "password": "YOUR_DB_PASSWORD",
      "table": "station_directory_config",
      "connect_timeout_seconds": 5,
      "query_timeout_seconds": 10
    }
  }
}
```

注意：

1. 示例配置不能放真实密码。
2. `config.json` 是本地私有配置，不应提交真实密码。

### 步骤 9：更新 README

修改：

```text
README.md
```

增加说明：

1. JSON 模式怎么用。
2. DB 模式怎么用。
3. DB 优先 JSON 兜底怎么用。
4. 如何建表。
5. 如何回滚到 JSON。

### 步骤 10：全量测试

执行：

```powershell
python -m unittest discover -s tests -v
```

预期：

```text
全部测试通过
```

## 18. 上线步骤

### 18.1 第一轮：保持 JSON 模式

配置：

```json
{
  "station_config": {
    "source": "json"
  }
}
```

执行：

```powershell
python -m unittest discover -s tests -v
python run_upload.py --config config.json --check-config
```

目标：

1. 确认第二阶段代码没有破坏第一阶段功能。
2. 确认不连接数据库也能正常运行。

### 18.2 第二轮：创建数据库表

执行建表 SQL：

```sql
CREATE TABLE station_directory_config (
  id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_station_directory_config PRIMARY KEY,
  station_code NVARCHAR(50) NOT NULL,
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
  ON station_directory_config (directory_path);

CREATE INDEX IX_station_directory_config_station_code
  ON station_directory_config (station_code);

CREATE INDEX IX_station_directory_config_enabled_sort
  ON station_directory_config (enabled, sort_order, id);

GO

CREATE TRIGGER TR_station_directory_config_set_updated_at
ON station_directory_config
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;

  UPDATE target
  SET updated_at = SYSDATETIME()
  FROM station_directory_config AS target
  INNER JOIN inserted AS source
    ON target.id = source.id;
END;
```

### 18.3 第三轮：插入配置

示例：

```sql
INSERT INTO station_directory_config
  (station_code, station_name, directory_path, enabled, sort_order, remark, created_by)
VALUES
  ('A10', 'V-CUT', 'ExampleStationDirectoryA', 1, 10, '示例目录', 'system'),
  ('A50', '阻抗', 'ExampleStationDirectoryB', 1, 20, '示例目录', 'system');
```

### 18.4 第四轮：切换 db_then_json

配置：

```json
{
  "station_config": {
    "source": "db_then_json",
    "on_db_error": "fallback_to_json",
    "db": {
      "enabled": true,
      "driver": "sqlserver",
      "odbc_driver": "ODBC Driver 17 for SQL Server",
      "host": "127.0.0.1",
      "port": 1433,
      "database": "YOUR_DATABASE",
      "username": "YOUR_DB_USERNAME",
      "password": "YOUR_DB_PASSWORD",
      "table": "station_directory_config",
      "connect_timeout_seconds": 5,
      "query_timeout_seconds": 10
    }
  }
}
```

执行：

```powershell
python run_upload.py --config config.json --check-config
```

目标：

1. 能连数据库时使用数据库配置。
2. 数据库异常时能回退 JSON。
3. 日志中能看出实际配置来源。

### 18.5 第五轮：dry-run 验证

设置：

```json
{
  "upload": {
    "dry_run": true
  }
}
```

执行：

```powershell
python run_upload.py --config config.json
```

检查日志：

1. 文件是否被扫描到。
2. 每个文件的 `station_code` 是否正确。
3. `source_dir` 是否正确。
4. 是否有误扫目录。
5. 是否有缺失目录。

### 18.6 第六轮：真实上传

确认无误后设置：

```json
{
  "upload": {
    "dry_run": false
  }
}
```

执行真实上传。

## 19. 回滚方案

### 19.1 配置级回滚

如果数据库配置异常，最快回滚方式是改配置：

```json
{
  "station_config": {
    "source": "json"
  }
}
```

然后继续使用 `scan.targets`。

### 19.2 关闭上传工站字段

如果后端接口不支持工站字段：

```json
{
  "upload": {
    "send_station_code": false
  }
}
```

这样本地仍记录工站，但上传请求不带工站字段。

### 19.3 Git 回滚

当前已有安全备份：

```text
branch: codex/zk-safety-backup
tag: backup-before-station-binding-20260626
```

如果代码需要整体回退，可以基于该分支或 tag 检出。

## 20. 验收标准

第二阶段完成后，应满足以下验收项：

1. 默认不配置 `station_config` 时，程序行为与第一阶段一致。
2. `station_config.source = json` 时，只使用 `scan.targets`。
3. `station_config.source = db` 时，可以从数据库读取配置。
4. `station_config.source = db` 且数据库异常时，任务明确失败。
5. `station_config.source = db_then_json` 且数据库正常时，使用数据库配置。
6. `station_config.source = db_then_json` 且数据库异常时，回退 JSON。
7. `station_config.source = db_then_json` 且数据库无有效配置时，回退 JSON。
8. 数据库配置读取后，扫描出来的文件能带正确 `station_code`。
9. 上传逻辑仍使用第一阶段的 `upload.station_field_name`。
10. 后端字段未知时，不影响第二阶段开发完成。
11. 单元测试通过。
12. README 和示例配置已更新。

## 21. 与后端字段问题的关系

第二阶段不依赖后端最终字段名。

原因：

1. Python 内部字段固定为 `station_code`。
2. 数据库配置表字段固定为 `station_code`。
3. 上传给后端的表单字段名已经可配置。

后端最终如果确认字段名为：

```text
station_code
```

则保持默认配置。

后端最终如果确认字段名为：

```text
stationCode
```

则修改：

```json
{
  "upload": {
    "station_field_name": "stationCode"
  }
}
```

后端如果暂时不收：

```json
{
  "upload": {
    "send_station_code": false
  }
}
```

因此，后端字段未知不会阻塞第二阶段 Python 侧开发。

## 22. 后续第三阶段建议

第二阶段完成后，后续可以继续做：

1. 后端导入接口确认并保存工站字段。
2. 后端业务表新增工站字段或映射字段。
3. 后端按工站查询已上传数据。
4. Web 页面维护 `station_directory_config`。
5. 工站主数据表。
6. 配置变更审计记录。
7. watcher 运行中自动刷新数据库配置。

## 23. 推荐开发结论

推荐第二阶段按以下策略完成：

1. 先做 Python 侧配置来源抽象。
2. 建立 `station_directory_config` 数据库配置表。
3. 保留 `config.json` 作为兜底。
4. 上线初期使用 `db_then_json`。
5. 后端字段未确认前，不改 Python 内部字段名。
6. 后端字段确认后，只调整 `upload.station_field_name`。

这样做的好处是：

1. 不阻塞当前 Python 开发。
2. 不强依赖后端字段。
3. 有清晰回滚路径。
4. 后续 Web 配置页面可以直接复用数据库表。
5. 对用户来说，维护目录和工站关系会比手写 JSON 更直观。
