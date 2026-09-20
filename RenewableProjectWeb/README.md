# RenewableProjectWeb

新能源项目公开信息查询工具的业务服务目录。完整功能、部署、配置和许可说明请阅读仓库根目录的 [README](../README.md)。

## 快速启动

首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_server.ps1
```

启动服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_server.ps1
```

访问 `http://127.0.0.1:8765/`。局域网用户使用 `http://服务器IP:8765/`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check .\static\app.js
```

## 运行数据

- `data/project_queries.db`：查询历史与证据
- `logs/`：运行日志
- `output/`：Excel 查询结果
- `config/sources.json`：来源、超时、重试与请求间隔配置

以上运行数据不会提交到 Git。
