"""批级 / 聚合级质量门（FR-10 §11.4）。

批级只做 AST/diff/写白名单等可在部分迁移状态下判定的信号；
全量 build/browser 硬门只在聚合门执行。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def evaluate_batch(*, ast_ok: bool, diff_ok: bool, write_scope_ok: bool = True,
                   scoped_tests_ok: bool = True, llm_score: Optional[float] = None,
                   truncated: bool = False, pass_score: float = 85.0,
                   warn_score: float = 70.0) -> Dict[str, Any]:
    reasons: List[str] = []
    hard_fail = False
    if not ast_ok:
        hard_fail = True
        reasons.append("AST/parse 失败")
    if not diff_ok:
        hard_fail = True
        reasons.append("diff 超限或为空")
    if not write_scope_ok:
        hard_fail = True
        reasons.append("越界写（staging 白名单不通过）")
    if hard_fail:
        return {"score": 0.0, "verdict": "rework", "hard_fail": True,
                "reasons": reasons, "truncated": truncated}
    signals = [
        (100.0 if ast_ok else 0.0, 0.30),
        (100.0 if diff_ok else 0.0, 0.20),
        (100.0 if scoped_tests_ok else 40.0, 0.20),
        (float(llm_score) if llm_score is not None else 80.0, 0.30),
    ]
    score = sum(v * w for v, w in signals)
    verdict = "pass" if score >= pass_score else ("warn" if score >= warn_score else "rework")
    if truncated:
        reasons.append("输出截断，建议拆批")
        verdict = "rework"
    return {"score": round(score, 2), "verdict": verdict, "hard_fail": False,
            "reasons": reasons, "truncated": truncated}


def aggregate_gate(*, batch_scores: List[float], coverage: float,
                   full_build_ok: bool, browser_ok: bool,
                   pass_score: float = 85.0) -> Dict[str, Any]:
    reasons: List[str] = []
    if not full_build_ok:
        reasons.append("全量构建失败")
    if not browser_ok:
        reasons.append("关键路由浏览器验证失败")
    if coverage < 1.0:
        reasons.append(f"覆盖率不足: {coverage:.2%}")
    avg = sum(batch_scores) / len(batch_scores) if batch_scores else 0.0
    ok = full_build_ok and browser_ok and coverage >= 1.0 and avg >= pass_score
    return {
        "score": round(avg, 2),
        "verdict": "pass" if ok else "rework",
        "coverage": round(coverage, 4),
        "reasons": reasons,
    }
