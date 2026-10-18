"""Registry 数据模型：Agent / Skill / WorkflowTemplate。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_LOOP_POLICY: Dict[str, Any] = {
    "enabled": True,
    "mode": "per_batch",              # per_batch | single_file | persistent_child(P2)
    "inner_loop": "serial",
    "max_files_per_batch": 7,
    "max_batches_per_launch": 1,
    "max_concurrent_batches": 1,
    "context_budget_chars": 28000,
    "split_on_failure": True,
    "max_split_depth": 2,
    "checkpoint_each_batch": True,
    "quality_gate_per_batch": True,
    "write_mode": "staging_apply",
}


@dataclass
class AgentSpec:
    id: str
    name: str
    description: str = ""
    role: str = ""
    skills: List[str] = field(default_factory=list)
    model: str = ""
    toolsets: List[str] = field(default_factory=list)
    max_turns: int = 60
    loop_policy: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_LOOP_POLICY))
    builtin: bool = False
    enabled: bool = True
    created_at: int = 0
    updated_at: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "role": self.role,
            "skills": list(self.skills),
            "model": self.model,
            "toolsets": list(self.toolsets),
            "max_turns": self.max_turns,
            "loop_policy": dict(self.loop_policy),
            "builtin": self.builtin,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSpec":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description", "")),
            role=str(data.get("role", "")),
            skills=[str(s) for s in data.get("skills", [])],
            model=str(data.get("model", "")),
            toolsets=[str(t) for t in data.get("toolsets", [])],
            max_turns=int(data.get("max_turns", 60)),
            loop_policy={**DEFAULT_LOOP_POLICY, **dict(data.get("loop_policy") or {})},
            builtin=bool(data.get("builtin", False)),
            enabled=bool(data.get("enabled", True)),
            created_at=int(data.get("created_at", 0)),
            updated_at=int(data.get("updated_at", 0)),
        )


@dataclass
class SkillSpec:
    id: str
    name: str
    description: str = ""
    path: str = ""
    phases: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    version: str = ""
    builtin: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "phases": list(self.phases),
            "tags": list(self.tags),
            "version": self.version,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillSpec":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description", "")),
            path=str(data.get("path", "")),
            phases=[str(p) for p in data.get("phases", [])],
            tags=[str(t) for t in data.get("tags", [])],
            version=str(data.get("version", "")),
            builtin=bool(data.get("builtin", False)),
        )


@dataclass
class WorkflowTemplate:
    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    definition: Dict[str, Any] = field(default_factory=dict)
    path: str = ""
    builtin: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "definition": self.definition,
            "path": self.path,
            "builtin": self.builtin,
        }
