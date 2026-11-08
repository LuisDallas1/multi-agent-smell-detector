"""Diagnóstico pago mínimo: um arquivo, um especialista, sem F1 experimental."""
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

import run_experiment as runner
from generation_protocol import public_preflight, FROZEN_PROVIDERS, validate_controlled_limits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, help='caminho relativo dentro de dataset')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--model', choices=['deepseek-v4.1-flash','deepseek-v4.1-flash-1017'],
                        default='deepseek-v4.1-flash')
    parser.add_argument('--omit-common-appendix', action='store_true',
                        help='ablação diagnóstica apenas do texto comum; mantém Pydantic e demais controles')
    parser.add_argument('--provider', help='endpoint alternativo somente para diagnóstico; não altera o padrão')
    from core.supervisor.agent_config import AGENTS, PROMPT_TYPES
    parser.add_argument('--prompt-type', choices=PROMPT_TYPES, default='simple_v2')
    parser.add_argument('--agent', choices=list(AGENTS), default='empty_catch_block',
                        help='especialista isolado; sem F1 da arquitetura inteira')
    options = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y%m%d_%H%M%S_%f')
    output = options.output_dir or Path.home() / 'TCC-results/technical_checks' / stamp
    output.mkdir(parents=True, exist_ok=False)
    runner.write_json(output / 'selection.json', [options.file])
    args = runner.parser().parse_args([
        '--architecture', 'multiagent', '--model', options.model,
        '--files-from', str(output / 'selection.json'), '--all-files',
        '--prompt-type', options.prompt_type, '--generation-profile', 'experiment',
        '--response-format', 'json_mode', '--json-normalization', 'markdown_fence', '--no-evaluate'])
    args.diagnostic_agent = options.agent
    args.diagnostic_omit_common_appendix = options.omit_common_appendix
    args.diagnostic_provider_override = options.provider
    args.evaluate = False
    validate_controlled_limits(args)
    files = runner.select_files(args)
    if len(files) != 1:
        raise RuntimeError('Diagnóstico permite somente um arquivo')
    model = runner.MODELS[options.model]
    args.generation_config = public_preflight([model], {model: options.provider or FROZEN_PROVIDERS[model]},
        response_format='json_mode', json_normalization='markdown_fence', generation_profile='experiment',
        diagnostic_provider_override=bool(options.provider))
    for endpoint in args.generation_config[model]['matching_endpoints']:
        limit = endpoint.get('max_completion_tokens')
        if limit is not None and limit < args.max_retry_tokens:
            raise ValueError('Endpoint não suporta o teto de saída do diagnóstico')
    print('Endpoint: ' + args.generation_config[model]['provider'], flush=True)
    original_factory = runner.load_factory(args, [options.model])

    def diagnostic_factory(**kwargs):
        detector = original_factory(**kwargs)
        detector.agent_configs = {args.diagnostic_agent: detector.agent_configs[args.diagnostic_agent]}
        if options.omit_common_appendix:
            detector.agent_configs[args.diagnostic_agent]['diagnostic_omit_common_appendix'] = True
        return detector

    print('Diagnóstico isolado: 1 arquivo, 1 especialista, no máximo 2 chamadas; sem F1 experimental.', flush=True)
    summary = asyncio.run(runner.execute(args, files, [options.model], [options.prompt_type],
                                         output / 'run', factory=diagnostic_factory))
    print(f'Evidências: {output}', flush=True)
    print(f"Válidas: {summary[0]['valid_tasks']}/1; custo conhecido: {summary[0]['known_cost_usd']}", flush=True)


if __name__ == '__main__':
    main()
