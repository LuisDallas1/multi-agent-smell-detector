"""Registro dos 11 especialistas e selecao explicita do conjunto de prompts."""
from importlib import import_module
from core.schemas import agent_response as schemas
from core.prompt_strategies import MULTI_PROMPT_TYPES

PROMPT_TYPES = MULTI_PROMPT_TYPES
AGENTS = {
    "complex_method": "MultipleComplexMethodResponse",
    "long_method": "MultipleLongMethodResponse",
    "complex_conditional": "MultipleComplexConditionalResponse",
    "long_parameter_list": "MultipleLongParameterListResponse",
    "long_statement": "MultipleLongStatementResponse",
    "long_identifier": "MultipleLongIdentifierResponse",
    "magic_number": "MultipleMagicNumberResponse",
    "empty_catch_block": "MultipleEmptyCatchBlockResponse",
    "missing_default": "MultipleMissingDefaultResponse",
    "long_lambda_function": "MultipleLongLambdaResponse",
    "long_message_chain": "MultipleLongMessageChainResponse",
}


def get_agent_configs(prompt_type: str = "simple_v2"):
    """Carrega diretamente os prompts do conjunto solicitado com os mesmos schemas."""
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"Conjunto de prompts invalido: {prompt_type}")
    return {
        name: {
            "prompt": getattr(import_module(f"core.prompts.{prompt_type}.{name}_prompt"),
                              f"{name.upper()}_AGENT_PROMPT"),
            "schema": getattr(schemas, schema),
        }
        for name, schema in AGENTS.items()
    }


AGENT_CONFIGS = get_agent_configs("simple_v2")
