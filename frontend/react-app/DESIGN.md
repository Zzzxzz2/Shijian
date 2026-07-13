# 覆盖率仪表盘 · Design System

> V3 前端 | 承影首秀 | React 18 + Tailwind + Chart.js

---

## 1. 设计原则

- **独立视觉** — 不做 V2 霓虹赛博风，用 GitHub dark 纯色基底
- **动画克制** — 只有卡片边框脉冲 + 列表滑入 + 骨架屏 shimmer，不搞花哨入场
- **数据优先** — 图表和数字是第一等公民，动画不干扰数据读取

---

## 2. 色彩系统

| Token | 值 | 用途 |
|-------|-----|------|
| `bg-surface` | `#0d1117` | 页面背景（GitHub dark） |
| `bg-surface-raised` | `#161b22` | 卡片/容器背景 |
| `bg-surface-overlay` | `#1c2128` | 列表项 hover |
| `border-default` | `#30363d` | 普通边框 |
| `border-muted` | `#21262d` | 网格线/分割线 |
| `accent-blue` | `#58a6ff` | 默认卡片边框，Chart.js 折线/条形 |
| `accent-purple` | `#bc8cff` | Param coverage |
| `accent-green` | `#3fb950` | 饼图已覆盖，通过率≥80% |
| `accent-red` | `#f85149` | 错误文字，DELETE badge |
| `accent-orange` | `#d29922` | 通过率<80%，PUT/PATCH badge |
| `text-primary` | `#e6edf3` | 正文/标题 |
| `text-muted` | `#8b949e` | 辅助文字/labels |
| `text-dim` | `#484f58` | 极淡（雷达 tick、placeholder） |

### 渐变色（卡片边框脉冲）

```
blue:   rgba(88, 166, 255, 0.3) → rgba(188, 140, 255, 0.3)
green:  rgba(63, 185, 80, 0.3) → rgba(88, 166, 255, 0.3)
purple: rgba(188, 140, 255, 0.3) → rgba(88, 166, 255, 0.3)
orange: rgba(210, 153, 34, 0.3) → rgba(255, 88, 73, 0.3)
```

---

## 3. 字体

| 用途 | 字体 | 尺寸 |
|------|------|------|
| 页面标题 | Tailwind `text-xl font-bold` | 20px |
| 卡片数字 | Tailwind `text-2xl font-bold` | 24px |
| 卡片标签 | Tailwind `text-xs uppercase` | 12px |
| 图表标题 | Tailwind `text-sm font-medium` | 14px |
| 端点列表 | Tailwind `text-sm font-mono` | 14px |
| HTTP Method badge | Tailwind `text-xs font-mono` | 12px |

---

## 4. 间距与圆角

| Token | 值 |
|-------|-----|
| 页面 padding | `px-4 py-8` |
| 卡片间距 | `gap-4` |
| 卡片圆角 | `rounded-xl` (12px) |
| 列表项圆角 | `rounded-lg` (8px) |
| 按钮圆角 | `rounded-lg` (8px) |
| 图表内边距 | `p-4` |
| 列表项内边距 | `px-3 py-2` |

---

## 5. 组件规范

### StatCard
- 背景 `bg-surface-raised`, 边框 `border-border`
- 1px 渐变伪边框（`bg-gradient-to-r` + `mask-composite: exclude`）
- hover 时边框透明度 0.4 → 0.7
- 内容区 `m-[1px]` + `bg-surface` 遮盖底层渐变，产生"边框发光"效果

### Chart Container (`.chart-container`)
- 背景 `bg-surface-raised`, 边框 `1px solid #30363d`, 圆角 `rounded-xl`
- 内边距 `p-4`
- 所有 Chart.js 图表共用此容器

### UncoveredList
- 空白态：居中显示 🎉 全部已覆盖
- 每行：HTTP method badge + path（`font-mono`）+ status tag
- 每行 `animate-slide-in` + 递增 `animation-delay` 实现交错入场
- 最多 80 行，超出滚动（`max-h-80 overflow-y-auto`）

### Skeleton
- 背景渐变 `161b22 → 1c2128 → 161b22`, 尺寸 `200% 100%`
- `shimmer` 动画 1.5s 无限循环，从右到左扫描
- 加载中展示 6 个以上骨架块，无 spinner

---

## 6. 响应式布局

| 断点 | 布局 |
|------|------|
| < 640px (sm) | 统计卡片 1 列，图表 1 列 |
| 640-768px (md) | 统计卡片 3 列，图表 3 列 |
| > 768px (md+) | 最大宽度 `max-w-7xl`，3 列图表网格 |

---

## 7. 暗色主题

- `color-scheme: dark` 全局
- scrollbar 8px 宽，thumb `#30363d`
- 所有 Chart.js 图表使用同样的暗色色板（tooltip 背景 `#1c2128`，文字 `#e6edf3`）
- 无明暗切换开关（纯暗色）

---

## 8. 数据流

```
页面加载 → 3 个 API 并行请求
  ├─ GET /coverage   → Schema/Simple 模式判定 + endpoints + 类型分布
  ├─ GET /stats      → 用例/执行次数（fallback null）
  └─ GET /runs?limit=20 → 执行趋势数据（fallback null）

各自 .catch(() => null) 静默降级，不阻断渲染
```

StatCard 覆盖率数字优先取 API 返回的 `endpoints_covered/total/uncovered`，后端没返时前端从 `endpoints[]` 自己算。
