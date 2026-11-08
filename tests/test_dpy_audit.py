"""A auditoria deve rejeitar omissoes, negativos incorretos e codigo alterado."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_dpy import audit


class AuditTests(unittest.TestCase):
    def test_complete_pair_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            dataset = base/'dataset'
            raw = base/'raw'
            raw.mkdir()
            (dataset/'P').mkdir(parents=True)
            (base/'dataset_full/P').mkdir(parents=True)
            for root in (dataset, base/'dataset_full'):
                (root/'P/x.py').write_text('x = 2\n', encoding='utf-8')
            row = dict(Project='P', Package='P', Module='x', Class='', Smell='Magic number',
                       Method='', **{'Line no': '1', 'Description': 'Magic number 2', 'File': 'P/x.py'})
            (raw/'P_implementation_smells.json').write_text(json.dumps([dict(row, File='D:/old/P/x.py')]))
            truth, pairs = base/'truth.csv', base/'pairs.csv'

            def write(path, rows, fields):
                with path.open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)

            write(truth, [row], list(row))
            pair = dict(File='P/x.py', Smell='Magic number', Count=1)
            write(pairs, [pair], list(pair))
            self.assertTrue(audit(dataset, pairs, truth, raw)['passed'])
            write(truth, [], list(row))
            self.assertFalse(audit(dataset, pairs, truth, raw)['passed'])
            write(pairs, [dict(pair, Count=0)], list(pair))
            self.assertFalse(audit(dataset, pairs, truth, raw)['passed'])
            write(truth, [row], list(row))
            write(pairs, [pair], list(pair))
            (dataset/'P/x.py').write_text('x = 3\n', encoding='utf-8')
            self.assertFalse(audit(dataset, pairs, truth, raw)['passed'])
