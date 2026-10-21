"""Prompts para os agentes especializados de detecao de code smells."""

from .complex_conditional_prompt import COMPLEX_CONDITIONAL_AGENT_PROMPT
from .complex_method_prompt import COMPLEX_METHOD_AGENT_PROMPT
from .empty_catch_block_prompt import EMPTY_CATCH_BLOCK_AGENT_PROMPT
from .long_identifier_prompt import LONG_IDENTIFIER_AGENT_PROMPT
from .long_lambda_function_prompt import LONG_LAMBDA_FUNCTION_AGENT_PROMPT
from .long_message_chain_prompt import LONG_MESSAGE_CHAIN_AGENT_PROMPT
from .long_method_prompt import LONG_METHOD_AGENT_PROMPT
from .long_parameter_list_prompt import LONG_PARAMETER_LIST_AGENT_PROMPT
from .long_statement_prompt import LONG_STATEMENT_AGENT_PROMPT
from .magic_number_prompt import MAGIC_NUMBER_AGENT_PROMPT
from .missing_default_prompt import MISSING_DEFAULT_AGENT_PROMPT

__all__ = [
    "COMPLEX_CONDITIONAL_AGENT_PROMPT",
    "COMPLEX_METHOD_AGENT_PROMPT",
    "EMPTY_CATCH_BLOCK_AGENT_PROMPT",
    "LONG_IDENTIFIER_AGENT_PROMPT",
    "LONG_LAMBDA_FUNCTION_AGENT_PROMPT",
    "LONG_MESSAGE_CHAIN_AGENT_PROMPT",
    "LONG_METHOD_AGENT_PROMPT",
    "LONG_PARAMETER_LIST_AGENT_PROMPT",
    "LONG_STATEMENT_AGENT_PROMPT",
    "MAGIC_NUMBER_AGENT_PROMPT",
    "MISSING_DEFAULT_AGENT_PROMPT",
]