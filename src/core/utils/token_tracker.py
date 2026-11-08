"""UtilitÃ¡rio para rastreamento de uso de tokens."""

import math

from langchain_core.callbacks import AsyncCallbackHandler


def _extract_token_usage_from_llm_result(response) -> dict:
    """Extrai informaÃ§Ãµes de uso de tokens de um LLMResult."""
    default_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if hasattr(response, "llm_output") and response.llm_output:
        if isinstance(response.llm_output.get("token_usage"), dict):
            usage = response.llm_output["token_usage"]
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

    if hasattr(response, "generations"):
        for generation_list in response.generations or []:
            for generation in generation_list or []:
                if hasattr(generation, "message"):
                    message = generation.message

                    if hasattr(message, "response_metadata"):
                        metadata = message.response_metadata or {}
                        if isinstance(metadata.get("token_usage"), dict):
                            usage = metadata["token_usage"]
                            return {
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }
                        if isinstance(metadata.get("usage"), dict):
                            usage = metadata["usage"]
                            return {
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }

                    if hasattr(message, "usage_metadata"):
                        usage = message.usage_metadata
                        if isinstance(usage, dict) and usage:
                            return {
                                "prompt_tokens": usage.get("input_tokens", 0),
                                "completion_tokens": usage.get("output_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }

    return default_usage


class TokenUsageCallback(AsyncCallbackHandler):
    """Callback simples para capturar uso de tokens."""

    def __init__(self):
        super().__init__()
        self.token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.usage_available = False
        self.reasoning_tokens = None
        self.cost_usd = None

    async def on_llm_end(self, response, **kwargs):
        """Captura uso de tokens quando a LLM termina."""
        usage = (getattr(response, "llm_output", None) or {}).get("token_usage", {})
        if not isinstance(usage, dict):
            usage = {}
        if "cost" not in usage:
            for group in getattr(response, "generations", []) or []:
                for generation in group:
                    metadata = getattr(getattr(generation, "message", None), "response_metadata", {}) or {}
                    candidate = metadata.get("token_usage", metadata.get("usage", {})) or {}
                    if isinstance(candidate, dict) and "cost" in candidate:
                        usage = candidate
        self.capture_cost(usage)
        self.token_usage = _extract_token_usage_from_llm_result(response)
        self.usage_available = any(self.token_usage.values())

    def capture_cost(self, usage):
        if not isinstance(usage, dict):
            return
        value = usage.get("cost")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            self.cost_usd = float(value)

    async def on_llm_error(self, error, **kwargs):
        """Preserva uso informado pelo SDK em erros de limite de saida."""
        completion = getattr(error, "completion", None)
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        usage = usage.model_dump() if hasattr(usage, "model_dump") else usage
        if not isinstance(usage, dict):
            return
        self.capture_cost(usage)
        self.token_usage = {key: usage.get(key, 0) or 0 for key in self.token_usage}
        self.usage_available = True
        self.reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
