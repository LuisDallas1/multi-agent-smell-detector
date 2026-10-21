"""Criterios fixos do experimento; nao sao configurados pela resposta da LLM."""
THRESHOLDS = {
    'complex method': 7,
    'complex conditional': 2,
    'long method': 67,
    'long parameter list': 4,
    'long statement': 80,
    'long identifier': 20,
    'long lambda function': 80,
    'long message chain': 2,
}
MAGIC_NUMBER_EXCEPTIONS = frozenset({0, 1, -1})
RULES_VERSION = '2.0'
