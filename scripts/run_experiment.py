"""Execucao de arquiteturas separadas com avaliacao compartilhada por ocorrencia."""
import argparse
import asyncio
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import platform
from importlib.metadata import version, PackageNotFoundError

BASE = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = BASE / 'dataset'
sys.path.insert(0, str(BASE / 'src'))
from checkpointing import FileStore, RunLock, VERSION as CHECKPOINT_VERSION, verify_resume, atomic_text
from checkpointing import write_json as durable_json
from core.prompt_strategies import resolve_prompt_types, SINGLE_PROMPT_SOURCES
from core.execution.evidence import EvidenceStore, VERSION as EVIDENCE_VERSION
from core.schemas.agent_response import CONTRACT_VERSION, FILTER_VERSION, INFERENCE_SCHEMA_VERSION
from result_layout import condition_directory, evidence_summaries
MODELS = {
    'gpt-6-luna': 'openai/gpt-6-luna',
    'deepseek-v4.1-flash': 'deepseek/deepseek-v4.1-flash',  # ID original, sem remapeamento
    'deepseek-v4.1-flash-1017': 'deepseek/deepseek-v4.1-flash-1017',
    'claude-haiku-5.5': 'anthropic/claude-haiku-5.5',
    'gpt-4o-mini': 'openai/gpt-4o-mini',
    'deepseek-v3': 'deepseek/deepseek-v3.2',
    'claude-sonnet': 'anthropic/claude-sonnet-4',
}


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('O valor deve ser positivo')
    return number


def parser(default_prompt='complete_v2'):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--architecture", choices=["multiagent", "single"], default="multiagent",
                    help="11 especialistas ou uma tarefa unica para todos os smells")
    models = ap.add_mutually_exclusive_group()
    models.add_argument('--model', help='apelido registrado ou ID completo do OpenRouter')
    models.add_argument('--models', nargs='+', help='mesmos arquivos para todos os modelos')
    ap.add_argument('--prompt-type', '--prompts', choices=['simple', 'complete', 'simple_v2', 'complete_v2', 'all', 'paired'], default=default_prompt,
                    help='paired executa somente simples e completo V2, pareados entre arquiteturas')
    ap.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    ap.add_argument('--env-file', type=Path, help='configuracao local carregada somente na execucao real, sem exibir valores')
    limit = ap.add_mutually_exclusive_group()
    limit.add_argument('--max-files', '--n', type=positive, help='padrao: 5 arquivos')
    limit.add_argument('--all-files', action='store_true', help='executar todos os arquivos elegiveis')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--files-from', type=Path, help='CSV File/file, lista JSON ou sample.json de outra rodada')
    ap.add_argument('--max-lines', type=positive, default=3000)
    ap.add_argument('--max-file-kb', type=positive, default=500)
    ap.add_argument('--max-tokens', type=positive, default=8192)
    ap.add_argument('--concurrency', type=positive, default=2, help='especialistas simultaneos; arquivos processados em sequencia')
    ap.add_argument('--sequential', action='store_true')
    ap.add_argument('--timeout', type=positive, default=120)
    ap.add_argument('--max-retries', type=int, choices=range(0, 6), default=0, help='repeticoes adicionais por chamada; padrao zero')
    ap.add_argument('--response-retries', type=int, choices=range(0, 4), default=1,
                    help='tentativas adicionais de resposta invalida; sem mudar prompt/modelo/raciocinio')
    ap.add_argument('--max-retry-tokens', type=positive, default=32768,
                    help='teto de saida nos retries por truncamento; padrao 32768')
    ap.add_argument('--allow-incomplete', action='store_true',
                    help='retorna sucesso mesmo com tarefas invalidas; status continua incomplete')
    ap.add_argument('--generation-profile', choices=['controlled', 'normalized', 'normalized_extended', 'experiment', 'custom'], default='controlled',
                    help='controlled valida capacidades publicas antes de carregar credenciais')
    ap.add_argument('--generation-seed', type=int, default=42, help='seed de geracao; independente da selecao de arquivos')
    ap.add_argument('--temperature', type=float, default=None)
    ap.add_argument('--response-format', choices=['json_mode', 'json_schema'], default='json_schema',
                    help='json_schema exige schema estrito no provedor; sem fallback para json_mode')
    ap.add_argument('--json-normalization', choices=['none', 'markdown_fence'], default='none',
                    help='custom/json_mode: remove apenas uma cerca Markdown externa; sem reparo')
    ap.add_argument('--omit-temperature', action='store_true',
                    help='somente custom: omite temperatura para modelos que nao a suportam')
    ap.add_argument('--reasoning', choices=['default', 'off', 'minimal', 'low', 'medium', 'high'], default=None,
                    help='default nao envia parametro; rejeicoes nao provocam mudanca silenciosa')
    ap.add_argument('--provider', help='fixa provedor para toda a execucao, sem fallback')
    ap.add_argument('--provider-for', action='append', default=[], metavar='MODELO=ENDPOINT',
                    help='provedor por modelo; repetivel para rodadas com multiplos modelos')
    ap.add_argument('--output-dir', type=Path, help='diretorio novo; nunca sobrescreve uma rodada existente')
    ap.add_argument('--output-layout', choices=['legacy', 'flat'], default='legacy',
                    help='flat: um unico modelo, com simple/complete_v2 diretamente na pasta da arquitetura')
    ap.add_argument('--no-evaluate', action='store_true', help='desativa o F1 automatico quando ha manifesto e gabarito DPy')
    ap.add_argument('--evaluation-pairs', type=Path, help='CSV de pares para avaliacao')
    ap.add_argument('--ground-truth', type=Path, help='CSV de ocorrencias do gabarito DPy')
    ap.add_argument('--resume', type=Path, help='retoma a mesma rodada usando sua configuração salva')
    ap.add_argument('--retry-interrupted', action='store_true', help='autoriza repetir arquivos interrompidos com possível cobrança anterior')
    ap.add_argument('--dry-run', action='store_true', help='lista arquivos e tarefas, sem .env, LLM ou criacao de resultados')
    return ap


