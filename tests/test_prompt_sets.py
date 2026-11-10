"""Selecao e integridade dos conjuntos de prompts, sem credenciais ou LLMs."""
import ast
import json
import re
from pathlib import Path
import sys
import unittest
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
sys.path.insert(0, str(BASE / 'scripts'))
from core.supervisor.agent_config import PROMPT_TYPES, get_agent_configs
import run_experiment

class PromptSetTests(unittest.TestCase):
    def test_chain_rules_are_unambiguous_and_shared_with_single(self):
        from core.single_agent.prompts import build_prompt
        rules = {}
        for group in PROMPT_TYPES:
            configs = get_agent_configs(group)
            single = build_prompt(group)
            self.assertNotIn('DPy', single)
            self.assertNotIn('1.7.8', single)
            for agent in ('long_message_chain', 'long_statement'):
                prompt = configs[agent]['prompt']
                rule = prompt.split('\n')[1] if group == 'simple_v2' else prompt.split('DEFINICAO:\n')[1].split('\n')[0]
                if agent in rules:
                    self.assertEqual(rule, rules[agent])
                rules[agent] = rule
                self.assertIn(configs[agent]['prompt'], single)
            chain = configs['long_message_chain']['prompt']
            self.assertIn('self.a.b não qualifica; self.a.b.c qualifica', chain)
            self.assertIn('nem seus prefixos', chain)
            self.assertIn('argumentos nomeados', chain)
            self.assertNotIn('conte somente obj.a (2)', chain)
            statement = configs['long_statement']['prompt']
            self.assertIn('assinaturas de def/async def', statement)
            self.assertIn('de if no módulo podem qualificar', statement)
            self.assertNotIn('imports globais', statement)

    def test_numeric_examples_agree_with_the_code_shown(self):
        configs = get_agent_configs('complete_v2')
        prompt = configs['long_identifier']['prompt']
        for name, count in re.findall(r'^(\w+) = .*?# (\d+) chars', prompt, re.M):
            self.assertEqual(len(name), int(count), name)
        for group, field in [('long_lambda_function', 'lambda_length'),
                             ('long_method', 'total_lines'),
                             ('long_parameter_list', 'parameter_count'),
                             ('complex_method', 'cyclomatic_complexity')]:
            prompt = configs[group]['prompt']
            code = re.search(r'```python\n(.*?)```', prompt, re.S).group(1)
            item = json.loads(re.search(r'```json\n(.*?)```', prompt, re.S).group(1))['detections'][0]
            tree = ast.parse(code)
            if group == 'long_lambda_function':
                node = next(n for n in ast.walk(tree) if isinstance(n, ast.Lambda))
                measure = len(ast.get_source_segment(code, node))
            else:
                node = tree.body[0]
                if group == 'long_method':
                    measure = node.end_lineno - node.lineno + 1
                elif group == 'long_parameter_list':
                    measure = len([a for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                                   if a.arg not in {'self', 'cls'}])
                else:
                    measure = 1 + sum(isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler))
                                      for n in ast.walk(node))
                    measure += sum(len(n.values) - 1 for n in ast.walk(node) if isinstance(n, ast.BoolOp))
            self.assertGreater(measure, {'long_lambda_function':80,'long_method':67,
                                        'long_parameter_list':4,'complex_method':7}[group], group)
            self.assertNotIn(field, item)

    def test_simple_prompts_are_compact_and_have_explicit_contract(self):
        for name, config in get_agent_configs('simple_v2').items():
            prompt = config['prompt']
            self.assertLess(len(prompt), 1800, name)
            self.assertNotIn('```', prompt, name)
            self.assertIn('todas as ocorrências', prompt, name)
            self.assertIn('"detected":false,"detections":[]', prompt, name)
            self.assertIn('Line_no (número positivo como string)', prompt, name)
            if name in {'long_method', 'complex_method'}:
                self.assertIn('Line_no é a linha do def/async def', prompt, name)

    def test_two_sets_use_same_specialists_and_schemas(self):
        sets = [get_agent_configs(group) for group in PROMPT_TYPES]
        self.assertEqual(len(sets), 2)
        for configs in sets:
            self.assertEqual(len(configs), 11)
            self.assertEqual(list(configs), list(sets[0]))
            for name, config in configs.items():
                self.assertIs(config['schema'], sets[0][name]['schema'])
                self.assertTrue(config['prompt'])
        self.assertNotEqual(sets[0]['magic_number']['prompt'], sets[1]['magic_number']['prompt'])

    def test_unknown_set_is_rejected(self):
        with self.assertRaises(ValueError):
            get_agent_configs('typo')

    def test_runner_accepts_all_sets_and_preserves_default(self):
        self.assertEqual(run_experiment.parser().parse_args([]).prompt_type, 'complete_v2')
        for group in (*PROMPT_TYPES, 'all'):
            self.assertEqual(run_experiment.parser().parse_args(['--prompt-type', group]).prompt_type, group)
