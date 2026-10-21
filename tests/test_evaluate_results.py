import ast
from collections import defaultdict
import importlib.util
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
from evaluate_results import normalize, count_metrics
from experiment_evaluation import Reference


class EvaluationTests(unittest.TestCase):
    def reference(self, truths):
        ref = Reference.__new__(Reference)
        ref.rows = defaultdict(list)
        for row in truths:
            ref.rows[('x.py', row['Smell'].lower())].append(row)
        tree = ast.parse('a = 7\nb = 7\n')
        ref.contexts = {'x.py': (tree, {}, [])}
        return ref

    def test_wrong_occurrence_is_not_a_true_positive_by_equal_count(self):
        truth = dict(File='x.py', Smell='Magic number', **{'Line no': '1'}, Description='Magic number 7 used here.')
        prediction = dict(rel='x.py', smell_key='magic number', Line_no=2, number=7)
        sample = {'x.py': {'magic number': 1}}
        ev = self.reference([truth]).evaluate([prediction], sample)
        self.assertEqual((ev['tp'], ev['fp'], ev['fn']), (0, 1, 1))
        self.assertEqual(count_metrics([prediction], sample)['tp'], 1)

    def test_negative_is_false_positive_and_unselected_pair_is_not_evaluated(self):
        predictions = [dict(rel='x.py', smell_key=s, Line_no=1) for s in ('magic number', 'long method')]
        ev = self.reference([]).evaluate(predictions, {'x.py': {'magic number': 0}})
        self.assertEqual(ev['fp'], 1)
        self.assertEqual(ev['out_of_scope'], 1)

    def test_normalization_uses_only_predicted_fields_and_unambiguous_file(self):
        prediction = dict(File='E:/root/x.py', Smell='Long method', **{'Line no': ''}, start_line=12)
        item, notes = normalize(prediction, ['x.py'])
        self.assertEqual(item['Line_no'], 12)
        self.assertTrue(notes)
        with self.assertRaises(ValueError):
            normalize(dict(File='outside.py'), ['x.py'])
        item, _ = normalize(dict(File='x.py', Smell='Magic number', **{'Line no': '2'},
                                 Description='Magic number 0.7 used here.'), ['x.py'])
        self.assertEqual(item['number'], .7)


if __name__ == '__main__':
    unittest.main()
