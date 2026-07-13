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
