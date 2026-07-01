# 工站目录配置 Web 工具

该工具用于维护 SQL Server 表 `dbo.station_directory_config`，让用户可以自行配置“目录 -> 工站”的绑定关系。

当前已支持：

- 配置列表页
- 新增和编辑
- 启用和停用
- 目录存在性检测
- 保存前目录安全检查
- 启用、停用、保存操作确认

暂未完成：

- 简单登录和操作权限控制

内部单人本机使用可以暂不做登录保护。部署到服务器并开放给多人访问前，建议补上登录保护，避免同网段用户误操作配置。

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

本机验证建议先使用仅本机可访问的监听地址：

```powershell
uvicorn station_config_web.app:app --host 127.0.0.1 --port 8088
```

打开 `http://127.0.0.1:8088/station-config` 后，按下面顺序验证：

1. 列表能正常显示数据库中的目录配置。
2. 点击“测试目录”，确认真实目录显示“目录存在”。
3. 新增一条测试目录配置，目录存在时应能直接保存。
4. 新增一条不存在的目录配置，第一次保存应只出现警告，不应写入数据库。
5. 在警告页面点击“确认仍然保存”后，才会写入数据库。
6. 测试数据可以启用、停用，并且会弹出确认框。
