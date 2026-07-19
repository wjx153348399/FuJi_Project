# 工站 flow 配置与实时上传改造计划

## 目标

实现一个最小且完整的实时上传闭环：

1. 用户在 Web 端工站配置页面维护 `station_directory_config`。
2. 每条启用配置必须有明确的 `flow` 和 `directory_path`。
3. 监听服务实时监听所有启用配置中的目录。
4. 目录中新生成或更新符合规则的文件时，自动调用上传接口。
5. 上传接口参数固定为文件本体、`flow`、`filePath`。
6. 上传过程和结果写入现有日志表/队列表，便于追踪。

不在本次计划内扩展复杂功能，例如审批流、多文件类型规则管理、并发调度 UI、历史报表重做等。

## 当前现状判断

现有代码已经具备主体链路：

- `station_config.py` 已支持从 SQL Server `station_directory_config` 读取启用目录。
- `watcher.py` 已支持实时监听模式，默认 `watch.mode=native`。
- `realtime_uploader.py` 已支持文件稳定性检查、入队、上传。
- `uploader.py` 上传时已发送 `file`、`flow`、`filePath`。
- `station_config_web` 已有工站配置页面，并且表单里已有 `flow` 字段。
- `zk_upload_task_queue` 可作为待上传任务队列。
- `zk_upload_runtime_log` 可作为运行日志表。

当前主要缺口：

- Web 端允许启用配置时 `flow` 为空，只是提示，不会阻止保存。
- 列表页和表单页文案里还把 `flow` 当成“可选”，不符合实时上传必须带工站代码的目标。
- 现有监听读取数据库配置后，依赖 `flow` 字段；如果 `flow` 为空，上传接口就拿不到工站代码。
- 当前路径设计要求 `directory_path` 是相对 `share.root` 的路径；如果业务要求直接保存完整 UNC 路径，需要另做兼容。

## 最终业务规则

### 工站配置规则

`station_directory_config` 中一条有效配置代表一个监听目标：

| 字段 | 规则 |
|---|---|
| `flow` | 启用时必填，上传接口使用的工站代码 |
| `station_name` | 页面显示名称，可填工站简称或中文名称 |
| `directory_path` | 监听目录路径，当前建议继续使用相对 `share.root` 的路径 |
| `enabled` | 只有 `enabled=1` 才会被监听服务读取 |
| `sort_order` | 页面排序和读取排序 |
| `remark` | 备注 |

启用配置必须满足：

- `flow` 非空。
- `directory_path` 非空。
- `directory_path` 不重复。
- 目录最好通过页面“测试目录”确认存在。

### 实时上传规则

监听服务只处理：

- `enabled=1` 的配置。
- 配置目录下的新建、修改、重命名文件。
- 文件后缀在 `scan.extensions` 中，当前为 `.xls`、`.xlsx`。
- 文件名不以排除前缀开头，当前默认排除 `~$`。
- 文件稳定后再上传，避免复制未完成时上传。

上传请求固定包含：

```text
file     = 文件本体
flow     = station_directory_config.flow
filePath = 文件完整路径
```

## 改造步骤

## 1. 数据库处理

### 1.1 检查现有空 flow

上线改造前先查出所有启用但 `flow` 为空的配置：

```sql
SELECT id, flow, station_name, directory_path, enabled
FROM dbo.station_directory_config
WHERE enabled = 1
  AND (flow IS NULL OR LTRIM(RTRIM(flow)) = '');
```

这些记录必须人工确认真实工站代码后补齐。

### 1.2 可选的一次性初始化

如果当前 `station_name` 中已经保存了真实工站代码，可以临时用下面 SQL 批量补齐：

```sql
UPDATE dbo.station_directory_config
SET flow = station_name,
    updated_by = N'migration'
WHERE enabled = 1
  AND (flow IS NULL OR LTRIM(RTRIM(flow)) = '')
  AND station_name IS NOT NULL
  AND LTRIM(RTRIM(station_name)) <> '';
```

注意：如果 `station_name` 只是显示名称，不是真实接口工站代码，不要直接执行这段 SQL。

### 1.3 是否需要新增文件类型字段

当前目标如果只上传 Excel，则不需要新增字段，继续使用 `config.json` 中的：

```json
"extensions": [".xls", ".xlsx"]
```

只有当不同工站目录需要不同文件类型时，才新增：

```sql
ALTER TABLE dbo.station_directory_config
ADD file_type NVARCHAR(100) NULL;
```

本次最小改造建议暂不加 `file_type`，避免扩大范围。

## 2. 后端配置读取改造

### 2.0 已确认的 flow 规则

