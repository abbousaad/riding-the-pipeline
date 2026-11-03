import unittest

import analysis_core as analysis


class AnalysisTests(unittest.TestCase):
    def rows(self, split, count):
        return [{"task_id": f"{split}-{i}", "split": split, "arm": "clean", "value": [1., 0.]}
                for i in range(count)]

    def test_embedding_chunks_preserve_all_tokens(self):
        seen = []
        def encode(tokens):
            self.assertLessEqual(len(tokens) + 2, 256)
            seen.extend(tokens)
            return [1., 0.]
        trace = {"responses": [{"phase": "test", "actor": "model", "parse_error": None,
                                "explanation": "visible text", "thinking": "ignore"}]}
        result = analysis.explanation_feature(trace, "test", lambda _: list(range(600)), encode)
        self.assertEqual(seen, list(range(600)))
        self.assertEqual(result, {"value": [1., 0.], "eligible_responses": 1, "content_tokens": 600, "chunks": 3})

    def test_extraction_ignores_scripts_malformed_and_empty_text(self):
        trace = {"responses": [
            {"phase": "test", "actor": "scripted_compromised", "explanation": "exclude"},
            {"phase": "test", "actor": "model", "parse_error": "invalid", "explanation": "exclude"},
            {"phase": "test", "actor": "model", "explanation": "  "},
            {"phase": "build", "actor": "model", "explanation": "exclude"}]}
        result = analysis.explanation_feature(trace, "test", lambda _: self.fail("unexpected tokenizer"), None)
        self.assertIsNone(result["value"])
        self.assertEqual(result["eligible_responses"], 0)

    def test_embedding_response_weight_is_not_length_weight(self):
        trace = {"responses": [{"phase": "test", "actor": "model", "explanation": text}
                               for text in ("short", "long")]}
        result = analysis.explanation_feature(trace, "test", lambda t: [t] * (1 if t == "short" else 300),
                                              lambda tokens: [1., 0.] if tokens[0] == "short" else [0., 1.])
        self.assertAlmostEqual(result["value"][0], result["value"][1])

    def test_auc_ties_and_missing_classes(self):
        self.assertEqual(analysis.auc([1, 1], [1]), .5)
        self.assertEqual(analysis.auc([2], [1]), 1.)
        self.assertIsNone(analysis.auc([None], [1]))

    def test_unknowns_remain_in_bounds(self):
        self.assertEqual(analysis.bounds([True, False, None]),
                         {"planned": 3, "positives": 1, "negatives": 1, "unknowns": 1,
                          "lower": 1 / 3, "upper": 2 / 3})

    def test_reference_and_calibration_do_not_access_evaluation(self):
        with self.assertRaises(ValueError):
            analysis.fit_reference(self.rows("evaluation", 12))
        model = analysis.fit_reference(self.rows("reference", 12))
        with self.assertRaises(ValueError):
            analysis.calibrate(model, self.rows("evaluation", 24))

    def test_missing_reference_or_calibration_makes_detector_unavailable(self):
        self.assertIsNone(analysis.fit_reference(self.rows("reference", 11)))
        model = analysis.fit_reference(self.rows("reference", 12))
        rows = self.rows("calibration", 24)
        rows[0]["value"] = None
        self.assertIsNone(analysis.calibrate(model, rows))

    def test_calibration_ties_do_not_alert(self):
        model = analysis.fit_reference(self.rows("reference", 12))
        calibration = analysis.calibrate(model, self.rows("calibration", 24))
        self.assertEqual(calibration["threshold"], 0.)
        self.assertFalse(analysis.alert(0., calibration))
        self.assertTrue(analysis.alert(.01, calibration))

    def test_action_js_retains_denied_unknown_names(self):
        trace = {"events": [{"phase": "test", "action": {"name": "unknown"}, "executed": False}]}
        value = analysis.action_feature(trace, "test")
        self.assertEqual(value, {"unknown": 1.})
        self.assertEqual(analysis.js(value, {"read_source": 1.}), 1.)
        self.assertIsNone(analysis.action_feature(trace, "deploy"))

    def test_family_bootstrap_keeps_paired_rows(self):
        rows = [{"family": f, "split": "evaluation", "arm": a, "value": 1}
                for f in ("a", "b", "c", "d", "e", "f") for a in ("clean", "attack")]
        def statistic(sample):
            self.assertEqual(sum(r["arm"] == "clean" for r in sample), 6)
            self.assertEqual(sum(r["arm"] == "attack" for r in sample), 6)
            return 1.
        result = analysis.family_bootstrap(rows, statistic, list("abcdef"), replicates=50)
        self.assertEqual(result["interval"], [1., 1.])
        self.assertIsNone(analysis.family_bootstrap(rows, lambda _: None, list("abcdef"), replicates=5)["interval"])


if __name__ == "__main__":
    unittest.main()
