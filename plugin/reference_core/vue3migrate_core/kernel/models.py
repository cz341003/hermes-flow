"""数据模型定义（dataclass）。与 PRD §5「核心数据模型」对齐。

本模块仅含纯数据结构与枚举常量，不依赖任何第三方库。
所有字段采用下划线命名（对应 SQLite 列名），JSON 列表字段在 store 层完成序列化。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# 枚举常量
# ---------------------------------------------------------------------------
class GoalStatus:
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_GATE = "waiting-gate"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"


class TodoStatus:
    READY = "ready"
    CLAIMED = "claimed"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class Phase:
    ANALYZE = "analyze"      # 结构分析
    DEPS = "deps"            # 依赖分析
    TRANSFORM = "transform"  # 代码转化
    QUALITY = "quality"      # 质量分析
    VERIFY = "verify"        # 浏览器验证
    FIX = "fix"              # 修复回环


class GateKind:
    HUMAN = "human"
    QUALITY = "quality"
    BUILD = "build"
    BROWSER = "browser"


class GateStatus:
    OPEN = "open"
    PASSED = "passed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class Goal:
    """一次迁移工程。"""
    id: str
    title: str
    description: str = ""
    scope: List[str] = field(default_factory=list)   # 影响范围（目录/文件）
    status: str = GoalStatus.PLANNING
    workflow_id: str = ""
    quota_total: int = 0          # 总槽位数，0 表示不限
    quota_used: int = 0           # 已消耗槽位
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class Todo:
    """最小工作切片（带依赖，天然支持依赖图串行）。"""
    id: str
    goal_id: str
    file_path: str
    phase: str = Phase.ANALYZE
    dependencies: List[str] = field(default_factory=list)  # 依赖的 Todo id
    owner_agent: Optional[str] = None
    status: str = TodoStatus.READY
    attempts: int = 0
    max_attempts: int = 3
    score: Optional[float] = None
    error: Optional[str] = None
    lease_expires_at: Optional[float] = None  # claim 租约过期时间
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class Gate:
    """质量/人工/构建/浏览器 门。"""
    id: str
    goal_id: str
    kind: str
    question: str = ""
    threshold: Optional[float] = None
    status: str = GateStatus.OPEN


@dataclass
class Evidence:
    """证据：某 todo 的执行结果与质量评分。"""
    id: str
    todo_id: str
    agent_id: Optional[str] = None
    score: Optional[float] = None
    artifacts: List[str] = field(default_factory=list)  # diff/日志/截图路径
    notes: str = ""
    timestamp: float = 0.0


@dataclass
class Checkpoint:
    """断点：序列化的状态快照，用于断点续跑。"""
    id: Optional[int] = None
    goal_id: str = ""
    todo_id: Optional[str] = None
    state: Any = field(default_factory=dict)   # 序列化状态（JSON 可表示）
    timestamp: float = 0.0


@dataclass
class Experience:
    """经验：踩坑沉淀（记忆写回）。"""
    id: str
    category: str
    trigger: str
    solution: str
    versions: Optional[str] = None
    times_hit: int = 1
    created_at: float = 0.0


@dataclass
class StateSnapshot:
    """refresh_state 返回的上下文快照（只注入必要状态，防长上下文膨胀）。"""
    goal: Optional[Goal] = None
    claimed_todos: List[Todo] = field(default_factory=list)   # 当前被认领中的
    next_todo: Optional[Todo] = None                          # 下一个可认领切片
    progress: dict = field(default_factory=dict)              # {done, total, failed, blocked, ready, claimed}
    open_gates: List[Gate] = field(default_factory=list)
    latest_checkpoint: Optional[Checkpoint] = None
    related_experiences: List[Experience] = field(default_factory=list)


@dataclass
class ShouldRunResult:
    """should_run 的判定结果。"""
    should: bool
    reason: str