`flow` 已确认为上传接口使用的真实工站代码，格式类似：

```text
A032
```

因此：

- `flow` 不能再使用 `AFC`、`AFX`、`JXN`、`LXD`、`ZGL`、`OUTER` 这类区域/目录简称。
- `station_name` 可以继续保存中文名称或区域简称，仅用于页面展示。
- 实时上传时，接口收到的 `flow` 必须是 `A032` 这一类工站代码。

### 2.1 保持读取字段不变

当前监听读取逻辑可以保留：

```sql
SELECT flow, directory_path
FROM dbo.station_directory_config
WHERE enabled = 1
ORDER BY sort_order ASC, id ASC
```

原因：

- 实时上传只需要 `flow` 和 `directory_path`。
- `station_name` 只用于页面显示。
- 文件类型当前走全局 `scan.extensions`。

### 2.2 增加启用配置校验

在 `zk_impedance_upload/station_config.py` 的数据库配置加载后增加校验：

- 如果 `enabled=1` 但 `flow` 为空，启动监听时直接报错。
- 错误信息要提示具体 `directory_path`，便于页面修正。

建议规则：

```text
启用的工站目录配置 flow 不能为空: directory_path=...
```

这样可以避免静默上传无工站代码的数据。

### 2.3 路径规则确认

当前代码要求 `directory_path` 是相对 `share.root` 的路径，例如：

```text
图形后(半成品)\LXD & AFX & JXN\AFX
```

实际监听路径由程序拼接：

```text
share.root + directory_path
```

本次建议保持这个规则，因为现有 Web 页面、目录测试、监听服务都按这个模型写好了。

如果后续要支持完整 UNC 路径，需要同时改：

- `station_config.py` 的绝对路径校验。
- `scanner.py` 的目标路径拼接。
- `watcher.py` 的监听目标拼接。
- `station_config_web/repository.py` 的目录校验与 full_path 展示。
- Web 表单中的路径提示文案。

这属于第二阶段，不建议和本次 flow 必填一起做。

## 3. 实时监听上传改造

### 3.1 启动方式

只启动监听服务即可：

```powershell
python run_watcher.py --config config.json
```

不需要启动定时扫描，也不需要额外上传命令。

### 3.2 确认配置项

`config.json` 必须满足：

```json
"station_config": {
  "source": "db_then_json",
  "db": {
    "enabled": true,
    "table": "dbo.station_directory_config"
  }
},
"watch": {
  "enabled": true
}
```

如果没有配置 `watch.mode`，代码默认使用 `native`，即实时监听。

### 3.3 保持现有上传链路

现有链路可以保留：

```text
文件事件
-> 检查是否目标目录和目标后缀
-> 等待文件稳定
-> 生成 CandidateFile(flow, filePath)
-> 写入 zk_upload_task_queue
-> worker 调用上传接口
-> 更新任务状态
-> 写运行日志
```

本次不建议改成轮询批处理，因为你当前明确要求实时。

## 4. Web 后端改造

### 4.1 新增/编辑时强制校验 flow

修改 `station_config_web/repository.py` 的 `validate_station_directory_input()`：

规则：

- 如果 `enabled=True` 且 `flow` 为空，抛出错误。
- 如果 `enabled=False`，可以允许 `flow` 为空，表示草稿配置。

建议错误：

```text
启用配置时 flow 不能为空，请填写上传接口使用的工站代码
```

### 4.2 启用按钮强制校验 flow

修改 `StationDirectoryRepository.set_enabled()`：

- 当 `enabled=True` 时，先查询当前记录 `flow`。
- 如果 `flow` 为空，不允许启用。

原因：

- 即使编辑页做了校验，列表页也可以直接点“启用”。
- 必须在后端阻止空 flow 启用，不能只靠前端确认框。

### 4.3 保存后监听服务自动生效

现有监听服务已有配置热加载逻辑，数据库配置变化后会重新加载目标目录。

需要保留这个行为：

- Web 保存 `flow` 后，不要求重启监听。
- Web 修改 `directory_path` 后，监听服务自动切换目录。
- Web 禁用配置后，监听服务停止监听该目录。

## 5. Web 前端改造

### 5.1 表单文案调整

当前表单里 `flow` 写的是“可选”，需要改成：

```text
flow（启用时必填）
```

输入框提示建议：

```text
请输入上传接口使用的工站代码，例如 A105
```

说明文字建议：

```text
启用后新文件上传会把该值作为 flow 参数传给接口。
```

### 5.2 启用状态下前端拦截空 flow

修改表单提交确认逻辑：

