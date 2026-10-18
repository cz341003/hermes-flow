"""Registry 独立测试：内置/用户自动加载、技能绑定、校验、重启持久化。

只读 flow_core，不改源码。临时目录统一落 ``E:\\deepSeek\\plugin\\.tmp``，
避免系统临时目录权限问题。运行：

    python -m unittest discover -s tests -q
"""
from __future__ import annotations

import json
import shutil
import sys
import os
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow_core.registry import Registry  # noqa: E402

TMP_BASE = Path(os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

LONG_ROLE = "你是 Vue2 到 Vue3 迁移专家，负责逐文件改造并保持行为完全不变。"
USER_ROLE = "你是用户定制的 Vue2->Vue3 专家，先分析依赖再逐文件迁移。"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_workflow(wid: str = "wf-6phase") -> dict:
    return {
        "id": wid,
        "name": "六阶段迁移",
        "description": "analyze->deps->transform(batch)->quality->verify->fix",
        "version": "1.0.0",
        "nodes": [
            {"id": "analyze", "name": "分析", "phase": "analyze", "type": "agent_task", "agent": "code-expert"},
            {"id": "deps", "name": "依赖", "phase": "deps", "type": "agent_task", "agent": "code-expert"},
            {"id": "transform", "name": "转化", "phase": "transform", "type": "batch",
             "agent": "code-expert", "batch": {"max_files_per_batch": 7, "max_split_depth": 2}},
            {"id": "quality", "name": "质量", "phase": "quality", "type": "quality_gate"},
            {"id": "verify", "name": "验证", "phase": "verify", "type": "agent_task", "agent": "code-expert"},
            {"id": "fix", "name": "修复", "phase": "fix", "type": "agent_task", "agent": "code-expert"},
        ],
        "edges": [
            {"source": "analyze", "target": "deps"},
            {"source": "deps", "target": "transform"},
            {"source": "transform", "target": "quality"},
            {"source": "quality", "target": "verify"},
            {"source": "verify", "target": "fix"},
        ],
    }


class RegistryTestBase(unittest.TestCase):
    """每个用例独立 plugin_root（内置资产）+ data_dir（用户资产）。"""

    def setUp(self) -> None:
        TMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=str(TMP_BASE)))
        self.plugin_root = self.tmp / "plugin"
        self.data_dir = self.tmp / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._seed_builtin_assets()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------- fixtures
    def _seed_builtin_assets(self) -> None:
        _write(self.plugin_root / "agents" / "code-expert.json", json.dumps({
            "id": "code-expert",
            "name": "代码转化专家",
            "description": "builtin",
            "role": LONG_ROLE,
            "skills": ["builtin-format"],
            "builtin": True,
        }, ensure_ascii=False))
        _write(self.plugin_root / "skills" / "builtin-format" / "SKILL.md",
               "---\nname: Builtin Format\ndescription: 内置格式化技能\nversion: 1.0.0\n"
               "phases: [transform]\ntags: [vue3]\n---\n\n## Procedure\n1. format code\n")
        _write(self.plugin_root / "workflows" / "wf-6phase.json",
               json.dumps(_valid_workflow(), ensure_ascii=False))

    def registry(self) -> Registry:
        return Registry(self.plugin_root, self.data_dir)


class AutoLoadTest(RegistryTestBase):
    def test_builtin_assets_autoloaded(self) -> None:
        reg = self.registry()
        self.assertEqual(reg.last_errors, [])
        agent = reg.get_agent("code-expert")
        self.assertIsNotNone(agent, "内置专家未自动加载")
        assert agent is not None
        self.assertTrue(agent.builtin)
        self.assertEqual(agent.skills, ["builtin-format"])
        self.assertIsNotNone(reg.get_skill("builtin-format"))
        self.assertIsNotNone(reg.get_workflow("wf-6phase"))
        ids = {a.id for a in reg.list_agents()}
        self.assertIn("code-expert", ids)

    def test_user_assets_autoload_and_override_builtin(self) -> None:
        # 用户同名专家覆盖内置；用户技能/工作流为新增
        _write(self.data_dir / "agents" / "code-expert.json", json.dumps({
            "id": "code-expert", "name": "用户代码专家", "role": USER_ROLE,
            "skills": [],
        }, ensure_ascii=False))
        _write(self.data_dir / "skills" / "user-skill" / "SKILL.md",
               "---\nname: User Skill\ndescription: 用户技能\n---\n\n## Procedure\n1. x\n")
        _write(self.data_dir / "workflows" / "wf-user.json",
               json.dumps(_valid_workflow("wf-user"), ensure_ascii=False))

        reg = self.registry()
        overridden = reg.get_agent("code-expert")
        self.assertIsNotNone(overridden)
        assert overridden is not None
        self.assertFalse(overridden.builtin, "用户资产应覆盖内置并标记 builtin=False")
        self.assertEqual(overridden.role, USER_ROLE)
        self.assertIsNotNone(reg.get_skill("user-skill"))
        self.assertIsNotNone(reg.get_skill("builtin-format"))
        self.assertIsNotNone(reg.get_workflow("wf-user"))
        self.assertIsNotNone(reg.get_workflow("wf-6phase"))

    def test_corrupt_json_does_not_block_load(self) -> None:
        _write(self.data_dir / "agents" / "broken.json", "{not valid json")
        reg = self.registry()
        self.assertTrue(reg.last_errors, "坏文件应记入 last_errors 而不是抛异常")
        self.assertIsNotNone(reg.get_agent("code-expert"), "坏文件不应影响其他资产加载")


