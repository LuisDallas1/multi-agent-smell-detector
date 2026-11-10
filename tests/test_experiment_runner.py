import ast
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('run_experiment', BASE / 'scripts/run_experiment.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setup_dataset(self, directory):
        root = Path(directory) / 'dataset'
        root.mkdir()
        for i in range(9):
            (root / f'f{i}.py').write_text(f'value = {i}\n', encoding='utf-8')
        (root / 'ground_truth').mkdir()
        (root / 'ground_truth/ignored.py').write_text('pass', encoding='utf-8')
        return root

    def test_default_limit_seed_and_ground_truth_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_dataset(directory)
            args = runner.parser().parse_args(['--dataset', str(root)])
            first = runner.select_files(args)
            self.assertEqual(len(first), 5)
            self.assertEqual(first, runner.select_files(args))
            self.assertTrue(all('ground_truth' not in r['File'] for r in first))
            args.all_files = True
            self.assertEqual(len(runner.select_files(args)), 9)

    def test_selection_accepts_legacy_hashes_without_content_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_dataset(directory)
            args = runner.parser().parse_args(['--dataset', str(root), '--n', '2'])
            selected = runner.select_files(args)
            manifest = Path(directory) / 'sample.json'
            runner.write_json(manifest, dict(files=selected))
            args.files_from = manifest
            self.assertEqual(runner.select_files(args), selected)
            (root / selected[0]['File']).write_text('changed = True', encoding='utf-8')
            legacy = dict(files=[dict(row, sha256='obsolete') for row in selected])
            runner.write_json(manifest, legacy)
            current = runner.select_files(args)
            self.assertEqual([r['File'] for r in current], [r['File'] for r in selected])
            self.assertTrue(all('sha256' not in r for r in current))

    def test_manifest_cannot_escape_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_dataset(directory)
            manifest = Path(directory) / 'files.json'
            runner.write_json(manifest, ['../outside.py'])
            args = runner.parser().parse_args(['--dataset', str(root), '--files-from', str(manifest)])
            with self.assertRaisesRegex(ValueError, 'fora do dataset'):
                runner.select_files(args)

    def test_original_supervisor_uses_supplied_model_and_transport_limits(self):
        import asyncio
        from typing import Any, Dict, List
        path = BASE / 'src/core/execution/engine.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DetectionEngine')
        recorded = {}
        def fake_model(**kwargs):
            recorded.update(kwargs)
            return object()
        ns = dict(asyncio=asyncio, Any=Any, Dict=Dict, List=List, ChatOpenAI=fake_model,
                  get_agent_configs=lambda kind: {}, settings=SimpleNamespace(
                      OPENROUTER_API_KEY='dummy', OPENROUTER_BASE_URL='https://example.invalid',
                      OPENROUTER_API_MODEL='fallback'))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
        ns['DetectionEngine']._get_agent_configs = lambda self, kind: {}
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules, {'config.settings': SimpleNamespace(settings=ns['settings'])}):
            ns['DetectionEngine'](model_name='chosen/model', max_tokens=1234, max_retries=0,
                                  timeout=17, concurrency=2, reasoning='low', provider='fixed')
        self.assertEqual(recorded['model'], 'chosen/model')
        self.assertEqual(recorded['api_key'], 'dummy')
        self.assertEqual(recorded['max_tokens'], 1234)
        self.assertEqual(recorded['max_retries'], 0)
        self.assertEqual(recorded['timeout'], 17)
        self.assertEqual(recorded['extra_body']['provider']['allow_fallbacks'], False)
        self.assertEqual(recorded['extra_body']['provider']['only'], ['fixed'])

    def test_models_and_prompt_variants_share_files_and_preserve_failures(self):
        calls = []
        class FakeSupervisor:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.agent_configs = {'a': {'prompt': 'fixed prompt'}}
            async def analyze_code(self, code, path, project):
                calls.append((self.kwargs['model_name'], self.kwargs['prompt_type'], Path(path).name))
                return dict(code_smells=[], token_usage=dict(prompt_tokens=3, completion_tokens=2, total_tokens=5),
                            agent_errors={'a': 'InvalidJSON'})
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_dataset(directory)
            args = runner.parser().parse_args(['--dataset', str(root), '--n', '2', '--allow-incomplete'])
            files = runner.select_files(args)
            output = Path(directory) / 'results'
            prompt_types = ['simple_v2', 'complete_v2']
            coroutine = runner.execute(args, files, ['one', 'two'], prompt_types, output, factory=FakeSupervisor)
            with redirect_stdout(io.StringIO()):
                try:
                    coroutine.send(None)
                except StopIteration as finished:
                    summaries = finished.value
                else:
                    self.fail('Teste simulado nao deve suspender para I/O')
            self.assertEqual(len(calls), 8)
            expected = [r['File'] for r in files]
            for model in ('one', 'two'):
                for kind in prompt_types:
                    self.assertEqual([file for m,p,file in calls if (m,p)==(model,kind)], expected)
            self.assertEqual(len(summaries), 4)
            self.assertTrue(all(r['agent_failures'] == 2 for r in summaries))
            self.assertTrue(all(r['token_usage']['total_tokens'] == 10 for r in summaries))
            self.assertTrue(all(r['total_cost_usd'] is None for r in summaries))

    def test_supervisor_does_not_hide_unexpected_agent_failure(self):
        from typing import Any, Dict, List
        path = BASE / 'src/core/execution/engine.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DetectionEngine')
        async def gather(*tasks, **kwargs):
            results = []
            for task in tasks:
                try:
                    results.append(await task)
                except Exception as error:
                    results.append(error)
            return results
        ns = dict(Any=Any, Dict=Dict, List=List, asyncio=SimpleNamespace(gather=gather),
                  logger=SimpleNamespace(info=lambda *a: None, error=lambda *a: None))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
        supervisor = ns['DetectionEngine'].__new__(ns['DetectionEngine'])
        supervisor.agent_configs = {'good': {}, 'bad': {}}
        supervisor.agent_errors = {}
        async def call(name, config, code):
            if name == 'bad':
                raise RuntimeError('simulated')
            return ['hit'], dict(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        supervisor._call_agent = call
        supervisor._add_metadata = lambda detections, *a, **kwargs: detections
        task = supervisor._analyze_parallel('pass', 'x.py', 'project')
        try:
            task.send(None)
        except StopIteration as finished:
            detections, usage = finished.value
        self.assertEqual(detections, ['hit'])
        self.assertEqual(supervisor.agent_errors, {'bad': 'RuntimeError'})
        self.assertEqual(usage['total_tokens'], 2)


if __name__ == '__main__':
    unittest.main()
