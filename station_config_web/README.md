# 工站目录配置 Web 工具

该工具用于维护 SQL Server 表 `dbo.station_directory_config`，让用户可以自行配置“目录 -> 工站”的绑定关系。

第一阶段只提供 Web 工具骨架和配置读取能力，后续会逐步加入：

- 配置列表页
- 新增和编辑
- 启用和停用
- 目录存在性检测
- 简单登录

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