- 如果 `enabled=1` 且 `flow` 为空，直接 `alert` 并阻止提交。
- 不再询问“是否确认空 flow 启用”。

### 5.3 列表页提示调整

列表页可以保留 `flow 待确认` 筛选。

但操作规则要改：

- `flow` 为空的记录只能编辑，不能直接启用。
- 如果保留启用按钮，点击后后端也会拒绝。
- 页面文案要说明“启用前必须配置 flow”。

### 5.4 页面字段建议

列表页建议展示：

| 字段 | 用途 |
|---|---|
| 状态 | 启用/停用 |
| flow | 上传接口工站代码 |
| 显示名称 | 人看的工站名称 |
| 目录路径 | 相对路径和完整路径 |
| 目录检测 | 是否存在 |
| 备注 | 说明 |
| 操作 | 编辑、测试目录、启用/停用 |

## 6. 测试计划

### 6.1 单元测试

补充或调整以下测试：

- `tests/test_station_config.py`
  - 数据库启用配置 `flow` 为空时，监听配置加载失败。
  - 数据库启用配置 `flow` 有值时，正常生成 target。

- `tests/test_station_config_web_repository.py`
  - 新增启用配置时 `flow` 为空，保存失败。
  - 新增停用配置时 `flow` 为空，保存成功。
  - 启用已有空 `flow` 配置时，启用失败。
  - 更新启用配置时 `flow` 为空，保存失败。

- `tests/test_station_config_web_app.py`
  - 页面提交启用且空 `flow` 返回错误。
  - 编辑补齐 `flow` 后保存成功。

- `tests/test_realtime_uploader.py`
  - 新文件事件生成上传任务时，任务中包含正确 `flow` 和 `filePath`。

### 6.2 本地联调

1. 在 Web 页面新增一条停用配置，`flow` 为空，保存成功。
2. 点击启用，确认被拒绝。
3. 编辑补齐 `flow`，启用成功。
4. 启动监听：

```powershell
python run_watcher.py --config config.json
```

5. 往对应目录放一个 `.xls` 或 `.xlsx` 文件。
6. 检查 `zk_upload_task_queue`：

```sql
SELECT TOP 20 id, status, flow, filePath, full_path, created_at, finished_at, error_message
FROM dbo.zk_upload_task_queue
ORDER BY id DESC;
```

7. 检查 `zk_upload_runtime_log`：

```sql
SELECT TOP 50 log_time, log_type, status, action, flow, filename, full_path, message
FROM dbo.zk_upload_runtime_log
ORDER BY id DESC;
```

8. 确认接口收到 `flow` 和 `filePath`。

## 7. 发布步骤

1. 备份数据库表：

```sql
SELECT *
INTO dbo.station_directory_config_backup_before_flow_required_20260719
FROM dbo.station_directory_config;
```

2. 查出空 `flow` 启用配置并人工补齐。
3. 部署后端和 Web 改造代码。
4. 重启 Web 服务。
5. 重启监听服务。
6. 页面检查 `flow 待确认` 是否还有启用记录。
7. 做一次真实目录投放文件测试。

## 8. 需要业务补充确认的信息

实施前需要确认这些信息：

1. `flow` 的真实取值规则是什么？
   - 已确认：`flow` 是 `A032` 这种真实工站代码。
   - 不是 `AFC/AFX/JXN/LXD/ZGL/OUTER` 这种目录/区域代码。

2. `station_name` 的定位是什么？
   - 是中文工站名称，比如“电测/飞针”？
   - 还是区域简称，比如 `AFX/JXN`？

3. `directory_path` 是否继续存相对路径？
   - 当前代码推荐相对 `share.root`。
   - 如果领导要求完整 UNC 路径，要安排第二阶段路径兼容。

4. 实时上传的文件类型是否只有 `.xls/.xlsx`？
   - 如果是，本次不用改表。
   - 如果每个工站不同，需要新增 `file_type` 字段。

5. 上传接口是否必须每次都带 `flow`？
   - 如果必须，本计划的“启用时 flow 必填”就是正确规则。

6. 新文件失败后是否需要自动重试？
   - 当前上传已有接口重试。
   - 失败任务是否要后续人工重跑，需要另定规则。

## 9. 建议实施顺序

推荐按这个顺序做：

1. Web 后端加“启用时 flow 必填”。
2. Web 前端改文案和提交拦截。
3. 监听配置加载加空 `flow` 防线。
4. 补测试。
5. 手工补齐历史启用配置的 `flow`。
6. 启动实时监听做端到端验证。

这样改动范围最小，能最快满足“配置工站 -> 监听目录 -> 新文件实时上传”的核心目标。
