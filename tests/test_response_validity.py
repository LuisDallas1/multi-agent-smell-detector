"""Falhas de saida e retries deterministas, sem importar settings ou chamar APIs."""
import ast
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Dict, List
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
sys.path.insert(0, str(BASE / 'scripts'))
from core.schemas.agent_response import MultipleLongStatementResponse
from core.utils.token_tracker import TokenUsageCallback
import run_experiment


def supervisor_class():
    path = BASE / 'src/core/execution/engine.py'
    node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n, ast.ClassDef))
    ns = dict(Any=Any, Dict=Dict, List=List, asyncio=asyncio, json=json,
              TokenUsageCallback=TokenUsageCallback,
              logger=SimpleNamespace(warning=lambda *a: None, info=lambda *a: None))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
    return ns['DetectionEngine']


NEGATIVE = {'detected': False, 'detections': []}
POSITIVE = {'detected': True, 'detections': [dict(detected=True, Smell='Long statement', Method='f', Line_no='3', Description='Long statement.', line_length=90, threshold=80)]}


def reply(payload=NEGATIVE, finish='stop', text=None):
    return dict(raw=SimpleNamespace(content=json.dumps(payload) if text is None else text,
                                   response_metadata={'finish_reason': finish}, usage_metadata={}),
                parsed=MultipleLongStatementResponse.model_validate(payload), parsing_error=None)


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.budgets = []
        self.messages = []

    def model_copy(self, update):
        self.budgets.append(update['max_tokens'])
        return self

    def with_structured_output(self, schema, method, include_raw):
        assert schema is MultipleLongStatementResponse
        assert method == 'json_mode' and include_raw
        return self

    async def ainvoke(self, messages, config):
        self.messages.append(messages)
        response = self.responses.pop(0)
        callback = config['callbacks'][0]
        if isinstance(response, Exception):
            await callback.on_llm_error(response)
            raise response
        await callback.on_llm_end(SimpleNamespace(llm_output={'token_usage': {
            'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}}))
        return response


class ResponseValidityTests(unittest.TestCase):
    def make(self, responses, retries=1, cap=16384):
        cls = supervisor_class()
        instance = cls.__new__(cls)
        instance.model = ScriptedModel(responses)
        instance.agent_errors = {}
        instance.agent_metrics = {}
        instance.agent_attempts = {}
        instance.fatal_agent_error = None
        instance._agent_semaphore = asyncio.Semaphore(2)
        instance.initial_max_tokens = 8192
        instance.max_retry_tokens = cap
        instance.response_retries = retries
        return instance

    def call(self, instance, name='long_statement'):
        return asyncio.run(instance._call_agent(name, dict(schema=MultipleLongStatementResponse,
                                                          prompt='Fixed prompt'), 'x = 1'))

    def test_truncated_valid_json_is_discarded_then_recovered_without_merging(self):
        instance = self.make([reply(POSITIVE, finish='length'), reply()])
        detections, usage = self.call(instance)
        self.assertEqual(detections, [])
        self.assertEqual(usage['total_tokens'], 60)
        self.assertEqual(instance.model.budgets, [8192, 16384])
        self.assertEqual(instance.model.messages[0], instance.model.messages[1])
        self.assertEqual(instance.agent_errors, {})
        self.assertTrue(instance.agent_metrics['long_statement']['recovered'])
        self.assertEqual(instance.agent_metrics['long_statement']['attempts'][0]['error'], 'TruncatedResponse')

    def test_partial_json_is_rejected_even_if_parser_returned_pydantic(self):
        instance = self.make([reply(text='{"detected":false,"detections":['), reply(POSITIVE)])
        detections, usage = self.call(instance)
        self.assertEqual(len(detections), 1)
        self.assertEqual(instance.agent_metrics['long_statement']['attempts'][0]['error'], 'InvalidJSON')
        self.assertEqual(instance.model.budgets, [8192, 8192])

    def test_single_truncation_retry_reaches_configured_32k_budget(self):
        instance = self.make([reply(finish='length'), reply()], cap=32768)
        self.call(instance)
        self.assertEqual(instance.model.budgets, [8192, 32768])
        self.assertEqual(instance.model.messages[0], instance.model.messages[1])
        self.assertEqual(instance.agent_errors, {})

    def test_retry_count_and_token_ceiling_are_bounded(self):
        instance = self.make([reply(finish='length')] * 3, retries=2, cap=12000)
        detections, usage = self.call(instance)
        self.assertEqual(detections, [])
        self.assertEqual(usage['total_tokens'], 90)
        self.assertEqual(instance.model.budgets, [8192, 12000, 12000])
        self.assertEqual(instance.agent_errors['long_statement'], 'TruncatedResponse')

    def test_authentication_failure_is_not_retried_and_blocks_pending_agents(self):
        error = type('AuthenticationError', (Exception,), {})('denied')
        instance = self.make([error], retries=2)
        self.call(instance)
        self.call(instance, 'other')
        self.assertEqual(len(instance.model.messages), 1)
        self.assertEqual(instance.agent_errors['other'], 'SkippedAfterAuthenticationFailure')

    def test_valid_negative_is_success_not_failure(self):
        instance = self.make([reply()])
        self.assertEqual(self.call(instance)[0], [])
        self.assertFalse(instance.agent_errors)
        self.assertEqual(len(instance.model.messages), 1)
        self.assertEqual(instance.agent_metrics['long_statement']['attempts'][0]['raw_response_text'],
                         json.dumps(NEGATIVE))

    def test_valid_positive_preserves_original_fields_before_pydantic(self):
        payload = {'detected': True, 'detections': [dict(POSITIVE['detections'][0],
                                                        unrecognized_evidence='preserve for audit')]}
        text = json.dumps(payload, indent=2)
        instance = self.make([reply(text=text)])
        detections, _ = self.call(instance)
        self.assertEqual(len(detections), 1)
        self.assertEqual(instance.agent_metrics['long_statement']['attempts'][0]['raw_response_text'], text)

    def test_nonstop_finish_is_not_accepted_or_retried(self):
        instance = self.make([reply(finish='content_filter')])
        self.call(instance)
        self.assertEqual(instance.agent_errors['long_statement'], 'NonStopFinishReason')
        self.assertEqual(len(instance.model.messages), 1)

    def test_inconsistent_envelope_and_nonfinite_json_are_rejected(self):
        for text in ('{"detected":true,"detections":[]}',
                     '{"detected":false,"detections":[],"x":NaN}'):
            instance = self.make([reply(text=text)], retries=0)
            self.call(instance)
            self.assertIn(instance.agent_errors['long_statement'], {'InvalidJSON', 'InvalidStructuredResponse'})

    def test_sdk_length_exception_preserves_reported_usage(self):
        error = type('LengthFinishReasonError', (Exception,), {})('length limit was reached')
        error.completion = SimpleNamespace(usage={'prompt_tokens': 10, 'completion_tokens': 8192,
                                                 'total_tokens': 8202,
                                                 'completion_tokens_details': {'reasoning_tokens': 8000}})
        instance = self.make([error, reply()])
        self.assertEqual(self.call(instance)[1]['total_tokens'], 8232)
        self.assertTrue(instance.agent_metrics['long_statement']['attempts'][0]['usage_available'])

    def test_cost_missing_zero_and_invalid_are_distinct(self):
        for value, expected in [(None, None), (0, 0.0), (0.012, 0.012), (-1, None), (float('nan'), None), (True, None)]:
            callback = TokenUsageCallback()
            callback.capture_cost({'cost': value})
            self.assertEqual(callback.cost_usd, expected)

    def test_runner_cost_sums_failed_and_successful_attempts(self):
        class FakeSupervisor:
            def __init__(self, **kwargs):
                self.agent_configs = {'a': {'prompt': 'fixed'}}
            async def analyze_code(self, *args):
                return dict(code_smells=[], token_usage={}, agent_errors={}, agent_metrics={
                    'a': {'attempts': [{'cost_usd': 0.01, 'error': 'TruncatedResponse'},
                                       {'cost_usd': 0.02, 'error': None}]}})
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory)/'dataset'
            dataset.mkdir()
            (dataset/'x.py').write_text('x = 1', encoding='utf-8')
            args = run_experiment.parser().parse_args(['--dataset', str(dataset)])
            with redirect_stdout(io.StringIO()):
                result = asyncio.run(run_experiment.execute(args, run_experiment.select_files(args),
                    ['fake'], ['complete_v2'], Path(directory)/'run', factory=FakeSupervisor))
            self.assertAlmostEqual(result[0]['total_cost_usd'], 0.03)
            self.assertTrue(result[0]['cost_complete'])
            self.assertEqual(result[0]['attempted_calls'], 2)

    def test_real_langchain_sdk_and_pydantic_with_mock_http(self):
        import httpx
        from langchain_openai import ChatOpenAI
        requests = []

        async def run():
            def handler(request):
                requests.append(json.loads(request.content))
                return httpx.Response(200, json={
                    'id': 'mock', 'object': 'chat.completion', 'created': 0, 'model': 'mock',
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(NEGATIVE)},
                                 'finish_reason': 'length' if len(requests) == 1 else 'stop'}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30, 'cost': 0.00123},
                })
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                instance = self.make([])
                instance.model = ChatOpenAI(model='mock', api_key='dummy', base_url='https://mock.invalid/v1',
                                            http_async_client=client, max_retries=0, max_tokens=8192,
                                            temperature=None, seed=42)
                result = await instance._call_agent('long_statement',
                    dict(schema=MultipleLongStatementResponse, prompt='Fixed prompt'), 'x = 1')
                self.assertEqual(result[0], [])
                self.assertEqual(result[1]['total_tokens'], 60)
                self.assertEqual([a['cost_usd'] for a in instance.agent_metrics['long_statement']['attempts']], [0.00123, 0.00123])
                self.assertFalse(instance.agent_errors)
        asyncio.run(run())
        self.assertEqual(len(requests), 2)
        self.assertEqual([r.get('max_completion_tokens', r.get('max_tokens')) for r in requests], [8192, 16384])
        self.assertTrue(all(r['response_format'] == {'type': 'json_object'} for r in requests))
        self.assertTrue(all(r['seed'] == 42 and 'temperature' not in r for r in requests))

    def test_lean_schema_preserves_detection_fields_and_original_pydantic(self):
        from core.schemas import agent_response as schemas
        cls = supervisor_class()
        metadata = {'Project', 'Package', 'Module', 'Class', 'File'}
        for name in dir(schemas):
            model = getattr(schemas, name)
            if not name.startswith('Multiple'):
                continue
            before = model.model_json_schema(by_alias=False)
            wire = cls._strict_response_schema(model)['schema']
            self.assertEqual(before, model.model_json_schema(by_alias=False))
            for key, definition in before['$defs'].items():
                if 'Method' not in definition.get('properties', {}):
                    continue
                actual = wire['$defs'][key]
                self.assertEqual(set(actual['properties']), set(definition['properties']) - metadata)
                self.assertEqual(set(actual['required']), set(actual['properties']))
                self.assertTrue({'Smell', 'Method', 'Line_no', 'Description', 'detected'} <= set(actual['properties']))
                self.assertFalse(actual['additionalProperties'])
        payload = {'detected': True, 'detections': [{'Smell': 'Long statement', 'Method': 'f',
            'Line_no': 3, 'Description': 'Long statement.', 'detected': True, 'line_length': 90, 'threshold': 80}]}
        result = MultipleLongStatementResponse.model_validate(payload)
        item = result.detections[0]
        self.assertEqual(item.Line_no, '3')
        self.assertIsNone(item.line_length)
        self.assertEqual(payload['detections'][0]['line_length'], 90)
        self.assertEqual(schemas.LongStatementDetection.model_validate(payload['detections'][0]).line_length, 90)
        self.assertEqual(item.Project, 'Code')
        self.assertEqual(item.File, '')
        self.assertEqual(item.Class, '')

    def test_message_header_has_correct_encoding_and_preserves_source(self):
        cls = supervisor_class()
        instance = cls.__new__(cls)
        code = 'texto = "ação ─"'
        message = instance._build_agent_message('PROMPT ORIGINAL', code)
        self.assertIn('numeração de linhas', message)
        self.assertIn('número da linha à esquerda', message)
        self.assertIn(code, message)
        self.assertTrue(message.startswith('PROMPT ORIGINAL'))
        self.assertNotIn('Ã', message)

    def test_strict_schema_generation_and_rejected_raw_text_with_real_sdk(self):
        import httpx
        from langchain_openai import ChatOpenAI
        requests = []
        async def run():
            def handler(request):
                body = json.loads(request.content)
                requests.append(body)
                schema = body['response_format']['json_schema']
                self.assertTrue(schema['strict'])
                self.assertFalse(schema['schema']['additionalProperties'])
                for definition in schema['schema'].get('$defs', {}).values():
                    if 'properties' in definition:
                        self.assertEqual(set(definition['required']), set(definition['properties']))
                        self.assertFalse(definition['additionalProperties'])
                        self.assertTrue({'Project', 'Package', 'Module', 'Class', 'File'}.isdisjoint(definition['properties']))
                text = '```json\n{"detected":false,"detections":[]}\n```' if len(requests) == 1 else json.dumps(NEGATIVE)
                return httpx.Response(200, json={
                    'id': 'mock', 'object': 'chat.completion', 'created': 0, 'model': 'mock',
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30, 'cost': 0.001}})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                instance = self.make([])
                instance.response_format = 'json_schema'
                instance.model = ChatOpenAI(model='mock', api_key='dummy', base_url='https://mock.invalid/v1',
                    http_async_client=client, max_retries=0, temperature=None)
                await instance._call_agent('long_statement', dict(schema=MultipleLongStatementResponse, prompt='fixed'), 'x=1')
                attempts = instance.agent_metrics['long_statement']['attempts']
                self.assertEqual(attempts[0]['error'], 'InvalidJSON')
                self.assertTrue(attempts[0]['raw_response_text'].startswith('```json'))
                self.assertEqual(attempts[0]['validation_error']['type'], 'JSONDecodeError')
                self.assertEqual(attempts[1]['raw_response_text'], json.dumps(NEGATIVE))
                self.assertFalse(instance.agent_errors)
        asyncio.run(run())
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(r['response_format']['type'] == 'json_schema' for r in requests))

    def test_markdown_normalization_accepts_only_whole_response_fence(self):
        fenced = '```json\n{"detected":false,"detections":[]}\n```'
        instance = self.make([reply(text=fenced)])
        instance.json_normalization = 'markdown_fence'
        self.call(instance)
        self.assertFalse(instance.agent_errors)
        attempt = instance.agent_metrics['long_statement']['attempts'][0]
        self.assertTrue(attempt['normalization_applied'])
        self.assertEqual(attempt['raw_response_text'], fenced)
        self.assertEqual(json.loads(attempt['normalized_response_text']), NEGATIVE)
        for invalid in ['Explanation\n'+fenced, fenced+'\nMore text',
                        fenced+'\n'+fenced, '```json\n{"detected":false,"detections":[],}\n```']:
            instance = self.make([reply(text=invalid)], retries=0)
            instance.json_normalization = 'markdown_fence'
            self.call(instance)
            self.assertEqual(instance.agent_errors['long_statement'], 'InvalidJSON')

    def test_missing_response_cannot_count_as_valid(self):
        result = run_experiment.summarize_tasks('fake', 'complete_v2', [{'File': 'x.py'}],
            {'agent': {}}, [{'file': 'x.py', 'agent_errors': {}}], 0)
        self.assertEqual(result['valid_tasks'], 0)
        self.assertEqual(result['task_statuses'][0]['error'], 'MissingValidResponseRecord')
        self.assertFalse(result['cost_complete'])

    def test_credit_error_stops_without_retry(self):
        error = type('APIStatusError', (Exception,), {})('payment required')
        error.status_code = 402
        instance = self.make([error], retries=1)
        self.call(instance)
        self.assertEqual(instance.fatal_agent_error, 'InsufficientCreditError')
        self.assertEqual(len(instance.model.messages), 1)

    def test_fatal_failure_saves_partial_cost_and_pending_tasks(self):
        calls = []
        class FakeSupervisor:
            def __init__(self, **kwargs):
                self.agent_configs = {'a': {'prompt': 'fixed'}}
            async def analyze_code(self, *args):
                calls.append(1)
                return dict(code_smells=[], token_usage={}, agent_errors={'a': 'PermissionDeniedError'},
                    fatal_error='PermissionDeniedError', agent_metrics={'a': {'attempts': [
                        {'error': 'PermissionDeniedError', 'cost_usd': 0.001}]}})
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory)/'dataset'
            dataset.mkdir()
            for name in ('x.py', 'y.py'):
                (dataset/name).write_text('x = 1', encoding='utf-8')
            args = run_experiment.parser().parse_args(['--dataset', str(dataset), '--all-files'])
            output = Path(directory)/'run'
            with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                asyncio.run(run_experiment.execute(args, run_experiment.select_files(args),
                    ['fake'], ['complete_v2'], output, factory=FakeSupervisor))
            summary = json.loads((output/'summary.json').read_text())[0]
            self.assertEqual(len(calls), 1)
            self.assertEqual(summary['not_executed_tasks'], 1)
            self.assertEqual(summary['known_cost_usd'], 0.001)
            self.assertIsNone(summary['total_cost_usd'])
            self.assertEqual(json.loads((output/'run_status.json').read_text())['status'], 'aborted_configuration_error')

    def test_runner_marks_incomplete_and_raises_after_saving(self):
        class FakeSupervisor:
            def __init__(self, **kwargs):
                self.agent_configs = {'long_statement': {'prompt': 'fixed'}}
            async def analyze_code(self, *args):
                return dict(code_smells=[], token_usage={}, agent_errors={'long_statement': 'TruncatedResponse'})
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / 'dataset'
            dataset.mkdir()
            (dataset / 'x.py').write_text('x = 1\n', encoding='utf-8')
            args = run_experiment.parser().parse_args(['--dataset', str(dataset)])
            files = run_experiment.select_files(args)
            output = Path(directory) / 'run'
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'Rodada incompleta'):
                asyncio.run(run_experiment.execute(args, files, ['fake'], ['complete_v2'], output,
                                                   factory=FakeSupervisor))
            status = json.loads((output / 'run_status.json').read_text(encoding='utf-8'))
            self.assertFalse(status['all_tasks_valid'])
            summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))[0]
            self.assertEqual(summary['valid_tasks'], 0)
            self.assertFalse(summary['usage_complete'])
