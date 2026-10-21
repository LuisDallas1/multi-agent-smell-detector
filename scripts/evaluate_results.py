"""F1 offline por ocorrencia, presenca e contagem nos pares do manifesto DPy."""
import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from experiment_evaluation import Reference, line_number, prf, read_csv


def save_reference(run, dataset, files, pairs_path=None, truth_path=None):
    """Congela os pares e rotulos antes da inferencia; nao sao entrada das LLMs."""
    pairs_path = pairs_path or dataset / 'ground_truth/evaluation_pairs.csv'
    truth_path = truth_path or dataset / 'ground_truth/dpy_implementation_smells_sample.csv'
    selected = {row['File'] for row in files}
    pairs = [row for row in read_csv(pairs_path) if row['File'] in selected]
    scope = defaultdict(dict)
    for row in pairs:
        key = row['Smell'].strip().lower()
        if key in scope[row['File']]:
            raise ValueError('Par duplicado no manifesto')
        scope[row['File']][key] = int(row['Count'])
    if set(scope) != selected:
        raise ValueError('Arquivos sem pares de avaliacao')
    reference = Reference(dataset, truth_path)
    reference.validate(scope)
    truths = [row for rel, smells in scope.items() for smell in smells for row in reference.rows[(rel, smell)]]
    if not truths:
        raise ValueError('Amostra sem ocorrencias positivas para calcular recall/F1')
    for name, rows in [('evaluation_pairs.csv', pairs), ('evaluation_reference.csv', truths)]:
        with (run / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    provenance = dict(pairs_source=str(pairs_path), truth_source=str(truth_path),
                      source_hashes={str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (pairs_path, truth_path)},
                      saved_hashes={name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                                    for name in ('evaluation_pairs.csv', 'evaluation_reference.csv')})
    (run / 'evaluation_scope.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    return scope


def normalize(prediction, files):
    item = dict(prediction)
    path = str(item.get('File', '')).replace('\\', '/')
    candidates = [rel for rel in files if path == rel or path.endswith('/' + rel)]
    if len(candidates) != 1:
        raise ValueError(f'Arquivo previsto fora da amostra ou ambiguo: {path}')
    item['rel'] = candidates[0]
    item['smell_key'] = str(item.get('Smell', '')).strip().lower().replace('_', ' ')
    declared = item.get('Line_no', item.get('Line no'))
    adaptations = []
    if declared in ('', None) and item['smell_key'] in {'long method', 'complex method'}:
        declared = item.get('start_line')
        adaptations.append('Line_no recebe start_line declarado pelo modelo')
    item['Line_no'] = line_number(declared)
    if item['smell_key'] == 'magic number' and item.get('number') is None:
        match = re.search(r'Magic number\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)',
                          str(item.get('Description', '')), re.I)
        if match:
            item['number'] = float(match.group(1))
            adaptations.append('number extraido da descricao declarada pelo modelo')
    # Nao infere linha/nome/medida a partir do gabarito e nao descarta linha invalida:
    # previsao sem correspondencia pode ser FP em um par avaliado.
    return item, adaptations


def count_metrics(detections, sample):
    counts = Counter((d['rel'], d['smell_key']) for d in detections)
    tp = fp = fn = 0
    for rel, smells in sample.items():
        for smell, truth in smells.items():
            predicted = counts[(rel, smell)]
            tp += min(predicted, truth)
            fp += max(0, predicted-truth)
            fn += max(0, truth-predicted)
    p, r, f = prf(tp, fp, fn)
    return dict(tp=tp, fp=fp, fn=fn, precision=p, recall=r, f1=f)


def evaluate_run(run, dataset=None, pairs_path=None, truth_path=None):
    selection = json.loads((run / 'sample.json').read_text(encoding='utf-8'))
    dataset = Path(dataset or selection['dataset']).resolve()
    files = {row['File']: row for row in selection['files']}
    for rel, row in files.items():
        path = (dataset / rel).resolve()
        if not path.is_relative_to(dataset):
            raise ValueError('Amostra fora do dataset')
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'Codigo mudou desde a inferencia: {rel}')
    snapshot = run / 'evaluation_scope.json'
    if snapshot.is_file():
        provenance = json.loads(snapshot.read_text(encoding='utf-8'))
        for name, expected in provenance['saved_hashes'].items():
            if hashlib.sha256((run / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Gabarito/manifesto salvo foi alterado: {name}')
    pairs_path = pairs_path or (run / 'evaluation_pairs.csv' if snapshot.is_file() else dataset / 'ground_truth/evaluation_pairs.csv')
    truth_path = truth_path or (run / 'evaluation_reference.csv' if snapshot.is_file() else dataset / 'ground_truth/dpy_implementation_smells_sample.csv')
    sample = defaultdict(dict)
    for row in read_csv(pairs_path):
        if row['File'] in files:
            smell = row['Smell'].strip().lower()
            if smell in sample[row['File']]:
                raise ValueError('Par duplicado no manifesto')
            sample[row['File']][smell] = int(row['Count'])
    if set(sample) != set(files):
        raise ValueError('Todos os arquivos executados precisam de pares no manifesto')
    reference = Reference(dataset, truth_path)
    reference.validate(sample)
    results = []
    for path in sorted(run.glob('*/*/results_*_prompts.json')):
        predictions = json.loads(path.read_text(encoding='utf-8'))
        normalized, adaptations = [], []
        for index, prediction in enumerate(predictions):
            item, notes = normalize(prediction, files)
            normalized.append(item)
            if notes:
                adaptations.append(dict(prediction_index=index, changes=notes))
        occurrence = reference.evaluate(normalized, sample)
        presence_counts = occurrence['presence']
        p, r, f = prf(presence_counts.get('tp', 0), presence_counts.get('fp', 0), presence_counts.get('fn', 0))
        presence = dict(presence_counts, precision=p, recall=r, f1=f)
        metrics_path = next(path.parent.glob('file_metrics_*_prompts.json'))
        file_metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
        result = dict(model_directory=path.parent.parent.name, prompt_type=path.parent.name,
                      files=len(files), evaluated_pairs=sum(len(v) for v in sample.values()),
                      positive_pairs=sum(c > 0 for v in sample.values() for c in v.values()),
                      negative_pairs=sum(c == 0 for v in sample.values() for c in v.values()),
                      ground_truth_occurrences=sum(sum(v.values()) for v in sample.values()),
                      occurrence=occurrence, presence=presence, count_diagnostic=count_metrics(normalized, sample),
                      total_predictions=len(predictions), normalizations=adaptations,
                      files_with_errors=sum(bool(m.get('error') or m.get('agent_errors')) for m in file_metrics),
                      agent_failures=sum(len(m.get('agent_errors', {})) for m in file_metrics),
                      note='Avalia as deteccoes apos filtros do supervisor original. Nao recupera itens descartados antes da gravacao. '
                           'Fora dos pares e nao avaliado. Falhas permanecem no resultado operacional.')
        (path.parent / 'evaluation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        results.append(result)
        print(f"{result['model_directory']}/{result['prompt_type']}: "
              f"TP={occurrence['tp']} FP={occurrence['fp']} FN={occurrence['fn']} "
              f"F1={occurrence['f1']:.4f} macro-F1={occurrence['macro_f1']:.4f} "
              f"presenca={f:.4f} contagem={result['count_diagnostic']['f1']:.4f} "
              f"fora_do_escopo={occurrence['out_of_scope']}")
    if not results:
        raise ValueError('Nenhum resultado de inferencia encontrado')
    report = dict(evaluation_version=Reference.VERSION, primary_metric='occurrence.f1',
                  pairs_source=str(pairs_path), ground_truth_source=str(truth_path),
                  pairs_sha256=hashlib.sha256(Path(pairs_path).read_bytes()).hexdigest(),
                  ground_truth_sha256=hashlib.sha256(Path(truth_path).read_bytes()).hexdigest(), results=results)
    (run / 'evaluation_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--pairs', type=Path)
    parser.add_argument('--ground-truth', type=Path)
    args = parser.parse_args()
    evaluate_run(args.run, args.dataset, args.pairs, args.ground_truth)
