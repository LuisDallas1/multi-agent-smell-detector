"""Prompt simplificado para o Complex Conditional Agent."""

COMPLEX_CONDITIONAL_AGENT_PROMPT = """Detecte Complex Conditional: condicionais (if, elif, while) com mais de 2 operadores lógicos (and/or).

Exemplo:
```python
def check_eligibility(user):  # linha 10
    if user.age > 18 and user.verified and user.balance > 100 and user.active:  # linha 11
        return True
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Complex conditional",
      "Method": "check_eligibility",
      "Line_no": "11",
      "Description": "Conditional at line 11 has 3 logical operators (threshold: 2). Extract into named boolean variables.",
      "logical_operators": 3,
      "threshold": 2
    }
  ]
}
```
"""
