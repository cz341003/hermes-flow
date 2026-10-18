"""经验库：踩坑经验的结构化沉淀 + 相似检索回灌（PRD §9 长期记忆层）。

复用 M1 Kernel 的 SQLite experience 表（category/trigger/solution/versions/times_hit），
在此之上补两层能力：
1. **去重沉淀** `record()`：相同 (category, trigger) 已存在 → 命中计数 +1，不重复插入。
2. **相似回灌** `recall()`：给定 phase + 上下文，检索相关经验，供子 Agent 跳过已知坑。
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..kernel import Experience, Kernel

# phase -> 经验类别（1:1 简化；后续可扩展为多对多）
_PHASE_CATEGORY = {
    "analyze": "analyze",
    "deps": "deps",
    "transform": "transform",
    "quality": "quality",
    "verify": "verify",
    "fix": "fix",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}")


def tokenize(text: Optional[str]) -> List[str]:
    """提取检索关键词：英文技术词（>=3 字符）与中文短语（>=2 字）。"""
    if not text:
        return []
    return _TOKEN_RE.findall(text)


class ExperienceBase:
    """经验库门面（长期记忆，跨工程共享）。"""

    def __init__(self, db_path: Optional[str] = None):
        self.kernel = Kernel(db_path or ":memory:")

    def close(self) -> None:
        self.kernel.close()

    # ------------------------------------------------------------------
    def record(self, category: str, trigger: str, solution: str,
               versions: Optional[str] = None) -> Experience:
        """沉淀一条经验；相同 (category, trigger) 已存在则命中计数 +1。"""
        for e in self.kernel.store.search_experience(category=category,
                                                     keyword=trigger):
            if e.category == category and e.trigger == trigger:
                self.kernel.hit_experience(e.id)
                refreshed = self.kernel.store.search_experience(category=category,
                                                                keyword=trigger)
                for r in refreshed:
                    if r.id == e.id:
                        return r
                return e
        return self.kernel.add_experience(category, trigger, solution, versions)

    def search(self, category: Optional[str] = None,
               keyword: Optional[str] = None, limit: int = 20) -> List[Experience]:
        return self.kernel.store.search_experience(category=category,
                                                   keyword=keyword)[:limit]

    def list_all(self, limit: int = 100) -> List[Experience]:
        return self.kernel.store.search_experience()[:limit]

    def hit(self, exp_id: str) -> None:
        self.kernel.hit_experience(exp_id)

    # ------------------------------------------------------------------
    def recall(self, phase: Optional[str] = None,
               context: str = "", limit: int = 10) -> List[Experience]:
        """相似场景回灌：按 phase 类别检索，再用上下文关键词加权排序。

        命中规则：trigger/solution 含关键词的经验优先（命中数越多越靠前），
        未命中关键词的按 times_hit 降序兜底。
        """
        category = phase
        keywords = tokenize(context)
        pool = self.search(category=category, limit=50)
        if not keywords:
            return pool[:limit]

        scored: List[tuple] = []
        for e in pool:
            haystack = f"{e.trigger} {e.solution}".lower()
            hits = sum(1 for kw in keywords if kw.lower() in haystack)
            scored.append((hits, e.times_hit, e))
        scored.sort(key=lambda t: (-t[0], -t[1]))
        return [e for _, _, e in scored[:limit]]
