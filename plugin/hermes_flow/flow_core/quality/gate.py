"""质量门：按得分判定通过/警告/回环，并对回环次数做硬上限（超限升级人工门）。

门控规则（对齐 PRD §8.2）：
- score >= pass_threshold（默认 85）→ PASS
- warn_threshold <= score < pass_threshold（默认 70~85）→ WARN（通过但有警告）
- score < warn_threshold → REWORK（回环修复）
- REWORK 累计达到 max_loops（默认 3）仍未通过 → MANUAL（升级人工 Gate）
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class Verdict(str, Enum):
    PASS = "pass"        # 通过
    WARN = "warn"        # 通过但有警告
    REWORK = "rework"    # 不通过，回环修复
    MANUAL = "manual"    # 回环超限，升级人工门


_VERDICT_LABEL = {
    Verdict.PASS: "通过",
    Verdict.WARN: "通过（有警告）",
    Verdict.REWORK: "不通过，回环修复",
    Verdict.MANUAL: "回环超限，升级人工门",
}


@dataclass
class GateDecision:
    verdict: Verdict
    score: float
    loop_count: int
    max_loops: int
    message: str
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "verdict_label": _VERDICT_LABEL[self.verdict],
            "score": round(self.score, 2),
            "loop_count": self.loop_count,
            "max_loops": self.max_loops,
            "message": self.message,
            "warnings": self.warnings,
        }


class QualityGate:
    """无状态的阈值判定器。"""

    def __init__(self, pass_threshold: float = 85.0,
                 warn_threshold: float = 70.0, max_loops: int = 3):
        if not (0 <= warn_threshold <= pass_threshold <= 100):
            raise ValueError("阈值非法：需 0 <= warn <= pass <= 100")
        if max_loops < 1:
            raise ValueError("max_loops 需 >= 1")
        self.pass_threshold = pass_threshold
        self.warn_threshold = warn_threshold
        self.max_loops = max_loops

    def evaluate(self, score: float, loop_count: int = 0) -> GateDecision:
        score = float(score)
        warnings: List[str] = []
        if score >= self.pass_threshold:
            return GateDecision(Verdict.PASS, score, loop_count,
                                self.max_loops, "达到通过线", warnings)
        if score >= self.warn_threshold:
            warnings.append(
                f"得分 {score:.1f} 低于通过线 {self.pass_threshold}，"
                "已通过但需关注待优化项")
            return GateDecision(Verdict.WARN, score, loop_count,
                                self.max_loops, "通过（有警告）", warnings)
        # score < warn_threshold
        if loop_count >= self.max_loops:
            return GateDecision(
                Verdict.MANUAL, score, loop_count, self.max_loops,
                f"回环已达上限 {self.max_loops} 次，升级人工门", warnings)
        return GateDecision(
            Verdict.REWORK, score, loop_count, self.max_loops,
            f"得分 {score:.1f} 低于 {self.warn_threshold}，回环修复"
            f"（第 {loop_count + 1}/{self.max_loops} 轮）", warnings)


class GateTracker:
    """带状态的回环计数跟踪器：按 subject（节点/文件）累计 REWORK 轮数。

    用法：
        tracker = GateTracker()
        d = tracker.submit("transform:App.vue", 60)   # -> REWORK, loop_count=1
        d = tracker.submit("transform:App.vue", 62)   # -> REWORK, loop_count=2
        d = tracker.submit("transform:App.vue", 65)   # -> REWORK, loop_count=3
        d = tracker.submit("transform:App.vue", 66)   # -> MANUAL
    """

    def __init__(self, gate: Optional[QualityGate] = None):
        self.gate = gate or QualityGate()
        self._loops: Dict[str, int] = {}

    def loop_count(self, subject: str) -> int:
        return self._loops.get(subject, 0)

    def submit(self, subject: str, score: float) -> GateDecision:
        count = self._loops.get(subject, 0)
        decision = self.gate.evaluate(score, loop_count=count)
        if decision.verdict is Verdict.REWORK:
            self._loops[subject] = count + 1
        elif decision.verdict in (Verdict.PASS, Verdict.WARN, Verdict.MANUAL):
            # 通过/警告/人工门后重置（人工门保留记录供人工复查）
            if decision.verdict in (Verdict.PASS, Verdict.WARN):
                self._loops.pop(subject, None)
        return decision


def gated_runner(runner, gate: Optional[QualityGate] = None):
    """把门控接到 Scheduler 的 runner 上，实现「低分自动回环」。

    包装后的 runner 逻辑：
    - runner 返回 success=False 或 score=None → 原样透传（引擎按失败回环）。
    - runner 返回 success=True 且 score 有值 → 用 QualityGate 判定：
        * PASS / WARN → 原样返回 success=True（引擎 complete）。
        * REWORK / MANUAL → 改写为 success=False，error=门控消息，引擎按失败
          回环（max_attempts 即回环上限，超限自动 FAILED=人工门）。

    用法：``scheduler.run(gated_runner(my_runner))``
    """
    from ..engine import ExecutionResult

    gate = gate or QualityGate()

    def wrapper(node, ctx):
        result = runner(node, ctx)
        if not result.success or result.score is None:
            return result
        loop_count = ctx.get("attempt", 0)
        decision = gate.evaluate(result.score, loop_count=loop_count)
        if decision.verdict in (Verdict.PASS, Verdict.WARN):
            return result
        return ExecutionResult(
            success=False, score=result.score, artifacts=result.artifacts,
            notes=result.notes, error=decision.message)

    return wrapper
