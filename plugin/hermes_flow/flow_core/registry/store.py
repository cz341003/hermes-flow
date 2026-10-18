"""Registry：专家 / 技能 / 工作流模板的自动加载与持久化。

- 内置：``<plugin_root>/agents/*.json``、``skills/<name>/SKILL.md``、``workflows/*.json``
- 用户：``<data_dir>/agents/*.json``、``<data_dir>/skills/<id>/SKILL.md``、``<data_dir>/workflows/*.json``
- 用户条目按 id 覆盖内置；启动时自动加载（PRD FR-1/FR-2）。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import AgentSpec, DEFAULT_LOOP_POLICY, SkillSpec, WorkflowTemplate
from ..engine.dag import CyclicGraphError, Workflow, topological_sort

try:  # PyYAML 在 Hermes 环境中可用；独立测试时允许降级
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_NODE_TYPES = {"agent_task", "batch", "quality_gate", "human_gate", "condition", "loop", "join", "script"}


def slugify(value: str) -> str:
    import hashlib
    raw = value.strip().lower()
    s = _SLUG_RE.sub("-", raw).strip("-")
    if len(s) < 2:
        s = "item-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return s


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """解析 SKILL.md 的 YAML frontmatter；无 yaml 时退化为 key: value。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw, body = parts[1], parts[2]
    meta: Dict[str, Any] = {}
    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw)
            if isinstance(loaded, dict):
                meta = dict(loaded)
        except Exception:
            meta = {}
    if not meta:
        for line in raw.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            if not k:
                continue
            if v.startswith("[") and v.endswith("]"):
                meta[k] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
            else:
                meta[k] = v
    return meta, body


