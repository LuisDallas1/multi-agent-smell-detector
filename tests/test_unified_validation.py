"""Plano unificado e preservação de consumo parcial, sem rede ou inferência."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import run_experiment
import run_validation
from generation_protocol import validate_controlled_limits


class UnifiedValidationTests(unittest.TestCase):
    def test_unified_commands_use_same_models_files_strategies_and_one_retry(self):
        for architecture, budget in [('multiagent', 8192), ('single', 32768)]:
            cmd = run_validation.command(architecture, Path('dataset'), Path('manifest.json'))
            args = run_experiment.parser().parse_args(cmd[4:])
            validate_controlled_limits(args)
            self.assertEqual(args.models, run_validation.MODELS)
            self.assertEqual(args.files_from, Path('manifest.json'))
            self.assertEqual(args.prompt_type, 'paired')
            self.assertEqual(args.generation_profile, 'experiment')
            self.assertEqual(args.response_retries, 1)
            self.assertEqual(args.max_tokens, budget)

    def test_source_inventory_excludes_credentials(self):
        inventory = run_experiment.source_snapshots()['source_files']
        self.assertIn('src/core/execution/engine.py', inventory)
        self.assertIn('src/core/single_agent/prompts/builder.py', inventory)
        self.assertTrue(all('.env' not in Path(p).name for p in inventory))

    def test_partial_summary_cost_preserved_without_completed_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            child = output / 'single'
            child.mkdir()
            (child / 'summary.json').write_text(json.dumps([
                dict(known_cost_usd=0.012, cost_complete=False)]))
            report = run_validation.collect(output)
            self.assertEqual(report['known_cost_usd'], 0.012)
            self.assertFalse(report['cost_complete'])
            self.assertIsNone(report['total_cost_usd'])
            self.assertFalse(report['all_tasks_valid'])


if __name__ == '__main__':
    unittest.main()
