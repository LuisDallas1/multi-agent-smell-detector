"""Prompt simplificado para o Long Message Chain Agent."""

LONG_MESSAGE_CHAIN_AGENT_PROMPT = """Detecte Long Message Chain: cadeias de mais de 2 métodos encadeados.

Exemplo:
```python
def get_zip(customer):  # linha 10
    return customer.get_address().get_city().get_zip_code()  # linha 11, 3 métodos
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Long message chain",
      "Method": "get_zip",
      "Line_no": "11",
      "Description": "Message chain at line 11 has 3 chained methods (threshold: 2). Use 'Hide Delegate' pattern.",
      "chain_length": 3,
      "threshold": 2
    }
  ]
}
```
"""
