"""DAG 单测：拓扑排序 + 环检测 + 序列化。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flow_core.engine import (  # noqa: E402
    CyclicGraphError,
    Edge,
    Node,
    Workflow,
    topological_sort,
)


def make_workflow():
    """A→C, B→C, C→D"""
    nodes = [
        Node(id="A", name="结构分析A", phase="analyze"),
        Node(id="B", name="结构分析B", phase="analyze"),
        Node(id="C", name="代码转化C", phase="transform"),
        Node(id="D", name="质量验证D", phase="quality"),
    ]
    edges = [Edge("A", "C"), Edge("B", "C"), Edge("C", "D")]
    return Workflow(id="wf1", name="测试流程", nodes=nodes, edges=edges)


class TestTopologicalSort(unittest.TestCase):
    def test_topological_order(self):
        wf = make_workflow()
        order = topological_sort(wf)
        self.assertEqual(len(order), 4)
        # 拓扑序性质：C 必须在 A、B 之后；D 必须在 C 之后
        self.assertLess(order.index("A"), order.index("C"))
        self.assertLess(order.index("B"), order.index("C"))
        self.assertLess(order.index("C"), order.index("D"))

    def test_cycle_detection(self):
        nodes = [Node(id="A", name="A", phase="analyze"),
                 Node(id="B", name="B", phase="analyze")]
        edges = [Edge("A", "B"), Edge("B", "A")]
        wf = Workflow(id="cyc", name="环", nodes=nodes, edges=edges)
        with self.assertRaises(CyclicGraphError):
            topological_sort(wf)

    def test_dangling_edge_rejected(self):
        nodes = [Node(id="A", name="A", phase="analyze")]
        edges = [Edge("A", "MISSING")]
        wf = Workflow(id="dang", name="悬空边", nodes=nodes, edges=edges)
        with self.assertRaises(CyclicGraphError):
            topological_sort(wf)

    def test_self_loop_rejected(self):
        nodes = [Node(id="A", name="A", phase="analyze")]
        wf = Workflow(id="self", name="自环", nodes=nodes,
                      edges=[Edge("A", "A")])
        with self.assertRaises(CyclicGraphError):
            topological_sort(wf)


class TestWorkflowSerialize(unittest.TestCase):
    def test_roundtrip(self):
        wf = make_workflow()
        d = wf.to_dict()
        wf2 = Workflow.from_dict(d)
        self.assertEqual(wf.id, wf2.id)
        self.assertEqual([n.id for n in wf2.nodes], ["A", "B", "C", "D"])
        self.assertEqual(topological_sort(wf), topological_sort(wf2))

    def test_predecessors_successors(self):
        wf = make_workflow()
        self.assertEqual(sorted(wf.predecessors("C")), ["A", "B"])
        self.assertEqual(wf.successors("C"), ["D"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
