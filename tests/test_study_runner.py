"""Coleta e retomada independentes de uma pasta externa de protocolo."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import frozen_study
import run_study
from checkpointing import write_json


class StudyRunnerTests(unittest.TestCase):
    def dataset(self, root):
        dataset = root / 'dataset'
        truth = dataset / 'ground_truth'
        truth.mkdir(parents=True)
        (dataset / 'x.py').write_text('def f(a,b,c,d,e):\n    pass\n', encoding='utf-8')
        (truth / 'evaluation_pairs.csv').write_text(
            'File,Smell,Count\nx.py,long parameter list,1\n', encoding='utf-8')
        (truth / 'dpy_implementation_smells_sample.csv').write_text(
            'File,Smell,Line no,Method,Description\nx.py,Long parameter list,1,f,Five parameters.\n',
            encoding='utf-8')
        return dataset

    def test_new_collection_and_resume_use_only_the_run_protocol(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = self.dataset(root)
            output = root / 'run'
            calls = []
            def execute(cmd):
                calls.append(cmd)
                child = Path(cmd[cmd.index('--output-dir') + 1])
                child.mkdir(parents=True)
                write_json(child / 'run_status.json', dict(status='valid'))
                return type('Result', (), {'returncode': 0})()
            with patch.object(run_study.runner, 'BASE', root), patch.object(
                    run_study.runner, 'DEFAULT_DATASET', dataset), patch.object(
                    run_study.runner, 'runtime_versions', return_value={'python': 'test'}), patch(
                    'run_study.subprocess.run', side_effect=execute), patch(
                    'sys.argv', ['run_study.py', '--output-dir', str(output)]), contextlib.redirect_stdout(io.StringIO()):
                run_study.main()
                protocol = (output / 'frozen_protocol.json').read_bytes()
                self.assertEqual(len(calls), 6)
                self.assertFalse((root / 'experiment').exists())
                for cmd in calls:
                    self.assertEqual(Path(cmd[cmd.index('--files-from') + 1]), output / 'sample.json')
                with patch('run_study.create', side_effect=AssertionError('must reuse saved plan')), patch(
                        'run_study.subprocess.run', side_effect=AssertionError('must skip completed runs')), patch(
                        'sys.argv', ['run_study.py', '--resume', str(output)]):
                    run_study.main()
                self.assertEqual((output / 'frozen_protocol.json').read_bytes(), protocol)
                self.assertEqual(json.loads((output / 'study_status.json').read_text())['status'], 'valid')

    def test_dry_run_uses_temporary_selection_and_creates_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = self.dataset(root)
            output = root / 'run'
            manifests = []
            def execute(cmd, check):
                self.assertTrue(check)
                self.assertIn('--dry-run', cmd)
                manifest = Path(cmd[cmd.index('--files-from') + 1])
                self.assertEqual(json.loads(manifest.read_text())['files'][0]['File'], 'x.py')
                manifests.append(manifest)
            with patch.object(run_study.runner, 'BASE', root), patch.object(
                    run_study.runner, 'DEFAULT_DATASET', dataset), patch.object(
                    run_study.runner, 'runtime_versions', return_value={'python': 'test'}), patch(
                    'run_study.subprocess.run', side_effect=execute), patch(
                    'sys.argv', ['run_study.py', '--dry-run', '--output-dir', str(output)]), contextlib.redirect_stdout(io.StringIO()):
                run_study.main()
            self.assertEqual(len(manifests), 6)
            self.assertTrue(all(not p.exists() for p in manifests))
            self.assertFalse(output.exists())
            self.assertFalse((root / 'experiment').exists())

    def test_resume_does_not_generate_a_new_plan_if_saved_protocol_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
                'run_study.create', side_effect=AssertionError('must not generate a new plan')):
            with self.assertRaises(FileNotFoundError):
                run_study.load_protocol(resume=Path(temporary))


if __name__ == '__main__':
    unittest.main()
