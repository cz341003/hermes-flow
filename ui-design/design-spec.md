# HERMES · 迁移控制面 — UI 设计规范（v1.0）

> 交付物：`index.html`（单文件可交互原型）+ `screenshots/`（8 屏 + 总览）+ 本规范 + `PROMPTS.md` + `screenshot.ps1`
> 场景：Vue2 → Vue3 多智能体迁移工程，工作流 = 结构分析 → 依赖分析 → 代码转化 → 质量门控 → 浏览器验证 → 修复回环
> 基准分辨率：1600 × 1000（桌面优先，兼容 1280 / 1440 / 1920）

---

## 1. 设计定位

**一句话：把"多智能体迁移"做成一台可读、可控、可追溯的工程仪表台。**

> **范围说明（重要）**：本设计稿是**独立演示壳**，仅用于评审与视觉验收。生产落地时它会被拆成 Hermes 插件 Dashboard `/flow` tab 内的 8 个子页，**复用宿主侧栏与顶栏**，不自建全局壳、不接管登录态；侧栏导航在落地时映射为 tab 内的子页签。集成细节见 §8。

| 关键词 | 落地方式 |
|---|---|
| 工程控制台 | 极深石墨底 + 发丝级描边 + 等宽数字 + 微标签（`9.5–10px / 0.14em` 字距） |
| 信号化状态 | 青绿 = 运行/交互，绿 = 通过，琥珀 = 回环/退避，红 = 失败/人工门，灰 = 空闲/等待 |
| 信息密度 | 12 列栅格、38px 面板头、31px 表头、44px 表格行、KPI 指标条 |
| 可追溯 | 每条证据、评分、异常都带时间戳 / 文件路径 / 来源，运行链路可回放 |
| 克制的动效 | 仅在"活数据"上动：运行点脉冲、日志插入、进度推进、审查雷达回弹；无大面积渐变、无玻璃拟态 |

**明确避免**：AI 紫色渐变、大面积毛玻璃、发光卡片堆叠、emoji 图标、无意义的 3D/粒子背景。所有图标为内联 SVG（68 个 symbol，Lucide 风格 24×24 线性图标），全部资源内联，双击即可离线打开。

---

## 2. 信息架构（IA）

```
HERMES / Migration Control Plane
├─ 运行 (RUN)
│  ├─ 工作台        #workbench   目标总览 / 当前运行 / Agent 实时态 / 证据流 / 信号快照
│  └─ 运行监控      #monitor     批次进度 / 时间轴 / 调度日志 / 异常自愈 / 证据链 / 断点续跑
├─ 构建 (BUILD)
│  ├─ 专家          #agents      8 个专家卡片 / 筛选 / 卡片·列表切换 / 详情抽屉
│  ├─ 技能          #skills      12 个技能库 / 阶段分布 / 导入 / 重新加载骨架屏
│  └─ 工作流编排    #flow        DAG 画布 / 节点库 / 属性面板 / 模板库 / 校验
├─ 治理 (GOVERN)
│  ├─ 记忆中心      #memory      经验卡片 / 用户偏好 / 工作区记忆 / 回灌开关
│  └─ 质量门控      #quality     五信号雷达 / 评分分布 / 门控规则 / 回环记录 / 重新审查
└─ 系统 (SYSTEM)
   └─ 设置          #settings    内核 / 并发 / 配额 / 门控权重 / 模型路由 / 危险区
```

**全局常驻**：左侧 236px 导航（分组 + 徽标 + 内核状态卡）、顶部 56px 全局栏（面包屑 / 命令搜索 / 目标胶囊 / 通知 / 头像）、右下 Toast 栈、Ctrl+K 命令面板、专家详情抽屉。

**页面标题体系**：`RUN · 01 / LIVE MISSION`（微标签）→ `工作台`（25px 展示字体）→ 一行说明（≤ 80 字）。右侧为页面级动作与同步状态。

---

## 3. 设计 Tokens

