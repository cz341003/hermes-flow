# R4 工作区写入边界审计报告（B11）

- 日期：2026-10-18
- 实现：[flow_core/batch/audit.py](../plugin/hermes_flow/flow_core/batch/audit.py)
- 集成：`flow_batch_auto(audit=true)`（默认开启）
- 测试：`tests/test_audit.py`（4 项）+ `tests/test_driver.py` drift 用例（1 项）+ 全量 66/66

## 1. 机制

1. **基线**：driver 首次进入某批次组时，对项目做一次快照：
   - 记录每个文件 `sha256/size`；
   - 复制完整源文件到 `plugin-data/hermes_flow/audit/<group_id>/<project>/files/`；
   - 排除 `node_modules/.git/dist/build/coverage/.quality-*/.vite/.cache` 等。
2. **允许写集合**：该 group 计划内所有批次的文件路径（含 repair 子批、新生成文件）。
3. **每批 apply 后审计**：
   - `post - pre - allowed` 非空 → 越界写（created / modified / deleted）；
   - 越界文件从基线备份恢复，基线不存在的新文件删除；
   - 证据写入 `audit/<group>/violation-*.json`；
   - 批次标记 `FLOW_BATCH_WRITE_SCOPE` 失败，Run 状态置 `gated`，driver 停止继续推进。
4. **重试**：越界批次按 `max_attempts` 回 ready；再次运行 driver 会重试；超过次数转 failed，等待人工门。

## 2. 单测/集成验证

| 用例 | 结果 |
|---|---|
| 允许路径内修改 → `ok=true` | ✅ |
| 批外文件被修改 → 检测 + 恢复原内容 | ✅ |
| 批外新建文件 → 检测 + 删除 | ✅ |
| 批外文件被删除 → 检测 + 从备份恢复 | ✅ |
| driver + 子代理写 `outside.txt` → `action=drift`、`write_scope_violation=true`、文件被删除、批次 verdict 含 `FLOW_BATCH_WRITE_SCOPE` | ✅ |

全量：**66/66 新单测**、123/123 legacy、`hermes plugins doctor` 34 tools。

## 3. 限制与后续

- 当前越界处理是**自动回滚 + gated + fail**；还没有 Dashboard 人工门按钮/审批流（R5）。
- 基线复制整棵源码树，超大项目（>10k 文件）需改为 git diff 或按批增量快照；当前 20 文件项目成本可忽略。
- 仅对 `flow_batch_auto` 的 apply 生效；手动 `flow_batch_ingest(apply=true)` 尚未强制审计（可复用同一 `WorkspaceAudit`）。
- 当前只做内容/存在性审计，不做符号链接/权限位审计。
