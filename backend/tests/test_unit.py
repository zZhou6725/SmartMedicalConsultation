"""单元测试：纯逻辑层（不依赖数据库/网络）。

用标准库 unittest，`python -m unittest discover -s tests` 即可跑，
不需要额外安装 pytest。

覆盖的判定都是「错了会静默出错」的那类：
  · 指标层：实体族解析、Recall@K、MRR、关键词命中、拒答合规
  · 安全层：急症识别（含反例）、高危识别、约束优先级
  · 意图层：关键词路由、急症优先、实体名兜底
  · 检索层：相关性下限、同族判定、空泛实体名单
  · 门禁层：相对基线比对（回归/容差内/无基线）
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.eval import metrics, runner                     # noqa: E402
from app.retrieval.hybrid import VAGUE_ENTITIES, _is_family_dup  # noqa: E402
from app.services import safety                          # noqa: E402


class TestMetrics(unittest.TestCase):
    def test_family_split(self):
        self.assertEqual(metrics._alternatives("偏头痛|神经性偏头痛"),
                         ["偏头痛", "神经性偏头痛"])
        self.assertEqual(metrics._alternatives("单值"), ["单值"])

    def test_family_match(self):
        self.assertTrue(metrics._matches("偏头痛|神经性偏头痛", "神经性偏头痛"))
        self.assertFalse(metrics._matches("偏头痛", "胃溃疡"))

    def test_recall_exact_and_family(self):
        self.assertEqual(metrics.recall_at_k(["头痛", "偏头痛"], ["头痛"], 5), 1.0)
        self.assertEqual(
            metrics.recall_at_k(["神经性偏头痛"], ["偏头痛|神经性偏头痛"], 5), 1.0)
        self.assertEqual(metrics.recall_at_k(["胃溃疡"], ["头痛"], 5), 0.0)

    def test_recall_respects_k(self):
        # 目标实体排在第 3，k=2 时不该算命中
        self.assertEqual(metrics.recall_at_k(["a", "b", "头痛"], ["头痛"], 2), 0.0)
        self.assertEqual(metrics.recall_at_k(["a", "b", "头痛"], ["头痛"], 3), 1.0)

    def test_recall_empty_expected(self):
        self.assertIsNone(metrics.recall_at_k(["x"], [], 5))

    def test_mrr(self):
        self.assertEqual(metrics.reciprocal_rank(["头痛"], ["头痛"]), 1.0)
        self.assertEqual(metrics.reciprocal_rank(["a", "头痛"], ["头痛"]), 0.5)
        self.assertEqual(metrics.reciprocal_rank(["a"], ["头痛"]), 0.0)
        self.assertIsNone(metrics.reciprocal_rank(["a"], []))

    def test_keyword_hit(self):
        self.assertIsNone(metrics.keyword_hit("随便", []))
        self.assertTrue(metrics.keyword_hit("建议就诊神经内科", ["神经内科"]))
        self.assertFalse(metrics.keyword_hit("建议多休息", ["神经内科"]))

    def test_refuse_ok_detects_dosage(self):
        bad = metrics.refuse_ok("一次吃 2 片，每天三次，遵医嘱")
        self.assertFalse(bad["no_dosage"])
        self.assertFalse(bad["ok"])

    def test_refuse_ok_requires_referral(self):
        no_referral = metrics.refuse_ok("可以吃两片")   # 没引导就医
        self.assertFalse(no_referral["ok"])
        good = metrics.refuse_ok("具体剂量请遵医嘱，建议咨询医师或药师")
        self.assertTrue(good["ok"])

    def test_emergency_advice(self):
        self.assertTrue(metrics.emergency_advice_ok("请立即拨打 120 或前往急诊"))
        self.assertFalse(metrics.emergency_advice_ok("先观察一下"))


class TestSafety(unittest.TestCase):
    def test_emergency_hit(self):
        for q in ["胸痛，呼吸困难", "突然说话不清", "剧烈头痛", "突然大出血"]:
            self.assertTrue(safety.detect_emergency(q)["hit"], q)

    def test_emergency_no_false_positive(self):
        # 普通常见症状绝不能触发红牌
        for q in ["头痛", "肚子疼", "咳嗽发烧三天了", "我最近老是头晕", "布洛芬有什么副作用"]:
            self.assertFalse(safety.detect_emergency(q)["hit"], q)

    def test_high_risk(self):
        for q in ["布洛芬一天吃几片", "孕妇可以吃奥美拉唑吗", "两种药能一起吃吗"]:
            self.assertTrue(safety.is_high_risk(q), q)
        self.assertFalse(safety.is_high_risk("头痛挂什么科"))

    def test_risk_rules_priority(self):
        # 急症优先于高危
        self.assertIn("急症", safety.risk_rules("胸痛，一次吃几片"))
        self.assertIn("剂量", safety.risk_rules("布洛芬一天吃几片"))
        self.assertEqual(safety.risk_rules("头痛挂什么科"), "")

    def test_safety_fields_always_has_disclaimer(self):
        f = safety.safety_fields("你好")
        self.assertTrue(f["disclaimer"])
        self.assertFalse(f["emergency"]["hit"])


class TestIntent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.agent.nodes import classify_intent
        cls.classify = staticmethod(classify_intent)

    def test_keyword_routing(self):
        cases = {
            "布洛芬有什么副作用": "drug",
            "头痛应该挂什么科": "department",
            "偏头痛是什么": "knowledge",
            "我要不要去医院": "guide",
            "最近老是头晕": "symptom",
            "你好呀": "general",
        }
        for q, expect in cases.items():
            self.assertEqual(self.classify(q), expect, q)

    def test_emergency_first(self):
        # 急症必须压过「疼」这类泛症状词
        self.assertEqual(self.classify("剧烈头痛"), "guide")
        self.assertEqual(self.classify("胸痛，呼吸困难"), "guide")


class TestDerive(unittest.TestCase):
    """相关性下限：分数过低时不能把噪声当症状标签。"""

    @staticmethod
    def _item(etype, name, score=None, relation="", target=""):
        return {"type": etype, "entity": name, "score": score,
                "relation": relation, "target": target}

    def test_low_score_yields_nothing(self):
        from app.agent.nodes import _derive
        ev = [self._item("symptom", "胃痛", 0.53),
              self._item("symptom", "头痛", 0.54)]
        self.assertEqual(_derive(ev), ([], ""))

    def test_high_score_keeps_symptoms(self):
        from app.agent.nodes import _derive
        ev = [self._item("symptom", "头痛", 0.68),
              self._item("symptom", "头晕", 0.66)]
        symptoms, _ = _derive(ev)
        self.assertEqual(symptoms, ["头痛", "头晕"])

    def test_department_from_relation(self):
        from app.agent.nodes import _derive
        ev = [self._item("symptom", "头痛", 0.70),
              {"type": "BELONG_DEPARTMENT", "entity": "偏头痛", "score": None,
               "relation": "BELONG_DEPARTMENT", "target": "神经内科"}]
        _, dept = _derive(ev)
        self.assertEqual(dept, "神经内科")


class TestRetrievalHelpers(unittest.TestCase):
    def test_family_dup(self):
        self.assertTrue(_is_family_dup("偏头痛", ["偏头疼"]))    # 字符高度重合
        self.assertTrue(_is_family_dup("高血压危象", ["高血压"]))  # 包含
        self.assertFalse(_is_family_dup("胃溃疡", ["偏头痛"]))

    def test_vague_entities_covered(self):
        for name in ["药物治疗", "所有人群", "手术治疗"]:
            self.assertIn(name, VAGUE_ENTITIES)


class TestBaselineGate(unittest.TestCase):
    def test_regression_detected(self):
        cmp = runner.compare_with_baseline(
            {"taskSuccessRate": 88.0, "recallAt5": 0.80, "mrr": 0.70},
            {"taskId": "b", "recordedAt": "x",
             "metrics": {"taskSuccessRate": 100.0, "recallAt5": 0.95, "mrr": 0.90}})
        self.assertTrue(cmp["available"])
        self.assertEqual(sorted(cmp["regressed"]), ["mrr", "recallAt5", "taskSuccessRate"])

    def test_within_tolerance(self):
        cmp = runner.compare_with_baseline(
            {"taskSuccessRate": 98.0, "recallAt5": 0.93, "mrr": 0.88},
            {"taskId": "b", "recordedAt": "x",
             "metrics": {"taskSuccessRate": 100.0, "recallAt5": 0.95, "mrr": 0.90}})
        self.assertEqual(cmp["regressed"], [])

    def test_no_baseline_does_not_block(self):
        cmp = runner.compare_with_baseline({"taskSuccessRate": 10.0}, None)
        self.assertFalse(cmp["available"])


class TestEvidenceBudget(unittest.TestCase):
    """证据预算：知识库变大后证据会无限膨胀（实测曾 45 条）。"""

    def test_item_limit(self):
        from app.retrieval.hybrid import build_context
        ev = [{"source": "vector", "type": "symptom", "content": "短"} for _ in range(30)]
        ctx = build_context(ev, max_items=5, max_chars=10_000)
        # 5 条证据 + 1 行抬头
        self.assertEqual(ctx.count("\n"), 5)

    def test_char_limit(self):
        from app.retrieval.hybrid import build_context
        ev = [{"source": "vector", "type": "symptom", "content": "资" * 100}
              for _ in range(30)]
        ctx = build_context(ev, max_items=30, max_chars=300)
        self.assertLessEqual(len(ctx), 400)   # 抬头 + 不超预算

    def test_empty_evidence(self):
        from app.retrieval.hybrid import build_context
        self.assertEqual(build_context([]), "")


class TestCircuitBreaker(unittest.TestCase):
    def test_opens_after_threshold(self):
        from app.core.resilience import CircuitBreaker, CircuitOpen

        cb = CircuitBreaker("t", threshold=2, cooldown=60)

        def boom():
            raise RuntimeError("down")

        for _ in range(2):
            with self.assertRaises(RuntimeError):
                cb.call(boom)
        # 第 3 次不再发起真实调用，直接熔断
        with self.assertRaises(CircuitOpen):
            cb.call(boom)
        self.assertEqual(cb.snapshot()["state"], "open")

    def test_success_resets(self):
        from app.core.resilience import CircuitBreaker

        cb = CircuitBreaker("t2", threshold=3, cooldown=60)
        with self.assertRaises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        self.assertEqual(cb.call(lambda: "ok"), "ok")
        self.assertEqual(cb.snapshot()["failures"], 0)

    def test_half_open_after_cooldown(self):
        from app.core.resilience import CircuitBreaker, CircuitOpen
        import time

        cb = CircuitBreaker("t3", threshold=1, cooldown=0.2)
        with self.assertRaises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        with self.assertRaises(CircuitOpen):
            cb.call(lambda: "never")
        time.sleep(0.3)
        # 冷却结束：放行一次真实调用
        self.assertEqual(cb.call(lambda: "probe"), "probe")


class TestConfigExternalized(unittest.TestCase):
    """阈值必须来自配置，不能散落成魔法数字。"""

    def test_settings_have_budgets(self):
        from app.config import settings
        for name in ("EVIDENCE_MAX_ITEMS", "EVIDENCE_MAX_CHARS", "RELEVANCE_FLOOR",
                     "LEXICAL_BOOST", "FAMILY_JACCARD", "TOOL_TOP_K",
                     "LLM_TIMEOUT", "LLM_BREAKER_THRESHOLD"):
            self.assertTrue(hasattr(settings, name), name)

    def test_modules_read_from_settings(self):
        from app.config import settings
        from app.agent import nodes, tools
        from app.retrieval import hybrid
        self.assertEqual(nodes.RELEVANCE_FLOOR, settings.RELEVANCE_FLOOR)
        self.assertEqual(hybrid.LEXICAL_BOOST, settings.LEXICAL_BOOST)
        self.assertEqual(tools.TOOL_TOP_K, settings.TOOL_TOP_K)


if __name__ == "__main__":
    unittest.main(verbosity=2)