### 3.1 色彩

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#07090B` | 应用底色 |
| `--side` | `#0A0D10 → #080B0E` | 侧栏（垂直渐变） |
| `--panel` | `#0F1419 → #0D1217` | 面板/卡片 |
| `--raise` / `--raise-2` | `#161D25` / `#1C242E` | 悬浮、输入框、选中行 |
| `--line` / `--line-2` / `--line-3` | `#1E262F` / `#2A3440` / `#394654` | 发丝分隔 / 控件描边 / 强调描边 |
| `--ink` | `#E6EDF3` | 一级文本（正文、标题） |
| `--ink-2` | `#A9B5C1` | 二级文本（说明、表体） |
| `--ink-3` | `#8B97A4` | 三级文本（表头、标签，≥ 4.5:1） |
| `--ink-4` | `#5D6976` | 装饰性元信息（时间戳、单位），不承载关键语义 |
| `--acc` / `--acc-hi` / `--acc-lo` | `#35CFC1` / `#63E4D7` / `#1E9E94` | 品牌信号色：运行中、可交互、焦点、进度 |
| `--ok` | `#56C98A` | 通过 / 完成 / 已恢复 |
| `--warn` | `#E0A93E` | 回环 / 退避 / 低分 / 待处理 |
| `--err` | `#E9695F` | 失败 / 人工门 / 构建错误 |
| `--info` | `#5E9CF5` | 中性信息 / 快照 / 上下文 |

**状态色语义（不可混用）**

| 状态 | 颜色 | 徽标样式 | 使用场景 |
|---|---|---|---|
| running / live | 青绿 `--acc` + 脉冲点 | `st.run` | 当前阶段、Agent 运行、门控评分中、LIVE |
| success | 绿 `--ok` | `st.ok` | 节点完成、门控通过、异常自愈完成 |
| warning / loop | 琥珀 `--warn` | `st.warn`、虚线回环边 | 评分未达标、429 退避、回环轮次 |
| error / manual gate | 红 `--err` | `st.err` | 构建失败、修复失败、人工门、危险操作 |
| idle / queued | 灰 `--ink-3` | `st.idle` | 空闲、等待、未绑定 |
| info | 蓝 `--info` | `st.info` | 快照、Diff、上下文信息 |

> 状态同时用「颜色 + 文案 + 点/图标」三重编码，色弱用户仍可区分。

### 3.2 字体与字号

| 角色 | 字体栈 | 字号 / 行高 | 字距 |
|---|---|---|---|
| 品牌 / 展示 / 微标签 | `Bahnschrift, DIN Alternate, Segoe UI, Microsoft YaHei UI` | 25 / 20 / 16 / 10 / 9.5 | `.14em–.20em`（大写微标签） |
| 正文 / 表格 / 导航 | `Segoe UI, Microsoft YaHei UI, PingFang SC` | 13 / 12.5 / 12 / 11.5 | 0 |
| 数字 / 代码 / 日志 / 时间 | `Cascadia Mono, Cascadia Code, Consolas, SFMono-Regular` | 27（KPI）/ 15 / 12 / 11 / 10.5 | `tabular-nums` |

> 全部为系统字体，不依赖网络字体（离线可开，避免 FOUT）。数字统一等宽 + 表格数字对齐。

### 3.3 间距 / 圆角 / 阴影 / 动效

| Token | 值 |
|---|---|
| 间距阶 | 2 / 4 / 6 / 8 / 9 / 10 / 12（`--gap`）/ 14 / 16 / 20 / 22（`--pad`）/ 30 |
| 圆角 `--r-xs/sm/md/lg` | 3 / 5 / 7 / 9 px（徽标 3、控件 5、面板 7、抽屉 0-9） |
| 阴影 | 面板：`inset 0 1px 0 rgba(255,255,255,.025), 0 14px 28px -24px #000`；浮层：`0 24px 60px -20px rgba(0,0,0,.85)` |
| 关键尺寸 | 侧栏 236、顶栏 56、面板头 38、表头 31、表格行 44、内容最大宽 1680（≥1760 屏）|
| 动效 | 交互 150–180ms；页面入场 280ms `cubic-bezier(.22,.8,.3,1)`；进度 700ms；脉冲 1.8s；日志行插入 2600ms 间隔；`prefers-reduced-motion` 全量降级 |
| z-index | 1 内容 / 2 表头 / 3 DAG 节点 / 5 画布浮层 / 10 顶栏 / 60 遮罩 / 70 抽屉 / 90 命令面板 / 100 Toast |

### 3.4 栅格

