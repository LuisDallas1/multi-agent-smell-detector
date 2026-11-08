"""Instrução de sistema comum; somente a forma da resposta varia."""
SYSTEM_PREFIX = (
    "You are a code smell detector. "
    "ALWAYS respond with valid JSON only. "
    "Never respond with explanations or questions. "
)


def system_prompt(response_contract):
    return SYSTEM_PREFIX + response_contract
