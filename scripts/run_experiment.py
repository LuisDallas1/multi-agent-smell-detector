"""Execucao do experimento multiagente com dataset e avaliacao por ocorrencia."""
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

BASE = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = BASE / 'dataset'
MODELS = {
    'gpt-6-luna': 'openai/gpt-6-luna',
    'deepseek-v4.1-flash': 'deepseek/deepseek-v4.1-flash',
    'gemini-3.5-flash-lite': 'google/gemini-3.5-flash-lite',
    'qwen3-coder-flash': 'qwen/qwen3-coder-flash',
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
    models = ap.add_mutually_exclusive_group()
    models.add_argument('--model', help='apelido registrado ou ID completo do OpenRouter')
    models.add_argument('--models', nargs='+', help='mesmos arquivos para todos os modelos')
    ap.add_argument('--prompt-type', '--prompts', choices=['simple_estevam', 'complete_estevam', 'complete_v2', 'all'], default=default_prompt)
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
    ap.add_argument('--temperature', type=float, default=0)
    ap.add_argument('--reasoning', choices=['default', 'off', 'minimal', 'low', 'medium', 'high'], default='default',
                    help='default nao envia parametro; rejeicoes nao provocam mudanca silenciosa')
    ap.add_argument('--provider', help='fixa provedor para toda a execucao, sem fallback')
    ap.add_argument('--output-dir', type=Path, help='diretorio novo; nunca sobrescreve uma rodada existente')
    ap.add_argument('--no-evaluate', action='store_true', help='desativa o F1 automatico quando ha manifesto e gabarito DPy')
    ap.add_argument('--evaluation-pairs', type=Path, help='CSV de pares para avaliacao')
    ap.add_argument('--ground-truth', type=Path, help='CSV de ocorrencias do gabarito DPy')
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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


async def execute(args, files, model_names, prompt_types, output, factory=None):
    if factory is None:
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
        from core.supervisor import CodeSmellSupervisor
        factory = CodeSmellSupervisor
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'sample.json', dict(dataset=args.dataset.resolve(), files=files, seed=args.seed))
    if getattr(args, 'evaluate', False):
        from evaluate_results import save_reference
        save_reference(output, args.dataset, files, args.evaluation_pairs, args.ground_truth)
    sources = list((BASE / 'src/core/prompts').rglob('*_prompt.py'))
    sources += [BASE / rel for rel in ('src/core/supervisor/supervisor.py', 'src/core/schemas/agent_response.py',
                                      'src/core/utils/detection_validator.py', 'src/core/smell_rules.py',
                                      'src/core/supervisor/agent_config.py',
                                      'scripts/experiment_evaluation.py', 'scripts/evaluate_results.py',
                                      'scripts/run_experiment.py')]
    write_json(output / 'protocol.json', dict(version='2.0',
        architecture='supervisor deterministico + 11 especialistas',
        transport='langchain_openai.ChatOpenAI', response='Pydantic via with_structured_output(json_mode)',
        primary_evaluation='correspondencia um a um nos pares positivos e negativos do manifesto',
        rules_version='2.0',
        source_sha256={str(path.relative_to(BASE)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}))
    write_json(output / 'config.json', dict(parameters=vars(args), models={m: MODELS.get(m, m) for m in model_names},
                                          prompt_types=prompt_types, architecture='supervisor-11-specialists',
                                          cost_note='Custos nao estimados com precos antigos. Tokens registrados; consultar cobranca do provedor.',
                                          metric_note='F1 automatico quando ha manifesto/gabarito, salvo --no-evaluate. Metricas separadas em evaluation_summary.json.'))
    summaries = []
    for model_index, name in enumerate(model_names):
        model_id = MODELS.get(name, name)
        for prompt_type in prompt_types:
            directory = output / f'{model_index+1:02d}_{name.replace("/", "__")}' / prompt_type
            directory.mkdir(parents=True)
            supervisor = factory(parallel=not args.sequential, prompt_type=prompt_type, model_name=model_id,
                                 max_tokens=args.max_tokens, temperature=args.temperature, timeout=args.timeout,
                                 max_retries=args.max_retries, concurrency=args.concurrency,
                                 reasoning=None if args.reasoning == 'default' else args.reasoning, provider=args.provider)
            supervisor.MAX_FILE_LINES = args.max_lines
            supervisor.MAX_FILE_SIZE_KB = args.max_file_kb
            for agent, config in supervisor.agent_configs.items():
                (directory / f'prompt_{agent}.txt').write_text(config['prompt'], encoding='utf-8')
            detections, metrics, totals = [], [], dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            for index, item in enumerate(files, 1):
                path = args.dataset.resolve() / item['File']
                started = time.monotonic()
                if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError(f'Arquivo mudou durante a rodada: {item["File"]}')
                try:
                    result = await supervisor.analyze_code(path.read_text(encoding='utf-8-sig'), str(path), item['File'].split('/')[0])
                except Exception as error:
                    result = dict(code_smells=[], error=type(error).__name__, agents_executed=0, token_usage={})
                elapsed = time.monotonic() - started
                record = dict(file=item['File'], elapsed_seconds=elapsed, result=result)
                with (directory / 'raw.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
                detections.extend(result.get('code_smells', []))
                usage = result.get('token_usage', {})
                for key in totals:
                    totals[key] += usage.get(key, 0)
                metrics.append(dict(file=item['File'], elapsed_seconds=elapsed, token_usage=usage,
                                    error=result.get('error'), agent_errors=result.get('agent_errors', {})))
                write_json(directory / f'results_{prompt_type}_prompts.json', detections)
                write_json(directory / f'file_metrics_{prompt_type}_prompts.json', metrics)
                print(f'[{name}/{prompt_type}] {index}/{len(files)} {item["File"]}: '
                      f'{len(result.get("code_smells", []))} deteccoes; '
                      f'{len(result.get("agent_errors", {}))} falhas de agente; {elapsed:.1f}s', flush=True)
                if result.get('fatal_error'):
                    write_json(output / 'failure.json', dict(status='aborted_configuration_error',
                        model=model_id, file=item['File'], error=result['fatal_error']))
                    raise RuntimeError('Execucao interrompida por falha de autenticacao/permissao. Confira a configuracao do OpenRouter.')
            summary = dict(model=model_id, prompt_type=prompt_type, total_files_analyzed=len(files),
                           total_smells_detected=len(detections), token_usage=totals,
                           files_with_errors=sum(bool(m['error'] or m['agent_errors']) for m in metrics),
                           agent_failures=sum(len(m['agent_errors']) for m in metrics), total_cost_usd=None)
            write_json(directory / f'token_usage_{prompt_type}_prompts.json', summary)
            summaries.append(summary)
    write_json(output / 'summary.json', summaries)
    print(f'Resultados: {output}')
    if getattr(args, 'evaluate', False):
        from evaluate_results import evaluate_run
        evaluate_run(output, args.dataset)
    return summaries


def main(default_prompt='complete_v2'):
    ap = parser(default_prompt)
    args = ap.parse_args()
    names = args.models or [args.model or 'gpt-6-luna']
    if len(set(names)) != len(names):
        ap.error('Modelos duplicados')
    for name in names:
        if name not in MODELS and not all(part and part not in ('.', '..') for part in name.split('/')):
            ap.error('ID de modelo invalido')
        if name not in MODELS and (name.count('/') != 1 or '\\' in name or ':' in name):
            ap.error('Use um apelido registrado ou ID completo provedor/modelo')
    prompt_type = args.prompt_type
    prompt_types = ['simple_estevam', 'complete_estevam', 'complete_v2'] if prompt_type == 'all' else [prompt_type]
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
    print(f'Dataset: {args.dataset.resolve()}')
    print(f'Arquivos: {len(files)}; modelos: {names}; prompts: {prompt_types}')
    print('F1: automatico por pares DPy.' if args.evaluate else 'F1: desativado ou sem manifesto/gabarito de ocorrencias.')
    print(f'Tarefas: {len(files)*len(names)*len(prompt_types)*11} especialistas; '
          f'concorrencia: {1 if args.sequential else args.concurrency}; retries adicionais: {args.max_retries}')
    for item in files:
        print(f'  {item["File"]} ({item["lines"]} linhas)')
    if args.dry_run:
        print('Dry-run: sem credenciais, chamadas de LLM ou escrita de resultados.')
        return
    stamp = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y%m%d_%H%M%S_%f')
    output = (args.output_dir or BASE / 'results/experiments' / stamp).resolve()
    if output.exists():
        ap.error('output-dir ja existe; use outro diretorio para preservar resultados')
    try:
        asyncio.run(execute(args, files, names, prompt_types, output))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