- 12 列栅格，间距 12px；面板可跨 3/4/5/7/8/12 列（`.sp3/.sp4/.sp5/.sp7/.sp8/.sp12`）。
- 页面内边距：`20px 22px 30px`；`>1760px` 时 `30px`，内容居中最大 1680。
- 桌面固定「左栏 + 顶栏 + 滚动内容区」，滚动只发生在 `.view`，侧栏和顶栏常驻。


### 3.5 门控语义（PRD 对齐，必须与实现一致）

| 项 | 规则 |
|---|---|
| 五信号权重 | AST **20** / 构建 **25** / 类型 **15** / 浏览器 **25** / 行为 **15**（合计 100） |
| 通过 | 加权综合 ≥ **85** |
| 警告通过 | 加权综合 **70–84**（记录 warning，不进入回环） |
| 回环 | 加权综合 **< 70**，最多 **3 轮** |
| 升级 | 回环 3 轮仍未通过 → 人工门（暂停等待迁移负责人） |
| 示例 | UserList 92/88/86/90/84 → 加权 88.4 → 88（通过）；TreeSelect 86/0/82/91/81 → 64.4 → 64（回环） |

> PRD 未定义的附加规则（如"任一信号 <60 直接回环""行为一致性下限 80"）已从设计稿与实现中移除，避免与评分口径冲突。


### 3.6 批次循环（FR-10）语义与组件

**三层循环**：L1 插件批次调度（默认串行 wave）→ L2 可选同层并行（1–3 批，仅同 wave）→ L3 子代理批内串行处理文件。

| 项 | 默认 / 规则 |
|---|---|
| 批大小 | 7 文件（1–12 自适应，按 28,000 chars 预算装箱） |
| 并发批次 | 1（默认波次串行；可选 2–3，`subagent_lifecycle` 池上限 8） |
| 每 tick 批数 | 10（到点 checkpoint 干净退出） |
| 单批等待 | 1800s（超时 cancel → 重试 → 拆分） |
| 失败拆分 | 最多 2 层（二分拆批，退到 single_file） |
| 上下文预算 | 28,000 chars / 批（lifecycle 结果 ≤32,000；delegate summary ≤24,000） |
| 批次状态 | planned / ready / running / gated / done / failed / split / skipped |
| 文件状态 | pending / running / staged / applied / failed / manual（staging + applied_hash + attempt_id） |
| 批次事件 | `batch.claim → batch.ingest → batch.apply → batch.gate → batch.split / batch.retry` |
| 证据 | 批次级 `batch-xx.summary.json` + 文件级 diff / parse / 评分 |
| 质量门 | **批级 AST/diff + 白名单**；wave 可选增量；全量 build/browser 只在聚合门；失败只重跑/拆该批 |

**新增组件**：批次进度条（workbench）、批次队列（wave 分组 + 可展开文件列表）、批次 chip（7 状态）、批次事件日志标签、专家批次循环配置卡、DAG 批次节点徽标 + 批量属性区 + 批次预览条、质量批次列 + 批次通过率 KPI、设置批量执行面板。

---

## 4. 页面清单与规格

### 01 工作台 `#workbench` — 运行总览

- **布局**：标题区 → 4 卡 KPI 条 → 左 62% 当前运行（含 6 阶段轨道 + 回环提示）/ 右 38% Agent 实时状态 → 底部 7:5 证据流 + 质量信号快照。
- **数据口径**：目标 287 文件 / 已转化 126（43.9%，门控通过 78）/ 通过率 91.0%（均值 88.6）/ 活跃异常 3；阶段 4/6 质量门控，批次 **18 / 43（42%）**，阶段进度 61.4%，已用 01:12:48。
- **批次进度**：当前 Run 卡新增「批次循环」细进度条：批次 18/43（42%）+ 文件 126/287（44%），两条 3px 细条；下钻可跳监控页批次队列。
- **状态**：运行中阶段青绿高亮 + 脉冲；完成 3 阶段绿色；后续 2 阶段灰；回环提示为琥珀虚线块（TreeSelect.vue 第 2/3 轮）。
- **微交互**：进度条随假数据缓慢推进（2.2s/step）；「暂停」切换；「查看当前运行」跳监控页。

### 02 运行监控 `#monitor` — 实时看板

