"""异常分类：把错误文本/状态码归类为失败类别（PRD §7 异常表）。"""
from __future__ import annotations

from enum import Enum


class FailureCategory(str, Enum):
    RATE_LIMIT = "rate_limit"                  # 429 限流
    TRUNCATION = "truncation"                  # 上下文/输出截断
    TIMEOUT = "timeout"                        # 执行超时
    DEPENDENCY_MISSING = "dependency_missing"  # 依赖缺失
    COMPILE_ERROR = "compile_error"            # 编译/构建失败
    QUALITY_LOW = "quality_low"                # 质量低分
    AGENT_DRIFT = "agent_drift"                # agent 跑偏/违规并行
    DESTRUCTIVE = "destructive"                # 破坏性/发布动作
    UNKNOWN = "unknown"                        # 未识别


# 关键字规则：按顺序匹配（越具体越靠前）。全小写匹配。
_RULES: list = [
    (FailureCategory.RATE_LIMIT,
     ["429", "rate limit", "rate_limit", "ratelimit", "too many requests",
      "throttl", "限流", "配额", "quota exceeded"]),
    (FailureCategory.TRUNCATION,
     ["truncat", "token limit", "max_tokens", "context length",
      "上下文超", "上下文过长", "截断", "output length", "context window"]),
    (FailureCategory.TIMEOUT,
     ["timeout", "timed out", "超时"]),
    (FailureCategory.DEPENDENCY_MISSING,
     ["module not found", "no module named", "import error", "cannot find module",
      "unresolved import", "依赖缺失", "依赖未安装", "dependency not found"]),
    (FailureCategory.COMPILE_ERROR,
     ["compile", "syntax error", "build failed", "parse error", "编译",
      "构建失败", "语法错误", "vue-tsc", "tsc error", "unexpected token"]),
    (FailureCategory.QUALITY_LOW,
     ["quality", "below threshold", "评分低于", "低分", "得分低于", "未达通过线",
      "回环修复"]),
    (FailureCategory.AGENT_DRIFT,
     ["parallel", "并行", "违规", "drift", "跑偏", "串行约束"]),
    (FailureCategory.DESTRUCTIVE,
     ["destructive", "破坏性", "publish", "deploy", "release", "发布", "删除生产"]),
]


def classify(error: str | None, status_code: int = 0) -> FailureCategory:
    """按状态码与错误文本归类。429 优先；否则关键字匹配；未命中 → UNKNOWN。"""
    if status_code == 429:
        return FailureCategory.RATE_LIMIT
    text = (error or "").lower()
    for category, keywords in _RULES:
        for kw in keywords:
            if kw in text:
                return category
    return FailureCategory.UNKNOWN
