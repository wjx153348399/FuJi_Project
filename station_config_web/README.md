# 工站目录配置 Web 工具

该工具用于维护 SQL Server 表 `dbo.station_directory_config`，让用户可以自行配置“目录 -> 工站”的绑定关系。

当前已支持：

- 配置列表页
- 新增和编辑
- 启用和停用
- 目录存在性检测

暂未完成：

- 简单登录和操作权限控制

部署到服务器前，建议先完成登录保护，避免同网段用户误操作配置。

## 本地配置

复制示例配置：

```powershell
copy web_config.example.json web_config.json
```

然后在 `web_config.json` 中填写真实数据库账号密码。

`web_config.json` 已加入 `.gitignore`，不要提交真实密码。

## 启动

```powershell
python -m station_config_web.app
```

或：

```powershell
uvicorn station_config_web.app:app --host 0.0.0.0 --port 8088
```
