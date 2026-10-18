# HERMES Flow 剩余任务分析（v0.2.0 之后）

- 对照基线：[PRD v2.2](PRD.md) FR-1..FR-10、§16 验收标准、B1–B17
- 当前实现：[plugin/hermes_flow](../plugin/hermes_flow/README.md) + [实现报告](IMPLEMENTATION_REPORT.md)
- 结论：**全部计划项（R2–R10 + R9 LoopX + DAG 拖拽 + 异步质量）已完成；唯一未执行的是 1000 文件真实 LLM 预算跑批与新版本发布**。

---

## 1. 总览（按 PRD 功能）

| FR | 功能 | 状态 | 已做 | 还差 |
|---|---|---|---|---|
| FR-1 | 专家注册/技能绑定 | ✅ 大部分 | 8 专家、技能绑定、CRUD、校验、Dashboard 专家卡 + **运行态（活跃批次/进度）** | 提示词热更新 |
| FR-2 | 技能注册与展示 | ✅ 大部分 | 12 SKILL.md、自动加载、按 phase/tag 校验、专家卡技能 chips、**独立技能页 + 正文查看** | 技能执行自动注入 |
| FR-3 | 工作流编排 | 🟡 大部分 | DAG DSL、2 模板、校验、创建 Run、只读 DAG、**JSON 编辑 + 节点重跑** | 可视化 DAG 拖拽编辑 |
| FR-4 | 运行监控 | ✅ 大部分 | Run/批次/文件明细、节点步进、专家运行态、driver/audit 侧栏、**事件流 + cursor 断线重放** | Run 证据面板细化 |
| FR-5 | 记忆系统 | ✅ | SQLite 经验库、add/search、记忆页、**每 turn 自动召回注入 + 批次失败自动沉淀** | 向量检索/深度 LLM 归纳（可选） |
| FR-6 | 异常/自治 | 🟡 部分 | 分类、退避、checkpoint、租约、429 requeue、自动 driver | wave 级暂停/恢复、后台常驻 driver、kill/restart 演练 |
| FR-7 | 质量门控 | ✅ | 五信号评分、批级硬门、聚合门、85/70 阈值；**真实 build/typecheck/Chrome 路由验证已实现**，R2 产物聚合门 pass 97.22 | 自动挂到 driver 时点（工程化） |
| FR-8 | LoopX | 🔴 未接 | 前序 adapter + LoopXBridge 代码 | CLI/后端开关、doctor/降级（P2） |
| FR-9 | 设置与运维 | 🟡 大部分 | 安装、数据目录、CLI、doctor、**设置页（阈值/driver 限制/API 索引）** | 备份/清理/诊断一键化 |
| FR-10 | 批量循环 | ✅ | 规划/队列/认领/租约/ingest/apply/split/repair/幂等；自动 driver；**同 wave 并行 + worktree 隔离** | 1000 文件真实 LLM 成本验证 |

---

## 2. B1–B17 验收清单

| # | 验收项 | 状态 | 说明 |
|---|---|---|---|
| B1 | 1000 文件计划无跨依赖倒置 | ✅ | 1000 文件 → 150 批/50 wave，覆盖 1000/1000；依赖链无倒置 |
| B2 | 287 文件全批完成、覆盖率 100%、聚合门通过 | 🟡 | 真实 20 文件 8/8 批、20/20 applied；287 真实迁移未跑 |
| B3 | 部分失败只 repair 失败文件 | ✅ | 单测覆盖 |
| B4 | 截断自动拆批 | ✅ | driver + 单测覆盖 `truncated→split→done` |
| B5 | 429 波次暂停/恢复无重复写 | 🟡 | driver 429 requeue 不消耗 attempt；wave 级暂停/恢复未做 |
| B6 | 杀进程重启只重跑未完成文件 | 🟡 | 状态持久化 + `applied_hash`；未做真实 kill/restart |
| B7 | 低分 repair 后提升，3 轮人工门 | 🟡 | repair 有上限；评分提升依赖外部评分；人工门未自动升级 |
| B8 | 同层并行仅同 wave（独立 worktree） | 🔴 | 当前串行 |
| B9 | 子代理 context ≤32k、结果 ≤24k | 🟡 | Packet 声明预算；无强制裁剪 |
| B10 | 批次 UI 与内核一致、断线补齐事件 | 🟡 | 2s 轮询，无事件回放 |
| B11 | 越界写拒绝并回滚 | ✅ | R4：基线 + 每批审计 + 自动恢复/删除 + `FLOW_BATCH_WRITE_SCOPE` + Run gated；单测/集成测试通过 |
| B12 | 写后崩溃不重复转换/应用 | ✅ | `applied_hash` + 幂等 apply 已测 |
| B13 | lifecycle 结果校验 + 一次纠正重派 | ✅ | driver 已实现并单测 |
| B14 | driver 单例 | ✅ | 文件锁 + 单测 + live driver |
| B15 | persistent_child | 🔴 | P2 |
| B16 | 部分迁移批级门 / 全量聚合门 | 🟡 | 函数分层；UI/流程未串 |
| B17 | 100 批 + 10 次故障 ≥95% | ✅（调度层） | 100/100 done、0 failed、110 launch（10 次重试），3.95s；fake lifecycle，不含真实 LLM |

---

## 3. 剩余工作包

### P0 — 安全底线（已完成）

R4 已完成：基线快照 + 每批 apply 后审计 + 越界回滚 + `FLOW_BATCH_WRITE_SCOPE` + Run gated。

### P1 — 剩余（约 3–4 人日）