- **布局**：运行摘要条（LIVE / 批次 18/43 / 批次 42% · 文件 44% / 已用 / ETA / 六阶段步进条）→ 三列：左 3 列（**批次队列** + 异常与自愈）、中 5 列（执行时间轴 + 调度日志终端）、右 4 列（Agent 实时状态 + 证据链）。
- **批次队列**：按 wave 分组（WAVE 3 · VIEWS / WAVE 2 · COMPONENTS），批次行 = `#18 · 7 文件 · running · 第 1 轮`，状态色 planned / ready / running / gated / done / failed / split；点击行展开批内文件列表（done / failed / pending），底部显示 tick / 并发 / 预算 / 拆分深度。
- **证据链**：Tab = 构建日志 / diff / 截图 / **批次**，默认为失败构建（`TS2339 filters`）→ 错误态；批次 tab 展示 `batch-18.summary.json` + 7 文件的 done/failed/pending 与 diff 行数。
- **异常与自愈**：429 限流（倒计时环 + 立即恢复）、上下文截断（已自愈）、任务超时（重试）→ 自动恢复开关 + 从检查点续跑。
- **动效**：计时器每秒 +0.4s；日志每 2.6s 顶部插入一条着色 `batch.claim / batch.ingest / batch.gate / batch.split / batch.retry`（另有 gate/turn/fix/verify/ckpt）；倒计时 8→0 自动恢复并更新导航异常徽标；暂停时冻结全部流。
- **状态**：LIVE 徽标、自愈开启、构建失败、回环中、等待。

### 03 专家 `#agents` — 专家注册表

- **布局**：筛选行（全部 8 / 运行 2 / 空闲 4 / 失败 1 / 已完成 1）→ 搜索 → 卡片/列表切换 → 3×3 卡片网格（8 专家 + 添加卡）。
- **卡片内容**：头像字（转/析/依/质/验/修/记/迁）、名称 + 版本、角色 mono、状态徽标、2 行提示词摘要、技能标签（+N）、成功率 / 最近任务、详情入口。运行中的代码转化专家额外显示 `循环 · 7 文件/批` 徽标 + 细进度条 + `批次 18/43`。
- **状态**：运行中卡顶部扫描线；失败卡左侧红条 + 红色状态；空闲卡常规；hover 抬升 1px + 边框提亮。
- **交互**：点击卡片/详情 → 右侧 468px 抽屉（状态、4 项指标、角色提示词全文、**批次循环配置**（per_batch / single_file、每批 7 文件、并发 1、内层 serial、失败拆分 2 层、上下文预算 28,000、每批质量门 ON）、技能绑定、最近运行时间轴、下线/保存并热加载）；循环配置区仅对代码转化专家展示；筛选/搜索无结果 → 空态；失败卡「重试」1.5s 后转运行中。

### 04 技能 `#skills` — 技能库

- **布局**：搜索 + 阶段筛选（全部12 / transform5 / deps3 / quality1 / verify1 / memory1）→ 左表（技能、适用阶段、绑定专家、使用率、最近使用、来源、编辑）+ 右栏（阶段分布、导入 SKILL.md、最近绑定变更、未绑定提示）。
- **状态**：默认直接展示表格；点面板头「刷新」触发 0.9s 骨架屏（5 行 shimmer）后恢复；搜索无结果显示空态。
- **数据**：Vue3 语法升级 86% / 128 次、Options→Composition 71%、Vuex→Pinia 48%、Webpack→Vite 33%、ztree→a-tree 27%、质量门控评分 76%、浏览器验证 41%。

### 05 工作流编排 `#flow` — DAG 画布

- **布局**：模板条（Vue2→Vue3 六阶段模板 v3）/ 保存 / 运行 → 画布（980×554 坐标空间，点阵背景，可滚动）+ 右侧 306px 属性面板。
- **节点**：8 节点 8 连线。串行链（结构分析→依赖分析→**代码转化 BATCH**→质量门→浏览器验证）、并行分支（依赖分析→配置迁移→质量门）、条件门（GATE，score ≥ 85）、回环（LOOP，虚线琥珀 ≤3 轮）、人工门（HUMAN）。代码转化节点显示 `×43 批` 徽标 + `批次 18/43`。
- **状态**：完成绿边、运行青绿脉冲（代码转化 64%）、等待灰、选中青绿描边 + 四角定位标记。
- **属性面板**：默认选中代码转化（batch）节点；Tab 属性/输入输出/运行记录；字段 = 名称、绑定专家、超时 180s、**批量执行区**（批量源 report:deps.files、批大小 7、并发批次 1、内层循环 serial、失败拆分 2 层、每批质量门 ON、上下文预算 28,000）、挂载技能、失败策略；选中质量门时切换为阈值 / 回环 / CEL 字段。底部 4 项运行统计 + 保存/删除；画布左下角常驻「批次预览」前 5 批。
- **交互**：点节点 → 选中并联动属性面板；名称输入实时改节点标题；面板头 Tab 切换；缩放控件 100%；模板切换 Toast。