class SkillAndAgentTest(RegistryTestBase):
    def test_create_skill_then_bind_agent(self) -> None:
        reg = self.registry()
        skill = reg.create_skill(
            "Vue3 语法升级", "把 Options API 迁移到 Composition API",
            "## Procedure\n1. 识别组件\n2. 改写 setup", phases=["transform"], tags=["vue3"])
        self.assertFalse(skill.builtin)
        self.assertTrue((self.data_dir / "skills" / skill.id / "SKILL.md").is_file())

        agent = reg.create_agent({
            "name": "代码转化专家-用户",
            "role": LONG_ROLE,
            "skills": [skill.id],
            "loop_policy": {"max_files_per_batch": 5, "max_split_depth": 1},
        })
        self.assertFalse(agent.builtin)
        self.assertEqual(agent.skills, [skill.id])
        self.assertEqual(agent.loop_policy["max_files_per_batch"], 5)
        self.assertEqual(agent.loop_policy["max_split_depth"], 1)
        self.assertIn(skill.id, reg.get_agent(agent.id).skills)  # type: ignore[union-attr]
        self.assertTrue((self.data_dir / "agents" / f"{agent.id}.json").is_file())

    def test_invalid_agent_rejected(self) -> None:
        reg = self.registry()
        with self.assertRaises(ValueError):
            reg.create_agent({"name": "短角色", "role": "太短"})
        with self.assertRaises(ValueError):
            reg.create_agent({"name": "缺技能", "role": LONG_ROLE, "skills": ["no-such-skill"]})
        with self.assertRaises(ValueError):
            reg.create_agent({"name": "坏策略", "role": LONG_ROLE,
                              "loop_policy": {"max_files_per_batch": 0}})
        with self.assertRaises(ValueError):
            reg.create_agent({"name": "", "role": LONG_ROLE})
        # 校验通过的不写盘（assure 目录里没有脏数据）
        self.assertEqual(list((self.data_dir / "agents").glob("*.json")), [])

    def test_duplicate_user_agent_rejected_and_builtin_delete_forbidden(self) -> None:
        reg = self.registry()
        reg.create_agent({"name": "用户专家", "role": LONG_ROLE})
        with self.assertRaises(ValueError):
            reg.create_agent({"name": "用户专家", "role": LONG_ROLE})
        with self.assertRaises(ValueError):
            reg.delete_agent("code-expert")  # 内置不可删
        user_agents = [a for a in reg.list_agents() if not a.builtin]
        self.assertEqual(len(user_agents), 1)
        self.assertTrue(reg.delete_agent(user_agents[0].id))

    def test_update_builtin_creates_user_override(self) -> None:
        reg = self.registry()
        updated = reg.update_agent("code-expert", {"role": USER_ROLE})
        self.assertFalse(updated.builtin)
        self.assertEqual(updated.id, "code-expert")
        # 重启后仍是用户覆盖版本
        reg2 = self.registry()
        agent = reg2.get_agent("code-expert")
        assert agent is not None
        self.assertFalse(agent.builtin)
        self.assertEqual(agent.role, USER_ROLE)


class RestartPersistenceTest(RegistryTestBase):
    def test_user_data_survives_new_registry_instance(self) -> None:
        reg = self.registry()
        skill = reg.create_skill("Vue3 升级", "升级 Vue2 到 Vue3", "## Procedure\n1. 改")
        agent = reg.create_agent({"name": "代码转化专家", "role": LONG_ROLE, "skills": [skill.id]})
        wf = reg.save_workflow(_valid_workflow("wf-persist"))

        reg2 = Registry(self.plugin_root, self.data_dir)  # 模拟插件重启
        self.assertIsNotNone(reg2.get_skill(skill.id))
        reloaded = reg2.get_agent(agent.id)
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.skills, [skill.id])
        self.assertEqual(reloaded.role, LONG_ROLE)
        self.assertEqual(reloaded.loop_policy["max_files_per_batch"], 7)
        self.assertIsNotNone(reg2.get_workflow(wf.id))
        self.assertIsNotNone(reg2.get_agent("code-expert"))  # 内置仍在


