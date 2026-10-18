# R6 记忆闭环报告

- 日期：2026-10-18
- 目标：每 turn 自动召回并注入相关经验；批次结束自动沉淀失败/恢复经验
- 代码：[hermes_flow/__init__.py](../plugin/hermes_flow/__init__.py)（pre_llm_call）、[runtime.py](../plugin/hermes_flow/runtime.py)（distill）
- 测试：[tests/test_memory_loop.py](../plugin/hermes_flow/tests/test_memory_loop.py)

## 1. 自动召回注入

`pre_llm_call` 现在会：

1. 读取活跃 Run（`running/queued/paused/gated`），注入批次进度与 `gated` 提示；
2. 以当前 `user_message` 为 query，调用 `experience.recall()` 召回最多 3 条经验；
3. 把 `category · trigger → solution` 压缩到 ≤9,000 字符注入当前 user turn。

- 没有活跃 Run/经验时返回 `None`，不产生空上下文。
- 钩子异常静默，不阻塞主流程。
- 无经验时仍可注入 Run 进度；无状态时完全无注入。

## 2. 批次自动沉淀

`auto_drive` 每轮 driver 结束后调用 `distill_batch_experiences()`：

| 事件 | category | 沉淀内容 |
|---|---|---|
| `drift` / `FLOW_BATCH_WRITE_SCOPE` | `write_scope` | 越界已回滚；只允许写 staging_path |
| `rate_limited` | `rate_limit` | 429 时 requeue 不消耗 attempt；稍后重试同 group |
| `split` / 截断 | `truncation` | 输出截断已拆批；控制批大小/结果 JSON |
| `repair` | `quality_rework` | 只修复失败文件，避免整批重写 |
| 其它 `failed` | 异常分类/`migration_failure` | 记录错误摘要与下一步建议 |

- 去重由 `ExperienceBase.record()` 按 `category + trigger` 完成。
- 每次沉淀写一条 `memory_distilled` 事件（seq 可回放）。
- 返回 `experiences_distilled` 字段；记忆失败不影响批次。

## 3. 验证

| 用例 | 结果 |
|---|---|
| pre_llm_call 注入经验 + Run 进度，≤9000 字符 | ✅ |
| 无状态时返回 None | ✅ |
| 4 类失败事件 → 4 类经验，并写 `memory_distilled` 事件 | ✅ |
| 全量新单测 | **72/72** |
| 前序 legacy | **123/123** |

## 4. 限制

- 自动沉淀是规则/异常分类级别，不是 LLM 深度归纳；`memory-distiller` 专家仍可做二次精炼。
- 召回使用词面/规则相似度，不是向量检索。
- 经验注入在每 turn 的 user message 侧，不修改 system prompt（宿主契约）。
- 记忆库清理/去重合并 UI 尚未提供（当前仅搜索/新增/自动去重）。
