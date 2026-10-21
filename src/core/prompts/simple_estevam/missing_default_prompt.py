"""Prompt simplificado para o Missing Default Agent."""

MISSING_DEFAULT_AGENT_PROMPT = """Detecte Missing Default: blocos match-case sem caso padrão (case _).

Exemplo:
```python
def handle_status(status):  # linha 10
    match status:  # linha 11
        case "active":
            activate()
        case "inactive":
            deactivate()
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Missing default",
      "Method": "handle_status",
      "Line_no": "11",
      "Description": "Match-case at line 11 missing default case. Add 'case _:' to handle unknown values."
    }
  ]
}
```
"""
