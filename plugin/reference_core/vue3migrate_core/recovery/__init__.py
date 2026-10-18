"""异常自愈：退避、异常分类、恢复策略、checkpoint 持久化、自愈循环。"""
from .autonomous import (
    AutonomousReport,
    RecoveryEvent,
    autonomous_run,
)
from .backoff import BackoffStrategy
from .checkpointing import JsonCheckpointStore, restore_scheduler, snapshot_scheduler
from .errors import FailureCategory, classify
from .policy import RecoveryAction, RecoveryDecision, RecoveryPolicy

__all__ = [
    "AutonomousReport", "RecoveryEvent", "autonomous_run",
    "BackoffStrategy",
    "JsonCheckpointStore", "restore_scheduler", "snapshot_scheduler",
    "FailureCategory", "classify",
    "RecoveryAction", "RecoveryDecision", "RecoveryPolicy",
]
