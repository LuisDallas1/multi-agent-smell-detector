"""Protocolo de geracao sem rede, credenciais ou inferencia."""
from pathlib import Path
import sys
import asyncio
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from generation_protocol import resolve_generation, public_preflight, validate_controlled_limits, CONTROLLED_LIMITS, EXTENDED_LIMITS
import run_experiment


class GenerationProtocolTests(unittest.TestCase):
    def test_experiment_budget_by_architecture_and_equal_retry_policy(self):
        for architecture, initial, ceiling in [('multiagent', 8192, 32768), ('single', 32768, 32768)]:
            args = run_experiment.parser().parse_args([
                '--architecture', architecture, '--generation-profile', 'experiment',
                '--response-format', 'json_mode', '--json-normalization', 'markdown_fence',
                '--max-tokens', str(initial), '--max-retry-tokens', str(ceiling)])
            validate_controlled_limits(args)
            self.assertEqual(args.response_retries, 1)
            args.response_retries = 0
            with self.assertRaises(ValueError):
                validate_controlled_limits(args)

    def test_experiment_generation_is_versioned_and_preserves_sampling(self):
        models, endpoints = self.data()
        result = resolve_generation('test/model', 'test/fp8', models, endpoints,
            generation_profile='experiment', response_format='json_mode', json_normalization='markdown_fence')
        self.assertEqual(result['profile'], 'experiment-v1')
        self.assertEqual((result['reasoning'], result['temperature'], result['seed']), ('low', 0, 42))

    def test_extended_profile_is_explicit_and_frozen_for_both_architectures(self):
        for architecture in ('single', 'multiagent'):
            args = run_experiment.parser().parse_args([
                '--architecture', architecture, '--generation-profile', 'normalized_extended',
                '--response-format', 'json_mode', '--json-normalization', 'markdown_fence',
                '--max-tokens', '32768', '--max-retry-tokens', '32768', '--response-retries', '0'])
            validate_controlled_limits(args)
            self.assertEqual(args.max_tokens, 32768)
            self.assertEqual(args.response_retries, 0)
            args.response_retries = 1
            with self.assertRaises(ValueError):
                validate_controlled_limits(args)
        unchanged = run_experiment.parser().parse_args([])
        validate_controlled_limits(unchanged)
        self.assertEqual(unchanged.max_tokens, 8192)
        self.assertEqual(unchanged.response_retries, 1)

    def test_extended_keeps_sampling_provider_and_low_without_invented_thinking_cap(self):
        models, endpoints = self.data()
        kwargs = dict(response_format='json_mode', json_normalization='markdown_fence')
        before = resolve_generation('test/model', 'test/fp8', models, endpoints, **kwargs)
        after = resolve_generation('test/model', 'test/fp8', models, endpoints,
                                   generation_profile='normalized_extended', **kwargs)
        self.assertEqual(after['profile'], 'normalized-extended-v1')
        for key in ('provider', 'reasoning', 'temperature', 'seed', 'response_format', 'json_normalization'):
            self.assertEqual(before[key], after[key], key)
        self.assertNotIn('reasoning_max_tokens', after)
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints,
                               generation_profile='normalized_extended')

    def test_extended_requires_preflight_before_loading_credentials(self):
        args = run_experiment.parser().parse_args(['--generation-profile', 'normalized_extended'])
        with self.assertRaisesRegex(RuntimeError, 'antes das credenciais'):
            asyncio.run(run_experiment.execute(args, [], [], [], Path('unused')))

    def test_haiku_uses_strict_low_and_omits_unsupported_sampling(self):
        models, endpoints = self.data(temperature=False)
        models[0]['id'] = 'anthropic/claude-haiku-5.5'
        models[0]['supported_parameters'].remove('seed')
        endpoints[0]['tag'] = 'anthropic'
        result = resolve_generation(models[0]['id'], None, models, endpoints)
        self.assertIsNone(result['seed'])
        self.assertIsNone(result['temperature'])
        self.assertEqual(result['response_format'], 'json_schema')
        self.assertTrue(result['strict'])
        self.assertEqual(result['profile'], 'controlled-v3')

    def test_controlled_rejects_json_mode_and_different_seed(self):
        args = run_experiment.parser().parse_args(['--response-format', 'json_mode'])
        with self.assertRaises(ValueError):
            validate_controlled_limits(args)
        args = run_experiment.parser().parse_args(['--generation-seed', '99'])
        with self.assertRaises(ValueError):
            validate_controlled_limits(args)

    def test_strict_requires_provider_capability(self):
        models, endpoints = self.data()
        endpoints[0]['supported_parameters'] = ['seed', 'reasoning', 'temperature', 'response_format']
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints)

    def test_normalized_profile_freezes_limits_and_sampling(self):
        args = run_experiment.parser().parse_args(['--generation-profile', 'normalized',
            '--response-format', 'json_mode', '--json-normalization', 'markdown_fence'])
        validate_controlled_limits(args)
        models, endpoints = self.data()
        config = resolve_generation('test/model', 'test/fp8', models, endpoints,
            response_format='json_mode', json_normalization='markdown_fence')
        self.assertEqual(config['profile'], 'normalized-v1')
        self.assertEqual(config['reasoning'], 'low')
        self.assertEqual(config['seed'], 42)
        self.assertEqual(config['temperature'], 0)
        self.assertFalse(config['strict'])
        args.max_tokens = 999
        with self.assertRaises(ValueError):
            validate_controlled_limits(args)

    def test_custom_can_explicitly_omit_temperature(self):
        args = run_experiment.parser().parse_args(['--generation-profile', 'custom', '--omit-temperature'])
        self.assertTrue(args.omit_temperature)
        self.assertIsNone(args.temperature)

    def test_provider_override_requires_explicit_diagnostic_and_preserves_sampling(self):
        models=[dict(id='deepseek/deepseek-v4.1-flash',supported_parameters=['reasoning','temperature','seed','response_format'],
                     reasoning=dict(supported_efforts=['low']))]
        endpoints=[dict(tag='other/fp8',provider_name='Other',status=0,
                        supported_parameters=['reasoning','temperature','seed','response_format'])]
        with self.assertRaises(ValueError):
            resolve_generation(models[0]['id'],'other/fp8',models,endpoints,response_format='json_mode',json_normalization='markdown_fence')
        result=resolve_generation(models[0]['id'],'other/fp8',models,endpoints,response_format='json_mode',
                                  json_normalization='markdown_fence',diagnostic_provider_override=True)
        self.assertTrue(result['diagnostic_provider_override'])
        self.assertEqual((result['provider'],result['reasoning'],result['temperature'],result['seed']),('other/fp8','low',0,42))

    def test_deepseek_1017_uses_new_id_and_same_controls_without_relabeling_history(self):
        self.assertEqual(run_experiment.MODELS['deepseek-v4.1-flash'],'deepseek/deepseek-v4.1-flash')
        self.assertEqual(run_experiment.MODELS['deepseek-v4.1-flash-1017'],'deepseek/deepseek-v4.1-flash-1017')
        models,endpoints=self.data()
        models[0]['id']='deepseek/deepseek-v4.1-flash-1017'
        endpoints[0]['tag']='deepinfra/fp8'
        result=resolve_generation(models[0]['id'],None,models,endpoints)
        self.assertEqual((result['provider'],result['reasoning'],result['temperature'],result['seed']),('deepinfra/fp8','low',0,42))

    def test_deepseek_provider_is_frozen(self):
        models, endpoints = self.data()
        models[0]['id'] = 'deepseek/deepseek-v4.1-flash'
        endpoints[0]['tag'] = 'deepinfra/fp8'
        result = resolve_generation(models[0]['id'], None, models, endpoints)
        self.assertEqual(result['provider'], 'deepinfra/fp8')
        with self.assertRaisesRegex(ValueError, 'congelado'):
            resolve_generation(models[0]['id'], 'decart/fp4', models, endpoints)

    def test_controlled_limits_are_frozen_and_custom_remains_configurable(self):
        args = run_experiment.parser().parse_args([])
        validate_controlled_limits(args)
        for key, value in CONTROLLED_LIMITS.items():
            setattr(args, key, value + 1)
            with self.assertRaises(ValueError):
                validate_controlled_limits(args)
            setattr(args, key, value)
        args.sequential = True
        with self.assertRaises(ValueError):
            validate_controlled_limits(args)
        args.generation_profile = 'custom'
        validate_controlled_limits(args)

    def test_execution_without_preflight_stops_before_credentials(self):
        args = run_experiment.parser().parse_args([])
        with self.assertRaisesRegex(RuntimeError, 'antes das credenciais'):
            asyncio.run(run_experiment.execute(args, [], [], [], Path('unused')))

    def data(self, reasoning=True, temperature=True):
        parameters = ['seed', 'response_format', 'structured_outputs', 'reasoning']
        if temperature:
            parameters.append('temperature')
        model = {'id': 'test/model', 'supported_parameters': parameters,
                 'reasoning': {'supported_efforts': ['low', 'high']} if reasoning else None}
        endpoint = {'provider_name': 'Test', 'tag': 'test/fp8', 'quantization': 'fp8',
                    'status': 0, 'supported_parameters': parameters}
        return [model], [endpoint]

    def test_low_temperature_zero_and_fixed_seed_when_supported(self):
        models, endpoints = self.data()
        result = resolve_generation('test/model', 'test/fp8', models, endpoints)
        self.assertEqual((result['reasoning'], result['temperature'], result['seed']), ('low', 0, 42))
        self.assertTrue(result['require_parameters'])

    def test_unsupported_temperature_is_omitted_and_override_rejected(self):
        models, endpoints = self.data(temperature=False)
        self.assertIsNone(resolve_generation('test/model', 'test/fp8', models, endpoints)['temperature'])
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints, temperature=0)

    def test_no_reasoning_support_is_explicit_not_fake_low(self):
        models, endpoints = self.data(reasoning=False)
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints)
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints, reasoning='low')

    def test_model_without_low_is_rejected(self):
        models, endpoints = self.data()
        models[0]['reasoning']['supported_efforts'] = ['high']
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints)

    def test_missing_or_incompatible_provider_fails(self):
        models, endpoints = self.data()
        for provider in (None, 'other/fp8'):
            with self.assertRaises(ValueError):
                resolve_generation('test/model', provider, models, endpoints)
        endpoints[0]['supported_parameters'] = ['response_format']
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints)

    def test_exact_tag_does_not_accept_another_quantization(self):
        models, endpoints = self.data()
        endpoints[0]['tag'] = 'test/fp4'
        with self.assertRaises(ValueError):
            resolve_generation('test/model', 'test/fp8', models, endpoints)

    def test_provider_name_resolves_to_canonical_endpoint(self):
        models, endpoints = self.data()
        self.assertEqual(resolve_generation('test/model', 'Test', models, endpoints)['provider'], 'test/fp8')

    def test_ambiguous_provider_name_is_rejected_but_exact_tag_is_accepted(self):
        models, endpoints = self.data()
        endpoints.append(dict(endpoints[0], tag='test/fp4', quantization='fp4'))
        with self.assertRaisesRegex(ValueError, 'ambiguo'):
            resolve_generation('test/model', 'Test', models, endpoints)
        result = resolve_generation('test/model', 'test/fp8', models, endpoints)
        self.assertEqual(len(result['matching_endpoints']), 1)

    def test_provider_mapping_resolves_without_inference(self):
        models, endpoints = self.data()
        with patch('generation_protocol.get_public_json', side_effect=[{'data': models}, {'data': {'endpoints': endpoints}}]):
            result = public_preflight(['test/model'], {'test/model': 'test/fp8'})
        self.assertEqual(result['test/model']['provider'], 'test/fp8')
