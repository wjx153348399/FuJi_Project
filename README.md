# ZK Impedance Upload

阻抗共享盘 Excel 上传与监听脚本。

第一阶段目标是先跑通每天定时上传任务的最小闭环：

- 读取配置
- 扫描共享盘目录
- 按日期窗口筛选 Excel 文件
- 解析基础文件信息
- 去重
- 上传接口
- 写入 JSON / JSONL 日志

当前按模块逐步实现，避免一次性写完整流程导致职责混乱。

## 当前状态

第一阶段代码已完成，当前包含两条独立运行链路：

- 上传链路：每天按目标日期窗口扫描前一天 Excel 文件，执行解析、去重、上传和上传日志记录。
- 监听链路：常驻监听共享盘目录变化，符合现有上传规则的 Excel 文件会实时进入上传流程。

当前版本优先保证：

- 职责边界清晰
- 日志可追踪
- 配置集中管理
- 先满足最小闭环，再逐步扩展

## 本地运行

```powershell
python run_upload.py --help
python run_upload.py --config config.example.json --check-config
python run_upload.py --config config.example.json
python run_watcher.py --config config.example.json
python run_all.py --config config.example.json --web-config web_config.example.json
```

`--check-config` 会检查配置文件格式，并尝试确认日志目录可写。使用真实共享盘路径时，运行账号需要能访问 `\\10.0.8.252\File\ZK_LOG`。

- `run_upload.py` 用于执行每天一次的上传任务。
- `run_watcher.py` 用于单独启动常驻监听上传任务。
- `run_all.py` 用于一次启动 Web 页面和常驻监听上传任务。

推荐日常使用方式：

```powershell
# 1. 先检查配置
python run_upload.py --config config.json --check-config

# 2. 手动预演上传任务
python run_upload.py --config config.json

# 3. 单独启动监听任务
python run_watcher.py --config config.json

# 4. 一次启动 Web 页面和监听任务
python run_all.py --config config.json --web-config web_config.json
```

## 运行模式

当前项目有两种运行模式：

### 1. 上传任务模式

入口：

```powershell
python run_upload.py --config config.json
```

特点：

- 按 `upload.day_offset` 计算目标日期窗口。
- 只处理目标日期窗口内的 Excel 文件。
- 执行扫描、解析、批内去重、历史跳过、上传、汇总输出。
- 适合由 Windows 计划任务在每天 `08:00` 触发。

### 2. 监听任务模式

入口：

```powershell
python run_watcher.py --config config.json
```

特点：

- 常驻运行，按轮询间隔扫描目标目录快照。
- 识别新增、修改、删除、重命名事件。
- 对短时间重复事件做防抖。
- 符合现有文件规则和日期窗口的 Excel 文件会实时上传。
- 监听日志、上传结果和异常会写入文件日志，并在启用时写入数据库运行日志。

### 3. 组合启动模式

入口：

```powershell
python run_all.py --config config.json --web-config web_config.json
```

特点：

- 一个命令同时启动 Web 页面和监听上传服务。
- 原来的 Web 单独启动、监听单独启动方式仍然保留，便于排查问题。
- 如果监听服务退出，组合进程会退出；如果 Web 端口被占用，会提示 Web 启动失败。

## 配置

复制 `config.example.json` 为 `config.json` 后按部署环境调整。

