"""Casos reais do parser do SDK com envelopes simulados; nenhuma chamada paga."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
from openai import omit
from openai.types.chat import ChatCompletion
from openai.lib._parsing._completions import parse_chat_completion
from core.execution.errors import diagnose_exception
from core.utils.token_tracker import TokenUsageCallback
import test_response_validity as response_tests


def malformed_completion(code=None, usage=None):
    completion = ChatCompletion.model_construct(
        id='simulated-completion', object='chat.completion', created=0, model='mock',
        choices=None, usage=usage, error={'code': code, 'message': 'private text must not be logged'})
    try:
        parse_chat_completion(response_format={'type': 'json_object'}, input_tools=omit,
                              chat_completion=completion)
    except TypeError as error:
        return error
    raise AssertionError('O SDK deveria rejeitar choices nulo')


class ProviderErrorTests(unittest.TestCase):
    def test_actual_sdk_typeerror_is_classified_without_recording_private_text(self):
        error = malformed_completion()
        diagnostic, usage = diagnose_exception(error)
        self.assertEqual(diagnostic['classification'], 'InvalidProviderResponse')
        self.assertIsNone(usage)
        self.assertNotIn('private text', json.dumps(diagnostic))

    def test_programming_typeerror_is_not_reclassified_or_retried(self):
        try:
            raise TypeError("Received response with null value for 'choices'. secret")
        except TypeError as error:
            diagnostic, _ = diagnose_exception(error)
            self.assertNotIn('classification', diagnostic)
            self.assertNotIn('secret', json.dumps(diagnostic))
            helper = response_tests.ResponseValidityTests()
            engine = helper.make([error])
            helper.call(engine)
            self.assertEqual(len(engine.model.messages), 1)
            self.assertEqual(engine.agent_errors['long_statement'], 'TypeError')

    def test_known_sdk_protocol_error_gets_one_bounded_retry(self):
        helper = response_tests.ResponseValidityTests()
        engine = helper.make([malformed_completion(), response_tests.reply()])
        helper.call(engine)
        metric = engine.agent_metrics['long_statement']
        self.assertTrue(metric['recovered'])
        self.assertEqual(metric['attempts'][0]['error'], 'InvalidProviderResponse')
        self.assertEqual(len(metric['attempts']), 2)
        self.assertEqual(engine.model.budgets, [8192, 8192])

    def test_provider_error_code_controls_fatal_vs_transient_classification(self):
        for code, expected in ((402, 'InsufficientCreditError'), (429, 'RateLimitError'),
                               (503, 'InternalServerError')):
            diagnostic, _ = diagnose_exception(malformed_completion(code))
            self.assertEqual(diagnostic['classification'], expected)
            self.assertEqual(diagnostic['provider_error_code'], code)

    def test_usage_returned_by_sdk_is_preserved_even_before_normal_callback(self):
        usage = dict(prompt_tokens=12, completion_tokens=4, total_tokens=16, cost=0.002)
        error = malformed_completion(usage=usage)
        helper = response_tests.ResponseValidityTests()
        engine = helper.make([error], retries=0)
        helper.call(engine)
        attempt = engine.agent_metrics['long_statement']['attempts'][0]
        self.assertEqual(attempt['cost_usd'], 0.002)
        self.assertEqual(attempt['token_usage']['total_tokens'], 16)

    def test_null_usage_does_not_break_token_callback(self):
        callback = TokenUsageCallback()
        asyncio.run(callback.on_llm_end(SimpleNamespace(llm_output={'token_usage': None}, generations=None)))
        self.assertFalse(callback.usage_available)
        self.assertIsNone(callback.cost_usd)


if __name__ == '__main__':
    unittest.main()