### 06 记忆中心 `#memory` — 经验库

- **布局**：4 卡统计（经验 128 / 命中 342 / 回灌率 76.4% / 偏好 12）→ 搜索 + 坑类型筛选 → 左 2 列经验卡（6 张）+ 右栏（用户偏好 5 条、工作区记忆 5 条、回灌设置）。
- **经验卡结构**：类型标签 + 标识 + 命中次数 → 标题 → 触发条件 → 解法（含 `code` 高亮）→ 最近命中文件与「回灌」动作。
- **状态**：搜索无结果 → 空态 + 清除筛选；回灌按钮 Toast；自动回灌/跨工作区开关。

### 07 质量门控 `#quality` — 五信号评分

- **布局**：**5 卡 KPI**（平均 88.6 / 通过率 91.0% / 回环中 1 / 未达标 1 / **批次通过率 92.0%**）→ 三列（五信号雷达 + 信号条 / 评分分布 / 门控规则）→ 底部（低分 Top 10 明细表 + 低分回环记录 + 门控审计）。
- **雷达**：AST 92 / 构建 88 / 类型 86 / 浏览器 90 / 行为 84，综合 88；琥珀虚线为门控阈值 85 参考环。
- **明细表**：文件 / **批次** / 轮次 / AST / 构建 / 类型 / 浏览器 / 行为 / 综合 / 状态 / 操作；按批次分组（同批相邻，`group-start` 分隔线），批次 chip 状态色 run/gated/done/split；TreeSelect.vue 64 分（#18）回环中；OrderDetail.vue 80 分（#16）警告通过；RichEditor.vue 67 分（#15）人工门。
- **交互**：顶部/行内「重新审查」→ 按钮 loading（2.6s）→ TreeSelect 64→69、轮次 2→3、审计日志插入一条、雷达回弹、Toast 提示仍 < 70，进入第 3 轮回环（超过 3 轮升级人工门）。

### 08 设置 `#settings` — 系统配置

- **布局**：左主栏两列栅格 —— 内核选择（整行 2 卡）/ 运行时与并发 + **批量执行**（左右并排）/ 质量门控（整行）；右栏（模型路由 3 通道 / 配额与用量 / 生效配置 JSON / 危险区）。
- **控件**：内核单选卡（自研 SQLite Kernel v0.8.4 已连接 vs LoopX v2.0.0a1 可选/未启用）、并发 stepper 3、超时 180s、断点 30s、自动恢复/上下文压缩开关、阈值滑杆 85、五信号权重 20/25/15/25/15、回环上限 3、失败升级人工门、危险操作二次确认。
- **交互**：内核切换 Toast 说明切换影响；保存按钮 loading 600ms；读取 token 配额 816K/1.2M（68%）。

---

## 5. 关键交互流程

1. **导航与深链**：点击侧栏 → `history.replaceState` 更新 `#hash`；刷新后按 hash 恢复页面；顶栏面包屑与 `document.title` 同步。8 个 hash 与截图一一对应。
2. **专家详情抽屉**：卡片/列表行点击（或命令面板选择专家）→ 抽屉从右滑入（260ms）+ 遮罩；`Esc` / 点遮罩 / 关闭按钮退出；打开时焦点移至关闭按钮。
3. **DAG 编辑**：点节点（button，可键盘 Tab 聚焦）→ `.sel` 选中态 + 属性面板更新；属性「节点名称」输入实时同步节点标题；Tab 切换输入/输出/运行记录；保存节点 Toast。
4. **监控实时流**：进入页面启动 1s 计时器（阶段进度、运行时长、Agent 计时、倒计时）与 2.6s 日志插入；暂停按钮冻结流；「立即恢复」1.4s 后异常行转绿并减导航徽标；「断点续跑」Toast + loading。
5. **质量回环演示**：重新审查 → loading → 分数/轮次/状态/KPI/审计日志联动 → 仍不达标进入第 3 轮 → 达到上限时提示升级人工门。
6. **批次队列**：点击批次行展开/收起批内文件（done/failed/pending），展开行的 chevron 旋转；wave 分组与批次状态色保持；批次行点击不触发全局导航。
7. **批次进度联动**：工作台批次条（18/43、126/287）与监控批次队列、质量页批次列使用同一口径。
6. **命令面板**：`Ctrl/Cmd + K` 或点击搜索框打开；输入实时过滤（页面 / 专家 / 动作）；`↑↓` 选择、`↵` 执行、`Esc` 关闭；背景遮罩点击关闭。
7. **筛选与空态**：专家、技能、记忆三处搜索 + 分类筛选，计数实时更新，无结果显示空态并提供「清除筛选」。

