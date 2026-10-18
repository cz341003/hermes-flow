"""DAG：显式工作流定义 + 拓扑排序 + 环检测。

工作流是一个有向无环图（DAG）：
- Node = 一个迁移步骤（绑定角色 + 技能 + 阶段），可显式声明 parallel 以允许并发。
- Edge = 依赖关系（source 完成后 target 才能执行）。
- 串行硬约束的依据：执行顺序由拓扑排序强制，而非 Prompt 软约束。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Node:
    id: str
    name: str
    phase: str                       # analyze|deps|transform|quality|verify|fix
    agent: str = ""                  # 执行角色（代码转化专家等）
    skill: Optional[str] = None      # 绑定技能
    parallel: bool = False           # 显式声明才允许并发
    meta: dict = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str


@dataclass
class Workflow:
    id: str
    name: str
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"节点不存在: {node_id}")

    def successors(self, node_id: str) -> List[str]:
        return [e.target for e in self.edges if e.source == node_id]

    def predecessors(self, node_id: str) -> List[str]:
        return [e.source for e in self.edges if e.target == node_id]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "nodes": [{"id": n.id, "name": n.name, "phase": n.phase,
                       "agent": n.agent, "skill": n.skill,
                       "parallel": n.parallel, "meta": n.meta} for n in self.nodes],
            "edges": [{"source": e.source, "target": e.target} for e in self.edges],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Workflow":
        nodes = [Node(id=n["id"], name=n["name"], phase=n["phase"],
                      agent=n.get("agent", ""), skill=n.get("skill"),
                      parallel=n.get("parallel", False),
                      meta=n.get("meta", {})) for n in d.get("nodes", [])]
        edges = [Edge(source=e["source"], target=e["target"])
                 for e in d.get("edges", [])]
        return cls(id=d["id"], name=d["name"], nodes=nodes, edges=edges)


class CyclicGraphError(ValueError):
    """图存在环或边引用了不存在的节点。"""


def topological_sort(workflow: Workflow) -> List[str]:
    """Kahn 算法，返回节点 id 的拓扑序。

    - 有环 → 抛 CyclicGraphError
    - 边引用不存在的节点 → 抛 CyclicGraphError
    """
    node_ids = [n.id for n in workflow.nodes]
    if len(set(node_ids)) != len(node_ids):
        raise CyclicGraphError("存在重复的节点 id")

    in_degree: Dict[str, int] = {n.id: 0 for n in workflow.nodes}
    adj: Dict[str, List[str]] = {n.id: [] for n in workflow.nodes}
    for e in workflow.edges:
        if e.source not in in_degree or e.target not in in_degree:
            raise CyclicGraphError(
                f"边引用了不存在的节点: {e.source} -> {e.target}")
        adj[e.source].append(e.target)
        in_degree[e.target] += 1

    queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
    order: List[str] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for t in adj[nid]:
            in_degree[t] -= 1
            if in_degree[t] == 0:
                queue.append(t)

    if len(order) != len(node_ids):
        raise CyclicGraphError("图中存在环，无法拓扑排序")
    return order