class Registry:
    def __init__(self, plugin_root: str | Path, data_dir: str | Path):
        self.plugin_root = Path(plugin_root)
        self.data_dir = Path(data_dir)
        self.agents: Dict[str, AgentSpec] = {}
        self.skills: Dict[str, SkillSpec] = {}
        self.workflows: Dict[str, WorkflowTemplate] = {}
        self.last_errors: List[str] = []
        self.load()

    # ------------------------------------------------------------------ load
    def load(self) -> None:
        self.agents.clear()
        self.skills.clear()
        self.workflows.clear()
        self.last_errors = []
        self._load_agents(self.plugin_root / "agents", builtin=True)
        self._load_agents(self.data_dir / "agents", builtin=False)
        self._load_skills(self.plugin_root / "skills", builtin=True)
        self._load_skills(self.data_dir / "skills", builtin=False)
        self._load_workflows(self.plugin_root / "workflows", builtin=True)
        self._load_workflows(self.data_dir / "workflows", builtin=False)

    def _iter_json(self, directory: Path) -> List[Path]:
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.glob("*.json") if p.is_file())

    def _load_agents(self, directory: Path, *, builtin: bool) -> None:
        for path in self._iter_json(directory):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                agents = data if isinstance(data, list) else [data]
                for item in agents:
                    item = dict(item)
                    item.setdefault("id", slugify(item.get("name", path.stem)))
                    item["builtin"] = builtin
                    spec = AgentSpec.from_dict(item)
                    self.agents[spec.id] = spec
            except Exception as exc:  # noqa: BLE001 - 单个坏文件不阻塞加载
                self.last_errors.append(f"agent {path.name}: {exc}")

    def _load_skills(self, directory: Path, *, builtin: bool) -> None:
        if not directory.is_dir():
            return
        for skill_md in sorted(directory.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
                meta, body = _parse_frontmatter(text)
                name = str(meta.get("name") or skill_md.parent.name)
                sid = slugify(str(meta.get("id") or name))
                desc = str(meta.get("description") or body.strip().splitlines()[0] if body.strip() else "")
                phases = meta.get("phases") or meta.get("applies_to") or []
                if isinstance(phases, str):
                    phases = [p.strip() for p in phases.split(",") if p.strip()]
                tags = meta.get("tags") or []
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                self.skills[sid] = SkillSpec(
                    id=sid, name=name, description=desc, path=str(skill_md),
                    phases=list(phases), tags=list(tags),
                    version=str(meta.get("version", "")), builtin=builtin,
                )
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append(f"skill {skill_md.parent.name}: {exc}")

    def _load_workflows(self, directory: Path, *, builtin: bool) -> None:
        for path in self._iter_json(directory):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                wid = str(data.get("id") or path.stem)
                self.workflows[wid] = WorkflowTemplate(
                    id=wid,
                    name=str(data.get("name") or wid),
                    description=str(data.get("description", "")),
                    version=str(data.get("version", "1.0.0")),
                    definition=data,
                    path=str(path),
                    builtin=builtin,
                )
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append(f"workflow {path.name}: {exc}")

    # ---------------------------------------------------------------- agents
    def list_agents(self) -> List[AgentSpec]:
        return sorted(self.agents.values(), key=lambda a: (not a.builtin, a.name))

    def get_agent(self, agent_id: str) -> Optional[AgentSpec]:
        return self.agents.get(agent_id)

    def validate_agent(self, data: Dict[str, Any], *, allow_missing_skills: bool = False) -> List[str]:
        errors: List[str] = []
        name = str(data.get("name", "")).strip()
        role = str(data.get("role", "")).strip()
        if not name:
            errors.append("name 必填")
        if len(role) < 20:
            errors.append("role（角色提示词）至少 20 字符")
        for skill in data.get("skills", []) or []:
            if not allow_missing_skills and str(skill) not in self.skills:
                errors.append(f"技能不存在: {skill}")
        policy = {**DEFAULT_LOOP_POLICY, **dict(data.get("loop_policy") or {})}
        if int(policy.get("max_files_per_batch", 7)) < 1:
            errors.append("loop_policy.max_files_per_batch 必须 >= 1")
        if int(policy.get("max_concurrent_batches", 1)) < 1:
            errors.append("loop_policy.max_concurrent_batches 必须 >= 1")
        return errors

    def create_agent(self, data: Dict[str, Any]) -> AgentSpec:
        errors = self.validate_agent(data)
        if errors:
            raise ValueError("; ".join(errors))
        now = int(time.time())
        agent_id = str(data.get("id") or slugify(data["name"]))
        if agent_id in self.agents and not self.agents[agent_id].builtin:
            raise ValueError(f"专家已存在: {agent_id}")
        spec = AgentSpec.from_dict({
            **data, "id": agent_id, "builtin": False,
            "created_at": now, "updated_at": now,
        })
        self._write_agent(spec)
        self.agents[spec.id] = spec
        return spec

    def update_agent(self, agent_id: str, patch: Dict[str, Any]) -> AgentSpec:
        current = self.agents.get(agent_id)
        if current is None:
            raise KeyError(agent_id)
        merged = {**current.to_dict(), **patch, "id": agent_id, "builtin": False,
                  "updated_at": int(time.time())}
        errors = self.validate_agent(merged)
        if errors:
            raise ValueError("; ".join(errors))
        spec = AgentSpec.from_dict(merged)
        self._write_agent(spec)
        self.agents[agent_id] = spec
        return spec

    def delete_agent(self, agent_id: str) -> bool:
        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        if agent.builtin:
            raise ValueError("内置专家不能删除，可停用")
        path = self.data_dir / "agents" / f"{agent_id}.json"
        if path.exists():
            path.unlink()
        self.agents.pop(agent_id, None)
        return True

    def _write_agent(self, spec: AgentSpec) -> None:
        directory = self.data_dir / "agents"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{spec.id}.json").write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- skills
    def list_skills(self) -> List[SkillSpec]:
        return sorted(self.skills.values(), key=lambda s: (not s.builtin, s.name))

    def get_skill(self, skill_id: str) -> Optional[SkillSpec]:
        return self.skills.get(skill_id)

    def validate_skill(self, text: str) -> Tuple[bool, List[str], Dict[str, Any]]:
        errors: List[str] = []
        meta, body = _parse_frontmatter(text)
        if not text.startswith("---"):
            errors.append("缺少 YAML frontmatter（---）")
        name = str(meta.get("name", "")).strip()
        desc = str(meta.get("description", "")).strip()
        if not name:
            errors.append("frontmatter.name 必填")
        if not desc:
            errors.append("frontmatter.description 必填")
        elif len(desc) > 120:
            errors.append("description 建议 ≤120 字符")
        if "Procedure" not in body and "procedure" not in body.lower():
            errors.append("正文建议含 Procedure 段落")
        return (not errors), errors, {"meta": meta, "body": body}

    def create_skill(self, name: str, description: str, body: str, *, phases: Optional[List[str]] = None,
                     tags: Optional[List[str]] = None) -> SkillSpec:
        text = (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"version: 1.0.0\n"
            f"phases: [{', '.join(phases or [])}]\n"
            f"tags: [{', '.join(tags or [])}]\n"
            "---\n\n" + body.strip() + "\n"
        )
        ok, errors, parsed = self.validate_skill(text)
        if not ok:
            raise ValueError("; ".join(errors))
        sid = slugify(name)
        directory = self.data_dir / "skills" / sid
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "SKILL.md"
        path.write_text(text, encoding="utf-8")
        spec = SkillSpec(
            id=sid, name=name, description=description, path=str(path),
            phases=list(phases or []), tags=list(tags or []), version="1.0.0", builtin=False,
        )
        self.skills[sid] = spec
        return spec

    # ------------------------------------------------------------- workflows
    def list_workflows(self) -> List[WorkflowTemplate]:
        return sorted(self.workflows.values(), key=lambda w: (not w.builtin, w.name))

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowTemplate]:
        return self.workflows.get(workflow_id)

    def validate_workflow(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not data.get("id"):
            errors.append("id 必填")
        nodes = data.get("nodes") or []
        if not nodes:
            errors.append("nodes 不能为空")
        ids = [str(n.get("id")) for n in nodes if isinstance(n, dict)]
        if len(ids) != len(set(ids)):
            errors.append("节点 id 重复")
        allowed = _NODE_TYPES
        for node in nodes:
            if not isinstance(node, dict) or not node.get("id"):
                errors.append("节点缺少 id")
                continue
            ntype = str(node.get("type", "agent_task"))
            if ntype not in allowed:
                errors.append(f"未知节点类型: {ntype}")
            if ntype == "batch" and not isinstance(node.get("batch"), dict):
                errors.append(f"batch 节点缺少 batch 配置: {node.get('id')}")
        try:
            wf = Workflow.from_dict({
                "id": data.get("id", "wf"),
                "name": data.get("name", data.get("id", "wf")),
                "nodes": [{"id": n["id"], "name": n.get("name", n["id"]),
                           "phase": n.get("phase", "transform"),
                           "agent": n.get("agent", ""), "skill": n.get("skill"),
                           "parallel": n.get("parallel", False)} for n in nodes],
                "edges": data.get("edges") or [],
            })
            topological_sort(wf)
        except (CyclicGraphError, KeyError, TypeError) as exc:
            errors.append(f"DAG 非法: {exc}")
        return (not errors), errors

    def save_workflow(self, data: Dict[str, Any]) -> WorkflowTemplate:
        ok, errors = self.validate_workflow(data)
        if not ok:
            raise ValueError("; ".join(errors))
        wid = str(data["id"])
        directory = self.data_dir / "workflows"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{wid}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmpl = WorkflowTemplate(
            id=wid, name=str(data.get("name") or wid),
            description=str(data.get("description", "")),
            version=str(data.get("version", "1.0.0")),
            definition=data, path=str(path), builtin=False,
        )
        self.workflows[wid] = tmpl
        return tmpl
