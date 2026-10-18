"""vue3migrate-core：Hermes Vue2→Vue3 迁移插件的共享内核库。

- kernel/   durable 状态内核（SQLite + LoopX 五原语）
- engine/   DAG 工作流引擎（串行硬约束调度）
- quality/  质量门控（多信号评分 + 门判定 + 回环计数）
- recovery/ 异常自愈（退避 + 异常分类 + 恢复策略 + checkpoint 断点续跑）
- experience/ 经验库（踩坑沉淀 + 相似检索回灌）
- board.py  看板渲染（workflow 状态 + 经验 → HTML）
- adapters/ 内核后端适配（自研 SQLite / LoopX JSONL 可切换）
"""
__version__ = "0.6.0"

from .kernel import Kernel, InvalidTransition  # noqa: F401
from .kernel.protocol import StateKernel  # noqa: F401
from .adapters import LoopXBridge, LoopXKernel, create_kernel  # noqa: F401
from .engine import (  # noqa: F401
    Workflow, Node, Edge, Scheduler, ExecutionResult, RunReport,
    CyclicGraphError, topological_sort,
)
from .quality import (  # noqa: F401
    QualityScore, SignalResult, SIGNALS, compute_score, signal_names,
    GateDecision, GateTracker, QualityGate, Verdict, gated_runner,
)
from .recovery import (  # noqa: F401
    AutonomousReport, RecoveryEvent, autonomous_run,
    BackoffStrategy, JsonCheckpointStore, restore_scheduler, snapshot_scheduler,
    FailureCategory, classify,
    RecoveryAction, RecoveryDecision, RecoveryPolicy,
)
from .experience import ExperienceBase, tokenize  # noqa: F401
from .board import render_board  # noqa: F401
