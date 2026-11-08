"""Persistencia antes do parser, falhas de disco/rede e hard kill, tudo offline."""
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import os
import threading
import unittest
from unittest.mock import patch

import httpx
from langchain_openai import ChatOpenAI

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
from core.execution.evidence import EvidenceStore, EvidenceWriteError
from core.single_agent import SingleAgentDetector
from core.single_agent.schema import AllSmellsResponse
from core.supervisor.agent_config import AGENTS
from test_single_agent import detector, empty, positive


def completion(payload, *, choices=True):
    return dict(id='provider-generation-id', object='chat.completion', created=0, model='mock',
        choices=[dict(index=0, message=dict(role='assistant', content=json.dumps(payload)),
                      finish_reason='stop')] if choices else None,
        usage=dict(prompt_tokens=40, completion_tokens=10, total_tokens=50, cost=0.002))


def stages(directory):
    return [e['stage'] for e in EvidenceStore.events(directory)]


class EvidenceTests(unittest.TestCase):
    def test_journal_write_can_be_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            store.emit('test', {'value': 1})
            self.assertEqual(EvidenceStore.verify(temporary), 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_short_reader_lock_retries_disk_replace_without_duplicate_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=EvidenceStore(temporary);store.emit('first',{})
            handle=(store.folder/'head.json').open('r',encoding='utf-8')
            release=threading.Timer(.05,handle.close);release.start()
            try:store.emit('second',{})
            finally:release.join();handle.close()
            self.assertFalse(store.failed)
            self.assertEqual([e['stage'] for e in EvidenceStore.events(temporary)],['first','second'])
            self.assertFalse((store.folder/'head.tmp').exists())

    def test_reader_checks_snapshot_head_when_writer_appends_after_listing(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=EvidenceStore(temporary);store.emit('first',{})
            original=Path.glob;appended=[]
            def listing(path,pattern,*args,**kwargs):
                paths=list(original(path,pattern,*args,**kwargs))
                if path==store.folder and pattern=='[0-9]*.json' and not appended:
                    appended.append(True);store.emit('second',{})
                return iter(paths)
            with patch.object(Path,'glob',listing):
                events=EvidenceStore.events(temporary)
            self.assertEqual([e['stage'] for e in events],['first'])
            self.assertEqual(EvidenceStore.verify(temporary),2)

    def test_real_sdk_preserves_original_fields_and_semantically_wrong_predictions(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            code = 'def f():\n    pass\n'
            store.start_file('file.py', code.encode(), code)
            payload = empty()
            payload['long_lambda_function'] = dict(detected=True, detections=[dict(
                detected=True, Smell='Long lambda function', Method='f', Line_no='2',
                Description='Audit occurrence.', lambda_length=80, threshold=80, original_extra='raw-only')])
            requests = []

            async def run():
                def handler(request):
                    requests.append(json.loads(request.content))
                    return httpx.Response(200, json=completion(payload), headers={'x-request-id': 'request-7'})
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler), event_hooks=store.hooks()) as client:
                    agent = detector([])
                    agent.evidence_store = store
                    agent.model = ChatOpenAI(model='mock', api_key='dummy', base_url='https://mock.invalid/v1',
                        http_async_client=client, max_retries=0, max_tokens=32768, temperature=None)
                    result = await agent.analyze_code(code, 'file.py', 'project')
                    self.assertEqual(result['agent_errors'], {})
                    self.assertEqual(len(result['code_smells']), 1)
                    self.assertEqual(result['agent_metrics']['all_smells']['attempts'][0]['cost_usd'], 0.002)
            asyncio.run(run())
            events = EvidenceStore.events(temporary)
            names = [e['stage'] for e in events]
            self.assertLess(names.index('http_response'), names.index('pydantic_validated'))
            self.assertLess(names.index('http_request'), names.index('http_response'))
            sent = json.loads(next(e for e in events if e['stage'] == 'http_request')['payload']['body']['text'])
            self.assertEqual(sent, requests[0])
            self.assertIn('   2 |     pass', sent['messages'][1]['content'])
            self.assertIn('CONTRATO FINAL OBRIGATÓRIO', sent['messages'][1]['content'])
            original = next(e for e in events if e['stage'] == 'decoded_payload')['payload']['payload']
            parsed = next(e for e in events if e['stage'] == 'pydantic_validated')['payload']['payload']
            self.assertEqual(original, payload)
            self.assertEqual(set(original), set(AGENTS))
            self.assertNotIn('original_extra', parsed['long_lambda_function']['detections'][0])
            rejection = next(e for e in events if e['stage'] == 'detection_decision')
            self.assertTrue(rejection['payload']['accepted'])
            self.assertIsNotNone(rejection['attempt_id'])
            self.assertFalse(any('authorization' in e['payload'].get('headers', {}) for e in events))

    def test_invalid_http_envelope_saved_before_real_sdk_failure_and_usage_recovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            store.start_file('file.py', b'pass\n', 'pass\n')
            async def run():
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=completion(empty(), choices=False))),
                    event_hooks=store.hooks()) as client:
                    agent = detector([], retries=0)
                    agent.evidence_store = store
                    agent.model = ChatOpenAI(model='mock', api_key='dummy', base_url='https://mock.invalid/v1',
                        http_async_client=client, max_retries=0, temperature=None)
                    return await agent.analyze_code('pass\n', 'file.py', 'project')
            result = asyncio.run(run())
            self.assertEqual(result['agent_errors']['all_smells'], 'InvalidProviderResponse')
            self.assertEqual(result['agent_metrics']['all_smells']['attempts'][0]['cost_usd'], 0.002)
            self.assertEqual(result['token_usage']['total_tokens'], 50)
            response = next(e for e in EvidenceStore.events(temporary) if e['stage'] == 'http_response')
            self.assertIsNone(json.loads(response['payload']['body']['text'])['choices'])
            self.assertLess(stages(temporary).index('http_response'), stages(temporary).index('exception'))

    def test_disk_failure_prevents_network_and_no_retry_is_hidden(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            agent = detector([empty()])
            agent.evidence_store = store
            with patch('core.execution.evidence.os.replace', side_effect=OSError('simulated full disk')):
                with self.assertRaises(EvidenceWriteError):
                    asyncio.run(agent.analyze_code('pass\n', 'file.py', 'project'))
            self.assertEqual(agent.model.messages, [])
            self.assertTrue(store.failed)
            with self.assertRaises(EvidenceWriteError):
                store.emit('another_request', {})

    def test_partial_http_body_is_preserved_when_connection_breaks(self):
        class BrokenStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"id":"partial-generation",'
                raise httpx.ReadError('simulated disconnection')
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            async def run():
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, stream=BrokenStream())), event_hooks=store.hooks()) as client:
                    with store.attempt('all_smells', 1, 32768):
                        with self.assertRaises(httpx.ReadError):
                            await client.post('https://mock.invalid/v1', json={'messages': []})
            asyncio.run(run())
            events = EvidenceStore.events(temporary)
            chunk = next(e for e in events if e['stage'] == 'http_response_chunk')
            self.assertEqual(base64.b64decode(chunk['payload']['body']['base64']), b'{"id":"partial-generation",')
            self.assertIn('http_response_incomplete', stages(temporary))
            self.assertNotIn('http_response', stages(temporary))

    def test_parallel_attempts_keep_request_correlation(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            async def run():
                ready = asyncio.Event()
                arrived = []
                async def handler(request):
                    arrived.append(json.loads(request.content)['label'])
                    if len(arrived) == 2:
                        ready.set()
                    await ready.wait()
                    return httpx.Response(200, json={'label': json.loads(request.content)['label']})
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler), event_hooks=store.hooks()) as client:
                    async def task(label):
                        with store.attempt(label, 1, 8192):
                            await client.post('https://mock.invalid/v1', json={'label': label})
                    await asyncio.gather(task('A'), task('B'))
            asyncio.run(run())
            events = EvidenceStore.events(temporary)
            identities = {e['attempt_id']: e['payload']['agent'] for e in events if e['stage'] == 'attempt_started'}
            for event in events:
                if event['stage'] in {'http_request', 'http_response'}:
                    self.assertEqual(json.loads(event['payload']['body']['text'])['label'], identities[event['attempt_id']])

    def test_credentials_are_excluded_and_echoed_known_key_is_redacted(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            store.register_secret('TEST-PRIVATE-KEY')
            async def run():
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
                    httpx.Response(403, json={'error': 'TEST-PRIVATE-KEY'}, headers={'set-cookie': 'TEST-PRIVATE-KEY'})),
                    event_hooks=store.hooks()) as client:
                    with store.attempt('agent', 1, 8192):
                        await client.post('https://mock.invalid/v1?api_key=TEST-PRIVATE-KEY',
                            headers={'Authorization': 'Bearer TEST-PRIVATE-KEY', 'Cookie': 'TEST-PRIVATE-KEY'}, json={})
            asyncio.run(run())
            all_text = ''.join(p.read_text(encoding='utf-8') for p in store.root.rglob('*.json'))
            self.assertNotIn('TEST-PRIVATE-KEY', all_text)
            self.assertNotIn('Bearer ', all_text)
            for event in EvidenceStore.events(temporary):
                body = event['payload'].get('body')
                if body:
                    self.assertNotIn(b'TEST-PRIVATE-KEY', base64.b64decode(body['base64']))

    def test_tampered_or_missing_middle_event_is_detected(self):
        for mode in ('tamper', 'delete', 'delete_last'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                store = EvidenceStore(temporary)
                for i in range(3):
                    store.emit('test', {'index': i})
                path = store.folder / '00000002.json'
                if mode == 'delete_last':
                    (store.folder / '00000003.json').unlink()
                elif mode == 'delete':
                    path.unlink()
                else:
                    payload = json.loads(path.read_text())
                    payload['event']['payload']['index'] = 999
                    path.write_text(json.dumps(payload))
                with self.assertRaises(RuntimeError):
                    EvidenceStore.events(temporary)

    def test_constructor_installs_hooks_without_loading_real_settings(self):
        from types import SimpleNamespace
        from core.supervisor import CodeSmellSupervisor
        with tempfile.TemporaryDirectory() as temporary:
            store = EvidenceStore(temporary)
            fake = SimpleNamespace(settings=SimpleNamespace(OPENROUTER_API_KEY='dummy',
                OPENROUTER_BASE_URL='https://mock.invalid/v1', OPENROUTER_API_MODEL='mock'))
            async def run():
                with patch.dict(sys.modules, {'config.settings': fake}):
                    engine = CodeSmellSupervisor(evidence_store=store, response_format='json_mode')
                self.assertEqual(len(engine._evidence_http_client.event_hooks['response']), 1)
                self.assertIs(engine.model.http_async_client, engine._evidence_http_client)
                await engine.close_evidence_client()
            asyncio.run(run())

    def test_hard_kill_retains_completed_attempt_inside_uncommitted_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            program = root / 'child.py'
            program.write_text('''import sys,time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from core.execution.evidence import EvidenceStore
s=EvidenceStore(sys.argv[2])
s.start_file('file.py', b'pass\\n', 'pass\\n')
with s.attempt('first',1,8192):
 s.emit('http_response', {'status_code':200,'body':s.body(b'{"id":"paid-response","usage":{"cost":0.003}}')})
 s.emit('attempt_completed', {'metrics':{'error':None,'cost_usd':0.003}})
with s.attempt('second',1,8192):
 s.emit('http_request', {'body':s.body(b'{}')})
 Path(sys.argv[3]).write_text('ready')
 time.sleep(3600)
''', encoding='utf-8')
            ready = root / 'ready'
            process = subprocess.Popen([sys.executable, '-B', str(program), str(BASE/'src'),
                                        str(root/'run'), str(ready)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                process.terminate()
                process.communicate(timeout=10)
                before = {p: p.read_bytes() for p in (root/'run/evidence').rglob('*.json')
                          if p.name != 'sessions.json'}  # Registry adds the new session; prior events remain immutable.
                summary = EvidenceStore.summarize(root/'run')
                self.assertEqual(len(summary['attempts']), 2)
                self.assertEqual(summary['uncommitted_known_cost_usd'], 0.003)
                self.assertEqual(sum(a['completed'] for a in summary['attempts']), 1)
                self.assertFalse(any(a['file_committed'] for a in summary['attempts']))
                resumed = EvidenceStore(root/'run')
                resumed.emit('new_session', {})
                self.assertTrue(all(path.read_bytes() == value for path, value in before.items()))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == '__main__':
    unittest.main()
