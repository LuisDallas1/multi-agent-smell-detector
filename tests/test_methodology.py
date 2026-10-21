"""Regressoes do protocolo sem carregar settings, .env ou servicos externos."""
import ast
import asyncio
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Dict, List
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
sys.path.insert(0, str(BASE / 'scripts'))
from core.schemas import agent_response as schemas
from core.smell_rules import THRESHOLDS
from core.utils.detection_validator import DetectionValidator
from evaluate_results import save_reference, evaluate_run

MODELS = {
    'complex method': (schemas.ComplexMethodDetection, 'cyclomatic_complexity'),
    'complex conditional': (schemas.ComplexConditionalDetection, 'logical_operators'),
    'long method': (schemas.LongMethodDetection, 'total_lines'),
    'long parameter list': (schemas.LongParameterListDetection, 'parameter_count'),
    'long statement': (schemas.LongStatementDetection, 'line_length'),
    'long identifier': (schemas.LongIdentifierDetection, 'length'),
    'long lambda function': (schemas.LongLambdaFunctionDetection, 'lambda_length'),
    'long message chain': (schemas.LongMessageChainDetection, 'chain_length'),
}


class MethodologyTests(unittest.TestCase):
    def test_numeric_boundaries_and_model_cannot_override_threshold(self):
        for smell, (schema, field) in MODELS.items():
            limit = THRESHOLDS[smell]
            self.assertEqual(schema().threshold, limit)
            with self.subTest(smell=smell):
                self.assertFalse(DetectionValidator.validate_detection(dict(Smell=smell, **{field:limit}, threshold=0)))
                self.assertTrue(DetectionValidator.validate_detection(dict(Smell=smell, **{field:limit+1}, threshold=999)))

    def test_magic_number_only_three_exceptions_and_keeps_pydantic_value(self):
        for number in (0, 1, -1, 0.0, 1.0, -1.0):
            self.assertFalse(DetectionValidator.validate_detection(dict(Smell='Magic number', number=number)))
        for number in (2, -2, 10, 100, .7, 9.81):
            prediction = schemas.MagicNumberDetection(number=number).model_dump()
            self.assertTrue(DetectionValidator.validate_detection(prediction))
            self.assertEqual(prediction['number'], number)
        self.assertFalse(DetectionValidator.validate_detection(dict(Smell='Magic number', number=float('inf'))))

    def test_prompts_match_rules_and_include_original_response_contract(self):
        for folder in ('prompts/complete_v2',):
            paths = list((BASE / 'src/core' / folder).glob('*_prompt.py'))
            self.assertEqual(len(paths), 11)
            for path in paths:
                tree = ast.parse(path.read_text(encoding='utf-8'))
                text = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)))
                smell = path.stem.removesuffix('_prompt').replace('_', ' ')
                with self.subTest(folder=folder, smell=smell):
                    self.assertNotIn('120', text)
                    self.assertNotIn('ximo 10', text)
                    self.assertIn('detections', text)
                    self.assertIn('Line_no', text)
                    if smell in MODELS:
                        self.assertIn(MODELS[smell][1], text)
                        self.assertIn(f'threshold={THRESHOLDS[smell]}', text)
                    if smell == 'long identifier':
                        self.assertIn('identifier_name', text)
                    if smell == 'magic number':
                        self.assertIn('number', text)
                    for block in re.findall(r'```json\s*(.*?)```', text, re.S):
                        envelope = json.loads(block)
                        self.assertIsInstance(envelope['detections'], list)

    def test_measurable_examples_are_real_code(self):
        for stem, field, expected in [('long_method', 'total_lines', 70),
                                      ('long_statement', 'line_length', 83),
                                      ('long_lambda_function', 'lambda_length', 83)]:
            path = BASE / 'src/core/prompts/complete_v2' / (stem+'_prompt.py')
            tree = ast.parse(path.read_text(encoding='utf-8'))
            text = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)))
            code = re.search(r'```python\n(.*?)```', text, re.S).group(1).rstrip('\n')
            node = ast.parse(code)
            item = json.loads(re.search(r'```json\s*(.*?)```', text, re.S).group(1))['detections'][0]
            if stem == 'long_method':
                measured = node.body[0].end_lineno - node.body[0].lineno + 1
            elif stem == 'long_statement':
                measured = len(code)
            else:
                measured = len(ast.get_source_segment(code, node.body[0].value))
            self.assertEqual(measured, expected)
            self.assertEqual(item[field], expected)

    def test_langchain_json_mode_still_returns_pydantic_detections(self):
        class FakeCallback:
            token_usage = dict(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        class FakeModel:
            def with_structured_output(self, schema, method):
                self.schema, self.method = schema, method
                return self
            async def ainvoke(self, messages, config):
                return self.schema.model_validate(dict(detected=True, detections=[dict(
                    Method='', Line_no='1', Description='Statement with 81 characters.', line_length=81)]))
        path = BASE / 'src/core/supervisor/supervisor.py'
        node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n, ast.ClassDef))
        logger = SimpleNamespace(info=lambda *a:None, error=lambda *a,**k:None, warning=lambda *a:None)
        ns = dict(Any=Any, Dict=Dict, List=List, TokenUsageCallback=FakeCallback, logger=logger,
                  LangChainException=type('DummyLangChainException', (Exception,), {}))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
        supervisor = ns['CodeSmellSupervisor'].__new__(ns['CodeSmellSupervisor'])
        supervisor.model = FakeModel()
        supervisor.agent_errors = {}
        task = supervisor._call_agent_inner('long_statement', dict(schema=schemas.MultipleLongStatementResponse,
                                                                  prompt='Detect statements'), 'x = 1')
        try:
            task.send(None)
        except StopIteration as done:
            detections, usage = done.value
        self.assertEqual(supervisor.model.method, 'json_mode')
        self.assertIsInstance(detections[0], schemas.LongStatementDetection)
        self.assertEqual(usage['total_tokens'], 15)

    def test_frozen_reference_and_duplicate_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, run = root/'dataset', root/'run'
            dataset.mkdir()
            run.mkdir()
            code = dataset/'x.py'
            code.write_text('def f(a,b,c,d,e):\n    pass\n', encoding='utf-8')
            files = [dict(File='x.py', sha256=hashlib.sha256(code.read_bytes()).hexdigest())]
            pairs, truths = root/'pairs.csv', root/'truth.csv'
            pairs.write_text('File,Smell,Count\nx.py,long parameter list,1\nx.py,magic number,0\n', encoding='utf-8')
            truths.write_text('File,Smell,Line no,Method,Description\nx.py,Long parameter list,1,f,f has 5 parameters.\n', encoding='utf-8')
            save_reference(run, dataset, files, pairs, truths)
            (run/'sample.json').write_text(json.dumps(dict(dataset=str(dataset), files=files)), encoding='utf-8')
            output = run/'model/complete'
            output.mkdir(parents=True)
            prediction = dict(File='x.py', Smell='Long parameter list', Method='f', Line_no='1', parameter_count=5)
            (output/'results_complete_prompts.json').write_text(json.dumps([prediction, prediction]), encoding='utf-8')
            (output/'file_metrics_complete_prompts.json').write_text('[{}]', encoding='utf-8')
            truths.write_text('source changed after inference', encoding='utf-8')
            with redirect_stdout(io.StringIO()):
                result = evaluate_run(run)['results'][0]['occurrence']
            self.assertEqual((result['tp'], result['fp'], result['fn']), (1, 1, 0))
            (run/'evaluation_reference.csv').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'alterado'):
                evaluate_run(run)

    def test_runner_saves_scope_and_computes_f1_automatically(self):
        import run_experiment as runner
        class FakeSupervisor:
            def __init__(self, **kwargs):
                self.agent_configs = {'long_parameter_list': {'prompt': 'fixed'}}
            async def analyze_code(self, code, path, project):
                prediction = schemas.LongParameterListDetection(
                    Method='f', Line_no=1, File=path, Description='f has five parameters.', parameter_count=5)
                return dict(code_smells=[prediction.model_dump()], token_usage={}, agent_errors={})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root/'dataset'
            dataset.mkdir()
            code = dataset/'x.py'
            code.write_text('def f(a,b,c,d,e):\n    pass\n', encoding='utf-8')
            files = [dict(File='x.py', sha256=hashlib.sha256(code.read_bytes()).hexdigest())]
            pairs, truths = root/'pairs.csv', root/'truth.csv'
            pairs.write_text('File,Smell,Count\nx.py,long parameter list,1\n', encoding='utf-8')
            truths.write_text('File,Smell,Line no,Method,Description\nx.py,Long parameter list,1,f,f has 5 parameters.\n', encoding='utf-8')
            args = runner.parser().parse_args(['--dataset', str(dataset), '--evaluation-pairs', str(pairs),
                                               '--ground-truth', str(truths)])
            args.evaluate = True
            run = root/'run'
            task = runner.execute(args, files, ['fake'], ['complete'], run, factory=FakeSupervisor)
            with redirect_stdout(io.StringIO()):
                try:
                    task.send(None)
                except StopIteration:
                    pass
                else:
                    self.fail('Teste simulado nao deve fazer I/O assincrono')
            evaluation = json.loads((run/'evaluation_summary.json').read_text(encoding='utf-8'))
            self.assertEqual(evaluation['results'][0]['occurrence']['f1'], 1)
            self.assertTrue((run/'evaluation_reference.csv').is_file())
            self.assertTrue((run/'protocol.json').is_file())


if __name__ == '__main__':
    unittest.main()
