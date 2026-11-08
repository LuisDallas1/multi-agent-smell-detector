"""Preflight publico e parametros explicitos do protocolo de geracao."""
import json
from urllib.request import urlopen

FROZEN_PARAMETERS = {
    'openai/gpt-6-luna': dict(provider='openai', temperature=None, seed=42),
    'deepseek/deepseek-v4.1-flash': dict(provider='deepinfra/fp8', temperature=0, seed=42),
    'deepseek/deepseek-v4.1-flash-1017': dict(provider='deepinfra/fp8', temperature=0, seed=42),
    'anthropic/claude-haiku-5.5': dict(provider='anthropic', temperature=None, seed=None),
}
FROZEN_PROVIDERS = {model: values['provider'] for model, values in FROZEN_PARAMETERS.items()}

CONTROLLED_LIMITS = dict(max_tokens=8192, max_retry_tokens=32768, response_retries=1,
                         max_retries=0, concurrency=2, timeout=120)
EXTENDED_LIMITS = dict(CONTROLLED_LIMITS, max_tokens=32768, max_retry_tokens=32768,
                       response_retries=0)
EXPERIMENT_LIMITS = {'multiagent': dict(CONTROLLED_LIMITS),
                     'single': dict(EXTENDED_LIMITS, response_retries=1)}
STANDARD_PROFILES = {'controlled', 'normalized', 'normalized_extended', 'experiment'}


def limits_for(profile, architecture='multiagent'):
    if profile == 'experiment':
        if architecture not in EXPERIMENT_LIMITS:
            raise ValueError('Arquitetura desconhecida')
        return dict(EXPERIMENT_LIMITS[architecture])
    return dict(EXTENDED_LIMITS if profile == 'normalized_extended' else CONTROLLED_LIMITS)


def validate_controlled_limits(args):
    """Impede que rodadas sob o mesmo perfil usem politicas de execucao diferentes."""
    if args.generation_profile not in STANDARD_PROFILES:
        return
    limits = limits_for(args.generation_profile, getattr(args, 'architecture', 'multiagent'))
    differences = {key: (getattr(args, key), expected) for key, expected in limits.items()
                   if getattr(args, key) != expected}
    normalized = args.generation_profile != 'controlled'
    expected_format = 'json_mode' if normalized else 'json_schema'
    expected_normalization = 'markdown_fence' if normalized else 'none'
    if getattr(args, 'response_format', expected_format) != expected_format:
        differences['response_format'] = (args.response_format, expected_format)
    if getattr(args, 'generation_seed', 42) != 42:
        differences['generation_seed'] = (args.generation_seed, 42)
    if getattr(args, 'json_normalization', expected_normalization) != expected_normalization:
        differences['json_normalization'] = (args.json_normalization, expected_normalization)
    if args.sequential:
        differences['sequential'] = (True, False)
    if differences:
        raise ValueError(f'Limites do perfil controlled alterados: {differences}. '
                         'Use --generation-profile custom para outro protocolo.')


