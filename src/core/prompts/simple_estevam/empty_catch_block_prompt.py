"""Prompt simplificado para o Empty Catch Block Agent."""

EMPTY_CATCH_BLOCK_AGENT_PROMPT = """Detecte Empty Catch Block: blocos except vazios ou apenas com 'pass', que silenciam exceções.

Exemplo:
```python
def load_data():  # linha 10
    try:
        risky_operation()
    except Exception:  # linha 13
        pass
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Empty catch block",
      "Method": "load_data",
      "Line_no": "13",
      "Description": "Empty catch block in 'load_data' at line 13. Add logging or proper error handling."
    }
  ]
}
```
"""
