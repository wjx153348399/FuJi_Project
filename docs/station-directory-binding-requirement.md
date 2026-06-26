# 工站目录绑定需求开发文档

## 1. 背景

当前项目用于扫描共享盘中的阻抗 Excel 文件，并按日期窗口执行解析、去重、上传和日志记录。

现有逻辑只知道“从哪些目录扫描文件”，但不知道“该目录上传的文件属于哪个工站”。业务侧希望按工站查询已采集/已上传的数据，因此需要在文件上传和日志记录过程中补充工站信息。

本需求的核心是：由用户维护“工站代码”和“目录位置”的对应关系，程序扫描目录时自动给该目录下的文件绑定 `station_code`，并在上传、日志、历史记录中保留该字段。

## 2. 用户目标

用户希望通过配置完成以下事情：

1. 指定某个共享盘目录属于某个工站。
2. 一个工站可以绑定一个或多个目录。
3. 一个目录只能绑定一个工站。
4. 程序扫描到目录下的 Excel 文件后，自动识别其工站代码。
5. 上传文件时，把工站代码一起传给后端接口。
6. 本地日志中能清楚看到每个文件属于哪个工站、来自哪个配置目录。
7. 后续数据库可以根据工站字段进行查询。

## 3. 第一阶段范围

第一阶段先实现配置文件版本，不做图形化配置界面。

用户通过 `config.json` 维护工站目录绑定关系。程序按配置扫描、上传、记录日志。

第一阶段需要实现：

- 支持新的 `scan.targets` 配置。
- 扫描时识别目标目录对应的 `station_code`。
- `CandidateFile` 和 `ParsedFile` 增加工站字段。
- 上传接口 multipart 表单中增加 `station_code` 字段。
- 上传日志、历史记录、汇总信息中记录 `station_code`。
- 去重 key 中纳入 `station_code`，避免不同工站之间误判重复。
- 保留旧 `scan.target_dirs` 的兼容能力。

第一阶段暂不实现：

- Web 配置页面。
- 数据库配置表。
- 自动同步后端数据表结构。
- 从 Excel 文件内容中读取工站。

## 4. 后续阶段范围

后续可以在第一阶段稳定后增加配置界面。

配置界面建议提供：

- 新增工站目录绑定。
- 编辑工站代码。
- 编辑或选择目录。
- 启用/停用配置。
- 校验目录是否存在。
- 校验目录是否重复绑定。
- 保存后写入 `config.json`，或后续改为保存到配置表。

如果后续需要多人维护、审计、权限控制，则可以考虑新建配置表，例如 `station_directory_config`。

## 5. 配置设计

### 5.1 推荐新配置

在 `scan` 节点下新增 `targets`：

```json
{
  "scan": {
    "recursive": true,
    "extensions": [".xls", ".xlsx"],
    "exclude_prefixes": ["~$"],
    "exclude_dirs": ["LOG", "log", "日志", "备份", "backup"],
    "targets": [
      {
        "station_code": "A10",
        "dir": "外型工序\\V-CUT",
        "enabled": true
      },
      {
        "station_code": "A50",
        "dir": "xxxx\\xxxx",
        "enabled": true
      }
    ]
  }
}
```

### 5.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `station_code` | string | 是 | 工站代码，第一阶段统一使用该字段名 |
| `dir` | string | 是 | 相对 `share.root` 的目录路径 |
| `enabled` | boolean | 否 | 是否启用，默认 `true` |

### 5.3 路径规则

`dir` 使用相对路径，最终扫描路径为：

```text
share.root + dir
```

示例：

```json
{
  "share": {
    "root": "\\\\10.0.8.252\\ProductionFieldFile 现场公共盘\\阻抗"
  },
  "scan": {
    "targets": [
      {
        "station_code": "A10",
        "dir": "外型工序\\V-CUT"
      }
    ]
  }
}
```

最终扫描：

```text
\\10.0.8.252\ProductionFieldFile 现场公共盘\阻抗\外型工序\V-CUT
```

### 5.4 兼容旧配置

旧配置：

```json
{
  "scan": {
    "target_dirs": ["目录A", "目录B"]
  }
}
```

兼容规则：

1. 如果配置了 `scan.targets`，优先使用 `scan.targets`。
2. 如果没有配置 `scan.targets`，继续使用旧的 `scan.target_dirs`。
3. 使用旧配置扫描出来的文件，`station_code` 可以设置为空字符串或 `"UNKNOWN"`。
4. 文档和示例配置应逐步引导用户迁移到 `scan.targets`。

## 6. 程序行为设计

### 6.1 扫描行为

程序读取 `scan.targets` 后，只扫描 `enabled=true` 的配置项。

每个配置项解析为：

```text
目标目录 = share.root / target.dir
工站代码 = target.station_code
```

扫描到文件后，生成的候选文件对象需要带上：

```text
station_code
source_dir
```

其中：

