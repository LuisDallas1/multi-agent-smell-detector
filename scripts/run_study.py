"""Coleta congelada: uma pasta por LLM, duas arquiteturas, dois prompts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import run_experiment as runner
from checkpointing import RunLock,write_json
from frozen_study import DEFAULT,verify
from generation_protocol import EXPERIMENT_LIMITS


def command(model,architecture,output,manifest,reference_root,*,dry_run=False):
    limits=EXPERIMENT_LIMITS[architecture]
    cmd=[sys.executable,'-B','-u',str(runner.BASE/'scripts/run_experiment.py'),
        '--model',model,'--architecture',architecture,'--prompt-type','paired',
        '--generation-profile','experiment','--response-format','json_mode',
        '--json-normalization','markdown_fence','--output-layout','flat',
        '--files-from',str(manifest),'--all-files','--output-dir',str(output)]
    for key,value in limits.items():cmd+=['--'+key.replace('_','-'),str(value)]
    if reference_root is not None:
        cmd+=['--evaluation-pairs',str(reference_root/'evaluation_pairs.csv'),
              '--ground-truth',str(reference_root/'evaluation_reference.csv')]
    if dry_run:cmd.append('--dry-run')
    return cmd


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,default=DEFAULT)
    parser.add_argument('--output-dir',type=Path,default=Path.home()/'TCC-results/final_experiment')
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--retry-interrupted',action='store_true')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if args.retry_interrupted and not args.resume:parser.error('--retry-interrupted exige --resume')
    protocol=verify(args.freeze)
    output=(args.resume or args.output_dir).resolve()
    if args.dry_run:
        print(json.dumps(dict(freeze_id=protocol['freeze_id'],expected=protocol['expected']),indent=2),flush=True)
        for architecture in protocol['architectures']:
            for model in protocol['models']:
                child=output/model/architecture
                print(f'{model}/{architecture}: simple_v2 + complete_v2 -> {child}',flush=True)
                subprocess.run(command(model,architecture,child,args.freeze.parent/'frozen_files.json',None,dry_run=True),check=True)
        return
    if args.resume:
        if not output.is_dir():parser.error('Pasta de retomada inexistente')
    else:output.mkdir(parents=True,exist_ok=False)
    with RunLock(output/'.study.lock'):
        if args.resume:
            saved=json.loads((output/'study.json').read_text(encoding='utf-8'))
            if saved['freeze_id']!=protocol['freeze_id']:raise ValueError('Rodada pertence a outro congelamento')
            for name,expected in saved['reference_sha256'].items():
                from frozen_study import sha
                if sha(output/name)!=expected:raise ValueError('Referencia da rodada alterada')
        else:
            from evaluate_results import save_reference
            from frozen_study import sha
            write_json(output/'sample.json',dict(dataset=str(runner.DEFAULT_DATASET),files=protocol['files'],seed=1))
            save_reference(output,runner.DEFAULT_DATASET,protocol['files'])
            write_json(output/'frozen_protocol.json',protocol)
            write_json(output/'study.json',dict(freeze_id=protocol['freeze_id'],
                models=protocol['models'],architectures=protocol['architectures'],prompts=protocol['prompts'],
                reference_sha256={name:sha(output/name) for name in ('sample.json','evaluation_pairs.csv','evaluation_reference.csv')}))
        write_json(output/'study_status.json',dict(status='running',all_tasks_valid=False))
        statuses=[]
        try:
            for architecture in protocol['architectures']:
                for model in protocol['models']:
                    verify(args.freeze)
                    child=output/model/architecture
                    status_path=child/'run_status.json'
                    status=json.loads(status_path.read_text(encoding='utf-8'))['status'] if status_path.exists() else None
                    if args.resume and status in ('valid','incomplete'):
                        statuses.append(status);continue
                    if args.resume and (child/'config.json').exists():
                        cmd=[sys.executable,'-B','-u',str(runner.BASE/'scripts/run_experiment.py'),'--resume',str(child)]
                        if args.retry_interrupted:cmd.append('--retry-interrupted')
                    else:cmd=command(model,architecture,child,output/'sample.json',output)
                    print(f'Coleta: {model}/{architecture}',flush=True)
                    result=subprocess.run(cmd)
                    status=json.loads(status_path.read_text(encoding='utf-8'))['status'] if status_path.exists() else 'failed'
                    statuses.append(status)
                    if result.returncode and status!='incomplete':raise RuntimeError(f'Coleta interrompida: {model}/{architecture}')
            verify(args.freeze)
            valid=len(statuses)==6 and all(s=='valid' for s in statuses)
            write_json(output/'study_status.json',dict(status='valid' if valid else 'incomplete',all_tasks_valid=valid))
        except BaseException:
            write_json(output/'study_status.json',dict(status='interrupted_or_aborted',all_tasks_valid=False))
            raise
        finally:
            interrupted=sys.exc_info()[0] is not None
            if any(output.glob('*/*/config.json')):
                from analyze_study import analyze
                try:
                    analyze(output,iterations=protocol['analysis']['bootstrap_iterations'],seed=protocol['analysis']['seed'])
                    state=json.loads((output/'study_status.json').read_text(encoding='utf-8'))
                    write_json(output/'study_status.json',dict(state,analysis_status='complete'))
                except Exception as error:
                    write_json(output/'analysis_failure.json',dict(error_type=type(error).__name__,message=str(error)))
                    state=json.loads((output/'study_status.json').read_text(encoding='utf-8'))
                    write_json(output/'study_status.json',dict(state,analysis_status='failed'))
                    print('Analise offline nao concluida; dados preservados. Execute analyze_study.py.',file=sys.stderr)
                    if not interrupted:raise RuntimeError('Analise incompleta; nao repetir inferencia para recalcular metricas') from error
        if not all(s=='valid' for s in statuses):raise SystemExit(1)


if __name__=='__main__':
    main()