| 编号 | 任务 | 内容 | 估时 |
|---|---|---|---|
| R5 ✅ | Dashboard 补齐 | 7 Tab：专家/技能/工作流/运行/质量/记忆/设置；专家运行态、DAG 只读、质量采集、记忆页；报告 `docs/R5_REPORT.md` | **主体已完成** |
| R5b ✅ | Dashboard 收尾 | 事件流/断线重放、人工门批准/驳回、节点级重跑、工作流 JSON 编辑；报告 `docs/R5B_REPORT.md` | **已完成** |
| R6 ✅ | 记忆闭环 | 每 turn 按用户消息召回注入；批次失败自动沉淀；事件 `memory_distilled` | **已完成** |
| R7 ✅ | 同 wave 并行 | 2–3 批并行 + 独立 worktree + apply/audit 按 seq 稳定提交；报告 `docs/R7_REPORT.md` | **已完成** |
| R8 ✅ | 压测/故障注入 | 1000 文件规划、100 批/10 故障、时间预算；报告 `docs/R8_REPORT.md` | **调度上界达标** |
| R8b ✅ | 真实并行 + kill/restart | 6 文件 3 批真实并行 79s 全 pass；kill 后 attempt=2 恢复 2/2 批/8 文件；报告 `docs/R8B_REPORT.md` | **已完成** |
| R8c | 1000 文件真实 LLM | 按采样粗估 3.5–4h wall；token 成本需 provider 账单 | 预算项 |
| R9 ✅ | LoopX 后端 | `backend=sqlite/loopx`、JSONL `LoopXKernel`、CLI `--backend`/doctor/backend --set、降级 sqlite；报告 `docs/R9_UX_REPORT.md` | **已完成** |
| UX ✅ | DAG 拖拽 + 异步质量 | 画布拖拽/增删节点/meta 保存；`QualityJobManager` + `/quality/jobs` + UI 轮询；报告 `docs/R9_UX_REPORT.md` | **已完成** |

### P2 — 可选/工程化（约 4–6 人日）

| 编号 | 任务 | 内容 | 估时 |
|---|---|---|---|
| R10 ✅ | 测试/发布 | 测试可移植、GitHub Actions、`ci_local.ps1`、`package.py`（0.2.0 zip+sha256）、质量自动挂 driver（可选） | **已完成** |
| R11 | 发布 0.3.0 | R9/DAG/异步质量超出 v0.2.0 Release 内容 | 0.5d |

---

## 4. 依赖与建议

**依赖**：无阻塞；R2–R10 + R9/UX 已完成。

**最近 1–2 周建议只做两件事**：
1. **1000 文件真实 LLM 迁移**（预算执行，约 3.5–4h wall）。
2. **发布 v0.3.0**（包含 R9/DAG/异步质量），再按需联调真实 `loopx` CLI。

已可对外说："真实 20 文件迁移 + 自动批次驱动 + 真实构建/浏览器门控 + 100 批调度压测 + 同 wave 并行 + kill/restart + Dashboard/记忆/LoopX/DAG 编辑/异步质量"闭环。

---

## 5. 风险/待决策

| 风险 | 影响 | 建议 |
|---|---|---|
| 子代理生命周期限制（并发/超时/结果 32k） | 并行 worker 需复制 parent contextvar（已修复） | driver 上限 3，留余量 |
| 真实质量采集依赖目标项目 Node/Chrome | R3 可能受环境阻塞 | 采集器可插拔，失败降级 warn + 人工门 |
| LLM 成本/时长 | 287/1000 文件昂贵 | 先 20 文件；预算 + 断点续跑 |
| Windows 子代理需 Git Bash | 换机易踩坑 | 已写 `HERMES_GIT_BASH_PATH`；安装脚本提示 |
| LoopX 价值不确定 | 投入产出不明 | 保持 P2 |

---

## 6. 已完成、不需再做

- 可行性分析、PRD v2.2、8 屏高保真 UI 设计稿、LoopX 调研、批量调研、QA 两轮
- 插件骨架/注册（34 tools + `/flow` + CLI + hook）、专家/技能/工作流注册中心
- 批次规划/队列/认领/租约/ingest/apply/split/repair/幂等
- **自动 driver `flow_batch_auto`（含 429/截断/格式纠正/单例锁）**
- **R2 真实 20 文件迁移：8/8 批、20/20 applied、全部 pass（97.0–97.6）**
- **R3 真实 build/typecheck/Chrome 路由验证：4/4 路由通过、聚合门 pass 97.22**
- **R4 写入边界审计：基线 + 每批越界检测/回滚 + `FLOW_BATCH_WRITE_SCOPE` + Run gated**
- **R5 Dashboard v2：7 Tab（专家/技能/工作流/运行/质量/记忆/设置）真实数据，7/7 渲染 0 console error**
- **R5b：事件流 cursor 重放、人工门批准/驳回、节点重跑、工作流 JSON 编辑**
- **R6：pre_llm_call 自动召回注入 + 批次失败自动沉淀（memory_distilled）**
- **R8：1000 文件→150 批/50 wave；100 批+10 故障 100/100 done、0 failed、3.95s**
- **R7：同 wave 并行 ≤3、worktree 隔离、稳定提交；0.552s→0.235s；真实 6 文件 3 批 79s**
- **R8b：真实 6 文件并行 3/3；kill/restart attempt=2 恢复 2/2 批、8/8 文件**
- **R10：测试可移植、GitHub Actions、本地 CI、0.2.0 zip+sha256、质量自动挂 driver**
- **R9：LoopX JSONL 后端 + CLI doctor/backend 切换/降级；DAG 拖拽编辑；异步质量 job**
- 五信号评分与分层门函数、异常分类/退避/checkpoint
- 经验库、HTML 看板、Dashboard v2 7 Tab、安装与启用、`hermes plugins doctor` 通过
- 84 个新单测 + 123 个前序回归 + mock E2E + 2 文件真实子代理 E2E