- `station_code`：配置中的工站代码。
- `source_dir`：配置中的目录值，即 `target.dir`。

### 6.2 目录不存在

如果某个配置目录不存在：

- 不应中断整个任务。
- 应记录到 `missing_dirs`。
- 日志或汇总中应能看到缺失目录数量。
- 建议在缺失目录信息中同时包含 `station_code` 和目录路径，方便排查。

### 6.3 目录不可访问

如果某个目录存在但不可访问：

- 不应中断整个任务。
- 应记录到 `failed_dirs`。
- 应保留 `station_code` 和目录路径。

### 6.4 重复配置校验

配置解析阶段建议校验：

1. `station_code` 不能为空。
2. `dir` 不能为空。
3. 同一个 `dir` 不允许绑定多个工站。
4. `enabled` 如果填写，必须是布尔值。

允许：

```text
同一个 station_code 绑定多个不同目录
```

不允许：

```text
同一个目录绑定多个 station_code
```

## 7. 数据结构变更

### 7.1 config.py

新增配置数据结构：

```python
@dataclass(frozen=True)
class ScanTargetConfig:
    station_code: str
    dir: str
    enabled: bool = True
```

`ScanConfig` 新增字段：

```python
targets: list[ScanTargetConfig] | None = None
```

保留旧字段：

```python
target_dirs: list[str] | None = None
```

### 7.2 scanner.py

`CandidateFile` 新增：

```python
station_code: str
source_dir: str
```

扫描 `scan.targets` 时，应将对应工站传入候选文件。

### 7.3 parser.py

`ParsedFile` 新增：

```python
station_code: str
source_dir: str
```

`parse_candidate()` 从 `CandidateFile` 继承这两个字段。

### 7.4 fingerprint.py

`build_upload_record()` 需要写入：

```python
"station_code": parsed_file.station_code,
"source_dir": parsed_file.source_dir,
```

### 7.5 runner.py

`_base_entry()` 需要写入：

```python
"station_code": parsed_file.station_code,
"source_dir": parsed_file.source_dir,
```

dry-run、成功、失败、跳过等日志都应自动带上这两个字段。

### 7.6 uploader.py

上传接口增加 `station_code` 表单字段。

建议第一阶段先固定使用：

```text
station_code
```

请求形式：

```python
http.post(
    url,
    files={"file": (path.name, file)},
    data={"station_code": station_code},
    timeout=timeout_seconds,
)
```

如果后续后端字段名调整，再将字段名做成配置项。

## 8. 上传接口约定

第一阶段暂定 multipart 请求包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `file` | file | Excel 文件 |
| `station_code` | string | 工站代码 |

示例：

```text
POST /service-qms/file/importImpedanceData
Content-Type: multipart/form-data

file=<Excel 文件>
station_code=A10
```

如果后端暂时未支持 `station_code`，Python 侧仍应先在日志中记录该字段；是否发送字段可在后续开发中增加开关。

## 9. 去重规则调整

当前 fallback key 主要基于：

```text
region + normalized_name + size + mtime
```

新需求下建议调整为：

```text
station_code + region + normalized_name + size + mtime
```

原因：

不同工站可能存在同名、同大小、同修改时间的文件。将 `station_code` 纳入 key，可以避免跨工站误判重复。

示例：

```text
FALLBACK|A10|AFX|FILE-NAME|1024|2026-06-25 10:00:00
FALLBACK|A50|AFX|FILE-NAME|1024|2026-06-25 10:00:00
```

这两条应被视为不同文件记录。

## 10. 日志与汇总要求

### 10.1 upload_log

每条文件处理日志应包含：

```json
{
  "run_id": "ZK-20260626-080000",
  "filename": "example.xlsx",
  "full_path": "\\\\server\\share\\dir\\example.xlsx",
  "directory": "\\\\server\\share\\dir",
  "station_code": "A10",
  "source_dir": "外型工序\\V-CUT",
  "action": "upload_success"
}
```

### 10.2 uploaded_file_fingerprints

成功上传历史记录应包含：

```json
{
  "filename": "example.xlsx",
  "station_code": "A10",
  "source_dir": "外型工序\\V-CUT",
  "fallback_key": "FALLBACK|A10|..."
}
```

### 10.3 summary

汇总文件中至少需要保证：

- `pending_files` 中的文件能通过上传日志查到对应工站。
- 如果后续扩展，可以增加按工站统计。

按工站统计可以作为后续增强，例如：

```json
{
  "station_stats": {
    "A10": {
      "candidate_count": 10,
      "success_count": 8,
      "fail_count": 1,
      "skip_count": 1
    }
  }
}
```

第一阶段不强制实现按工站统计。

## 11. 用户验收标准

### 11.1 配置验收

给定配置：

```json
{
  "scan": {
    "targets": [
      {
        "station_code": "A10",
        "dir": "A10目录",
        "enabled": true
      },
      {
        "station_code": "A50",
        "dir": "A50目录",
        "enabled": true
      }
    ]
  }
}
```

