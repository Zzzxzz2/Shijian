# 部署

## Docker/Podman Compose

前提：Docker Engine 24+ 与 Compose v2，或兼容的 Podman Compose。

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_hex(32))"
```

将输出写入 `.env`：

- `JWT_SECRET`：随机 URL-safe 字符串。
- `API_KEY_ENCRYPTION_KEY`：64 个十六进制字符，对应 32 字节 AES Key。
- `CORS_ALLOW_ORIGINS`：实际访问主 SPA 和 React 页面的 origin，逗号分隔，不能使用 `*`。
- `BASE_URL`：外部可访问的主系统 URL。

邮件默认关闭。旧开发环境的 QQ SMTP 授权码已撤销，本仓库没有保存该值。需要邮件时重新生成独立授权码，只写入服务器 `.env`：

```ini
QQ_ALERT_EMAIL=receiver@example.com
QQ_SMTP_USER=sender@qq.com
QQ_SMTP_AUTH_CODE=  # 仅在服务器 .env 中填写新授权码
QQ_SMTP_HOST=smtp.qq.com
QQ_SMTP_PORT=587
```

启动：

```bash
docker compose config -q
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/docs
curl http://127.0.0.1:5173/
curl http://127.0.0.1:8003/
```

服务：

| 服务 | 端口 | 数据 |
|---|---:|---|
| backend + 原生 SPA | 8000 | `shijian-data`、uploads、screenshots volumes |
| React 报告页 | 5173 | 无状态静态文件 |
| 演示靶场 | 127.0.0.1:8003 | 仅用于本机测试，Compose 不对外网监听 |

## 首次初始化

打开 `/app.html` 注册第一个用户；全新数据库的第一个用户自动成为管理员。不要在公网环境使用 E2E 默认账号。

## 反向代理

生产环境建议只公开同域 HTTPS：

- `/` 与 `/api`、`/ws` 代理 backend:8000。
- `/report` 或独立子域代理 report-ui:80。
- WebSocket 代理必须转发 Upgrade/Connection headers。
- 保留 Compose 中的 `127.0.0.1:8003:8003` 绑定，不公开靶场端口。

## 更新与备份

```bash
docker compose pull
docker compose up --build -d
docker run --rm -v shijian-data:/data -v "$PWD:/backup" alpine \
  cp /data/shijian.db /backup/shijian-$(date +%F).db
```

升级前同时备份数据库、uploads 和 screenshots volumes。SQLite 文件备份应在停止写入或使用 SQLite backup API 时执行；Windows 本地可使用 `scripts/backup.ps1`。

## 生产限制

当前为单实例 SQLite 部署。需要多副本、高并发或严格任务可靠性时，应先迁移 PostgreSQL、外部任务队列与集中对象存储。
