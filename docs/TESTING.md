# 测试

## 分层

| 层级 | 命令 | 外部依赖 |
|---|---|---|
| 后端模块 | `python -m pytest -q --ignore=tests/e2e` | 无；每进程独立临时 SQLite |
| 前端构建 | `npm ci && npm run build:spa-css && npm run build` | Node 22；同时验证原生 SPA CSS 与 React |
| 主 E2E | `python run_e2e.py` | 本仓库 backend:8000 + target:8003 |
| 扩展回归 | `python tests/e2e_regression.py` | backend:8000 |
| 浏览器流程 | `python -m pytest tests/e2e -q` | backend:8000、Chromium；按需运行 |

2026-07-13 公共目录发布验证：后端 458 passed / 1 skipped，主 E2E 73/73，扩展流程 60/60，React 干净构建与直接报告路由通过。容器配置已解析；由于本机 Podman WSL 虚拟机无法进入 running 状态，本轮没有把镜像构建标记为已验证。

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
