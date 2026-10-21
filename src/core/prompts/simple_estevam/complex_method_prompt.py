"""Prompt simplificado para o Complex Method Agent."""

COMPLEX_METHOD_AGENT_PROMPT = """Detecte Complex Method: funções com Complexidade Ciclomática > 7.
Complexidade Ciclomática = 1 + número de pontos de decisão (if, elif, for, while, except, and, or).

Exemplo:
```python
def validate(data):  # linha 10
    if data:
        if data.valid:
            if data.type == "A":
                if data.status:
                    for item in data.items:
                        if item.checked:
                            if item.value > 0:
                                return True
    return False
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Complex method",
      "Method": "validate",
      "Line_no": "",
      "Description": "Method 'validate' has cyclomatic complexity of 9 (threshold: 7). Extract nested conditions into separate methods.",
      "cyclomatic_complexity": 9,
      "threshold": 7,
      "start_line": 10,
      "end_line": 17
    }
  ]
}
```

IMPORTANTE: Para smells de método (Long Method, Complex Method), sempre retorne:
- Line_no vazio ("") - pois o smell se refere ao método inteiro
- start_line: linha onde o método começa (linha do 'def')
- end_line: última linha do método
"""
