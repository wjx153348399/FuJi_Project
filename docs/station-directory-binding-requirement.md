# 工站目录绑定需求

## 目标

项目统一使用后端字段：

| 字段 | 含义 |
|---|---|
| `flow` | 工站代码/工站标识 |
| `filePath` | Excel 文件完整路径 |

用户维护“目录 -> flow”的绑定关系。程序扫描到目录下的 Excel 文件后，将该文件绑定到对应 `flow`，并在上传、日志、历史记录、去重 key 中使用同一字段。

## 配置格式

```json
{
  "scan": {
    "targets": [
      {
        "flow": "A10",
        "dir": "ExampleStationDirectoryA",
        "enabled": true
      }
    ]
  }
}
```

`dir` 是相对 `share.root` 的目录路径。

## 上传接口

```text
POST /service-qms/file/importImpedanceData
Content-Type: multipart/form-data

file=<Excel 文件>
flow=<工站代码，可选，有值才提交>
filePath=<文件完整路径，可选，有值才提交>
```

不再支持上传字段名配置，也不再提供关闭工站字段的兼容开关。

## 处理要求

- 扫描结果中的候选文件保留 `flow` 和 `filePath` 字段，`flow` 允许为空。
- 解析结果必须继承 `flow` 和 `filePath`。
- 上传日志、历史记录、汇总信息必须使用 `flow` 和 `filePath`，空 `flow` 也要记录。
- 去重 fallback key 有 `flow` 时使用 `flow`，无 `flow` 时使用 `filePath`，避免跨目录误判重复。
- 同一目录只能绑定一个 `flow`。
- 同一个 `flow` 可以绑定多个目录。

## 验收标准

- 配置中使用 `scan.targets[].flow`。
- 上传请求固定包含 `file`；`flow`、`filePath` 有值才提交。
- 日志和历史记录不出现旧字段。
- 全量测试通过。
