"""质量门控：多信号评分模型 + 门判定 + 回环计数。"""
from .scoring import (
    QualityScore,
    SignalResult,
    SIGNALS,
    compute_score,
    signal_names,
)
from .gate import (
    GateDecision,
    GateTracker,
    QualityGate,
    Verdict,
    gated_runner,
)

__all__ = [
    "QualityScore", "SignalResult", "SIGNALS", "compute_score", "signal_names",
    "GateDecision", "GateTracker", "QualityGate", "Verdict", "gated_runner",
]
