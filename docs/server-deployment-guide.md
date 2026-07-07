# 服务器部署指导

本文档用于指导将阻抗文件上传工具部署到服务器。推荐部署方式是：

- 网页配置服务常驻运行，用于维护工站目录、工站代码和启用状态。
- 上传模块由系统定时任务每天执行一次，用于上传前一天的数据。
- 日志统一写入共享盘日志目录，方便排查上传结果。

## 1. 部署目标

部署完成后，系统链路应为：

```text
用户打开网页配置工站目录
        ↓
配置保存到数据库 QMS.dbo.station_directory_config
        ↓
服务器定时执行 run_upload.py
        ↓
上传模块读取数据库中 enabled=1 的目录配置
        ↓
扫描这些目录内前一天的 Excel 文件
        ↓
上传到后端接口
        ↓
写入上传日志和汇总文件
```

## 2. 推荐服务器结构

建议将项目固定放在服务器目录中，例如：

```text
D:\apps\ZK
```

推荐运行结构：

```text
D:\apps\ZK
├─ run_upload.py
├─ config.json
├─ web_config.json
├─ requirements.txt
├─ station_config_web
├─ zk_impedance_upload
└─ docs
```

## 3. 服务器前置条件

服务器需要具备：

- 可以访问共享盘，例如 `\\10.0.8.252\File`
- 可以访问上传接口，例如 `http://10.0.8.217:8108/service-qms/file/importImpedanceData`
- 可以访问 SQL Server 数据库
- 已安装 Python，建议 Python 3.11
- 运行账号具备共享盘读取权限和日志目录写入权限

如果使用 Windows 任务计划程序或 Windows 服务，必须确认运行账号有共享盘权限。不要只用当前登录用户手动测试通过就认为服务账号也有权限。

## 4. 准备 Python 环境

进入项目目录：

```bat
cd /d D:\apps\ZK
```

安装依赖：

```bat
pip install -r requirements.txt
```

如果服务器使用 conda，建议创建独立环境：

```bat
conda create -n zk_upload python=3.11
conda activate zk_upload
pip install -r requirements.txt
```

后续 Windows 任务计划程序和服务中使用这个环境对应的 `python.exe`。

## 5. 配置上传模块

确认服务器上的 `config.json` 使用真实环境配置。

关键配置示例：

```json
{
  "share": {
    "root": "\\\\10.0.8.252\\File"
  },
  "log": {
    "dir": "\\\\10.0.8.252\\File\\ZK_LOG"
  },
  "station_config": {
    "source": "db",
    "db": {
      "enabled": true,
      "driver": "sqlserver",
      "table": "QMS.dbo.station_directory_config"
    }
  },
  "upload": {
    "url": "http://10.0.8.217:8108/service-qms/file/importImpedanceData",
    "day_offset": 1,
    "dry_run": false
  }
}
```

配置说明：

- `share.root`：共享盘根目录。
- `log.dir`：上传日志目录。
- `station_config.source`：服务器建议使用 `db`。
- `station_config.db.table`：工站目录配置表。
- `upload.url`：后端上传接口。
- `upload.day_offset=1`：上传前一天的数据。
- `upload.dry_run=false`：真实上传。

## 6. 配置网页服务

确认服务器上的 `web_config.json` 使用真实配置。

网页服务用于维护 `QMS.dbo.station_directory_config` 表中的配置，用户在页面保存后，上传模块下一次执行时会读取最新配置。

临时启动测试：

```bat
cd /d D:\apps\ZK
python -m station_config_web.app
```

浏览器访问：

```text
http://服务器IP:8088/station-config
```

如果服务器本机测试，可以访问：

```text
http://127.0.0.1:8088/station-config
```

## 7. 将网页服务注册为 Windows 服务

正式环境建议使用 NSSM 将网页服务注册为 Windows 服务。

示例：

```bat
nssm install ZKStationConfigWeb
```

在 NSSM 界面中填写：

```text
Application path:
你的 python.exe 路径

Startup directory:
D:\apps\ZK

Arguments:
-m station_config_web.app
```

服务建议配置：

- 启动类型：自动
- 登录账号：使用有共享盘和数据库权限的账号
- 标准输出和错误输出：写入服务器本地日志目录，例如 `D:\apps\ZK\service_logs`

启动服务：

```bat
nssm start ZKStationConfigWeb
```

验证服务：

```text
http://服务器IP:8088/station-config
```

## 8. 配置每天自动上传任务

使用 Windows 任务计划程序创建任务。

推荐配置：

```text
任务名称:
ZK Daily Upload

触发器:
每天固定时间，例如 08:00

操作-程序:
你的 python.exe 路径

操作-参数:
D:\apps\ZK\run_upload.py --config D:\apps\ZK\config.json

起始位置:
D:\apps\ZK
```

注意：