推荐直接基于 [config.example.json](file:///D:/PythonProject/ZK/config.example.json) 复制修改。

主要配置分组如下：

- `share`：共享盘根目录、账号、密码。
- `log`：日志目录。
- `upload`：上传地址、目标日期偏移、超时、重试、dry-run。
- `scan`：扫描目标目录、扩展名、排除目录、临时文件前缀。
- `station_config`：工站目录绑定配置来源，可使用 JSON 或 SQL Server。
- `runtime_log`：运行日志数据库写入配置，默认写入 `dbo.zk_upload_runtime_log`，同时保留共享盘日志文件。
- `watch`：监听功能开关、监听模式、轮询间隔、防抖窗口。

### 工站目录绑定

通过 `scan.targets` 维护“flow -> 目录位置”的绑定关系：

```json
{
  "scan": {
    "targets": [
      {
        "flow": "A10",
        "dir": "ExampleStationDirectoryA",
        "enabled": true
      },
      {
        "flow": "A50",
        "dir": "ExampleStationDirectoryB",
        "enabled": true
      }
    ]
  }
}
```

`dir` 是相对 `share.root` 的目录路径。程序扫描到该目录下的 Excel 文件后，会自动把对应的 `flow` 写入上传请求、上传日志和历史成功记录。

上传给后端的 multipart 字段名统一为：

```text
file=<Excel 文件>
flow=<工站代码，可选，有值才提交>
filePath=<文件完整路径，可选，有值才提交>
```

项目内不再保留上传字段名兼容配置，`flow` 和 `filePath` 是全项目统一字段。`file` 是必传文件字段；`flow`、`filePath` 按后端可选规则处理，有值才随请求提交。

兼容旧配置 `scan.target_dirs`；如果同时配置了 `scan.targets`，程序优先使用 `scan.targets`。

第二阶段支持从 SQL Server 配置表读取工站目录绑定关系。默认仍使用 JSON：

```json
{
  "station_config": {
    "source": "json"
  }
}
```

上线初期推荐使用数据库优先、JSON 兜底：

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
      "table": "dbo.station_directory_config"
    }
  }
}
```

建表脚本见 `docs/sql/create_station_directory_config.sql`，示例数据见 `docs/sql/seed_station_directory_config.sql`。

监听相关配置位于 `watch` 节点，例如：

```json
{
  "watch": {
    "enabled": true,
    "notice_mode": "log_and_daily_summary",
    "poll_interval_seconds": 5,
    "debounce_seconds": 5
  }
}
```

- `enabled` 控制是否允许启动监听任务。
- `notice_mode` 当前支持 `log_and_daily_summary`，表示写监听日志并在每日上传任务执行时生成监听汇总。
- `poll_interval_seconds` 是监听轮询间隔秒数。
- `debounce_seconds` 是相同事件的防抖时间窗口。

共享盘登录：

- 脚本启动上传、监听或 `--check-config` 时，会先根据 `share.root` 和 `log.dir` 推导共享根目录。
- 如果共享根目录当前不可访问，会使用 `share.username` 和 `share.password` 执行 Windows `net use` 登录。
- 如果 Windows 已经用其他账号连接同一台共享服务器，脚本不会自动断开旧连接，需要人工处理后再运行。

推荐配置习惯：

- 联调阶段把 `upload.dry_run` 设为 `true`。
- 首次上线前先单独跑一次 `--check-config`。
- 监听先确认 `watch.enabled=true`，日常部署优先启动 `run_all.py`。
- 如果共享盘事件很多，可以适当把 `poll_interval_seconds` 调大。

## 当前模块结构

```text
zk_impedance_upload/
  __init__.py      版本号
  cli.py           命令行入口，只负责参数解析和调用模块
  config.py        配置数据结构、UTF-8 读取、必填项校验
  date_window.py   目标日期、开始时间、结束时间和时间戳窗口判断
  dedupe.py        批内重复文件识别，保留最新文件
  exceptions.py    项目自定义异常
  fingerprint.py   文件 SHA256、上传成功记录、历史上传跳过判断
  log_store.py     JSON / JSONL 日志、汇总、历史记录读写
  db_log_store.py  运行日志数据库写入、读取和文件日志双写包装
  parser.py        区域识别、文件名标准化、基础 key 生成
  runner.py        串联配置、扫描、解析、去重、上传和日志记录
  scanner.py       目标目录扫描、扩展名过滤、临时文件过滤、日期窗口过滤
  share_auth.py    Windows 共享盘访问检查和 net use 登录
  station_config.py 工站目录配置来源解析、SQL Server 读取、JSON 回退
  uploader.py      HTTP multipart 上传、超时、重试、结果封装
  watcher.py       监听快照采集、事件差异、防抖、监听日志和监听汇总
