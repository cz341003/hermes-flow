"""经验库 + 看板单测。"""
import unittest

from vue3migrate_core.board import render_board
from vue3migrate_core.experience import ExperienceBase, tokenize


class TestTokenize(unittest.TestCase):
    def test_english_tech_words(self):
        tokens = tokenize("v-model filters Vuex -> Pinia router")
        self.assertIn("v-model", tokens)
        self.assertIn("filters", tokens)
        self.assertIn("Vuex", tokens)
        self.assertIn("Pinia", tokens)

    def test_chinese_phrases(self):
        tokens = tokenize("过滤器被移除 需要改用计算属性")
        self.assertIn("过滤器被移除", tokens)
        self.assertIn("需要改用计算属性", tokens)

    def test_short_english_ignored(self):
        # "of" "to" 长度 <3 应被过滤
        tokens = tokenize("of to in")
        self.assertEqual(tokens, [])

    def test_empty(self):
        self.assertEqual(tokenize(None), [])
        self.assertEqual(tokenize(""), [])


class TestExperienceBase(unittest.TestCase):
    def setUp(self):
        self.exp = ExperienceBase()  # 内存 SQLite

    def tearDown(self):
        self.exp.close()

    def test_record_and_search(self):
        e = self.exp.record("transform", "filters 被移除", "改用 computed")
        self.assertEqual(e.category, "transform")
        results = self.exp.search(category="transform")
        self.assertEqual(len(results), 1)

    def test_dedup_increments_hits(self):
        self.exp.record("transform", "filters 被移除", "改用 computed")
        e2 = self.exp.record("transform", "filters 被移除", "改用 computed")
        self.assertEqual(e2.times_hit, 2)  # 命中计数 +1，不重复插入
        self.assertEqual(len(self.exp.search(category="transform")), 1)

    def test_recall_by_phase(self):
        self.exp.record("transform", "filters 被移除", "改用 computed")
        self.exp.record("quality", "浏览器渲染报错", "检查 ztree 兼容")
        results = self.exp.recall(phase="transform")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].trigger, "filters 被移除")

    def test_recall_ranks_by_keyword(self):
        self.exp.record("transform", "filters 被移除", "改用 computed")
        self.exp.record("transform", "v-model 语义变化", "改用 modelValue")
        results = self.exp.recall(phase="transform", context="组件里用了 filters")
        # filters 相关经验应排最前
        self.assertEqual(results[0].trigger, "filters 被移除")

    def test_recall_no_keyword_orders_by_hits(self):
        self.exp.record("transform", "a 坑", "解 a")
        self.exp.record("transform", "b 坑", "解 b")
        self.exp.record("transform", "b 坑", "解 b")  # b 命中 2 次
        results = self.exp.recall(phase="transform")
        self.assertEqual(results[0].trigger, "b 坑")


class TestBoard(unittest.TestCase):
    def test_render_contains_nodes_and_experiences(self):
        workflows = [{
            "id": "wf", "name": "迁移", "done": False,
            "nodes": [
                {"id": "a", "name": "结构分析", "phase": "analyze",
                 "agent": "结构分析专家", "status": "done", "score": 95},
                {"id": "b", "name": "代码转化", "phase": "transform",
                 "agent": "代码转化专家", "status": "running", "attempts": 1},
                {"id": "c", "name": "质量分析", "phase": "quality",
                 "agent": "质量分析专家", "status": "ready"},
            ],
            "trace": ["a", "b"],
        }]
        experiences = [{"category": "transform", "trigger": "filters 被移除",
                        "solution": "改用 computed", "times_hit": 3}]
        html = render_board(workflows, experiences)
        self.assertIn("结构分析", html)
        self.assertIn("代码转化", html)
        self.assertIn("filters 被移除", html)
        self.assertIn("改用 computed", html)
        self.assertIn("3 次", html)

    def test_render_empty(self):
        html = render_board([], [])
        self.assertIn("暂无工作流", html)
        self.assertIn("暂无经验沉淀", html)

    def test_render_escapes_html(self):
        html = render_board(
            [{"id": "<script>", "name": "<b>x</b>", "done": False,
              "nodes": [], "trace": []}], [])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
