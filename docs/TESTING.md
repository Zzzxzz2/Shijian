# 测试

## 分层

| 层级 | 命令 | 外部依赖 |
|---|---|---|
| 后端模块 | `python -m pytest -q --ignore=tests/e2e` | 无；每进程独立临时 SQLite |
| 前端构建 | `npm ci && npm run build:spa-css && npm run build` | Node 22；同时验证原生 SPA CSS 与 React |
| 主 E2E | `python run_e2e.py` | 本仓库 backend:8000 + target:8003 |
| 扩展回归 | `python tests/e2e_regression.py` | backend:8000 |
| 原生 SPA 浏览器流程 | `$env:E2E_BASE_URL='http://127.0.0.1:8000'; python -m pytest tests/e2e -q` | backend:8000、Chromium |
| React 浏览器回归 | `cd frontend/react-app; npx playwright test` | Vite:5173、Chromium |

2026-07-19 发布验证：后端 464/464，主 E2E 73/73，扩展流程 60/60，React Chromium 24/24，原生 SPA Chromium 18/18，Python 编译、SPA CSS 和 React 生产构建通过。本机未安装 Docker CLI，因此本轮不将本地镜像构建标记为已验证；GitHub Actions 仍会执行 Compose 配置检查和三服务镜像构建。

## 主 E2E 覆盖

- 服务与认证
- 项目、统计、覆盖率、认证配置
- API/UI/Workflow/Contract 用例
- 执行结果字段、四步 Workflow、schema_match
- Schema coverage/fuzz/security/all
- Mock 完整管理链路
- Suite 与 Schedule CRUD/trigger
- Profile、Admin、Token、Analytics
- 靶场错误码、慢请求和未认证 401

`run_e2e.py` 会在仓库根目录生成 `e2e-results.json`；该文件被 Git 忽略，防止把运行数据误提交。

## CI

GitHub Actions 执行后端模块测试、Python 编译、React clean build、Compose 配置检查和三服务镜像构建。需要启动真实浏览器与服务的 E2E 保留为本地/发布门禁，避免普通提交依赖外部端口。


## 2026-09 本轮复现方法

主 E2E 需要一个已存在的管理员账号（新数据库的首个注册账号为管理员）。普通账号访问管理员统计返回 403 是正确行为，不能把它放宽为通过。

```powershell
$env:SHIJIAN_BASE_URL='http://127.0.0.1:8010'
$env:SHIJIAN_TARGET_URL='http://127.0.0.1:8013'
$env:E2E_ADMIN_USERNAME='<已有管理员用户名>'
$env:E2E_ADMIN_PASSWORD='<该测试账号密码>'
python run_e2e.py
python -m pytest -q -p no:cacheprovider
node tests/frontend_maturity_check.cjs
```

在 `frontend/react-app` 下执行 `npm run build:spa-css`、`npm run build` 和 `npx playwright test`。开发代理默认指向 8000；使用本轮隔离后端时，启动 Vite 前设置 `$env:BACKEND_URL='http://127.0.0.1:8010'`。

主 E2E 现有 74 个检查，增加 Workflow 四步全部通过断言；失败进程返回非零退出码。React 现有 25 个场景，含过期登录后直达报告的回归。React 自动化使用接口模拟，真实后端浏览器体验另见本轮交接报告。

隔离数据库可通过 DATABASE_URL 指定为仓库内其他 SQLite 文件。不要为方便验收重置已有用户的业务数据库。用例、报告和靶场测试数据会保留以供检查。

## 可靠性与权限专题回归

- `python -m pytest -q -p no:cacheprovider`：包括 `test_run_reliability.py`（冻结、取消、超时、权限、重启恢复）和 `test_target_state_policy.py`（真实靶场路由与隔离数据库）。
- `frontend/react-app` 内执行 `npx playwright test`：模拟 API 的浏览器回归，含中断通过率；`npm run build` 验证生产构建。
- 启动本地平台 8010、靶场 8013、React 5173，配置平台账号环境变量后执行 `python tests/e2e_reliability.py`：实际浏览器验证取消、超时、旧快照与窄屏。
- `python scripts/run_permission_state_topic.py`：实际平台执行 13 条专题 Workflow；失败退出码非零。具体准备及证据见 [专题说明](PERMISSION-STATE-TOPIC.md)。

自动化模拟的恢复测试与实际进程强制终止分别记录；不要把模拟 API 浏览器测试称为后端集成测试。全量最新结果见 [STATUS](STATUS.md)。
