"""批次规划：拓扑分层 + 上下文预算装箱（PRD §8.4 / FR-10）。"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, Iterable, List, Optional

from .models import BatchPlan, BatchPolicy, FileItem, PlannedBatch

PROMPT_OVERHEAD = 2000


def estimate_chars(item: FileItem) -> int:
    """估算单个文件在 prompt 中的字符数（含说明开销）。"""
    size = item.size if item.size > 0 else 4096
    return int(size * 1.2) + PROMPT_OVERHEAD


def topo_sort_files(items: Iterable[FileItem]) -> List[FileItem]:
    """Kahn 拓扑排序；deps 中不存在的路径忽略；有环则抛 ValueError。"""
    items = list(items)
    by_path = {it.path: it for it in items}
    indegree: Dict[str, int] = {it.path: 0 for it in items}
    adj: Dict[str, List[str]] = defaultdict(list)
    for it in items:
        for dep in it.deps:
            if dep in by_path and dep != it.path:
                adj[dep].append(it.path)
                indegree[it.path] += 1
    queue = deque([it.path for it in items if indegree[it.path] == 0])
    ordered: List[FileItem] = []
    while queue:
        path = queue.popleft()
        ordered.append(by_path[path])
        for nxt in adj.get(path, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(ordered) != len(items):
        raise ValueError("文件依赖图存在环，无法分批")
    return ordered


def compute_levels(items: List[FileItem]) -> Dict[str, int]:
    """依赖层级：无依赖=0；否则 1+max(dep level)。"""
    by_path = {it.path: it for it in items}
    memo: Dict[str, int] = {}

    def visit(path: str, stack: set) -> int:
        if path in memo:
            return memo[path]
        if path in stack:
            raise ValueError(f"文件依赖图存在环: {path}")
        stack.add(path)
        deps = [d for d in by_path[path].deps if d in by_path]
        level = 0 if not deps else 1 + max(visit(d, stack) for d in deps)
        stack.discard(path)
        memo[path] = level
        return level

    for it in items:
        visit(it.path, set())
    return memo


def plan_batches(items: Iterable[FileItem], policy: BatchPolicy) -> BatchPlan:
    """按 wave 分组，并在每个 wave 内按拓扑序做预算装箱。"""
    items = list(items)
    if not items:
        return BatchPlan(batches=[], total_files=0)
    ordered = topo_sort_files(items)
    levels = compute_levels(items)
    waves: Dict[int, List[FileItem]] = defaultdict(list)
    for it in ordered:
        waves[levels[it.path]].append(it)

    planned: List[PlannedBatch] = []
    seq = 0
    for wave in sorted(waves):
        pending = waves[wave][:]
        while pending:
            batch: List[FileItem] = []
            budget = policy.context_budget_chars
            while pending and len(batch) < min(policy.max_files_per_batch, policy.max_batch_size_cap):
                nxt = pending[0]
                cost = estimate_chars(nxt)
                if batch and cost > budget:
                    break
                # 高风险文件单独成批（人工复核）
                if nxt.risk == "high" and batch:
                    break
                batch.append(nxt)
                pending.pop(0)
                budget -= cost
                if nxt.risk == "high":
                    break
            if not batch:  # 单个超大文件也必须成批
                batch = [pending.pop(0)]
            seq += 1
            planned.append(PlannedBatch(
                id=f"b-{seq:04d}", wave=wave, seq=seq, files=batch,
                priority="high" if any(f.risk == "high" for f in batch) else "normal",
            ))
    return BatchPlan(batches=planned, total_files=len(items))
