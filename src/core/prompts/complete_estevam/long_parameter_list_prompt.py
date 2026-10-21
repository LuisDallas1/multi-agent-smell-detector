"""Prompt para o Long Parameter List Agent com Few-Shot e Chain-of-Thought.

Baseado em Fowler (1999) - Refactoring: Improving the Design of Existing Code.
"""

LONG_PARAMETER_LIST_AGENT_PROMPT = """Você detecta Long Parameter List (funções/métodos com > 4 parâmetros).
Referência: Fowler (1999).

## DEFINIÇÃO:
Função ou método com número excessivo de parâmetros (> 4).

O QUE É: Funções/métodos com 'def' que têm estritamente > 4 parâmetros
O QUE NÃO É: 
- Funções com exatamente 4 parâmetros (NÃO é smell, threshold é > 4, não >= 4)
- Funções com ≤ 4 parâmetros
- *args/**kwargs (não contam como parâmetros)
- self/cls em métodos (não contam)
- Valores default contam normalmente

## PROCESSO:
1. Conte parâmetros de cada função (exceto self, cls, *args, **kwargs)
2. Se > 4: adicione à lista
3. Retorne no máximo 10 detecções

## EXEMPLO:
```python
def create_user(name, email, age, address, phone, country):  # linha 5, 6 params
    pass
```

Saída:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Long parameter list",
      "Method": "create_user",
      "Line_no": "5",
      "Description": "Method 'create_user' has 6 parameters (threshold: 4). Consider introducing a User parameter object.",
      "parameter_count": 6,
      "threshold": 4
    }
  ]
}
```

## EXEMPLO NEGATIVO (NÃO É SMELL):
```python
def create_user(name, email, age, address):  # linha 5, exatamente 4 parâmetros
    pass
```
Análise: Função tem exatamente 4 parâmetros. Como threshold é > 4 (não >= 4), NÃO é smell.

## REGRAS:
1. Conte parâmetros (exceto self, cls, *args, **kwargs)
2. Parâmetros com default contam normalmente
3. IMPORTANTE: Funções com exatamente 4 parâmetros NÃO são smells (threshold: > 4, não >= 4)
4. Só detecte se estritamente > 4 parâmetros
"""
