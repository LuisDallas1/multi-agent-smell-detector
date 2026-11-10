"""Preservação e retomada, incluindo encerramento abrupto de processo offline."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import run_experiment as runner
from checkpointing import FileStore, RunLock
from checkpointing import atomic_text


def setup(root, architecture='multiagent'):
    root = Path(root)
    dataset = root / 'dataset'
    dataset.mkdir(exist_ok=True)
    for index in range(3):
        (dataset / f'f{index}.py').write_text('value = 7\n', encoding='utf-8')
    args = runner.parser().parse_args([
        '--architecture', architecture, '--dataset', str(dataset), '--all-files',
        '--generation-profile', 'custom', '--response-format', 'json_mode', '--no-evaluate'])
    return args, runner.select_files(args), root / 'run'


def factory(calls, interrupt=None, ready=None):
    class Fake:
        def __init__(self, **kwargs):
            self.agent_configs = {'test_agent': {'prompt': 'fixed prompt'}}

        async def analyze_code(self, code, path, project):
            name = Path(path).name
            calls.append(name)
            if name == interrupt:
                if ready:
                    Path(ready).write_text('ready', encoding='utf-8')
                    await asyncio.sleep(3600)
                raise asyncio.CancelledError()
            return dict(code_smells=[dict(File=path, Smell='Magic number', number=7,
                                          **{'Line no': '1'}, Description='Magic number 7.')],
                        token_usage=dict(prompt_tokens=2, completion_tokens=3, total_tokens=5),
                        agent_errors={}, agent_metrics={'test_agent': dict(attempts=[dict(
                            error=None, cost_usd=0.001, token_usage=dict(
                                prompt_tokens=2, completion_tokens=3, total_tokens=5))])})
    return Fake


def resumed(output, allow=False):
    request = runner.parser().parse_args(['--resume', str(output)] + (['--retry-interrupted'] if allow else []))
    args = runner.restore_resume_args(request)
    return args, runner.select_files(args)


def run(args, files, output, fake):
    return asyncio.run(runner.execute(args, files, ['mock'], ['complete_v2'], output, factory=fake))


class ResumeTests(unittest.TestCase):
    def test_atomic_write_leaves_complete_file_without_temporary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'checkpoint.json'
            atomic_text(path, '{"saved": true}')
            self.assertEqual(json.loads(path.read_text()), {'saved': True})
            self.assertFalse(path.with_name(path.name + '.tmp').exists())

    def test_interruption_preserves_completed_files_and_explicit_resume_has_no_duplicates(self):
        for architecture in ('multiagent', 'single'):
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                args, files, output = setup(temporary, architecture)
                calls = []
                with self.assertRaises(asyncio.CancelledError):
                    run(args, files, output, factory(calls, interrupt='f1.py'))
                directory = output / '01_mock/complete_v2'
                before = next((directory / 'checkpoints').glob('*.json')).read_bytes()
                self.assertEqual(len(FileStore(directory, files).records()), 1)
                self.assertEqual(json.loads((output / 'run_status.json').read_text())['status'], 'interrupted')
                resume, selected = resumed(output)
                with self.assertRaisesRegex(RuntimeError, 'possível cobrança'):
                    run(resume, selected, output, factory([]))
                resume, selected = resumed(output, allow=True)
                resumed_calls = []
                summary = run(resume, selected, output, factory(resumed_calls))[0]
                self.assertEqual(resumed_calls, ['f1.py', 'f2.py'])
                self.assertEqual(len(json.loads((directory / 'results_complete_v2_prompts.json').read_text())), 3)
                self.assertEqual(len((directory / 'raw.jsonl').read_text().splitlines()), 3)
                self.assertIn(before, [p.read_bytes() for p in (directory / 'checkpoints').glob('*.json')])
                self.assertEqual(summary['valid_tasks'], 3)
                self.assertEqual(summary['known_cost_usd'], 0.003)
                self.assertFalse(summary['cost_complete'])
                self.assertIsNone(summary['total_cost_usd'])
                self.assertEqual(len(summary['interrupted_files']), 1)
                # Repetir resume após tudo concluído não chama o detector.
                no_calls = []
                run(*resumed(output), output, factory(no_calls))
                self.assertEqual(no_calls, [])

    def test_crash_after_commit_before_aggregate_write_rebuilds_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, files, output = setup(temporary)
            original = runner.rebuild_projection
            count = [0]
            def crash(*args):
                count[0] += 1
                if count[0] == 2:
                    raise OSError('simulated disk projection failure')
                return original(*args)
            with patch.object(runner, 'rebuild_projection', side_effect=crash):
                with self.assertRaises(OSError):
                    run(args, files, output, factory([]))
            calls = []
            summary = run(*resumed(output), output, factory(calls))[0]
            self.assertEqual(calls, ['f1.py', 'f2.py'])
            self.assertTrue(summary['cost_complete'])
            self.assertEqual(summary['valid_tasks'], 3)

    def test_changed_parameters_still_block_before_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, files, output = setup(temporary)
            run(args, files, output, factory([]))
            resume, selected = resumed(output)
            resume.max_tokens += 1
            with self.assertRaisesRegex(RuntimeError, 'Parâmetros'):
                run(resume, selected, output, factory([]))
    def test_legacy_sha_fields_are_ignored_without_rewriting_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'checkpoints').mkdir()
            record = dict(file='x.py', result={'code_smells': []})
            path = directory / 'checkpoints' / ('a' * 64 + '.json')
            path.write_text(json.dumps(dict(version='file-v1', record=record,
                sha256='obsolete', source_sha256='obsolete')), encoding='utf-8')
            before = path.read_bytes()
            store = FileStore(directory, [dict(File='x.py')])
            self.assertEqual(store.records(), {'x.py': record})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.path('x.py'), path)
            store.commit(record)
            self.assertEqual(len(list(store.folder.glob('*.json'))), 1)
            self.assertNotIn('sha256', json.loads(path.read_text()))

    def test_run_lock_rejects_simultaneous_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / '.lock'
            with RunLock(path):
                with self.assertRaisesRegex(RuntimeError, 'Já existe'):
                    with RunLock(path):
                        self.fail('Não deveria obter dois locks')

    def test_changed_runtime_blocks_resume_before_detector(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, files, output = setup(temporary)
            run(args, files, output, factory([]))
            with patch.object(runner, 'runtime_versions', return_value={'python': 'changed'}):
                with self.assertRaisesRegex(RuntimeError, 'dependências mudaram'):
                    run(*resumed(output), output, factory([]))

    def test_process_termination_preserves_checkpoint_and_releases_os_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                                        '--checkpoint-worker', temporary], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE)
            ready = Path(temporary) / 'ready'
            deadline = time.monotonic() + 30
            try:
                while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
                    time.sleep(0.05)
                self.assertTrue(ready.exists(), 'Worker não chegou ao ponto de interrupção')
                process.terminate()  # Encerra apenas o processo de teste criado acima.
                process.communicate(timeout=10)
                output = Path(temporary) / 'run'
                calls = []
                summary = run(*resumed(output, allow=True), output, factory(calls))[0]
                self.assertEqual(calls, ['f1.py', 'f2.py'])
                self.assertEqual(summary['valid_tasks'], 3)
                self.assertFalse(summary['cost_complete'])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--checkpoint-worker':
        args, files, output = setup(sys.argv[2])
        run(args, files, output, factory([], interrupt='f1.py', ready=Path(sys.argv[2]) / 'ready'))
    else:
        unittest.main()
