# API 指南

运行后以 `/docs` 和 `/openapi.json` 为机器可验证的完整接口文档；本文只维护稳定分组，避免手写字段与代码漂移。

| 前缀 | 功能 |
|---|---|
| `/api/auth` | 注册、登录、当前用户、访客 Token、改密、邮箱验证 |
| `/api/projects` | 项目、统计、覆盖率、成员、用例、运行、Mock、Suite、Schedule、Schema、安全生成 |
| `/api/runs` | 跨项目运行查询与历史 diff |
| `/api/quick-test` | 自然语言即时执行 |
| `/api/api-keys` | 加密 API Key 管理 |
| `/api/docs` | 项目文档上传与删除 |
| `/api/user` | 个人中心与通知设置 |
| `/api/admin` | 系统统计、用户和项目管理 |
| `/api/token-stats` | LLM Token 统计 |
| `/api/analytics` | 页面访问统计与验证链接 |
| `/api/screenshots` | UI 截图与 Trace 下载 |
| `/ws` | Run 与 Quick Test 实时事件 |

## 认证

除注册、登录、访客 Token 和静态页面外，API 使用：

```http
Authorization: Bearer <access_token>
```

未认证返回 401；已认证但项目角色不足返回 403；为避免泄露项目存在性，部分非成员资源可返回 404。

## 错误响应

```json
{"detail": "Human-readable message"}
```

未处理异常统一返回 `{"detail":"Internal server error"}`，堆栈只写服务端日志。


## 2026-09 行为补充

- `POST /api/projects/{pid}/runs/{run_id}/retry-failed`：editor 及以上；终态执行中仍存在的 fail/error 用例创建新执行，返回 201。运行中返回 409，无可重跑用例返回 400。
- `DELETE /api/projects/{pid}/runs/{run_id}`：queued/running 返回 409，防止删除执行中的记录。
- 项目列表附加 `case_count`、`latest_run`；offset 非负，limit 为 1–200。
- Schema parse 成功后更新项目端点基线；`coverage_summary` 描述本次生成候选覆盖的唯一端点数。项目 `/coverage` 描述基线与已保存用例的交集，两者口径不同。
- `/api/analytics/leave/{view_id}` 同时接受 PUT 和 sendBeacon 使用的 POST。

## 执行生命周期与历史输入

创建执行、按标签执行支持 `timeout_seconds`：整数 1–3600，默认 300，不含队列等待。
`POST /api/projects/{pid}/runs/{run_id}/cancel` 需要 editor 权限；对终态重复调用返回当前记录，不重复执行或改写终态。跨项目请求返回 404。

运行响应增加 `timeout_seconds`、`termination_reason`；活动态为 queued/pending/running，终态为 done/failed/cancelled/timeout/interrupted。`summary.skipped` 记录未完成数，`summary.total` 是计划数。
详情接口提供只读 `snapshot`，包含创建时冻结的项目与用例，公开内容经过常见凭据脱敏；旧记录可为 null。失败重跑使用当前用例创建新快照。完整行为与限制见 [可靠性说明](RELIABILITY.md)。
