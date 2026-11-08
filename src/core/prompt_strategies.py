"""Estratégias V2 compartilhadas pelas duas arquiteturas."""
MULTI_PROMPT_TYPES = ("simple_v2", "complete_v2")
SINGLE_PROMPT_SOURCES = {name: name for name in MULTI_PROMPT_TYPES}


def resolve_prompt_types(architecture, prompt_type):
    if architecture not in {"single", "multiagent"}:
        raise ValueError("Arquitetura desconhecida")
    if prompt_type in {"all", "paired"}:
        return list(MULTI_PROMPT_TYPES)
    # Atalhos antigos continuam aceitos; nomes gravados são sempre V2.
    prompt_type = {"simple": "simple_v2", "complete": "complete_v2"}.get(prompt_type, prompt_type)
    if prompt_type not in MULTI_PROMPT_TYPES:
        raise ValueError("Estratégia desconhecida: use simple_v2 ou complete_v2")
    return [prompt_type]
