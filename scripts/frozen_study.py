"""Plano do experimento gerado dos dados atuais ou lido de uma rodada salva."""
import argparse
import uuid
import json
from pathlib import Path

import run_experiment as runner
from generation_protocol import FROZEN_PARAMETERS, EXPERIMENT_LIMITS
from checkpointing import write_json

VERSION='tcc-frozen-v1'


def create(path=None):
    path=Path(path) if path is not None else None
    if path is not None and path.exists():raise ValueError('Congelamento existente nao sera sobrescrito')
    args=runner.parser().parse_args(['--all-files', '--files-from',
        str(runner.DEFAULT_DATASET/'ground_truth/evaluation_pairs.csv')])
    files=runner.select_files(args)
    from experiment_evaluation import Reference,read_csv
    pairs=runner.DEFAULT_DATASET/'ground_truth/evaluation_pairs.csv'
    truth=runner.DEFAULT_DATASET/'ground_truth/dpy_implementation_smells_sample.csv'
    scope={}
    for row in read_csv(pairs):scope.setdefault(row['File'],{})[row['Smell'].lower()]=int(row['Count'])
    Reference(runner.DEFAULT_DATASET,truth).validate(scope)
    if {f['File'] for f in files}!=set(scope):raise ValueError('Selecao nao cobre exatamente o manifesto')
    artifacts=[pairs,truth,runner.DEFAULT_DATASET/'ground_truth/evaluation_manifest.json',
        runner.BASE/'dataset_full/config.json',runner.BASE/'dataset_full/DPy.exe']
    artifacts+=sorted((runner.DEFAULT_DATASET/'ground_truth/dpy_raw').glob('*.json'))
    artifacts+=[p for p in [runner.DEFAULT_DATASET/'sample_config.json'] if p.exists()]
    artifact_files=[p.relative_to(runner.BASE).as_posix() for p in artifacts]
    models=['gpt-6-luna','deepseek-v4.1-flash','claude-haiku-5.5']
    protocol=dict(version=VERSION,decision='Frozen by author; no claim of advisor approval.',
        models=models,
        architectures=['multiagent','single'],prompts=['simple_v2','complete_v2'],
        repetitions=1,order='multiagent then single; within each architecture GPT, DeepSeek, Haiku; simple_v2 then complete_v2; sequential files',
        documentation='README.md',
        generation_profile='experiment',
        generation={runner.MODELS[name]:FROZEN_PARAMETERS[runner.MODELS[name]] for name in models},
        budgets=EXPERIMENT_LIMITS,
        response_format='json_mode',json_normalization='markdown_fence',reasoning='low',
        persistence_policy='flush-close-atomic-replace-v1',
        files=files,artifact_files=artifact_files,runtime=runner.runtime_versions(),
        analysis=dict(bootstrap_iterations=10000,seed=20261106,confidence=.95,primary='occurrence micro-F1',
            secondary='descriptive metrics, paired file bootstrap, project sensitivity, presence McNemar/Holm',
            unavailable='AUC/calibration without scores; LLM execution variance without repetitions'),
        expected=dict(files=len(files),pairs=sum(len(v) for v in scope.values()),
            occurrences=sum(sum(v.values()) for v in scope.values()),conditions=12,
            initial_tasks=len(files)*3*2*12),**runner.source_snapshots())
    protocol['freeze_id']=uuid.uuid4().hex
    if path is not None:
        path.parent.mkdir(parents=True,exist_ok=True)
        write_json(path,protocol)
        write_json(path.parent/'frozen_files.json',dict(files=files))
    return protocol


def validate(protocol):
    if protocol.get('version')!=VERSION or not protocol.get('freeze_id'):
        raise ValueError('Formato de protocolo desconhecido')
    if protocol['runtime']!=runner.runtime_versions():raise ValueError('Runtime mudou desde o congelamento')
    for row in protocol['files']:
        source=(runner.DEFAULT_DATASET/row['File']).resolve()
        if not source.is_relative_to(runner.DEFAULT_DATASET.resolve()) or not source.is_file():
            raise ValueError(f"Arquivo ausente ou fora do dataset: {row['File']}")
    return protocol


def verify(path):
    path=Path(path)
    protocol=validate(json.loads(path.read_text(encoding='utf-8')))
    # New runs keep selection in sample.json; historical explicit manifests may
    # still have frozen_files.json. Neither requires an external protocol folder.
    selection=next((p for p in (path.parent/'sample.json',path.parent/'frozen_files.json')
                    if p.is_file()),None)
    if selection is not None:
        files=json.loads(selection.read_text(encoding='utf-8'))['files']
        if sorted(r['File'] for r in files)!=sorted(r['File'] for r in protocol['files']):
            raise ValueError('Selecao da rodada diverge do protocolo')
    return protocol


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create',action='store_true')
    parser.add_argument('--manifest',type=Path,help='protocolo opcional; sem argumento, mostra o plano atual')
    args=parser.parse_args()
    if args.create and args.manifest is None:parser.error('--create exige --manifest para escolher o destino')
    result=create(args.manifest) if args.create else (verify(args.manifest) if args.manifest else create())
    print(json.dumps(dict(freeze_id=result['freeze_id'],expected=result['expected']),indent=2))
