"""M7 演示：内核可切换（自研 SQLite ↔ LoopX JSONL）+ LoopX CLI 桥接点。

展示：
1. 同一操作序列，在 sqlite 与 loopx 两种内核后端下结果完全一致。
2. create_kernel 工厂切换零改动。
3. LoopXBridge（真实 loopx CLI 桥接点）在未安装 loopx 时的优雅降级。
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vue3migrate_core.adapters import LoopXBridge, create_kernel


def run_sequence(k, label):
    """在两个后端执行同一操作序列，打印结果。"""
    g = k.create_goal("迁移", quota_total=10)
    a = k.create_todo(g.id, "a.vue", "analyze")
    b = k.create_todo(g.id, "b.vue", "transform", dependencies=[a.id])

    print(f"\n[{label}]")
    print(f"  should_run        = {k.should_run(g.id).should}")
    c1 = k.claim(g.id, "结构分析专家")
    print(f"  claim #1          = {c1.id} ({c1.file_path}, {c1.phase})")
    c2 = k.claim(g.id, "代码转化专家")   # b 依赖 a 未完成 → 应拒绝
    print(f"  claim #2 (应拒)   = {c2}")
    k.update(a.id, "done")
    c3 = k.claim(g.id, "代码转化专家")
    print(f"  claim #3          = {c3.id if c3 else None} ({c3.file_path if c3 else '-'})")
    k.update(b.id, "done")
    snap = k.refresh_state(g.id)
    print(f"  最终 goal 状态    = {snap.goal.status} | progress = {snap.progress}")
    k.close()


def main():
    with tempfile.TemporaryDirectory() as d:
        print("=" * 60)
        print("内核工厂切换：同一操作序列，两种后端结果一致")
        print("=" * 60)

        sqlite = create_kernel("sqlite", db_path=f"{d}/state.db")
        run_sequence(sqlite, "backend=sqlite（自研 SQLite）")

        loopx = create_kernel("loopx", root=f"{d}/lx")
        run_sequence(loopx, "backend=loopx（JSONL domain-state）")

    print("\n" + "=" * 60)
    print("LoopXBridge：真实 loopx CLI 桥接点（未安装时优雅降级）")
    print("=" * 60)
    bridge = LoopXBridge(registry=".loopx/registry.json")
    try:
        bridge.resolve_agent_thread("session-1")
    except RuntimeError as exc:
        print(f"  → 预期降级：{exc}")


if __name__ == "__main__":
    main()
