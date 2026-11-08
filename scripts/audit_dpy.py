"""Auditoria offline dos pares e ocorrencias contra a exportacao bruta do DPy."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from experiment_evaluation import read_csv


def signature(row):
    # Preserva multiplicidade, linha, descricao, classe e metodo do detector.
    return tuple((key, str(row.get(key, '')).strip()) for key in
                 ('Project', 'Package', 'Module', 'Class', 'Smell', 'Method', 'Line no', 'Description'))


def audit(dataset, pairs_path, truth_path, raw_dir, selected=None):
    dataset, raw_dir = Path(dataset), Path(raw_dir)
    pairs = [r for r in read_csv(pairs_path) if selected is None or r['File'] in selected]
    issues, hashes = [], {}
    files = {r['File'] for r in pairs}
    projects = {rel.split('/')[0] for rel in files}
    raw = defaultdict(list)
    for project in sorted(projects):
        path = raw_dir / f'{project}_implementation_smells.json'
        if not path.is_file():
            issues.append(dict(type='missing_raw_export', project=project))
            continue
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(rows, list):
            raise ValueError(f'Exportacao DPy deve ser lista: {path}')
        for row in rows:
            parts = str(row.get('File', '')).replace('\\', '/').split('/')
            # Resolve pelo nome completo do projeto e sufixo exato, nunca pelo basename.
            candidates = {'/'.join(parts[i:]) for i, part in enumerate(parts) if part == project}
            matches = candidates & files
            if len(matches) > 1:
                raise ValueError('Caminho DPy ambiguo')
            if matches:
                rel = next(iter(matches))
                raw[(rel, row['Smell'].strip().lower())].append(row)
    truth = defaultdict(list)
    for row in read_csv(truth_path):
        truth[(row['File'], row['Smell'].strip().lower())].append(row)
    seen = set()
    for pair in pairs:
        key = pair['File'], pair['Smell'].strip().lower()
        if key in seen:
            issues.append(dict(type='duplicate_pair', file=key[0], smell=key[1]))
        seen.add(key)
        expected, actual = Counter(map(signature, raw[key])), Counter(map(signature, truth[key]))
        if expected != actual or int(pair['Count']) != len(raw[key]):
            issues.append(dict(type='occurrence_mismatch', file=key[0], smell=key[1],
                               declared=int(pair['Count']), raw_count=len(raw[key]), csv_count=len(truth[key]),
                               missing=sum((expected-actual).values()), extra=sum((actual-expected).values())))
    source_check = []
    for rel in sorted(files):
        path = dataset / rel
        original = dataset.parent / 'dataset_full' / rel
        if not path.is_file():
            issues.append(dict(type='missing_source', file=rel))
        elif original.is_file():
            equal = path.read_bytes() == original.read_bytes()
            source_check.append(dict(file=rel, matches_dataset_full=equal))
            if not equal:
                issues.append(dict(type='source_differs_from_dataset_full', file=rel))
        else:
            source_check.append(dict(file=rel, matches_dataset_full=None))
    for path in (Path(pairs_path), Path(truth_path)):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(passed=not issues, files=len(files), evaluated_pairs=len(pairs), issues=issues,
                source_checks=source_check, source_hashes=hashes,
                limitation='Compara exportacoes existentes; nao reexecuta o DPy nem certifica seus thresholds ou a versao do codigo usada na mineracao.')


if __name__ == '__main__':
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=base/'dataset')
    parser.add_argument('--raw-dir', type=Path, default=base/'dataset/ground_truth/dpy_raw')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.dataset, args.dataset/'ground_truth/evaluation_pairs.csv',
                   args.dataset/'ground_truth/dpy_implementation_smells_sample.csv', args.raw_dir)
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(content, encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('passed', 'files', 'evaluated_pairs', 'issues')}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