def listed_files(path):
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as stream:
            data = list(csv.DictReader(stream))
    else:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict):
            data = data['files'] if 'files' in data else list(data)
    if not isinstance(data, list):
        raise ValueError('files-from deve conter uma lista de arquivos')
    return data


def select_files(args):
    dataset = args.dataset.resolve()
    if not dataset.is_dir():
        raise ValueError(f'Dataset inexistente: {dataset}')
    listed = listed_files(args.files_from) if args.files_from else None
    candidates = listed if listed is not None else sorted(
        p.relative_to(dataset).as_posix() for p in dataset.rglob('*.py')
        if 'ground_truth' not in p.relative_to(dataset).parts)
    found, seen = [], set()
    for row in candidates:
        rel = row.get('File', row.get('file')) if isinstance(row, dict) else row
        if not isinstance(rel, str):
            raise ValueError('Entrada de arquivo sem File/file')
        path = (dataset / rel.replace('\\', '/')).resolve()
        if not path.is_relative_to(dataset) or path.suffix != '.py':
            raise ValueError(f'Arquivo fora do dataset ou extensao invalida: {rel}')
        if path in seen:
            continue  # manifestos por par podem repetir o mesmo arquivo
        seen.add(path)
        if not path.is_file():
            raise ValueError(f'Arquivo listado nao existe: {rel}')
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if isinstance(row, dict) and row.get('sha256') and row['sha256'] != digest:
            raise ValueError(f'Arquivo mudou desde a selecao: {rel}')
        lines = len(content.decode('utf-8-sig').split('\n'))
        if lines > args.max_lines or len(content) > args.max_file_kb * 1024:
            if listed is not None:
                raise ValueError(f'Arquivo listado excede max-lines/max-file-kb: {rel}')
            continue
        found.append(dict(File=path.relative_to(dataset).as_posix(), sha256=digest, lines=lines, bytes=len(content)))
    count = None if args.all_files else args.max_files or 5
    if count is not None and len(found) > count:
        found = random.Random(args.seed).sample(found, count)
    if not found:
        raise ValueError('Nenhum arquivo elegivel')
    return sorted(found, key=lambda r: r['File'])


def write_json(path, value):
    durable_json(path, value)


