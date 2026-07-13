# 试剑 V3 产品范围

## 目标

为个人开发者和小型团队提供一套可本地部署的自动化测试工作台：用统一的数据模型管理目标系统、测试用例、执行任务和报告，并将 API、UI、Workflow、Contract、Mock、Schema 和安全测试串成可重复回归流程。

## 已交付范围

- 用户认证、访客模式、个人中心和管理员管理
- 项目 CRUD、成员管理和 owner/editor/viewer 权限
- API、UI、Workflow、Contract 用例及导入导出
- 异步执行、断言、报告、失败分类、历史 diff
- Mock 录制/回放/转换
- OpenAPI coverage/fuzz/security/all
- Suite、Cron 调度和手动触发
- Quick Test 与 WebSocket 事件流
- Playwright 截图与 Trace
- Token/页面统计和 React 覆盖率/报告页
- 自包含演示靶场

## 明确不在完成范围

- 分布式任务队列与多实例调度
- 企业级审计日志、SSO、组织/租户计费
- 专业漏洞扫描器级别的安全判定
- 性能压测执行器
- 仓库内置第三方 LLM、SMTP 或 Webhook 凭据

## 完成标准

1. 主 E2E 和扩展回归在干净环境中通过。
2. 默认后端测试集通过，浏览器 E2E 单独分层。
3. React 构建通过。
4. Git secret/生成物扫描无违规文件。
5. Compose 配置可解析，生产密钥缺失时 fail-fast。
6. README、部署、API、测试和状态文档使用同一端口与同一功能口径。
