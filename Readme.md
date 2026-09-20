# 新能源项目公开信息查询工具

基于 [EasySpider](https://github.com/NaiboWang/EasySpider) 二次开发的公司内部公开信息查询工具。系统将 EasySpider 作为底层浏览器采集引擎，对普通用户提供简化的 Web 页面，不开放 XPath、CSS Selector、JS、节点配置或原始任务设计器。

普通用户只需在浏览器中输入关键词，从广东省投资项目在线审批监管平台的公开备案目录筛选项目，再勾选需要深度查询的项目。系统会保存来源证据、整理结构化字段、记录历史与日志，并生成 Excel。

> 当前版本为第一阶段实现，重点适配广东省备案公开目录。自然资源、生态环境、公共资源交易、招投标和电网等信息通过配置的公开搜索范围发现候选页面，再交由 EasySpider 抓取。查询结果仅代表本次检索到的公开信息，不能替代主管部门正式文件。

## 主要功能

- 按关键词、城市、区县和备案通过日期搜索备案项目
- 支持上一页、下一页和官网页码跳转，浏览全部匹配结果
- 支持跨页勾选项目；单次最多选择 10 个项目执行深度查询
- 调用 EasySpider 执行动态网页采集并保留页面原始文本
- 统一整理项目名称、项目代码、建设单位、建设地点、建设规模、投资、备案、土地、环评、EPC、接入系统等字段
- 按项目代码、名称、单位、地点和规模合并来源，避免重复生成主记录
- 为每条来源保存网站、标题、URL、发布日期、抓取时间、原始文本和证据等级
- 使用 SQLite 保存查询条件、历史结果、来源证据和查询日志
- 单个网站访问失败时记录错误并继续处理其他来源
- 自动生成包含 5 个工作表的 Excel，URL 可直接点击

## 土地状态规则

系统不会因为备案材料中出现地址或拟用地面积就判断“土地已落实”。土地状态按明确证据逐级判断：

| 公开证据 | 输出结论 |
| --- | --- |
| 仅有“拟选址”“拟建于”“项目地址”“拟用地”等描述 | 已初步选址，土地落实情况待核实 |
| 建设项目用地预审与选址意见书 | 已取得用地预审及选址意见 |
| 建设用地批准文件 | 建设用地已获批 |
| 土地成交公告、划拨决定书或土地出让合同 | 项目用地已落实 |
| 不动产权证或土地使用权证 | 土地权属已落实 |

没有明确证据时，相关字段显示“公开信息暂未查询到”，不自行推断。

## 系统结构

```text
EasySpider/
├─ ExecuteStage/                 EasySpider 任务执行引擎
├─ ElectronJS/                   EasySpider 上游任务与运行资源
└─ RenewableProjectWeb/          新能源项目查询业务系统
   ├─ app.py                     FastAPI 服务及业务接口
   ├─ project_tool/              采集适配、归一化、存储和导出
   ├─ static/                    普通用户 Web 页面
   ├─ config/sources.json        来源范围与运行参数
   ├─ scripts/                   ChromeDriver 配置与检查脚本
   ├─ tests/                     自动测试
   ├─ install_server.ps1         Windows 首次安装脚本
   └─ run_server.ps1             Windows 启动脚本
```

业务处理链路：

```text
关键词检索 → 展示备案候选项目 → 用户勾选 → 发现其他公开来源
→ EasySpider 抓取页面 → 字段归一化与证据合并 → SQLite 保存 → Excel 导出
```

## Windows 服务器部署

### 环境要求

- Windows 10/11 或 Windows Server
- Python 3.10 及以上版本
- Google Chrome
- 可以访问目标公开网站的网络环境

普通用户电脑只需要浏览器，不需要安装 Python、Node.js 或 EasySpider。

### 首次安装

在 PowerShell 中进入业务目录：

```powershell
cd C:\Users\Jamyoung\Desktop\Python\EasySpider\RenewableProjectWeb
powershell -ExecutionPolicy Bypass -File .\install_server.ps1
```

安装脚本会创建独立的 `.venv`、安装依赖，并在 `runtime` 目录配置与本机 Chrome 匹配的 ChromeDriver。

### 启动服务

```powershell
cd C:\Users\Jamyoung\Desktop\Python\EasySpider\RenewableProjectWeb
powershell -ExecutionPolicy Bypass -File .\run_server.ps1
```

本机访问：`http://127.0.0.1:8765/`

局域网其他电脑访问：`http://服务器IP:8765/`

如其他电脑无法访问，请检查 Windows 防火墙、公司网络策略以及服务器的 8765 端口。生产环境建议通过反向代理提供访问控制和 HTTPS；当前应用自身不包含用户登录与权限管理。

## 使用流程

1. 输入项目关键词；城市、区县和备案通过日期可以留空。
2. 点击“搜索项目”，等待官网返回结果。
3. 使用“上一页”“下一页”或页码跳转查看结果。
4. 勾选需要深度查询的项目，单次最多 10 个。
5. 点击“查询所选项目”，等待各公开来源查询完成。
6. 点击结果行查看完整字段、来源链接和原始文本。
7. 点击“导出 Excel”下载结果，也可通过“历史查询”和“查看日志”检查过去的执行记录。

官网每页最多返回 15 条数据。按钮显示“正在加载…”时表示 EasySpider 正在访问官网，通常需要等待数秒。

## Excel 输出

完成查询后，文件保存在 `RenewableProjectWeb/output/`，文件名格式为 `项目查询结果_YYYYMMDD_HHMMSS.xlsx`，包含以下工作表：

1. 项目汇总
2. 信息来源
3. 土地情况
4. 招投标情况
5. 查询日志

## 数据与日志

| 内容 | 位置 |
| --- | --- |
| SQLite 数据库 | `RenewableProjectWeb/data/project_queries.db` |
| 每日日志 | `RenewableProjectWeb/logs/YYYY-MM-DD.log` |
| Excel 文件 | `RenewableProjectWeb/output/` |
| 来源配置 | `RenewableProjectWeb/config/sources.json` |

`data`、`logs`、`output`、虚拟环境和本机浏览器驱动均已在 `.gitignore` 中排除，不应提交到仓库。

## 配置

编辑 `RenewableProjectWeb/config/sources.json` 可以调整：

- 请求间隔 `request_interval_seconds`
- 页面超时 `page_timeout_seconds`
- 失败重试次数 `retry_count`
- 单个项目最多发现的候选网址数 `max_discovered_urls`
- 启用的来源类别与搜索域名 `sources`
- 已知公开页面 `bootstrap_pages`

新增来源时应只配置无需登录、无需绕过权限即可访问的公开网站，并保持合理请求频率。

## 开发与测试

在 `RenewableProjectWeb` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check .\static\app.js
```

核心模块：

- `project_tool/easyspider_adapter.py`：生成并执行内部 EasySpider 任务
- `project_tool/discovery.py`：按来源配置发现候选公开页面
- `project_tool/normalization.py`：字段抽取、证据分级、冲突合并和土地规则
- `project_tool/database.py`：SQLite 数据存储
- `project_tool/exporter.py`：Excel 工作簿生成
- `project_tool/jobs.py`：后台任务、进度、停止与异常隔离

## 使用边界

本项目只访问无需绕过权限即可公开访问的信息，不实现验证码破解、登录绕过、反爬绕过、代理池攻击或高频并发请求。遇到人工验证、403、超时、页面改版或网络异常时，程序应记录日志并继续查询其他来源。

公开页面可能发生变化，自动抽取也可能遗漏或误判。对投资、土地、环评、招标和电网接入等重要事项，应打开保存的来源 URL 核对原始文件。

## 上游项目与许可证

本项目基于 EasySpider 二次开发：

- 上游仓库：[NaiboWang/EasySpider](https://github.com/NaiboWang/EasySpider)
- 上游网站：[easyspider.net](http://www.easyspider.net)
- 上游许可证：AGPL-3.0

本仓库继续遵守 AGPL-3.0。分发修改版、提供网络服务或对外部署时，请同时遵守上游许可证关于对应源代码提供、版权声明和免责声明的要求。详见仓库中的 `LICENSE`。