---

## 6. 响应式规则

| 断点 | 变化 |
|---|---|
| ≥ 1760px | 内容最大宽 1680 居中；padding 30；gap 14；专家 3 列 |
| 1440–1759 | 基准布局（侧栏 236 / padding 22 / gap 12） |
| 1280–1439 | 侧栏 214；padding 18；专家与记忆改 2 列；质量页门控面板换行 + 审计面板隐藏；运行/质量栅格比例收紧 |
| 1024–1279 | 侧栏 196；padding 14；gap 10；搜索框 190；KPI 数字 23px；画布/属性面板允许横向滚动；表格允许横向滚动 |
| < 1024 | 原型未覆盖移动端（产品定位桌面控制台）；侧栏可折叠为图标栏为后续迭代项 |

- **DAG 画布**：固定 `980×554` 坐标系（避免节点与连线错位），窄屏在 `.canvas` 内滚动，缩放控件常驻右下；节点库/缩放控件相对画布容器绝对定位，不随滚动。
- **表格**：`.table-wrap` 横向滚动 + 表头 sticky；关键列固定宽度，文本列可压缩。
- **高度**：除画布/日志/终端外不使用固定高度；页面在 1600×1000 下主内容区基本一屏可见，允许少量纵向滚动。
- 1920 下侧栏与顶栏不拉伸，内容区居中，保持单屏信息密度不被拉散。

---

## 7. 可访问性（A11y）

| 项目 | 做法 |
|---|---|
| 对比度 | 一级 `#E6EDF3 / #0F1419` ≈ 14.2:1；二级 `#A9B5C1` ≈ 8.1:1；三级 `#8B97A4` ≈ 5.4:1（表头、标签均 ≥ 4.5:1）；四级 `#5D6976` 仅用于装饰性时间戳，不承载关键信息 |
| 状态非颜色唯一 | 状态 = 文案 + 色点/图标 + 背景色；失败/回环同时有 icon 与文字；图表数值均以文本复述（雷达旁有信号条 + 数字） |
| 键盘 | 导航/按钮/卡片/节点/开关/Tab 均可 Tab 聚焦；卡片与节点支持 Enter/Space 打开；`Esc` 关闭抽屉/命令面板；`Ctrl/Cmd+K` 打开命令面板；开关支持 Enter 切换 |
| 焦点 | 全局 `:focus-visible` 2px 青色描边 + 2px 偏移；遮罩打开时焦点进入弹层 |
| 语义 | `nav[aria-label]`、`section[aria-label]`、`role="switch"` + `aria-checked`、`role="dialog"/aria-modal`（命令面板）、按钮均含可见文字或 `aria-label`（纯图标按钮） |
| 动效 | `@media (prefers-reduced-motion: reduce)` 将动画/过渡降到 0.001ms；无闪烁 > 3Hz |
| 缩放 | 1280 断点即为 1600 的 200% 等效布局；容器使用相对单位与 flex/grid，无固定像素文本截断 |
| 字号 | 正文 12–13px（桌面控制台密度），微标签 9.5–10px 仅用于分类/装饰；关键数值 ≥ 15px 等宽 |

---

## 8. 与 Hermes 插件的集成方式（生产落地）

> **设计稿的独立壳仅用于评审。** 生产落地 = Hermes **React Plugin SDK + dashboard tab**：插件不自建全局壳、不自带 React、不复刻宿主导航；侧栏/顶栏、登录态、主题、通知中心全部来自宿主。设计稿中的 8 屏对应 `/flow` tab 内的 8 个子页。