run_upload.py      上传任务入口
run_watcher.py     监听任务入口，固定以 --watch 模式启动
run_all.py         Web 页面和监听任务组合启动入口
tests/
  test_config.py             配置模块测试
  test_date_window.py        日期窗口模块测试
  test_dedupe.py             批内去重模块测试
  test_fingerprint.py        文件指纹和历史跳过测试
  test_log_store.py          日志模块测试
  test_parser.py             解析模块测试
  test_project_structure.py  项目入口和基础结构测试
  test_runner.py             运行入口整合测试
  test_scanner.py            扫描模块测试
  test_uploader.py           上传模块测试
  test_watcher.py            监听模块测试
```

日志模块当前负责维护：

- `upload_log_YYYY-MM-DD.jsonl`
- `summary_YYYY-MM-DD_HH-MM-SS.json`
- `uploaded_file_fingerprints.json`
- `uploaded_business_keys.json`
- `watch_log_YYYY-MM-DD.jsonl`
- `watch_summary_YYYY-MM-DD_HH-MM-SS.json`

## Hash 策略

当前采用轻量优先策略，避免共享盘大文件全量 hash 导致 dry-run 或日常运行过慢：

- 历史上传跳过：按 `fallback_key` 判断，不读取文件内容。
- 批内去重：先按 `region + normalized_name + size + mtime` 分组。
- 只有疑似重复组内有多个文件时，才计算 SHA256。
- 上传成功历史默认不写 `file_hash`。

普通运行会执行上传任务；上线前建议先在 `config.json` 中设置 `upload.dry_run=true` 做预演。

## 日志说明

### 上传相关日志

- `upload_log_YYYY-MM-DD.jsonl`
  - 记录单个文件的扫描、跳过、上传成功、上传失败等处理结果。
- `summary_YYYY-MM-DD_HH-MM-SS.json`
  - 记录一次上传任务的总体统计结果。
- `uploaded_file_fingerprints.json`
  - 记录历史成功上传的文件指纹，用于下次跳过。
- `uploaded_business_keys.json`
  - 记录历史成功上传的业务键。

### 监听相关日志

- `watch_log_YYYY-MM-DD.jsonl`
  - 记录监听到的新增、修改、删除、重命名、异常、提示事件。
- `watch_summary_YYYY-MM-DD_HH-MM-SS.json`
  - 由每日上传任务固定时点生成，对目标日期的监听日志做汇总。

当前监听事件类型包括：

- `watch_created`
- `watch_modified`
- `watch_deleted`
- `watch_renamed`
- `watch_notice`
- `watch_error`

## 监听与上传边界

当前代码里，监听入口和上传处理仍保持模块边界清晰：

- 上传主流程在 `runner.py`，只负责日期窗口、扫描、解析、去重、上传和上传日志。
- 监听主流程在 `watcher.py`，负责目录事件识别、防抖，并把符合规则的文件交给实时上传流程。
- `run_upload.py` 只进入上传任务。
- `run_watcher.py` 只进入监听任务。
- `run_all.py` 同时启动 Web 页面和监听任务，但不改变两者内部逻辑。
- 每日上传任务执行时，如果启用了 `watch.notice_mode=log_and_daily_summary`，会顺带按目标日期生成监听汇总，方便把“前一天监听到的变化”和“当天上传结果”放在同一个时间点查看。

可以把当前结构理解为：

- 监听模块负责“发现变化并触发实时上传”
- 上传模块负责“按规则解析、去重并调用后端接口”

两者共享的只有：

- 同一份配置
- 同一个日志目录

更准确地说，当前是“逻辑分离、日志协同”的结构：

- 上传模块不依赖监听才能执行。
- 监听中断不会阻止上传任务运行。
- 组合启动只减少部署命令数量，不改变上传规则。

## 推荐上线方式

推荐拆成两个独立任务上线：

### 1. 上传任务

- 运行方式：Windows 计划任务。
- 执行频率：每天一次。
- 建议时间：每天 `08:00`。
- 入口命令：

```powershell
python run_upload.py --config D:\PythonProject\ZK\config.json
```

### 2. Web + 监听组合任务

- 运行方式：后台常驻进程。
- 启动方式：开机启动、任务计划或运维托管均可。
- 作用：提供网页配置入口，并实时监听共享盘变化触发上传。

```powershell
python run_all.py --config D:\PythonProject\ZK\config.json --web-config D:\PythonProject\ZK\web_config.json
```

### 3. 单独监听任务

- 运行方式：后台常驻进程。
- 启动方式：开机启动、任务计划或运维托管均可。
- 入口命令：

```powershell
python run_watcher.py --config D:\PythonProject\ZK\config.json
```

推荐上线顺序：

1. 先只上线上传任务，确认扫描、上传、日志都稳定。
2. 再上线 `run_all.py`，观察 Web 访问、监听日志量和实时上传结果。
3. 稳定后再考虑做 Windows 服务化或开机自启动。

## 典型流程

### 上传任务流程

1. 读取配置并检查日志目录。
2. 计算目标日期窗口。
3. 扫描共享盘目标目录。
4. 解析候选文件基础信息。
5. 执行批内去重。
6. 按历史成功记录跳过已上传文件。
7. 调用接口上传剩余文件。
8. 写上传流水、成功历史和运行汇总。
9. 如果启用了监听汇总模式，顺带生成目标日期监听汇总。

### 监听任务流程

1. 读取配置并检查日志目录。
2. 建立初始目录快照。
3. 按轮询间隔重新采集目录快照。
4. 识别新增、修改、删除、重命名事件。
5. 对短时间重复事件做防抖。
6. 写入监听日志。
7. 如遇异常，写 `watch_error` 后继续下一轮。

## 当前已实现能力

- 支持 `.xls`、`.xlsx` 扫描。
- 支持按前一天日期窗口筛选文件。
- 支持跳过 `~$` 临时文件。
- 支持排除 `LOG`、`log`、`日志`、`备份`、`backup` 目录。
- 支持区域识别、文件名标准化和 fallback key 生成。
- 支持轻量历史成功跳过。
- 支持疑似重复文件的按需 SHA256 校验。
- 支持批内重复跳过。
- 支持上传成功、失败、dry-run 日志记录。
- 支持监听新增、修改、删除、重命名事件。
- 支持监听事件防抖。
- 支持每日监听汇总生成。

## 当前未实现或暂不处理

- 监听事件直接触发上传。
- 监听事件进入上传队列。
- `serialNo` 解析。
- Excel 内容级 hash。
- 企业微信、邮件、弹窗等实时通知。
- Windows 计划任务自动创建脚本。
- 监听进程守护、自动拉起、服务化包装。

## 常见说明

### 为什么还保留单独启动入口

- 组合启动适合日常部署。
- 单独 Web、单独监听入口适合排查端口、数据库、共享盘和上传接口问题。
- 原入口保留后，出现问题时可以更快定位是哪一部分异常。

### 为什么监听汇总在上传任务里生成

- 需求本身更接近“每天看一次前一天变化汇总”。
- 放在上传任务固定时点生成，时间语义更稳定。
- 可以避免监听常驻进程跨天时重复生成多份汇总。

### 监听任务停止了会不会影响上传

- 不会影响 Web 页面已经保存的配置。
- 手动上传任务仍然可以单独运行。
- 只是当天可能没有完整的监听日志与监听汇总可供排查。

## 上线检查清单

上线前建议逐项确认：

### 基础环境

- Python 版本满足项目运行要求。
- 运行账号具备共享盘访问权限。
- 运行账号具备日志目录写权限。
- 运行机器可以访问上传接口地址。
- 配置文件保存为 UTF-8 编码。

### 上传任务

- `python run_upload.py --config config.json --check-config` 可以通过。
- `upload.dry_run=true` 时可以正常完成一次预演。
- 能正确筛选前一天日期窗口内的 Excel 文件。
- 能跳过当天文件、临时文件、非 Excel 文件。
- 能生成 `upload_log` 和 `summary` 文件。
- 成功上传后能写入 `uploaded_file_fingerprints.json`。
- 再次执行时已上传文件会被跳过。

### 监听任务

- 配置中 `watch.enabled=true`。
- `python run_all.py --config config.json --web-config web_config.json` 可以正常启动。
- 必要时 `python run_watcher.py --config config.json` 可以单独启动监听。
- 新增、修改、删除、重命名文件时会写入 `watch_log`。
- 明显重复触发的短时间事件会被防抖压缩。
- 监听目录不存在或访问失败时会写 `watch_notice`。
- 监听内部异常时会写 `watch_error`，并继续下一轮。

### 汇总与日志

- 上传任务执行时能生成 `summary_*.json`。
- 启用 `watch.notice_mode=log_and_daily_summary` 后，上传任务执行时能生成 `watch_summary_*.json`。
- 日志目录中各类 JSON / JSONL 文件内容可正常打开且无乱码。

### 上线顺序

1. 先验证 `--check-config`。
2. 再执行 dry-run 预演。
3. 再执行一次真实上传验证。
4. 最后上线 `run_all.py` 作为日常常驻服务。

## 故障排查清单

### 1. 上传任务无法启动

优先检查：

- 配置文件路径是否正确。
- JSON 格式是否有效。
- 必填项是否齐全。
- 日志目录是否可写。

建议先执行：

```powershell
python run_upload.py --config config.json --check-config
```

### 2. 监听任务无法启动

优先检查：

- 配置里是否设置了 `watch.enabled=true`。
- 共享盘路径是否可访问。
- 如果提示用户名或密码错误，检查是否已有其他账号连接 `\\10.0.8.252`。
- 日志目录是否可写。
- Python 进程是否被安全软件或权限策略拦截。

建议先执行：

```powershell
python run_watcher.py --config config.json
```

如果启动后立刻退出，优先查看控制台输出和日志目录。

组合启动排查命令：

```powershell
python run_all.py --config config.json --web-config web_config.json
```

### 3. 扫描不到文件

优先检查：

- `share.root` 是否正确。
- `scan.target_dirs` 是否存在。
- 文件修改时间是否真的落在目标日期窗口。
- 文件扩展名是否在 `scan.extensions` 中。
- 文件是否被排除目录规则过滤。
- 文件是否是 `~$` 临时文件。

### 4. 文件没有上传

优先检查：

- 当前是否为 `upload.dry_run=true`。
- 文件是否被批内去重跳过。
- 文件是否命中历史成功记录而被跳过。
- 文件是否根本不在目标日期窗口内。
- 上传接口是否返回失败。

建议查看：

- `upload_log_YYYY-MM-DD.jsonl`
- `summary_YYYY-MM-DD_HH-MM-SS.json`

### 5. 已上传文件重复上传

优先检查：

- `uploaded_file_fingerprints.json` 是否存在且内容正常。
- 日志目录是否在上传后成功写入历史记录。
- 文件是否被修改，导致指纹发生变化。
- 是否误删了历史记录文件。

### 6. 监听没有记录事件

优先检查：

- 监听任务是否仍在运行。
- `watch.enabled` 是否开启。
- 被操作的目录是否在监听范围内。
- 事件是否在防抖窗口内被合并。
- 日志目录是否能正常写入 `watch_log`。

建议先手动做四类动作验证：

- 新建文件
- 修改文件
- 删除文件
- 重命名文件

### 7. 监听汇总没有生成

优先检查：

- 是否启用了 `watch.notice_mode=log_and_daily_summary`。
- 当天是否真的执行了上传任务。
- 目标日期对应的 `watch_log_YYYY-MM-DD.jsonl` 是否存在。

说明：

- `watch_summary` 不是监听进程实时生成的。
- 它是在上传任务固定时点生成的。

### 8. 日志乱码或无法读取

优先检查：

- 文件是否用 UTF-8 打开。
- 是否被外部工具改写成了其他编码。
- JSON / JSONL 是否被手工编辑破坏了格式。

### 9. 接口上传失败

优先检查：

- 上传地址是否可访问。
- 网络是否可连通。
- 超时和重试参数是否合适。
- 接口是否返回了状态码和响应内容。

建议重点查看 `upload_log` 中的：

- `http_status`
- `response`
- `response_text`
- `error`

### 10. 监听和上传是否需要同时在线

- 不需要。
- 上传任务可以单独运行。
- 监听任务也可以单独运行。
- 建议最终上线时使用 `run_all.py` 常驻运行，保留单独入口作为排查手段。