验收结果：

- 程序只扫描 `A10目录` 和 `A50目录`。
- `A10目录` 下文件的 `station_code` 为 `A10`。
- `A50目录` 下文件的 `station_code` 为 `A50`。

### 11.2 上传验收

当扫描到 `A10目录/example.xlsx` 时，上传请求应包含：

```text
file=example.xlsx
station_code=A10
```

### 11.3 日志验收

上传日志中应出现：

```json
{
  "filename": "example.xlsx",
  "station_code": "A10",
  "source_dir": "A10目录"
}
```

### 11.4 去重验收

如果 `A10` 和 `A50` 两个工站下有同名、同大小、同修改时间文件：

- 不应因为另一个工站已上传而跳过当前工站文件。
- 两个文件应拥有不同的 fallback key。

### 11.5 异常验收

如果配置目录不存在：

- 程序不中断。
- 汇总中 `missing_dir_count` 增加。
- 日志或调试输出能看到缺失的是哪个工站目录。

如果目录配置重复：

- `--check-config` 应失败。
- 错误信息应说明重复目录。

## 12. 测试用例建议

### 12.1 test_config.py

新增测试：

- 能解析 `scan.targets`。
- `enabled` 缺省时默认为 `true`。
- `station_code` 为空时报错。
- `dir` 为空时报错。
- 重复 `dir` 报错。
- 旧 `target_dirs` 仍能解析。

### 12.2 test_scanner.py

新增测试：

- 扫描 `targets` 时，候选文件带正确 `station_code`。
- `enabled=false` 的目录不扫描。
- 缺失目录能进入 `missing_dirs`。
- 同一工站多个目录都能扫描。

### 12.3 test_parser.py

新增测试：

- `ParsedFile.station_code` 来自 `CandidateFile.station_code`。
- `ParsedFile.source_dir` 来自 `CandidateFile.source_dir`。
- fallback key 包含 `station_code`。

### 12.4 test_uploader.py

新增测试：

- 上传请求包含 `station_code` 表单字段。
- 上传成功/失败逻辑保持不变。

### 12.5 test_runner.py

新增测试：

- dry-run 日志包含 `station_code`。
- upload success 日志包含 `station_code`。
- 历史成功记录包含 `station_code`。

## 13. 开发步骤

建议按以下顺序开发：

1. 修改 `config.py`，新增 `ScanTargetConfig` 和 `scan.targets` 解析。
2. 补充 `test_config.py`，确保配置解析和校验稳定。
3. 修改 `scanner.py`，让候选文件带 `station_code` 和 `source_dir`。
4. 补充 `test_scanner.py`。
5. 修改 `parser.py`，让解析结果继承工站信息，并调整 fallback key。
6. 补充 `test_parser.py`。
7. 修改 `fingerprint.py` 和 `runner.py`，日志与历史记录写入工站字段。
8. 修改 `uploader.py`，上传 multipart 请求增加 `station_code`。
9. 补充 `test_uploader.py` 和 `test_runner.py`。
10. 更新 `config.example.json`，展示新配置格式。
11. 更新 `README.md`，说明工站目录绑定的配置方式。
12. 执行全量测试。
13. 使用 `upload.dry_run=true` 做一次本地预演，确认日志中的工站字段正确。

## 14. 实施风险

### 14.1 后端字段未确认

当前暂定上传字段为 `station_code`。如果后端最终字段名不同，需要改上传字段名，或增加配置项：

```json
{
  "upload": {
    "station_field_name": "stationCode"
  }
}
```

### 14.2 历史去重记录兼容

fallback key 增加 `station_code` 后，历史记录中的旧 key 不包含工站。

影响：

- 旧历史记录可能无法命中新 key。
- 首次上线后，部分历史文件可能被认为是新文件。

建议：

- 上线前使用 `dry_run=true` 预演。
- 检查 pending 文件数量是否符合预期。
- 如有必要，制定一次性历史 key 迁移方案。

### 14.3 目录配置错误

如果用户把目录绑定到错误工站，程序无法从文件内容判断，只会按配置执行。

缓解方式：

- `--check-config` 校验目录存在性。
- dry-run 日志中展示 `station_code` 和 `source_dir`。
- 上线前由业务确认配置表。

## 15. 推荐上线流程

1. 业务提供工站目录绑定表。
2. 将绑定关系写入 `config.json` 的 `scan.targets`。
3. 执行：

```powershell
python run_upload.py --config config.json --check-config
```

4. 设置：

```json
{
  "upload": {
    "dry_run": true
  }
}
```

5. 执行 dry-run，检查日志中的 `station_code` 是否正确。
6. 与后端确认接口已接收并保存 `station_code`。
7. 关闭 dry-run，执行真实上传。
8. 在数据库中按工站查询验证结果。

