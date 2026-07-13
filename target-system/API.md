# 试剑靶场系统 - API 手册

> 版本：3.0.0 | 端口：8003 | 基地址：`http://localhost:8003/api`
>
> 本系统为试剑 V3 安全测试靶场，**包含故意植入的安全漏洞**，仅供授权测试使用。

---

## 目录

1. [认证方式](#1-认证方式)
2. [公共端点](#2-公共端点)
3. [认证端点](#3-需认证端点)
4. [管理员端点](#4-管理员端点)
5. [工具端点](#5-工具端点)
6. [状态机流转规则](#6-状态机流转规则)
7. [权限说明](#7-权限说明)
8. [已知漏洞](#8-已知漏洞)

---

## 1. 认证方式

```
Authorization: Bearer <JWT_token>
```

所有 `/api` 端点除注册和登录外均需认证。JWT token 通过登录接口获取，有效期 120 分钟。

### 获取 token

```
POST /api/login
Content-Type: application/json

{"username": "admin", "password": "admin123"}
```

响应：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@shijian.test",
    "role": "admin",
    "created_at": "2026-07-06 08:51:01"
  }
}
```

后续请求携带：

```
GET /api/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

预置管理员账号：**admin** / **admin123**

---

## 2. 公共端点

### POST /api/register — 用户注册

> 无需认证

**请求格式：**

| 字段 | 类型 | 约束 |
|------|------|------|
| `username` | string | 2-50 字符 |
| `password` | string | 4-100 字符 |
| `email` | string | 最大 100 字符 |

**请求示例：**

```json
{
  "username": "testuser",
  "password": "pass1234",
  "email": "user@example.com"
}
```

**响应 201：**

```json
{
  "id": 2,
  "username": "testuser",
  "email": "user@example.com",
  "role": "user",
  "created_at": "2026-07-06 08:51:01"
}
```

**错误：**
- `400` — 用户名已存在

---

### POST /api/login — 用户登录

> 无需认证

**请求格式：**

| 字段 | 类型 |
|------|------|
| `username` | string |
| `password` | string |

**请求示例：**

```json
{"username": "admin", "password": "admin123"}
```

**响应 200：**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@shijian.test",
    "role": "admin",
    "created_at": "2026-07-06 08:51:01"
  }
}
```

**错误：**
- `401` — 用户名或密码错误

---

## 3. 需认证端点

以下所有端点均需在 Header 中携带 `Authorization: Bearer <token>`。

### GET /api/me — 获取当前用户

**响应 200：**

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@shijian.test",
  "role": "admin",
  "created_at": "2026-07-06 08:51:01"
}
```

**错误：** `401` — 无 token 或 token 无效

---

### GET /api/tasks — 任务列表（分页 + 筛选）

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码，≥1 |
| `limit` | int | 10 | 每页条数，1-100 |
| `status` | string | — | 筛选状态：`todo` / `doing` / `done` / `archived` |
| `search` | string | — | **标题搜索（存在 SQL 注入漏洞）** |

**⚠️ 搜索参数存在 SQL 注入漏洞** — 见第 8 节。

**响应 200：**

```json
{
  "items": [
    {
      "id": 1,
      "title": "完成任务",
      "description": "这是描述",
      "status": "todo",
      "priority": "high",
      "user_id": 2,
      "created_at": "2026-07-06 08:51:01",
      "updated_at": "2026-07-06 08:51:01"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 10
}
```

---

### POST /api/tasks — 创建任务

**请求格式：**

| 字段 | 类型 | 约束 | 默认值 |
|------|------|------|--------|
| `title` | string | 1-200 字符，必填 | — |
| `description` | string | 最大 2000 字符 | `""` |
| `priority` | string | `low` / `medium` / `high` | `"medium"` |

**请求示例：**

```json
{
  "title": "测试 SQL 注入",
  "description": "试试 f-string 拼接",
  "priority": "high"
}
```

**响应 201：**

```json
{
  "id": 2,
  "title": "测试 SQL 注入",
  "description": "试试 f-string 拼接",
  "status": "todo",
  "priority": "high",
  "user_id": 2,
  "created_at": "2026-07-06 08:51:01",
  "updated_at": "2026-07-06 08:51:01"
}
```

---

### GET /api/tasks/{id} — 获取单个任务（嵌套用户信息）

**响应 200：**

```json
{
  "id": 1,
  "title": "完成任务",
  "description": "这是描述",
  "status": "todo",
  "priority": "high",
  "user_id": 2,
  "created_at": "2026-07-06 08:51:01",
  "updated_at": "2026-07-06 08:51:01",
  "user": {
    "id": 2,
    "username": "testuser",
    "email": "user@example.com",
    "role": "user",
    "created_at": "2026-07-06 08:51:01"
  }
}
```

**错误：** `404` — 任务不存在

---

### PUT /api/tasks/{id} — 更新任务

**请求格式（全部可选）：**

| 字段 | 类型 | 约束 |
|------|------|------|
| `title` | string | 1-200 字符 |
| `description` | string | 最大 2000 字符 |
| `priority` | string | `low` / `medium` / `high` |

**请求示例：**

```json
{
  "title": "更新后的标题",
  "priority": "low"
}
```

**响应 200：** 返回更新后的完整任务对象。

**错误：**
- `403` — 非创建者且非 admin
- `404` — 任务不存在

---

### PUT /api/tasks/{id}/status — 状态流转

**请求格式：**

| 字段 | 类型 | 约束 |
|------|------|------|
| `status` | string | 只能按流转规则设置下一状态 |

**请求示例：**

```json
{"status": "doing"}
```

**响应 200：**

```json
{
  "id": 1,
  "status": "doing",
  "updated_at": "2026-07-06 08:52:00",
  ...
}
```

**状态流转规则见第 6 节。**

**错误：**
- `400` — 无效的状态流转（如从 `todo` 直接到 `done`）
- `404` — 任务不存在

---

### DELETE /api/tasks/{id} — 删除任务

> 仅 admin 角色可用

**响应：** `204 No Content`

**错误：**
- `403` — 非 admin 用户
- `404` — 任务不存在

---

## 4. 管理员端点

### GET /api/admin/users — 获取全部用户列表

> 仅 admin 角色可用

**响应 200：**

```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@shijian.test",
      "role": "admin",
      "created_at": "2026-07-06 08:51:01"
    }
  ]
}
```

**错误：** `403` — 非 admin 用户

---

## 5. 工具端点

### POST /api/upload — 文件上传

> 需认证。接收 multipart/form-data。

**请求格式：** 表单字段 `file`，任意类型文件

**响应 200：**

```json
{
  "filename": "test.txt",
  "size": 1024,
  "message": "File uploaded successfully"
}
```

---

### GET /api/slow?delay=5 — 慢响应

**查询参数：**

| 参数 | 类型 | 默认值 | 约束 |
|------|------|--------|------|
| `delay` | int | 5 | 1-30 秒 |

**响应 200（延迟后返回）：**

```json
{"message": "Response after 5s delay"}
```

---

### GET /api/error/{code} — 指定状态码

**路径参数：** `code` — 支持的值：`200` / `400` / `401` / `403` / `404` / `422` / `500`

**响应示例（`GET /api/error/404`）：**

```json
{"detail": "Not found"}
```

状态码与 `detail` 对应关系：

| 状态码 | detail |
|--------|--------|
| 200 | OK |
| 400 | Bad request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not found |
| 422 | Unprocessable entity |
| 500 | Internal server error |

---

## 6. 状态机流转规则

任务状态仅允许**单向流转**，不可回退：

```
todo  ──→  doing  ──→  done  ──→  archived
```

| 当前状态 | 允许的下一个状态 |
|----------|----------------|
| `todo` | `doing` |
| `doing` | `done` |
| `done` | `archived` |
| `archived` | 无（终态） |

状态流转通过 `PUT /api/tasks/{id}/status` 执行，请求体中只需传入目标状态。

**示例：todo → doing**

```
PUT /api/tasks/1/status
{"status": "doing"}
```

---

## 7. 权限说明

| 端点 | 认证要求 | admin | 普通用户 |
|------|---------|-------|---------|
| `POST /api/register` | ❌ 无需 | ✅ | ✅ |
| `POST /api/login` | ❌ 无需 | ✅ | ✅ |
| `GET /api/me` | ✅ 需要 | ✅ | ✅ |
| `GET /api/tasks` | ✅ 需要 | ✅ | ✅ |
| `POST /api/tasks` | ✅ 需要 | ✅ | ✅ |
| `GET /api/tasks/{id}` | ✅ 需要 | ✅ | ✅ |
| `PUT /api/tasks/{id}` | ✅ 需要 | ✅ | ✅（仅自己的任务） |
| `PUT /api/tasks/{id}/status` | ✅ 需要 | ✅ | ✅（仅自己的任务） |
| `DELETE /api/tasks/{id}` | ✅ 需要 | ✅ | ❌ 403 |
| `POST /api/upload` | ✅ 需要 | ✅ | ✅ |
| `GET /api/slow` | ❌ 无需 | ✅ | ✅ |
| `GET /api/error/{code}` | ❌ 无需 | ✅ | ✅ |
| `GET /api/admin/users` | ✅ 需要 | ✅ | ❌ 403 |

### 权限错误响应

非 admin 用户访问管理端点：

```json
// 状态码 403
{"detail": "Admin access required"}
```

非创建者且非 admin 更新任务：

```json
// 状态码 403
{"detail": "Not authorized to update this task"}
```

---

## 8. 已知漏洞

本系统包含两个故意植入的安全漏洞，供安全测试使用。

### 8.1 SQL 注入 — GET /api/tasks?search=

**位置：** `main.py` 第 287 行

**漏洞描述：** `search` 参数直接通过 Python f-string 拼接到 SQL 查询中，未使用参数化查询。

```python
# 漏洞代码
where_clauses.append(f"title LIKE '%{search}%'")  # 故意不安全
```

**利用方法：**

```bash
# 绕过搜索，返回所有任务
GET /api/tasks?search=' OR '1'='1

# 联合查询探测
GET /api/tasks?search=' UNION SELECT * FROM users--

# 布尔盲注
GET /api/tasks?search=' AND (SELECT COUNT(*) FROM users) > 0--
```

### 8.2 XSS（跨站脚本） — 任务标题渲染

**位置：** `index.html` 第 416-418 行

**漏洞描述：** 任务列表使用 `innerHTML` 直接渲染标题，未做 HTML 转义。

```javascript
// 漏洞代码
<div class="task-title">${t.title}</div>  <!-- 未转义 -->
```

**利用方法：** 创建任务时标题包含 HTML/JavaScript：

```json
POST /api/tasks
{"title": "<img src=x onerror=alert(document.cookie)>", "description": "XSS测试"}
```

当其他用户访问任务列表时，脚本将在其浏览器中执行。

---

## 附录：完整 API 路径速查

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/register` | 注册 | ❌ |
| POST | `/api/login` | 登录 | ❌ |
| GET | `/api/me` | 当前用户 | ✅ |
| GET | `/api/tasks` | 任务列表 | ✅ |
| POST | `/api/tasks` | 创建任务 | ✅ |
| GET | `/api/tasks/{id}` | 获取任务 | ✅ |
| PUT | `/api/tasks/{id}` | 更新任务 | ✅ |
| PUT | `/api/tasks/{id}/status` | 状态流转 | ✅ |
| DELETE | `/api/tasks/{id}` | 删除任务 | ✅ admin |
| POST | `/api/upload` | 文件上传 | ✅ |
| GET | `/api/slow` | 慢响应 | ❌ |
| GET | `/api/error/{code}` | 指定状态码 | ❌ |
| GET | `/api/admin/users` | 用户列表 | ✅ admin |
| GET | `/openapi.json` | OpenAPI 规范 | ❌ |
