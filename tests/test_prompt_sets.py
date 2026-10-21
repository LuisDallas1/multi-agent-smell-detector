"""Selecao e integridade dos conjuntos de prompts, sem credenciais ou LLMs."""
import hashlib
from pathlib import Path
import sys
import unittest
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
sys.path.insert(0, str(BASE / 'scripts'))
from core.supervisor.agent_config import PROMPT_TYPES, get_agent_configs
import run_experiment

# Hashes do original afb065c, alterando somente 120 -> 80 em Long statement.
EXPECTED = {'simple_estevam': '9c9f616801e2e9627d1b76c41c37dcd64596b0f80aa7f9c18d413d0cef53fffa', 'complete_estevam': 'e7a1612da9be5e4fca8e5f625918bb80bc704cc055b2cbd901ac770449531a29'}

class PromptSetTests(unittest.TestCase):
    def test_original_sets_preserve_instructions_except_thresholds(self):
        for group, expected in EXPECTED.items():
            digest = hashlib.sha256()
            paths = sorted((BASE / 'src/core/prompts' / group).glob('*_prompt.py'))
            self.assertEqual(len(paths), 11)
            for path in paths:
                digest.update(path.name.encode())
                digest.update(path.read_text(encoding='utf-8').replace('\r\n', '\n').encode())
            self.assertEqual(digest.hexdigest(), expected, group)

    def test_three_sets_use_same_specialists_and_schemas(self):
        sets = [get_agent_configs(group) for group in PROMPT_TYPES]
        self.assertEqual(len(sets), 3)
        for configs in sets:
            self.assertEqual(len(configs), 11)
            self.assertEqual(list(configs), list(sets[0]))
            for name, config in configs.items():
                self.assertIs(config['schema'], sets[0][name]['schema'])
                self.assertTrue(config['prompt'])
        self.assertNotEqual(sets[1]['magic_number']['prompt'], sets[2]['magic_number']['prompt'])

    def test_unknown_set_is_rejected(self):
        with self.assertRaises(ValueError):
            get_agent_configs('typo')

    def test_runner_accepts_all_sets_and_preserves_default(self):
        self.assertEqual(run_experiment.parser().parse_args([]).prompt_type, 'complete_v2')
        for group in (*PROMPT_TYPES, 'all'):
            self.assertEqual(run_experiment.parser().parse_args(['--prompt-type', group]).prompt_type, group)
