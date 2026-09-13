# 当前状态

更新日期：2026-09-14

## GitHub 展示与发布收尾（2026-09-14）

| 验证 | 结果 | 范围 |
|---|---|---|
| 后端全量 | 493 passed，0 failed，253.19s | 增加 10 项生产密钥、E2E 初始化保护与 WAL 备份回归 |
| 主 E2E | 74/74 | 实际平台与本地靶场，隔离数据库 |
| React Chromium | 26/26 | 模拟 API；包含报告认证、中断统计与图表渲染 |
| 前端构建 | 通过 | SPA CSS、React production build |
| 真实截图 | 5 张已复核 | 工作台、覆盖率、失败报告、Workflow、项目总览，无页面脚本错误或横向溢出 |
| 备份收尾定向回归 | 10/10 | 调整连接释放后再次执行，通过 |

日志位于忽略提交的 `test-results/release-*.log`。演示使用单独的 `backend/shijian_showcase.db`，没有修改历史验收库或正式业务库；[截图数据口径](SHOWCASE.md) 单独说明。生产密钥在初始化数据库前验证，E2E 初始化禁止生产环境，备份使用 SQLite backup API。

本机没有 Docker 命令，镜像构建依赖 GitHub CI 验证；不能把本地测试通过等同于容器已验证。

## 可靠性迭代已验证（2026-09-13）

| 验证 | 结果 | 范围 |
|---|---|---|
| 后端全量 | 483 passed，0 failed，263.41s | 包括 6 条生命周期/快照回归与 4 条靶场策略回归 |
| 主 E2E | 74/74，退出码 0 | 实际 backend:8010 + target:8013，隔离业务数据库 |
| React Chromium | 26/26 | 模拟 API，包括中断通过率与报告登录恢复 |
| React 生产构建 | 通过 | Vite build |
| 原生前端轻量回归 | 通过 | frontend_maturity_check.cjs |
| 真实浏览器 | 通过 | 项目 12，取消 62、超时 63；旧快照、脱敏、SPA/React 报告、390px 窄屏 |
| 实际进程中断恢复 | 通过 | 运行 44，强制终止测试服务后重启，1 条已完成结果保留、1 条未完成 |
| 权限/状态专题 | 13/13 | 基线 9/13，修复后失败重跑 4/4，再全专题 13/13 |
| diff 空白检查 | 通过 | git diff --check |

仅在仓库内 `backend/shijian_review.db` 运行主应用验收；专题修改对象为项目自带的本地靶场。最新日志位于忽略提交的 `test-results/backend-final.log`、`react-final.log`、`e2e-final.log`、`browser-final.log`。下面保留上轮数据，不与本轮累加。

交接：[运行可靠性与限制](RELIABILITY.md)、[权限与状态专题及复现步骤](PERMISSION-STATE-TOPIC.md)。没有重新执行全部历史扩展 E2E，不将模拟 API 测试算作真实后端验证。

## 本轮已验证（2026-09-11）

| 验证 | 结果 | 范围 |
|---|---|---|
| 后端全量 | 473 passed，0 failed | `python -m pytest -q -p no:cacheprovider`，420.53s |
| 收尾定向回归 | 9 passed | 含标签特殊字符精确匹配的最终修复 |
| 主 E2E | 74/74，退出码 0 | 隔离数据库，实际 backend:8010 + target:8013 |
| React Chromium | 25/25 | 模拟 API，含过期登录恢复后报告直达 |
| 前端构建 | 通过 | SPA CSS 与 React production build |
| Node 轻量检查 | 通过 | 编辑保留、调度选择、转义、登录态与 UTC 时间 |
| 实际浏览器 | 通过所列流程 | Schema→保存→执行；失败→修正→重跑→新通过；Workflow 证据；React 返回主平台 |
| HTML 报告 | 生成检查通过 | Workflow 步骤/请求/状态证据与响应式规则 |
| 静态检查 | 通过 | 后端 Python 编译、原生 JS 语法、git diff --check |

实际浏览器还检查了桌面和 390px 窄屏报告，详细过程与已知限制见 [本轮交接报告](OPTIMIZATION-2026-09-11.md)。本轮没有重新执行下方历史记录中的全部扩展 E2E 与原生 SPA 自动化，不合并这些历史数字作本轮总数。

本轮主应用仅使用 `backend/shijian_review.db`；原有业务数据库未用于修改验证。测试数据保留以便复查。首次 E2E 普通账号访问管理员接口得到 403，改用已有管理员测试账号后全部通过；原结果未被当成产品缺陷或放宽断言。

## 历史验证记录（2026-07-19）

- 后端模块测试：464 passed、0 failed
- V3 主 E2E：73/73（本公共目录的独立数据库、backend 与内置 target-system）
- 扩展 E2E：16 个流程、60/60
- 原生 SPA：真实 Chromium 18/18，登录、项目/用例、AI Plan、文档、Schema、UI 执行、截图与 Trace 流程通过
- React：生产构建通过，Chromium 覆盖率页回归 24/24，`/report/1` 直访、未知路由 404 与 401 登录态清理通过
- Python：全项目 `compileall` 与 `pip check` 通过
- Compose：CI 配置会校验 YAML 并构建三个镜像；本机未安装 Docker CLI，本轮未宣称完成本地镜像构建
- Workflow、Contract、Mock、Schedule、权限、Quick Test/WS、截图与 Trace：通过
- CORS allowlist、未认证 401、500 信息隐藏：通过

公共仓库整理后的最终复验结果会以 README 和本文件为唯一发布口径，不再携带旧 PRD 未勾选项或修复前 REVIEW 结论。

## 已知边界

- Perf executor 未实现。
- 外部 SMTP 和各 LLM 供应商需要使用者凭据，仓库不提供也不在默认 CI 调用。
- 浏览器 E2E 是发布门禁，不属于每次提交的快速单测。
- 单实例 SQLite 适合演示与小团队，不宣称分布式生产能力。
