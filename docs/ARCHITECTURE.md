# 架构

## 组件

```text
Browser
  ├─ :8000 原生 SPA + FastAPI API/WebSocket
  └─ :5173 React 报告页（Nginx 代理 /api 与 /ws）
             │
             ▼
FastAPI backend
  ├─ SQLAlchemy / SQLite
  ├─ asyncio task manager
  ├─ APScheduler persistent job store
  ├─ httpx API/Workflow executor
  ├─ Playwright UI subprocess
  ├─ Mock engine registry
  └─ LLM provider/failover
             │
             ▼
Target APIs / 自带 :8003 演示靶场
```

## 核心数据流

1. 路由验证 JWT 和项目角色。
2. TestRun 固化 case_ids，并交给受信号量限制的后台执行器。
3. 执行器按类型分发至 API、Workflow 或 UI executor。
4. 每个 TestResult 保存状态、耗时、detail 和 failure_category。
5. WebSocket 推送事件；报告 API 提供摘要、截图、Trace 和 diff。

## 权限

- owner：项目、成员和全部执行权限。
- editor：创建/编辑用例并执行。
- viewer：只读项目、用例和报告。
- admin：系统级用户/项目管理，并可按设计绕过项目成员检查。
- guest：显式访客 Token，仅访问允许的公开能力。

## 可靠性边界

- SQLite 启用 WAL、busy timeout 和写入重试。
- TestRun 通过全局信号量限制并发，默认 10。
- APScheduler job 持久化到同一数据库。
- 单个用例异常被转换为 error 结果，run 必须完成收尾。
- 当前仍是单进程架构；需要水平扩展时迁移 PostgreSQL 与独立 worker。