def runtime_versions():
    packages = {}
    for name in ('langchain-openai', 'langchain-core', 'openai', 'pydantic', 'httpx'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return dict(python=platform.python_version(), system=platform.system(), packages=packages)


def summarize_tasks(model, prompt_type, files, agents, metrics, detections):
    """Nao confunde ausencia de erro com resposta valida; inclui tarefas nao executadas."""
    by_file = {m['file']: m for m in metrics}
    tasks = []
    attempts = []
    totals = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    for file in files:
        metric = by_file.get(file['File'])
        if metric:
            for key in totals:
                totals[key] += metric.get('token_usage', {}).get(key, 0)
        for agent in agents:
            detail = (metric or {}).get('agent_metrics', {}).get(agent, {})
            error = ((metric or {}).get('agent_errors', {}).get(agent)
                     or (metric or {}).get('error') or detail.get('error'))
            history = detail.get('attempts', [])
            attempts.extend(history)
            if metric is None:
                status, error = 'not_executed', 'NotExecuted'
            elif error:
                status = 'skipped' if error.startswith('Skipped') else 'failed'
            elif not history or history[-1].get('error'):
                status, error = 'failed', 'MissingValidResponseRecord'
            else:
                status = 'valid'
            tasks.append(dict(file=file['File'], agent=agent, status=status, error=error, attempts=len(history)))
    valid = sum(t['status'] == 'valid' for t in tasks)
    known_cost = sum(a.get('cost_usd') or 0 for a in attempts)
    complete_cost = (len(by_file) == len(files) and bool(attempts)
                     and all(a.get('cost_usd') is not None for a in attempts)
                     and all(t['attempts'] > 0 for t in tasks))
    return dict(model=model, prompt_type=prompt_type, total_files_analyzed=len(metrics),
                planned_files=len(files), total_smells_detected=detections, token_usage=totals,
                files_with_errors=sum(bool(m.get('error') or m.get('agent_errors')) for m in metrics),
                agent_failures=sum(t['status'] == 'failed' for t in tasks),
                expected_tasks=len(tasks), valid_tasks=valid,
                not_executed_tasks=sum(t['status'] in ('not_executed', 'skipped') for t in tasks),
                valid_response_rate=valid/len(tasks) if tasks else 0,
                status='valid' if valid == len(tasks) and tasks else 'incomplete',
                total_cost_usd=known_cost if complete_cost else None,
                known_cost_usd=known_cost, cost_complete=complete_cost,
                cost_source='OpenRouter usage.cost; includes retries; missing remains null',
                normalized_responses=sum(bool(a.get('normalization_applied')) for a in attempts),
                attempted_calls=len(attempts), failed_attempts=sum(bool(a.get('error')) for a in attempts),
                usage_complete=bool(attempts) and all(a.get('usage_available') for a in attempts)
                               and len(by_file) == len(files) and all(t['attempts'] > 0 for t in tasks),
                task_statuses=tasks)


def source_snapshots():
    """Separa código fixo de fontes dos prompts; nunca inclui credenciais."""
    paths = list((BASE / 'src').rglob('*.py')) + list((BASE / 'scripts').glob('*.py'))
    paths += [BASE / name for name in ('pyproject.toml', 'uv.lock', '.python-version', '.gitattributes')]
    core, prompts = {}, {}
    for path in sorted(set(paths)):
        rel = path.relative_to(BASE)
        target = prompts if 'prompts' in rel.parts else core
        target[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    return dict(core_source_sha256=core, prompt_source_sha256=prompts, core_fingerprint=fingerprint)


def load_factory(args, model_names):
    if args.generation_profile in {'controlled', 'normalized', 'normalized_extended', 'experiment'} and not getattr(args, 'generation_config', None):
        raise RuntimeError('Protocolo controlled requer preflight de geracao antes das credenciais.')
    # Carga interna apenas durante execucao real; nunca imprime credenciais.
    from dotenv import dotenv_values
    env_path = args.env_file or BASE / '.env'
    if args.env_file and not env_path.is_file():
        raise RuntimeError('Arquivo de configuracao indicado nao existe')
    for key, value in dotenv_values(env_path).items():
        if value is not None:
            os.environ.setdefault(key, value)
    if not os.environ.get('OPENROUTER_API_KEY'):
        raise RuntimeError('OPENROUTER_API_KEY ausente no ambiente/configuracao local')
    os.environ.setdefault('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    os.environ.setdefault('OPENROUTER_API_MODEL', MODELS.get(model_names[0], model_names[0]))
    sys.path.insert(0, str(BASE / 'src'))
    if args.architecture == "single":
        from core.single_agent import SingleAgentDetector
        factory = SingleAgentDetector
    else:
        from core.supervisor import CodeSmellSupervisor
        factory = CodeSmellSupervisor
    return factory


def apply_uncertainty(summary, store):
    events = store.uncertainty()
    summary['interrupted_files'] = events
    if events:
        summary.update(cost_complete=False, total_cost_usd=None, usage_complete=False)
    return summary


def rebuild_projection(directory, prompt_type, files, records):
    ordered = [records[item['File']] for item in files if item['File'] in records]
    detections = [d for record in ordered for d in record['result'].get('code_smells', [])]
    metrics = [dict(file=record['file'], elapsed_seconds=record['elapsed_seconds'],
                    token_usage=record['result'].get('token_usage', {}),
                    error=record['result'].get('error'),
                    agent_errors=record['result'].get('agent_errors', {}),
                    agent_metrics=record['result'].get('agent_metrics', {})) for record in ordered]
    atomic_text(directory / 'raw.jsonl', ''.join(json.dumps(record, ensure_ascii=False, default=str)+'\n' for record in ordered))
    write_json(directory / f'results_{prompt_type}_prompts.json', detections)
    write_json(directory / f'file_metrics_{prompt_type}_prompts.json', metrics)
    return detections, metrics


async def execute(args, files, model_names, prompt_types, output, factory=None):
    if getattr(args, 'output_layout', 'legacy') == 'flat' and len(model_names) != 1:
        raise ValueError('Layout flat exige somente um modelo por pasta de arquitetura')
    if (factory is None and args.generation_profile in {'controlled', 'normalized', 'normalized_extended', 'experiment'}
            and not getattr(args, 'generation_config', None)):
        raise RuntimeError('Protocolo requer preflight antes das credenciais.')
    output = Path(output)
    resuming = bool(getattr(args, 'resume', None))
    if not resuming:
        output.mkdir(parents=True, exist_ok=False)
    elif not output.is_dir():
        raise RuntimeError('Pasta de retomada não existe')
    with RunLock(output / '.run.lock'):
        if resuming:
            verify_resume(output, source_snapshots(), files, model_names, prompt_types, args.architecture, vars(args))
            saved_runtime = json.loads((output / 'protocol.json').read_text())['runtime']
            if saved_runtime != runtime_versions():
                raise RuntimeError('Python ou dependências mudaram; retomada bloqueada')
            for index, name in enumerate(model_names):
                for prompt in prompt_types:
                    directory = condition_directory(output, index, name, prompt, getattr(args, 'output_layout', 'legacy'))
                    if directory.exists():
                        EvidenceStore.verify(directory)  # Integrity checked before any replay/API call.
                        FileStore(directory, files).recover(getattr(args, 'retry_interrupted', False))
        resources = []
        try:
            return await _execute(args, files, model_names, prompt_types, output, factory, resources)
        except BaseException as error:
            status_path = output / 'run_status.json'
            status = json.loads(status_path.read_text()).get('status') if status_path.exists() else None
            if status not in {'valid', 'incomplete', 'aborted_configuration_error'}:
                write_json(status_path, dict(status='interrupted' if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)) else 'failed',
                    all_tasks_valid=False, note='Checkpoints concluídos preservados; arquivos em voo exigem reconhecimento explícito.'))
            raise
        finally:
            try:
                for supervisor, evidence, directory in resources:
                    write_json(directory / 'evidence_summary.json', evidence.summarize(directory))
                inventory = []
                for path in evidence_summaries(output):
                    summary = json.loads(path.read_text(encoding='utf-8'))
                    inventory.append(dict(directory=str(path.parent.relative_to(output)),
                        events=summary['event_count'], attempts=len(summary['attempts']),
                        uncommitted_temporary_files=summary['uncommitted_temporary_files'],
                        known_cost_usd=summary['known_cost_usd'],
                        uncommitted_known_cost_usd=summary['uncommitted_known_cost_usd']))
                write_json(output / 'evidence_inventory.json', dict(version=EVIDENCE_VERSION,
                    combinations=inventory,
                    note='Includes previous interrupted sessions. Journal costs overlap checkpoint costs; do not sum them.'))
            except BaseException:
                write_json(output / 'run_status.json', dict(status='failed_evidence', all_tasks_valid=False,
                    note='Arquivo de evidencias/resumo nao confirmado. Dados ja gravados foram preservados.'))
                raise
            finally:
                for supervisor, evidence, directory in resources:
                    closer = getattr(supervisor, 'close_evidence_client', None)
                    if closer is not None:
                        await closer()


async def _execute(args, files, model_names, prompt_types, output, factory=None, resources=None):
    if factory is None:
        factory = load_factory(args, model_names)
    resuming = bool(getattr(args, 'resume', None))
    write_json(output / 'run_status.json', dict(status='running', all_tasks_valid=False))
    if not resuming:
        write_json(output / 'sample.json', dict(dataset=args.dataset.resolve(), files=files, seed=args.seed))
        if getattr(args, 'evaluate', False):
            from evaluate_results import save_reference
            save_reference(output, args.dataset, files, args.evaluation_pairs, args.ground_truth)
        snapshots = source_snapshots()
        write_json(output / 'protocol.json', dict(version='2.0',
            architecture=args.architecture,
            diagnostic_only=bool(getattr(args, 'diagnostic_agent', None)),
            diagnostic_agent=getattr(args, 'diagnostic_agent', None),
            prompt_sources={kind: SINGLE_PROMPT_SOURCES.get(kind, kind) for kind in prompt_types},
            transport='langchain_openai.ChatOpenAI', response=f'Pydantic via with_structured_output({args.response_format})',
            response_validation='include_raw, finish_reason=stop, JSON estrito, envelope consistente e Pydantic',
            primary_evaluation='correspondencia um a um nos pares positivos e negativos do manifesto',
            rules_version='2.0', response_validation_version=CONTRACT_VERSION,
            prediction_filter_version=FILTER_VERSION,
            occurrence_response_policy='Identity/location and qualitative evidence; no exact measures or semantic postfilter; identifier_name and number retained',
            long_statement_policy='DPy >80; classification/location without an exact self-reported length or numeric post-filter',
            error_policy_version='sdk-envelope-v1', inference_schema_version=INFERENCE_SCHEMA_VERSION if args.response_format == 'json_schema' else None,
            evidence_version=EVIDENCE_VERSION,
            evidence_policy='Per-attempt events, flush/close and atomic replacement; HTTP bodies before SDK parsing, parsed values and filter decisions; no credentials.',
            persistence_policy='flush-close-atomic-replace-v1',
            runtime=runtime_versions(),
            **snapshots))
        write_json(output / 'config.json', dict(parameters=vars(args), models={m: MODELS.get(m, m) for m in model_names},
                                              prompt_types=prompt_types, architecture=args.architecture, checkpoint_version=CHECKPOINT_VERSION,
                                              prompt_sources={kind: SINGLE_PROMPT_SOURCES.get(kind, kind) for kind in prompt_types},
                                              cost_note='usage.cost por tentativa; total somente com cobertura completa. known_cost_usd e parcial quando cost_complete=false. Sem estimativa silenciosa.',
                                              metric_note='F1 automatico quando ha manifesto/gabarito, salvo --no-evaluate. Metricas separadas em evaluation_summary.json.'))
        write_json(output / 'generation_protocol.json', getattr(args, 'generation_config', {}) or {
            MODELS.get(name, name): dict(profile='custom', provider=args.provider, reasoning=args.reasoning,
                                       temperature=args.temperature, seed=None,
                                       response_format=args.response_format, json_normalization=args.json_normalization,
                                       note='Configuracao exploratoria; fora do perfil controlled.') for name in model_names})
        if getattr(args, 'dpy_audit', None):
            write_json(output / 'dpy_audit.json', args.dpy_audit)
    summaries = []
    for model_index, name in enumerate(model_names):
        model_id = MODELS.get(name, name)
        for prompt_type in prompt_types:
            directory = condition_directory(output, model_index, name, prompt_type, getattr(args, 'output_layout', 'legacy'))
            directory.mkdir(parents=True, exist_ok=resuming)
            evidence = EvidenceStore(directory)
            generation = getattr(args, 'generation_config', {}).get(model_id, {})
            supervisor = factory(parallel=not args.sequential, prompt_type=prompt_type, model_name=model_id,
                                 max_tokens=args.max_tokens,
                                 temperature=generation.get('temperature', args.temperature), timeout=args.timeout,
                                 max_retries=args.max_retries, concurrency=args.concurrency,
                                 reasoning=generation.get('reasoning', None if args.reasoning == 'default' else args.reasoning),
                                 provider=generation.get('provider', args.provider),
                                 response_retries=args.response_retries, max_retry_tokens=args.max_retry_tokens,
                                 seed=generation.get('seed'), require_parameters=(generation.get('require_parameters', False) or args.response_format == 'json_schema'),
                                 response_format=args.response_format, json_normalization=args.json_normalization,
                                 evidence_store=evidence)
            supervisor.evidence_store = evidence
            if resources is not None:
                resources.append((supervisor, evidence, directory))
            supervisor.MAX_FILE_LINES = args.max_lines
            supervisor.MAX_FILE_SIZE_KB = args.max_file_kb
            for agent, config in supervisor.agent_configs.items():
                prompt_path = directory / f'prompt_{agent}.txt'
                if resuming and prompt_path.exists() and prompt_path.read_text(encoding='utf-8') != config['prompt']:
                    raise RuntimeError('Prompt salvo foi alterado')
                atomic_text(prompt_path, config['prompt'])
                if args.response_format == 'json_schema' and config.get('schema') is not None:
                    write_json(directory / f'schema_{agent}.json', supervisor._strict_response_schema(config['schema']))
                if config.get('schema') is not None:
                    write_json(directory / f'validation_schema_{agent}.json', config['schema'].model_json_schema(by_alias=False))
            store = FileStore(directory, files)
            records = store.recover(getattr(args, 'retry_interrupted', False))
            detections, metrics = rebuild_projection(directory, prompt_type, files, records)
            for index, item in enumerate(files, 1):
                if item['File'] in records:
                    continue
                path = args.dataset.resolve() / item['File']
                started = time.monotonic()
                source = path.read_bytes()
                if hashlib.sha256(source).hexdigest() != item['sha256']:
                    raise ValueError(f'Arquivo mudou durante a rodada: {item["File"]}')
                store.start(item)
                code = source.decode('utf-8-sig')
                evidence.start_file(item['File'], source, code)
                try:
                    result = await supervisor.analyze_code(code, str(path), item['File'].split('/')[0])
                except Exception as error:
                    import traceback
                    evidence.emit('file_exception', dict(exception_type=type(error).__name__,
                        exception_message=str(error), traceback=''.join(traceback.format_exception(error))))
                    result = dict(code_smells=[], error=type(error).__name__, agents_executed=0, token_usage={},
                                  agent_metrics=dict(getattr(supervisor, 'agent_metrics', {})),
                                  agent_errors=dict(getattr(supervisor, 'agent_errors', {})))
                elapsed = time.monotonic() - started
                record = dict(file=item['File'], elapsed_seconds=elapsed, result=result)
                evidence.emit('file_completed', record)
                store.commit(record)
                evidence.emit('file_committed', dict(file=item['File']))
                records[item['File']] = record
                detections, metrics = rebuild_projection(directory, prompt_type, files, records)
                print(f'[{name}/{prompt_type}] {index}/{len(files)} {item["File"]}: '
                      f'{len(result.get("code_smells", []))} deteccoes; '
                      f'{len(result.get("agent_errors", {}))} falhas de agente; {elapsed:.1f}s', flush=True)
                checkpoint = summarize_tasks(model_id, prompt_type, files, supervisor.agent_configs, metrics, len(detections))
                checkpoint['architecture'] = args.architecture
                apply_uncertainty(checkpoint, store)
                write_json(directory / f'token_usage_{prompt_type}_prompts.json', checkpoint)
                write_json(output / 'summary.json', summaries + [checkpoint])
                if result.get('fatal_error'):
                    write_json(output / 'run_status.json', dict(status='aborted_configuration_error', all_tasks_valid=False))
                    if getattr(args, 'evaluate', False):
                        from evaluate_results import evaluate_run
                        evaluate_run(output, args.dataset)

                    write_json(output / 'failure.json', dict(status='aborted_configuration_error',
                        model=model_id, file=item['File'], error=result['fatal_error']))
                    raise RuntimeError('Execucao interrompida por falha de autenticacao/permissao. Confira a configuracao do OpenRouter.')
            summary = summarize_tasks(model_id, prompt_type, files, supervisor.agent_configs, metrics, len(detections))
            summary['architecture'] = args.architecture
            apply_uncertainty(summary, store)
            write_json(directory / f'token_usage_{prompt_type}_prompts.json', summary)
            summaries.append(summary)
    write_json(output / 'summary.json', summaries)
    print(f'Resultados: {output}')
    if getattr(args, 'evaluate', False):
        from evaluate_results import evaluate_run
        evaluate_run(output, args.dataset)
    incomplete = any(s['status'] != 'valid' for s in summaries)
    write_json(output / 'run_status.json', dict(status='incomplete' if incomplete else 'valid',
               all_tasks_valid=not incomplete, note='Validade tecnica nao significa deteccao correta.'))
    if incomplete and not args.allow_incomplete:
        raise RuntimeError('Rodada incompleta: ha respostas invalidas. Resultados e F1 operacional foram preservados; '
                           'a rodada nao atende ao criterio de 100% de validade tecnica.')
    return summaries


def restore_resume_args(request):
    output = request.resume.resolve()
    saved = json.loads((output / 'config.json').read_text(encoding='utf-8'))
    if saved.get('checkpoint_version') != CHECKPOINT_VERSION:
        raise RuntimeError('Rodada sem checkpoints retomáveis; arquivos antigos serão preservados')
    if saved['parameters'].get('diagnostic_agent'):
        raise RuntimeError('Diagnóstico isolado não é uma coleta completa; não use a retomada geral')
    args = argparse.Namespace(**saved['parameters'])
    for key in ('dataset', 'env_file', 'files_from', 'output_dir', 'evaluation_pairs', 'ground_truth'):
        value = getattr(args, key, None)
        setattr(args, key, Path(value) if value else None)
    args.dataset = Path(json.loads((output / 'sample.json').read_text())['dataset'])
    args.files_from = output / 'sample.json'
    args.all_files, args.max_files = True, None
    args.output_dir = args.resume = output
    args.retry_interrupted = request.retry_interrupted
    if getattr(args, 'evaluate', False):
        args.evaluation_pairs = output / 'evaluation_pairs.csv'
        args.ground_truth = output / 'evaluation_reference.csv'
    return args


def main(default_prompt='complete_v2'):
    ap = parser(default_prompt)
    args = ap.parse_args()
    if args.resume:
        provided = {token.split('=')[0] for token in sys.argv[1:] if token.startswith('-')}
        if provided - {'--resume', '--retry-interrupted'}:
            ap.error('Retomada aceita somente --resume e, opcionalmente, --retry-interrupted; usa os parâmetros salvos.')
        try:
            args = restore_resume_args(args)
        except (OSError, ValueError, RuntimeError) as error:
            ap.error(str(error))
    elif args.retry_interrupted:
        ap.error('--retry-interrupted exige --resume')
    if args.json_normalization != 'none' and (args.generation_profile not in {'custom', 'normalized', 'normalized_extended', 'experiment'} or args.response_format != 'json_mode'):
        ap.error('Normalizacao Markdown exige custom ou perfil normalized e json_mode')
    if args.max_retry_tokens < args.max_tokens:
        ap.error('--max-retry-tokens deve ser >= --max-tokens')
    if args.omit_temperature and (args.generation_profile != 'custom' or args.temperature is not None):
        ap.error('--omit-temperature exige custom e nao pode ser combinado com --temperature')
    from generation_protocol import validate_controlled_limits
    try:
        validate_controlled_limits(args)
    except ValueError as error:
        ap.error(str(error))
    names = args.models or [args.model or 'gpt-6-luna']
    if len(set(names)) != len(names):
        ap.error('Modelos duplicados')
    for name in names:
        if name not in MODELS and not all(part and part not in ('.', '..') for part in name.split('/')):
            ap.error('ID de modelo invalido')
        if name not in MODELS and (name.count('/') != 1 or '\\' in name or ':' in name):
            ap.error('Use um apelido registrado ou ID completo provedor/modelo')
    prompt_type = args.prompt_type
    try:
        prompt_types = resolve_prompt_types(args.architecture, prompt_type)
    except ValueError as error:
        ap.error(str(error))
    try:
        files = select_files(args)
    except (ValueError, OSError) as error:
        ap.error(str(error))
    pairs_path = args.evaluation_pairs or args.dataset / 'ground_truth/evaluation_pairs.csv'
    truth_path = args.ground_truth or args.dataset / 'ground_truth/dpy_implementation_smells_sample.csv'
    if not args.no_evaluate and (args.evaluation_pairs or args.ground_truth) and not (pairs_path.is_file() and truth_path.is_file()):
        ap.error('Manifesto ou gabarito indicado nao existe')
    args.evaluate = not args.no_evaluate and pairs_path.is_file() and truth_path.is_file()
    if args.evaluate:
        # Valida escopo e contagens antes de qualquer carga de credenciais/chamada.
        from experiment_evaluation import Reference, read_csv
        selected = {r['File'] for r in files}
        scope = {}
        for row in read_csv(pairs_path):
            if row['File'] in selected:
                smell = row['Smell'].strip().lower()
                if smell in scope.setdefault(row['File'], {}):
                    ap.error('Par duplicado no manifesto')
                scope[row['File']][smell] = int(row['Count'])
        if set(scope) != selected:
            ap.error('Ha arquivos selecionados sem pares no manifesto de avaliacao')
        Reference(args.dataset, truth_path).validate(scope)
        from audit_dpy import audit
        args.dpy_audit = audit(args.dataset, pairs_path, truth_path, BASE / 'dataset/ground_truth/dpy_raw', selected)
        if not args.dpy_audit['passed']:
            ap.error('Auditoria DPy falhou: ' + json.dumps(args.dpy_audit['issues'][:5], ensure_ascii=False))
    print(f'Dataset: {args.dataset.resolve()}')
    print(f'Arquivos: {len(files)}; modelos: {names}; prompts: {prompt_types}')
    print('F1: automatico por pares DPy.' if args.evaluate else 'F1: desativado ou sem manifesto/gabarito de ocorrencias.')
    print(f'Arquitetura: {args.architecture}; tarefas: {len(files)*len(names)*len(prompt_types)*(1 if args.architecture == "single" else 11)}; '
          f'concorrencia: {1 if args.sequential else args.concurrency}; retries SDK: {args.max_retries}; '
          f'retries de resposta: {args.response_retries}; teto de tokens: {args.max_retry_tokens}')
    for item in files:
        print(f'  {item["File"]} ({item["lines"]} linhas)')
    if args.dry_run:
        print('Dry-run: sem credenciais, chamadas de LLM ou escrita de resultados. '
              f'Perfil {args.generation_profile}: formato={args.response_format}, normalizacao={args.json_normalization}; '
              'capacidades publicas serao verificadas na execucao real.')
        return
    try:
        if args.generation_profile in {'controlled', 'normalized', 'normalized_extended', 'experiment'}:
            from generation_protocol import public_preflight, FROZEN_PROVIDERS
            providers = {MODELS.get(n, n): args.provider or FROZEN_PROVIDERS.get(MODELS.get(n, n)) for n in names}
            for pair in args.provider_for:
                if '=' not in pair:
                    ap.error('--provider-for requer MODELO=ENDPOINT')
                name, provider = pair.split('=', 1)
                key = MODELS.get(name, name)
                if key not in providers or not provider:
                    ap.error('--provider-for deve indicar um modelo da rodada e endpoint nao vazio')
                providers[key] = provider
            if any(not provider for provider in providers.values()):
                ap.error('controlled exige --provider ou --provider-for para cada modelo.')
            args.generation_config = public_preflight([MODELS.get(n, n) for n in names], providers,
                reasoning=args.reasoning, temperature=args.temperature, seed=args.generation_seed,
                response_format=args.response_format, json_normalization=args.json_normalization,
                generation_profile=args.generation_profile)
            for model_id, config in args.generation_config.items():
                for endpoint in config['matching_endpoints']:
                    limit = endpoint.get('max_completion_tokens')
                    if limit is not None and limit < args.max_retry_tokens:
                        ap.error(f'Endpoint {endpoint.get("tag")} nao suporta o teto de tokens configurado.')
                print(f'Geracao {model_id}: reasoning={config["reasoning"]}; '
                      f'temperature={config["temperature"]}; seed={config["seed"]}; provider={config["provider"]}')
        else:
            if args.provider_for:
                ap.error('--provider-for pertence ao perfil controlled; em custom use --provider.')
            args.temperature = None if args.omit_temperature else (0 if args.temperature is None else args.temperature)
            args.reasoning = args.reasoning or 'default'
            args.generation_config = {}
        if args.response_format == 'json_schema' and args.generation_profile == 'custom':
            from generation_protocol import get_public_json
            for name in names:
                model_id = MODELS.get(name, name)
                generation = args.generation_config.get(model_id, {})
                provider = generation.get('provider', args.provider)
                endpoints = get_public_json(f'https://openrouter.ai/api/v1/models/{model_id}/endpoints')['data']['endpoints']
                matching = [e for e in endpoints if e.get('status') == 0 and e.get('tag') == provider
                            and {'structured_outputs', 'response_format'} <= set(e.get('supported_parameters', []))]
                if not matching:
                    raise ValueError('JSON Schema exige endpoint exato ativo com structured_outputs e response_format')
                if not generation:
                    generation = dict(profile='custom', provider=provider, reasoning=args.reasoning,
                                      temperature=args.temperature, seed=None)
                    args.generation_config[model_id] = generation
                generation.update(response_format='json_schema', require_parameters=True,
                    schema_endpoints=[{k: e.get(k) for k in ('tag', 'supported_parameters', 'max_completion_tokens')} for e in matching])
    except (ValueError, OSError, KeyError) as error:
        ap.error(f'Preflight de geracao falhou: {error}')
    stamp = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y%m%d_%H%M%S_%f')
    output = (args.output_dir or Path.home() / 'TCC-results/experiments' / args.architecture / stamp).resolve()
    if output.exists() and not args.resume:
        ap.error('output-dir ja existe; use outro diretorio para preservar resultados')
    try:
        asyncio.run(execute(args, files, names, prompt_types, output))
    except KeyboardInterrupt:
        if output.is_dir():
            write_json(output / 'run_status.json', dict(status='interrupted', all_tasks_valid=False,
                note='Resumo preservado ate o ultimo arquivo concluido; chamadas em voo podem ter cobranca nao registrada.'))
        print('Execucao interrompida; checkpoints preservados. Chamadas em voo podem ter custo desconhecido.', file=sys.stderr)
        raise SystemExit(130)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
