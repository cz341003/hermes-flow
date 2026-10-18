"""质量评分模型：多信号加权 0–100。

五信号（权重合计 100，对齐 PRD §8.1）：

| key      | 信号                         | 权重 |
|----------|------------------------------|------|
| ast      | AST 语法正确（parse 不报错）   | 20   |
| build    | 构建通过（vite build 成功）   | 25   |
| types    | 类型检查通过（vue-tsc）        | 15   |
| browser  | 浏览器自动化验证（渲染+交互）  | 25   |
| behavior | 行为一致性（diff 语义比对）    | 15   |

每个信号可取 [0,1] 的置信度（默认布尔 0/1），也支持部分通过（如 behavior 0.5）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# 信号 key -> (中文名, 权重)
SIGNALS: Dict[str, tuple] = {
    "ast":      ("AST 语法正确", 20),
    "build":    ("构建通过", 25),
    "types":    ("类型检查通过", 15),
    "browser":  ("浏览器自动化验证", 25),
    "behavior": ("行为一致性", 15),
}

_TOTAL_WEIGHT = sum(w for _, w in SIGNALS.values())


@dataclass
class SignalResult:
    """单个信号的评测结果。"""
    key: str
    value: float          # 0.0 ~ 1.0
    detail: str = ""

    def __post_init__(self):
        self.value = max(0.0, min(1.0, float(self.value)))


@dataclass
class QualityScore:
    """一次质量评测的加权得分与明细。"""
    score: float                       # 0 ~ 100
    breakdown: Dict[str, float] = field(default_factory=dict)   # key -> 得分贡献
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    partial: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "breakdown": {k: round(v, 2) for k, v in self.breakdown.items()},
            "passed": self.passed,
            "failed": self.failed,
            "partial": self.partial,
        }


def _coerce_signals(signals) -> Dict[str, SignalResult]:
    """把输入规整为 {key: SignalResult}。支持三种输入：
    - List[SignalResult]
    - List[dict]  （含 key + value/passed + detail）
    - Dict[str, bool|float]
    """
    if isinstance(signals, dict):
        out = {}
        for k, v in signals.items():
            if k not in SIGNALS:
                continue
            val = float(v) if isinstance(v, (int, float)) else (1.0 if v else 0.0)
            out[k] = SignalResult(key=k, value=val)
        return out

    out = {}
    for item in signals:
        if isinstance(item, SignalResult):
            out[item.key] = item
            continue
        key = item.get("key")
        if key not in SIGNALS:
            continue
        if "value" in item:
            val = item["value"]
        elif "passed" in item:
            val = 1.0 if item["passed"] else 0.0
        else:
            val = 0.0
        out[key] = SignalResult(key=key, value=float(val),
                                detail=item.get("detail", ""))
    return out


def compute_score(signals) -> QualityScore:
    """按信号权重计算 0–100 加权得分。缺失的信号视为 0 分（硬失败）。"""
    results = _coerce_signals(signals)
    score = 0.0
    breakdown: Dict[str, float] = {}
    passed: List[str] = []
    failed: List[str] = []
    partial: List[str] = []

    for key, (name, weight) in SIGNALS.items():
        r = results.get(key)
        if r is None:
            # 未提供 = 未验证 = 0 分，计入失败
            breakdown[key] = 0.0
            failed.append(key)
            continue
        contribution = weight * r.value
        breakdown[key] = contribution
        score += contribution
        if r.value >= 1.0:
            passed.append(key)
        elif r.value > 0.0:
            partial.append(key)
        else:
            failed.append(key)

    return QualityScore(score=score, breakdown=breakdown,
                        passed=passed, failed=failed, partial=partial)


def signal_names() -> Dict[str, str]:
    return {k: v[0] for k, v in SIGNALS.items()}