### 8.1 生产形态

| 层 | 载体 | 说明 |
|---|---|---|
| 注册 | `dashboard/manifest.json` | 声明 `tab: /flow`、8 个子页路由、图标与权限；由 Hermes Dashboard 加载 |
| 前端 | 预构建 `dist/index.js`（IIFE） | 运行时读取 `window.__HERMES_PLUGIN_SDK__`；**React 由宿主提供**，bundle 不打包 React/ReactDOM；CSS 变量继承宿主 theme |
| 后端 | `plugin_api.py`（FastAPI router） | 挂载 `/api/plugins/hermes_flow/`，提供 runs / agents / skills / workflows / memory / quality / settings 资源与动作 |
| 实时 | 宿主 WebSocket 通道 | stage / agent / log / evidence / score 增量推送；断线重连与 seq 校验 |
| 静态 | `dist/index.js` + `dist/index.css` | 无外部 CDN、无网络字体，SVG 图标内联 |

### 8.2 路由映射

| 设计稿 hash | Dashboard 子页 | 说明 |
|---|---|---|
| `#workbench` | `/flow/workbench` | 目标总览 / 当前运行 |
| `#monitor` | `/flow/monitor` | 运行看板 / 日志 / 异常自愈 |
| `#agents` | `/flow/agents` | 专家注册表 |
| `#skills` | `/flow/skills` | 技能库 |
| `#flow` | `/flow/orchestration` | DAG 编排（tab 内全宽画布） |
| `#memory` | `/flow/memory` | 记忆中心 |
| `#quality` | `/flow/quality` | 质量门控 |
| `#settings` | `/flow/settings` | 插件级设置（内核/并发/权重/模型） |

- 路由由 SDK 的 `navigate(path)` 处理，深链形如 `dashboard/flow/quality`；插件不修改宿主 URL 结构。
- tab 内只保留页面级面包屑与操作区，全局导航由宿主提供。

### 8.3 主题 / 密度 / 响应式

- 宿主通过 SDK 注入 token；插件以本规范 §3 为兜底：`--bg #07090B`、`--panel #0F1419`、`--acc #35CFC1`、`--ok #56C98A`、`--warn #E0A93E`、`--err #E9695F`、`--ink #E6EDF3`；禁止硬编码第二套主题。
- 密度 `comfortable / compact` 由宿主下发；间距使用 token，断点 1280 / 1440 / 1600 / 1920 复用 §6。
- 顶栏/侧栏随宿主折叠；插件内容区自适应，画布/表格按 §6 滚动。

### 8.4 SDK 契约（建议）

```js
window.__HERMES_PLUGIN_SDK__ = {
  react, ReactDOM,                 // 宿主提供，插件 bundle 需 external
  mount(el, { tab, subRoute }),    // 插件注册挂载函数
  navigate(subRoute),              // /flow/workbench → /flow/quality
  api: { get, post, patch },       // 代理到 /api/plugins/hermes_flow/
  ws: { subscribe(topic, cb), unsubscribe(topic, cb) },
  theme: { tokens, density, onChange(cb) },
  toast, confirm, i18n, currentUser
};
```

### 8.5 接口草案

```
GET  /api/plugins/hermes_flow/runs/current
GET  /api/plugins/hermes_flow/runs/{id}/timeline
GET  /api/plugins/hermes_flow/runs/{id}/evidence
GET  /api/plugins/hermes_flow/runs/{id}/batches
GET  /api/plugins/hermes_flow/batches/{id}/items
POST /api/plugins/hermes_flow/batches/{id}/retry
POST /api/plugins/hermes_flow/batches/{id}/split
POST /api/plugins/hermes_flow/batches/{id}/ingest
POST /api/plugins/hermes_flow/batches/{id}/apply
GET  /api/plugins/hermes_flow/agents
POST /api/plugins/hermes_flow/agents
GET  /api/plugins/hermes_flow/skills
GET  /api/plugins/hermes_flow/workflows/{id}
PUT  /api/plugins/hermes_flow/workflows/{id}        # DAG 保存
GET  /api/plugins/hermes_flow/memory
POST /api/plugins/hermes_flow/memory/feedback        # 回灌 / 命中
GET  /api/plugins/hermes_flow/quality/report
POST /api/plugins/hermes_flow/quality/review         # 重新审查
GET  /api/plugins/hermes_flow/settings
PUT  /api/plugins/hermes_flow/settings
WS   /api/plugins/hermes_flow/stream?run_id=...
```

