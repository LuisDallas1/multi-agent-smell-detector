"""Diagnóstico restrito de falhas de protocolo no SDK, sem texto ou headers."""
from collections.abc import Mapping


def diagnose_exception(error):
    """Só reconhece envelope inválido observado em frames conhecidos do SDK.

    Não classifica TypeError por mensagem nem captura locais arbitrários. Dados
    de uso são devolvidos separadamente; mensagens, prompts e headers não são salvos.
    """
    diagnostic = dict(exception_type=type(error).__name__, frames=[])
    recovered_usage = None
    trace = error.__traceback__
    while trace is not None:
        frame = trace.tb_frame
        module = frame.f_globals.get('__name__', '')
        function = frame.f_code.co_name
        diagnostic['frames'].append(dict(module=module, function=function, line=trace.tb_lineno))
        candidate = None
        if (module == 'openai.lib._parsing._completions' and function == 'parse_chat_completion'
                and 'choices' in frame.f_locals):
            candidate = frame.f_locals.get('chat_completion')
        elif module == 'langchain_openai.chat_models.base' and function == '_create_chat_result':
            candidate = frame.f_locals.get('response_dict')
        if candidate is not None and isinstance(error, TypeError):
            try:
                payload = candidate if isinstance(candidate, Mapping) else candidate.model_dump()
            except (AttributeError, ValueError, TypeError):
                payload = None
            if isinstance(payload, Mapping) and payload.get('choices') is None:
                diagnostic['classification'] = 'InvalidProviderResponse'
                diagnostic['reason'] = 'SDK completion envelope has null or missing choices'
                provider_error = payload.get('error')
                code = provider_error.get('code') if isinstance(provider_error, Mapping) else None
                if isinstance(code, str) and code.isdigit():
                    code = int(code)
                if isinstance(code, int) and not isinstance(code, bool) and 400 <= code <= 599:
                    diagnostic['provider_error_code'] = code
                    if code in (401, 403, 402, 429):
                        diagnostic['classification'] = {
                            401: 'AuthenticationError', 403: 'PermissionDeniedError',
                            402: 'InsufficientCreditError', 429: 'RateLimitError'}[code]
                    elif code >= 500:
                        diagnostic['classification'] = 'InternalServerError'
                usage = payload.get('usage')
                if isinstance(usage, Mapping):
                    recovered_usage = dict(usage)
        trace = trace.tb_next
    diagnostic['frames'] = diagnostic['frames'][-8:]
    return diagnostic, recovered_usage
