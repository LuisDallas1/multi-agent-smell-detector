"""Prompt simplificado para o Long Parameter List Agent."""

LONG_PARAMETER_LIST_AGENT_PROMPT = """Detecte Long Parameter List: funções/métodos com mais de 4 parâmetros (exceto self, cls, *args, **kwargs).

Exemplo:
```python
def create_user(name, email, age, address, phone, country):  # linha 5, 6 params
    pass
```

Saída esperada:
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
"""