def get_public_json(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def resolve_generation(model_id, provider, models, endpoints, *, reasoning=None, temperature=None, seed=42, response_format="json_schema", json_normalization="none", generation_profile=None, diagnostic_provider_override=False):
    """Resolve capacidades sem inventar equivalencia de esforco entre modelos."""
    if (response_format, json_normalization) not in {('json_schema', 'none'), ('json_mode', 'markdown_fence')}:
        raise ValueError('Politica de resposta nao padronizada')
    if generation_profile is not None:
        if generation_profile not in STANDARD_PROFILES:
            raise ValueError('Perfil de geracao desconhecido')
        expected = 'json_schema' if generation_profile == 'controlled' else 'json_mode'
        if response_format != expected:
            raise ValueError('Formato incompativel com perfil de geracao')
    frozen = FROZEN_PROVIDERS.get(model_id)
    if frozen and provider not in (None, frozen) and not diagnostic_provider_override:
        raise ValueError(f'Provedor congelado para {model_id}: {frozen}')
    override = bool(diagnostic_provider_override and frozen and provider and provider != frozen)
    provider = provider if override else (frozen or provider)
    if not provider:
        raise ValueError('O protocolo controlled exige --provider (preferencialmente o tag exato do endpoint).')
    model = next((m for m in models if m['id'] == model_id), None)
    if model is None:
        raise ValueError(f'Modelo ausente nos metadados publicos: {model_id}')
    capabilities = model.get('reasoning')
    if not capabilities or 'low' not in (capabilities.get('supported_efforts') or []):
        raise ValueError(f'{model_id} nao declara esforco low; modelo incompativel com controlled.')
    effective_reasoning = 'low'
    if reasoning is not None and reasoning != effective_reasoning:
        raise ValueError('controlled exige reasoning=low. '
                         'Use --generation-profile custom para outras condicoes.')
    policy = FROZEN_PARAMETERS.get(model_id)
    parameters = set(model.get('supported_parameters', []))
    effective_temperature = policy['temperature'] if policy else (0 if 'temperature' in parameters else None)
    effective_seed = policy['seed'] if policy else (seed if 'seed' in parameters else None)
    if seed != 42:
        raise ValueError('controlled exige generation_seed=42; Haiku omite seed por politica explicita.')
    if temperature is not None and temperature != effective_temperature:
        raise ValueError('Temperatura solicitada incompativel com controlled ou nao suportada pelo modelo.')
    required = {'response_format'}
    if response_format == 'json_schema':
        required.add('structured_outputs')
    if effective_seed is not None:
        required.add('seed')
    if effective_reasoning is not None:
        required.add('reasoning')
    if effective_temperature is not None:
        required.add('temperature')
    active = [e for e in endpoints if e.get('status') == 0]
    selected = [e for e in active if e.get('tag', '').lower() == provider.lower()]
    if not selected:
        selected = [e for e in active if e.get('provider_name', '').lower() == provider.lower()]
    tags = {e.get('tag') for e in selected}
    if len(tags) > 1:
        raise ValueError(f'Provedor ambiguo: escolha um endpoint exato entre {sorted(tags)}.')
    compatible = [e for e in selected if required <= set(e.get('supported_parameters', []))]
    if not compatible:
        raise ValueError(f'Nenhum endpoint ativo de {provider} declara suporte a {sorted(required)}.')
    canonical_provider = compatible[0].get('tag')
    if not canonical_provider:
        raise ValueError('Endpoint sem tag exato nos metadados publicos.')
    profile = ('experiment-v1' if generation_profile == 'experiment'
               else 'normalized-extended-v1' if generation_profile == 'normalized_extended'
               else 'normalized-v1' if response_format == 'json_mode' else 'controlled-v3')
    return dict(profile=profile, model=model_id, provider=canonical_provider,
                diagnostic_provider_override=override,
                reasoning=effective_reasoning, temperature=effective_temperature, seed=effective_seed,
                response_format=response_format, strict=response_format == 'json_schema',
                json_normalization=json_normalization,
                inference_schema_version='lean-v4-identity-location' if response_format == 'json_schema' else None,
                require_parameters=True,
                seed_note='42 solicitado' if effective_seed is not None else 'omitida: nao declarada pelo endpoint; politica congelada',
                reasoning_note='low solicitado; esforco computacional nao equivalente entre modelos',
                temperature_note='0 solicitado' if effective_temperature == 0 else 'nao suportada; parametro omitido',
                caveat='Mesmo nivel low e mesma seed nao garantem computacao equivalente ou determinismo.',
                model_reasoning_capabilities=capabilities,
                matching_endpoints=[{k: e.get(k) for k in ('provider_name', 'name', 'tag', 'quantization',
                                                          'supported_parameters', 'max_completion_tokens')}
                                    for e in compatible])


def public_preflight(model_ids, provider, **options):
    models = get_public_json('https://openrouter.ai/api/v1/models')['data']
    resolved = {}
    for model_id in model_ids:
        endpoints = get_public_json(f'https://openrouter.ai/api/v1/models/{model_id}/endpoints')['data']['endpoints']
        selected = provider.get(model_id) if isinstance(provider, dict) else provider
        resolved[model_id] = resolve_generation(model_id, selected, models, endpoints, **options)
    return resolved
