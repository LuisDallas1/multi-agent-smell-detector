"""Prompt simplificado para o Long Lambda Function Agent."""

LONG_LAMBDA_FUNCTION_AGENT_PROMPT = """Detecte Long Lambda Function: funções lambda com mais de 80 caracteres.

Exemplo:
```python
result = map(lambda x: x * 2 if x > 0 else x * -1 if x < 0 else 0 if x == 0 else x + 10, numbers)  # linha 5, 95 chars
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Long lambda function",
      "Method": "",
      "Line_no": "5",
      "Description": "Lambda at line 5 has 95 characters (threshold: 80). Convert to named function.",
      "lambda_length": 95,
      "threshold": 80
    }
  ]
}
```
"""
