"""Criacao e verificacao do congelamento solicitado; nunca inclui .env."""
import argparse
import hashlib
import json
from pathlib import Path

import run_experiment as runner
from generation_protocol import FROZEN_PARAMETERS, EXPERIMENT_LIMITS
from checkpointing import write_json

VERSION='tcc-frozen-v1'
DEFAULT=runner.BASE/'experiment/final/frozen_protocol.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(path=DEFAULT):
    path=Path(path)
    if path.exists():raise ValueError('Congelamento existente nao sera sobrescrito')
    args=runner.parser().parse_args(['--all-files'])
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
    hashes={p.relative_to(runner.BASE).as_posix():sha(p) for p in artifacts}
    models=['gpt-6-luna','deepseek-v4.1-flash','claude-haiku-5.5']
    protocol=dict(version=VERSION,decision='Frozen by author; no claim of advisor approval.',
        models=models,
        architectures=['multiagent','single'],prompts=['simple_v2','complete_v2'],
        repetitions=1,order='multiagent then single; within each architecture GPT, DeepSeek, Haiku; simple_v2 then complete_v2; sequential files',
        documentation_sha256=sha(runner.BASE/'README.md'),
        generation_profile='experiment',
        generation={runner.MODELS[name]:FROZEN_PARAMETERS[runner.MODELS[name]] for name in models},
        budgets=EXPERIMENT_LIMITS,
        response_format='json_mode',json_normalization='markdown_fence',reasoning='low',
        persistence_policy='flush-close-atomic-replace-v1',
        files=files,artifacts_sha256=hashes,runtime=runner.runtime_versions(),
        analysis=dict(bootstrap_iterations=10000,seed=20261106,confidence=.95,primary='occurrence micro-F1',
            secondary='descriptive metrics, paired file bootstrap, project sensitivity, presence McNemar/Holm',
            unavailable='AUC/calibration without scores; LLM execution variance without repetitions'),
        expected=dict(files=len(files),pairs=sum(len(v) for v in scope.values()),
            occurrences=sum(sum(v.values()) for v in scope.values()),conditions=12,
            initial_tasks=len(files)*3*2*12),**runner.source_snapshots())
    protocol['freeze_id']=hashlib.sha256(json.dumps(protocol,sort_keys=True,default=str).encode()).hexdigest()
    path.parent.mkdir(parents=True,exist_ok=True)
    write_json(path,protocol)
    write_json(path.parent/'frozen_files.json',dict(files=files))
    return protocol


def verify(path=DEFAULT):
    path=Path(path)
    protocol=json.loads(path.read_text(encoding='utf-8'))
    frozen=dict(protocol);identifier=frozen.pop('freeze_id')
    if identifier!=hashlib.sha256(json.dumps(frozen,sort_keys=True,default=str).encode()).hexdigest():
        raise ValueError('Manifesto de congelamento alterado')
    current=runner.source_snapshots()
    if any(protocol[k]!=current[k] for k in ('core_source_sha256','prompt_source_sha256')):
        raise ValueError('Codigo, dependencias ou prompts mudaram desde o congelamento')
    if protocol['runtime']!=runner.runtime_versions():raise ValueError('Runtime mudou desde o congelamento')
    for rel,expected in protocol['artifacts_sha256'].items():
        if sha(runner.BASE/rel)!=expected:raise ValueError(f'Insumo alterado: {rel}')
    for row in protocol['files']:
        if sha(runner.DEFAULT_DATASET/row['File'])!=row['sha256']:raise ValueError(f"Arquivo alterado: {row['File']}")
    if json.loads((path.parent/'frozen_files.json').read_text(encoding='utf-8'))['files']!=protocol['files']:
        raise ValueError('Selecao congelada alterada')
    return protocol


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create',action='store_true')
    parser.add_argument('--manifest',type=Path,default=DEFAULT)
    args=parser.parse_args()
    result=create(args.manifest) if args.create else verify(args.manifest)
    print(json.dumps(dict(freeze_id=result['freeze_id'],expected=result['expected']),indent=2))