- `run_upload.py` 执行一次就结束。
- 每次执行都会读取数据库中的最新启用配置。
- 当前逻辑会根据 `upload.day_offset=1` 扫描前一天的数据。
- 如果某个目录的 `flow` 为空，会正常上传文件，但不会传 `flow` 字段。

## 9. 部署后校验

### 9.1 校验配置

在服务器执行：

```bat
cd /d D:\apps\ZK
python run_upload.py --config config.json --check-config
```

期望结果：

```text
配置校验通过: config.json
```

### 9.2 测试网页配置

打开：

```text
http://服务器IP:8088/station-config
```

检查：

- 可以打开页面。
- 可以新增或修改目录配置。
- 可以保存 `flow` 为空的配置。
- 可以看到启用状态。
- 可以使用目录测试功能确认目录存在。

### 9.3 测试真实上传

手动执行一次：

```bat
cd /d D:\apps\ZK
python run_upload.py --config config.json
```

检查输出中是否出现：

```text
工站目录配置加载完成: source=db
目标日期窗口: yyyy-mm-dd
扫描完成
上传任务汇总
上传任务完成
```

### 9.4 检查日志

检查日志目录：

```text
\\10.0.8.252\File\ZK_LOG
```

应生成类似文件：

```text
summary_yyyy-mm-dd_hh-mm-ss.json
upload_log_yyyy-mm-dd.jsonl
uploaded_file_fingerprints.json
```

重点查看 `summary` 中：

- `success_count`
- `fail_count`
- `skip_count`
- `with_flow_count`
- `blank_flow_count`

## 10. 工站配置规则

网页配置中：

- `directory_path` 是相对共享盘根目录的目录。
- `flow` 是后端需要的工站代码。
- `station_name` 是显示名称，不参与上传字段。
- `enabled=1` 的配置才会被上传模块读取。

上传规则：

```text
一个目录配置一个 flow
扫描到该目录下的文件时，使用该配置的 flow
不会从文件名中解析 AA01、OUTER、AFC 等作为 flow
```

如果真实工站代码暂时未确认：

```text
flow 留空
```

此时上传模块仍会上传文件，但不会向接口传 `flow` 字段。

## 11. 常见问题

### 11.1 网页能打开，但上传任务读取不到配置

检查：

- `config.json` 中 `station_config.source` 是否为 `db`
- 数据库表是否为 `QMS.dbo.station_directory_config`
- 配置记录是否 `enabled=1`
- 上传任务运行账号是否有数据库访问权限

### 11.2 手动运行可以访问共享盘，定时任务失败

通常是任务计划程序运行账号权限不同。

处理方式：

- 将任务运行账号改为有共享盘权限的域账号或指定账号。
- 确认该账号可以访问 `\\10.0.8.252\File`。
- 确认该账号可以写入 `\\10.0.8.252\File\ZK_LOG`。

### 11.3 没有上传文件

检查：

- `upload.day_offset` 是否为 `1`
- 前一天目标目录内是否有 Excel 文件
- 文件修改时间是否落在目标日期窗口
- 目录配置是否启用
- 目录路径是否相对 `share.root`
- 是否已经被历史记录判定为上传过

### 11.4 flow 不确定时怎么办

不要填写 `AFC`、`OUTER` 或文件名中的 `AA01`。

如果真实工站代码未确认，先将 `flow` 留空。上传模块会正常上传文件，只是不传 `flow` 字段。

### 11.5 后端提示 filePath 或 flow 字段问题

当前上传模块已将 `flow` 和 `filePath` 作为可选字段：

- 有值时传。
- 为空时不传。

如果后端仍报字段错误，需要确认后端接口当前版本是否已经支持这些字段，或是否仍连接到旧表结构。

## 12. 推荐上线顺序

1. 将项目代码放到服务器固定目录。
2. 安装 Python 依赖。
3. 配置 `config.json` 和 `web_config.json`。
4. 执行 `--check-config`。
5. 启动网页配置服务。
6. 在网页中配置或核对工站目录。
7. 手动执行一次 `run_upload.py` 验证上传。
8. 配置 Windows 任务计划程序。
9. 第二天检查定时任务日志和上传结果。

## 13. 上线确认清单

- [ ] 服务器可以访问共享盘。
- [ ] 服务器可以访问 SQL Server。
- [ ] 服务器可以访问上传接口。
- [ ] `config.json` 指向真实数据库和上传接口。
- [ ] `web_config.json` 指向真实数据库。
- [ ] 网页配置服务可以打开。
- [ ] 工站目录配置已保存到数据库。
- [ ] 至少一条配置为启用状态。
- [ ] `python run_upload.py --config config.json --check-config` 通过。
- [ ] 手动执行真实上传成功或能生成明确失败日志。
- [ ] Windows 任务计划程序已配置。
- [ ] 定时任务运行账号具备共享盘和数据库权限。
- [ ] 日志目录能看到 summary 和 upload_log 文件。
