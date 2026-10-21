"""Prompt simplificado para o Long Identifier Agent."""

LONG_IDENTIFIER_AGENT_PROMPT = """Detecte Long Identifier: nomes de funções, classes, variáveis ou constantes com mais de 20 caracteres.

Exemplo:
```python
DESKTOP_ENVIRONMENT_CONFIG_NAME = "config"  # linha 5, 31 chars
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Long identifier",
      "Method": "",
      "Line_no": "5",
      "Description": "Identifier 'DESKTOP_ENVIRONMENT_CONFIG_NAME' has 31 characters (threshold: 20). Consider shortening.",
      "identifier_name": "DESKTOP_ENVIRONMENT_CONFIG_NAME",
      "length": 31,
      "threshold": 20
    }
  ]
}
```
"""
