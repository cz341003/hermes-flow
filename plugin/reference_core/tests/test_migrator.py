"""migrator 转换器单测：分析 / 依赖图 / 转换 / 评分。"""
from __future__ import annotations

import os
import tempfile
import unittest

from vue3migrate_core.migrator import (
    analyze,
    build_deps,
    score_signals,
    topo_order_files,
    transform_file,
)
from vue3migrate_core.quality import compute_score


def _mkfile(root: str, rel: str, content: str) -> str:
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return full


class TestAnalyze(unittest.TestCase):
    def test_detect_vue2_patterns(self):
        with tempfile.TemporaryDirectory() as d:
            _mkfile(d, "src/main.js", "import Vue from 'vue';\nnew Vue({}).$mount('#app');")
            _mkfile(d, "src/A.vue", "<template><p>{{ x | f }}</p></template>")
            _mkfile(d, "src/clean.js", "export const x = 1;")
            report = analyze(d)
            self.assertEqual(report.total, 3)
            self.assertIn("new Vue", report.issue_counts)
            self.assertIn("template filter", report.issue_counts)

    def test_clean_file_no_issue(self):
        with tempfile.TemporaryDirectory() as d:
            _mkfile(d, "src/a.js", "export const a = 1;")
            report = analyze(d)
            self.assertEqual(report.files[0].issues, [])


class TestDeps(unittest.TestCase):
    def test_topo_order_dependency_first(self):
        with tempfile.TemporaryDirectory() as d:
            _mkfile(d, "src/utils.js", "export const u = 1;")
            _mkfile(d, "src/App.js", "import { u } from './utils';\n")
            files = analyze(d).files
            order = topo_order_files(files, d)
            # utils.js 应在 App.js 之前
            self.assertLess(order.index("src/utils"), order.index("src/App"))

    def test_deps_graph_edges(self):
        with tempfile.TemporaryDirectory() as d:
            _mkfile(d, "src/a.js", "export const a = 1;")
            _mkfile(d, "src/b.js", "import { a } from './a';\n")
            files = analyze(d).files
            deps = build_deps(files, d)
            self.assertIn("src/a", deps["src/b"])


class TestTransform(unittest.TestCase):
    def test_sfc_options_to_setup(self):
        src = ("<template><p>{{ msg }}</p></template>\n"
               "<script>export default {\n"
               "  data() {\n    return {\n      msg: 'hi',\n    };\n  },\n"
               "};</script>")
        r = transform_file("X.vue", src)
        self.assertIn("<script setup>", r.output)
        self.assertIn("const msg = ref(", r.output)

    def test_filter_pipe_to_call(self):
        src = ("<template><p>{{ user.role | roleText }}</p></template>\n"
               "<script>export default {\n"
               "  filters: {\n    roleText(r) {\n      return r;\n    },\n  },\n"
               "};</script>")
        r = transform_file("X.vue", src)
        self.assertIn("roleText(user.role)", r.output)
        self.assertNotIn("| roleText", r.output)

    def test_or_operator_not_treated_as_filter(self):
        src = "<template><p>{{ user.name || 'guest' }}</p></template>\n<script>export default {};</script>"
        r = transform_file("X.vue", src)
        self.assertIn("user.name || 'guest'", r.output)

    def test_before_destroy_to_unmount(self):
        src = ("<script>export default {\n  data() {\n    return {};\n  },\n"
               "  beforeDestroy() {\n    this.x = 1;\n  },\n};</script>")
        r = transform_file("X.vue", src)
        self.assertIn("onBeforeUnmount", r.output)
        self.assertNotIn("beforeDestroy", r.output)

    def test_router3_to_router4(self):
        src = ("import VueRouter from 'vue-router';\n"
               "const router = new VueRouter({\n  mode: 'history',\n  routes: [],\n});")
        r = transform_file("src/router/index.js", src)
        self.assertIn("createRouter", r.output)
        self.assertIn("createWebHistory", r.output)
        self.assertNotIn("new VueRouter", r.output)

    def test_vuex_to_pinia(self):
        src = ("import Vue from 'vue';\nimport Vuex from 'vuex';\n"
               "import user from './modules/user';\n\nVue.use(Vuex);\n\n"
               "export default new Vuex.Store({\n  modules: {\n    user,\n  },\n});")
        r = transform_file("src/store/index.js", src)
        self.assertIn("createPinia", r.output)
        self.assertNotIn("Vuex.Store", r.output)

    def test_mixin_to_composable(self):
        src = ("export default {\n  data() { return { loading: false }; },\n"
               "  methods: { setLoading(v) { this.loading = v; } },\n"
               "  beforeDestroy() { this.loading = false; },\n};")
        r = transform_file("src/mixins/loadingMixin.js", src)
        self.assertIn("export function useLoading", r.output)
        self.assertIn("onBeforeUnmount", r.output)
        self.assertNotIn("beforeDestroy", r.output)

    def test_ztree_to_a_tree(self):
        src = ("<template><ul class='ztree'></ul></template>\n"
               "<script>import 'jquery.ztree'; export default {};</script>")
        r = transform_file("TreeMenu.vue", src)
        self.assertIn("a-tree", r.output)
        self.assertNotIn("ztree", r.output)


class TestScoring(unittest.TestCase):
    def _signals(self, original, transformed):
        return score_signals(original, transformed)

    def test_clean_file_full_score(self):
        # 纯工具文件无 Vue2 特征 → 满分
        signals = self._signals("export const x = 1;", "export const x = 1;")
        self.assertEqual(compute_score(signals).score, 100.0)

    def test_migrated_file_full_score(self):
        src = "<script>export default { data() { return { a: 1 }; } };</script>"
        r = transform_file("X.vue", src)
        signals = self._signals(src, r.output)
        self.assertEqual(compute_score(signals).score, 100.0)

    def test_unmigrated_file_low_score(self):
        # 含 Vue2 特征但未转换 → 低分
        src = "import Vue from 'vue';\nnew Vue({}).$mount('#app');"
        signals = self._signals(src, src)  # 原样 → 未迁移
        score = compute_score(signals).score
        self.assertLess(score, 70)

    def test_or_operator_not_filter_signal(self):
        # {{ x || y }} 不应被判为 filter 管道残留
        tpl = "<template><p>{{ user.name || 'guest' }}</p></template>\n"
        signals = self._signals("", tpl)
        browser = [s for s in signals if s["key"] == "browser"][0]
        self.assertEqual(browser["value"], 1.0)


if __name__ == "__main__":
    unittest.main()
