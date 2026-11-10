"""Validação exploratória unificada: duas arquiteturas, três modelos, dois prompts."""
import argparse
from datetime import datetime, timezone, timedelta
import csv
import json
from pathlib import Path
import subprocess
import sys

import run_experiment as runner
from evaluate_results import save_reference
from generation_protocol import EXPERIMENT_LIMITS, FROZEN_PARAMETERS

MODELS = ['gpt-6-luna', 'deepseek-v4.1-flash', 'claude-haiku-5.5']


def command(architecture, dataset, manifest, output=None, *, dry_run=False):
    limits = EXPERIMENT_LIMITS[architecture]
    result = [sys.executable, '-B', '-u', str(runner.BASE / 'scripts/run_experiment.py'),
              '--architecture', architecture, '--models', *MODELS, '--prompt-type', 'paired',
              '--dataset', str(dataset), '--files-from', str(manifest), '--all-files',
              '--generation-profile', 'experiment', '--response-format', 'json_mode',
              '--json-normalization', 'markdown_fence']
    for key, value in limits.items():
        result += ['--' + key.replace('_', '-'), str(value)]
    if output is not None:
        result += ['--output-dir', str(output)]
        result += ['--evaluation-pairs', str(output.parent / 'evaluation_pairs.csv'),
                   '--ground-truth', str(output.parent / 'evaluation_reference.csv')]
    if dry_run:
        result.append('--dry-run')
    return result


def collect(output, planned=12):
    rows = []
    summaries = []
    for architecture in EXPERIMENT_LIMITS:
        summary_path = output / architecture / 'summary.json'
        if summary_path.exists():
            summaries.extend(json.loads(summary_path.read_text()))
        for path in sorted((output / architecture).glob('*/*/evaluation.json')):
            evaluation = json.loads(path.read_text(encoding='utf-8'))
            usage = json.loads(next(path.parent.glob('token_usage_*_prompts.json')).read_text())
            occurrence = evaluation['occurrence']
            rows.append(dict(architecture=architecture, model=usage['model'],
                strategy=runner.SINGLE_PROMPT_SOURCES.get(usage['prompt_type'], usage['prompt_type']),
                prompt_type=usage['prompt_type'],
                **{key: occurrence[key] for key in ('tp', 'fp', 'fn', 'precision', 'recall', 'f1', 'macro_f1')},
                **{key: usage[key] for key in ('expected_tasks', 'valid_tasks', 'attempted_calls',
                                               'failed_attempts', 'known_cost_usd', 'total_cost_usd', 'cost_complete')},
                status=evaluation['technical_status'],
                ground_truth_occurrences=evaluation['ground_truth_occurrences'],
                failed_evaluated_pairs=len(evaluation['failed_evaluated_pairs']),
                evidence=path.relative_to(output).as_posix()))
    complete = len(rows) == planned
    cost_complete = complete and len(summaries) == planned and all(s['cost_complete'] for s in summaries)
    known = sum(s['known_cost_usd'] for s in summaries)
    report = dict(purpose='exploratory validation, not final collection', planned_combinations=planned,
                  completed_combinations=len(rows),
                  all_tasks_valid=complete and all(row['status'] == 'valid' for row in rows),
                  known_cost_usd=known, total_cost_usd=known if cost_complete else None,
                  cost_complete=cost_complete, rows=rows,
                  note='F1 operational; no minimum F1 used as a technical acceptance criterion. '
                       'Prompt sources paired; budgets dimensioned by architecture.')
    runner.write_json(output / 'validation_summary.json', report)
    if rows:
        with (output / 'validation_summary.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files-from', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, default=runner.DEFAULT_DATASET)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    selection_args = runner.parser().parse_args([
        '--dataset', str(args.dataset), '--files-from', str(args.files_from), '--all-files'])
    files = runner.select_files(selection_args)
    print(f'Validação: {len(files)} arquivos; 12 combinações; '
          f'{len(files) * 3 * 2 * 12} tarefas iniciais.', flush=True)
    if args.dry_run:
        for architecture in EXPERIMENT_LIMITS:
            subprocess.run(command(architecture, args.dataset, args.files_from, dry_run=True), check=True)
        return
    stamp = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y%m%d_%H%M%S_%f')
    output = (args.output_dir or Path.home() / 'TCC-results/validations' / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    runner.write_json(output / 'sample.json', dict(dataset=str(args.dataset.resolve()), files=files, seed=1))
    save_reference(output, args.dataset, files)
    snapshots = runner.source_snapshots()
    runner.write_json(output / 'protocol.json', dict(version='experiment-v1',
        budgets=EXPERIMENT_LIMITS, models=FROZEN_PARAMETERS,
        reasoning='low', response_format='json_mode', json_normalization='markdown_fence',
        prompt_policy='mutable between rounds; fixed within each unified validation',
        runtime=runner.runtime_versions(), **snapshots))
    runner.write_json(output / 'run_status.json', dict(status='running'))
    try:
        for architecture in EXPERIMENT_LIMITS:
            child = output / architecture
            result = subprocess.run(command(architecture, args.dataset, output / 'sample.json', child))
            report = collect(output)
            if (child / 'failure.json').exists():
                raise RuntimeError('Falha fatal de configuração; demais chamadas canceladas')
            status_path = child / 'run_status.json'
            status = json.loads(status_path.read_text()).get('status') if status_path.exists() else None
            if result.returncode and status != 'incomplete':
                raise RuntimeError('Executor interrompido; demais chamadas canceladas')
        report = collect(output)
        runner.write_json(output / 'run_status.json', dict(status='valid' if report['all_tasks_valid'] else 'incomplete'))
        print(f'Validação consolidada: {output}', flush=True)
        for row in report['rows']:
            print(f"{row['architecture']:10s} {row['model']:36s} {row['prompt_type']:16s} "
                  f"F1={row['f1']:.4f} válidas={row['valid_tasks']}/{row['expected_tasks']} "
                  f"custo_conhecido=${row['known_cost_usd']:.6f}", flush=True)
        if not report['all_tasks_valid']:
            raise SystemExit(1)
    except (RuntimeError, KeyboardInterrupt):
        collect(output)
        runner.write_json(output / 'run_status.json', dict(status='interrupted_or_aborted'))
        raise


if __name__ == '__main__':
    main()
