"""Prompt simplificado para o Long Statement Agent."""

LONG_STATEMENT_AGENT_PROMPT = """Detecte Long Statement: linhas com mais de 80 caracteres.
O código será fornecido com numeração de linhas. Use o número à esquerda do "|" como Line_no.

Exemplo:
```python
  1 | x = 1
  2 | result = some_function(arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9, arg10, arg11, arg12, arg13)  # 150 chars
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Long statement",
      "Method": "",
      "Line_no": "2",
      "Description": "Line 2 has 150 characters (threshold: 80). Break into multiple lines.",
      "line_length": 150,
      "threshold": 80
    }
  ]
}
```
"""
