"""看板渲染：把 workflow 状态 + 经验库渲染为自包含 HTML。

纯函数：输入结构化数据，输出完整 HTML 字符串，便于测试与插件 `board_render` 工具复用。
"""
from __future__ import annotations

from html import escape
from typing import List, Optional

# 节点状态 -> (中文标签, 颜色)
_STATUS_META = {
    "ready":   ("未开始", "#9aa4b2"),
    "running": ("运行中", "#3b82f6"),
    "done":    ("已完成", "#22c55e"),
    "failed":  ("失败",   "#ef4444"),
    "blocked": ("阻塞",   "#f59e0b"),
}

# phase -> 中文
_PHASE_LABEL = {
    "analyze": "结构分析", "deps": "依赖分析", "transform": "代码转化",
    "quality": "质量分析", "verify": "浏览器验证", "fix": "修复",
}


def _status_meta(status: str):
    return _STATUS_META.get(status, (status, "#9aa4b2"))


def render_board(workflows: List[dict], experiences: List[dict],
                 title: str = "Vue3 迁移看板") -> str:
    """生成自包含 HTML 看板。"""
    wf_cards = "\n".join(_render_workflow(w) for w in workflows) or \
        '<p class="empty">暂无工作流</p>'
    exp_rows = _render_experiences(experiences)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root {{
  --bg:#f6f7f9; --card:#ffffff; --border:#e5e7eb; --text:#1f2937;
  --muted:#6b7280; --accent:#6366f1;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--text); padding:24px; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:20px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:16px 18px; margin-bottom:16px; }}
.card h2 {{ font-size:16px; margin:0 0 12px; display:flex; align-items:center; gap:10px; }}
.badge {{ font-size:12px; padding:2px 10px; border-radius:999px; color:#fff; }}
.progress {{ height:8px; background:#e5e7eb; border-radius:999px; overflow:hidden; margin:8px 0 14px; }}
.progress > div {{ height:100%; background:var(--accent); border-radius:999px; transition:width .3s; }}
.nodes {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }}
.node {{ border:1px solid var(--border); border-radius:8px; padding:10px 12px; }}
.node .name {{ font-weight:600; font-size:14px; }}
.node .meta {{ font-size:12px; color:var(--muted); margin-top:2px; }}
.node .bar {{ display:flex; align-items:center; gap:8px; margin-top:8px; }}
.dot {{ width:10px; height:10px; border-radius:50%; flex:0 0 auto; }}
.score {{ margin-left:auto; font-size:12px; font-weight:600; }}
.trace {{ font-size:12px; color:var(--muted); margin-top:12px; }}
.trace code {{ background:#f3f4f6; padding:2px 6px; border-radius:4px; margin-right:4px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }}
th {{ color:var(--muted); font-weight:600; }}
.tag {{ font-size:11px; padding:1px 8px; border-radius:999px; background:#eef2ff; color:#4f46e5; }}
.hits {{ color:var(--muted); }}
.empty {{ color:var(--muted); }}
</style>
</head>
<body>
<h1>{escape(title)}</h1>
<div class="sub">工作流进度 · 节点状态 · 质量评分 · 经验库</div>
{wf_cards}
<div class="card">
  <h2>经验库 <span class="badge" style="background:#8b5cf6">{len(experiences)}</span></h2>
  {exp_rows}
</div>
</body>
</html>"""


def _render_workflow(w: dict) -> str:
    wid = escape(str(w.get("id", "")))
    name = escape(str(w.get("name", "")))
    done = bool(w.get("done", False))
    nodes = w.get("nodes", [])
    total = len(nodes)
    done_count = sum(1 for n in nodes if n.get("status") == "done")
    pct = round(done_count / total * 100) if total else 0
    badge_color = "#22c55e" if done else "#3b82f6"
    badge_text = "已完成" if done else "进行中"

    node_html = "\n".join(_render_node(n) for n in nodes)
    trace = " → ".join(f'<code>{escape(str(t))}</code>' for t in w.get("trace", []))
    return f"""
<div class="card">
  <h2>{name} <span style="color:var(--muted);font-weight:400">({wid})</span>
    <span class="badge" style="background:{badge_color}">{badge_text}</span>
    <span style="margin-left:auto;font-size:13px;color:var(--muted)">{done_count}/{total}</span>
  </h2>
  <div class="progress"><div style="width:{pct}%"></div></div>
  <div class="nodes">{node_html}</div>
  <div class="trace">执行轨迹：{trace or "—"}</div>
</div>"""


def _render_node(n: dict) -> str:
    status = n.get("status", "ready")
    label, color = _status_meta(status)
    name = escape(str(n.get("name", n.get("id", ""))))
    phase = _PHASE_LABEL.get(n.get("phase", ""), n.get("phase", ""))
    agent = escape(str(n.get("agent", "")))
    score = n.get("score")
    attempt = n.get("attempts", 0)
    score_html = f'<span class="score">{score:.0f}分</span>' if score is not None else \
        (f'<span class="score hits">第{attempt}次</span>' if attempt else "")
    return f"""
  <div class="node">
    <div class="name">{name}</div>
    <div class="meta">{phase}{(' · ' + agent) if agent else ''}</div>
    <div class="bar"><span class="dot" style="background:{color}"></span>
      <span style="font-size:12px">{label}</span>{score_html}</div>
  </div>"""


def _render_experiences(experiences: List[dict]) -> str:
    if not experiences:
        return '<p class="empty">暂无经验沉淀</p>'
    rows = []
    for e in experiences:
        cat = escape(str(e.get("category", "")))
        trigger = escape(str(e.get("trigger", "")))
        solution = escape(str(e.get("solution", "")))
        hits = e.get("times_hit", 1)
        rows.append(
            f'<tr><td><span class="tag">{cat}</span></td>'
            f'<td>{trigger}</td><td>{solution}</td>'
            f'<td class="hits">{hits} 次</td></tr>')
    return ('<table><thead><tr><th>类别</th><th>触发条件</th>'
            '<th>解法</th><th>命中</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table>')