class WorkflowValidationTest(RegistryTestBase):
    def test_valid_workflow_accepted_and_persisted(self) -> None:
        reg = self.registry()
        data = _valid_workflow("wf-valid")
        ok, errors = reg.validate_workflow(data)
        self.assertTrue(ok, errors)
        saved = reg.save_workflow(data)
        self.assertEqual(saved.id, "wf-valid")
        reg2 = self.registry()
        self.assertIsNotNone(reg2.get_workflow("wf-valid"))
        self.assertEqual(reg2.get_workflow("wf-valid").definition["nodes"][2]["type"], "batch")  # type: ignore[union-attr]

    def test_invalid_workflows_rejected(self) -> None:
        reg = self.registry()
        base_nodes = [
            {"id": "a", "name": "a", "phase": "analyze", "type": "agent_task"},
            {"id": "b", "name": "b", "phase": "transform", "type": "agent_task"},
        ]
        cases = {
            "cycle": {"id": "bad-cycle", "nodes": base_nodes,
                      "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]},
            "dangling_edge": {"id": "bad-edge", "nodes": base_nodes,
                              "edges": [{"source": "a", "target": "missing"}]},
            "unknown_node_type": {"id": "bad-type",
                                  "nodes": [{"id": "a", "type": "teleport"}]},
            "batch_without_config": {"id": "bad-batch",
                                     "nodes": [{"id": "a", "type": "batch"}]},
            "duplicate_ids": {"id": "bad-dup",
                              "nodes": [{"id": "a"}, {"id": "a"}]},
            "empty_nodes": {"id": "bad-empty", "nodes": []},
            "missing_id": {"nodes": [{"id": "a"}]},
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                ok, errors = reg.validate_workflow(data)
                self.assertFalse(ok, f"{name} 应被拒绝")
                self.assertTrue(errors, f"{name} 应给出错误原因")
                with self.assertRaises(ValueError):
                    reg.save_workflow(data)
        self.assertEqual(list((self.data_dir / "workflows").glob("*.json")), [])

    def test_unknown_node_type_message_contains_type(self) -> None:
        reg = self.registry()
        ok, errors = reg.validate_workflow(
            {"id": "bad", "nodes": [{"id": "a", "type": "teleport"}]})
        self.assertFalse(ok)
        self.assertTrue(any("teleport" in e for e in errors), errors)


def _disk_builtin_counts() -> tuple:
    """当前插件根目录中内置资产文件数（agents/skills/workflows）。"""
    agents = len([p for p in (ROOT / "agents").glob("*.json") if p.is_file()]) \
        if (ROOT / "agents").is_dir() else 0
    skills_dir = ROOT / "skills"
    skills = len([p for p in skills_dir.glob("*/SKILL.md") if p.is_file()]) \
        if skills_dir.is_dir() else 0
    workflows = len([p for p in (ROOT / "workflows").glob("*.json") if p.is_file()]) \
        if (ROOT / "workflows").is_dir() else 0
    return agents, skills, workflows


@unittest.skipUnless(
    any(_disk_builtin_counts()),
    "插件尚未提供内置 agents/skills/workflows 资产（由 content-dev 生成）")
class RealPluginBuiltinAssetsTest(unittest.TestCase):
    """真实插件根目录的内置资产应可被自动加载。"""

    def test_real_plugin_root_loads_builtin_assets(self) -> None:
        TMP_BASE.mkdir(parents=True, exist_ok=True)
        data_dir = Path(tempfile.mkdtemp(dir=str(TMP_BASE)))
        try:
            # 资产可能正被其他协作者写入：以"读取前的磁盘文件数"为准，允许短暂重试。
            expected = _disk_builtin_counts()
            reg = None
            loaded = (0, 0, 0)
            for _ in range(3):
                reg = Registry(ROOT, data_dir)
                loaded = (
                    len([a for a in reg.list_agents() if a.builtin]),
                    len([s for s in reg.list_skills() if s.builtin]),
                    len([w for w in reg.list_workflows() if w.builtin]),
                )
                if loaded == expected:
                    break
                time.sleep(0.3)
                expected = _disk_builtin_counts()
            self.assertEqual(
                loaded, expected,
                f"内置资产应全部自动加载：磁盘 {expected} / 已加载 {loaded}；"
                f"errors={reg.last_errors if reg else None}")
        finally:
            shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