### 8.6 组件与实现映射（React）

- 组件：`PluginRoot / PageRouter / KpiCard / StatusChip / DataTable / Panel / StageRail / AgentCard / ExpertDrawer / DAGCanvas / NodeInspector / LogStream / Timeline / EvidenceTabs / ExceptionList / MemoryCard / SignalRadar / GatePanel / CommandPalette / ToastHost`。
- 图表：雷达 / 分布 / 迷你趋势均 SVG 自绘（本稿无图表库依赖）；DAG 可用 React Flow / AntV X6；diff 用 Monaco diff 或自绘行内 diff。
- 状态：React Query / Zustand + WebSocket 增量；日志与长列表用虚拟滚动，避免整页重渲染。
- 截图回归：`screenshot.ps1` 可在独立壳按 hash 出图；插件内使用相同子页路由。

---

## 9. 文件结构与交付

```
E:\deepSeek\ui-design\
├─ index.html            单文件可交互原型（8 屏 / 无外部依赖 / 单文件离线可开）
├─ design-spec.md        本规范
├─ PROMPTS.md            逐屏还原提示词（v0 / Cursor 复刻用）
├─ screenshot.ps1        正常机器的批量截图脚本（Edge/Chrome headless）
├─ screenshots\
│  ├─ 00-overview.png    8 屏缩略总览
│  ├─ 01-workbench.png   #workbench
│  ├─ 02-monitor.png     #monitor
│  ├─ 03-agents.png      #agents
│  ├─ 04-skills.png      #skills
│  ├─ 05-flow.png        #flow
│  ├─ 06-memory.png      #memory
│  ├─ 07-quality.png     #quality
│  └─ 08-settings.png    #settings
└─ _src\                 可维护源码（CSS 4 段 / HTML 5 段 / JS / 构建与校验脚本）
```

**截图说明**：本会话的 Windows 沙箱为低完整性 + 写受限令牌，Chromium 在创建/连接 mojo 命名管道时被系统拒绝（`CreateFileW` on own pipe → 0x5），Edge/Chrome/Firefox/Playwright 在沙箱内均无法启动；`screenshots/` 由具备完整权限的渲染通道按 `screenshot.ps1` 同等参数生成（Chrome headless，1600×1000，virtual-time-budget 3500ms）。在普通桌面环境直接运行 `screenshot.ps1` 即可复现。

---

## 10. 验收清单

- [x] 8 屏可切换（hash 深链）、侧栏分组与面包屑同步
- [x] 深色工程控制台风，设计 tokens 全量收敛于 `:root`
- [x] 表格/卡片/图表/进度/状态徽标/日志/时间轴/DAG 全为真实密度布局
- [x] 空态（专家/技能/记忆）、骨架屏（技能重新加载）、错误态（监控构建日志）、加载态（审查/保存/恢复按钮）均覆盖
- [x] 专家详情抽屉、DAG 节点选中、监控假数据推进、质量重新审查回环、异常恢复、命令面板（Ctrl+K）全部可交互
- [x] 图标 100% 内联 SVG，无 CDN / 网络字体 / 外部请求
- [x] 1280 / 1440 / 1600 / 1920 断点规则与滚动策略
- [x] 对比度、焦点、键盘、`prefers-reduced-motion`、状态非颜色唯一编码
- [x] 业务数据自洽：`src/views/UserList.vue` ast 92 / build 88 / types 86 / browser 90 / behavior 84 → 综合 88；TreeSelect.vue build 0 → 64 分回环；287 文件 / 已转化 126 / 批次 18/43；门控阈值 85；五信号权重 20/25/15/25/15；70–84 警告通过；默认内核 SQLite
- [x] 批次循环（FR-10）：工作台批次进度、监控批次队列/事件/证据 tab、专家循环徽标与配置抽屉、DAG 批次节点/属性/预览、质量批次通过率与批次列、设置批量执行面板，全部可交互且口径一致（7 文件/批、并发 1、拆分 2 层、28k 预算）
