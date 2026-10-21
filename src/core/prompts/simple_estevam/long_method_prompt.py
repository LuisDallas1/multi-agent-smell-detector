"""Prompt simplificado para o Long Method Agent."""

LONG_METHOD_AGENT_PROMPT = """Detecte Long Method: métodos com mais de 67 linhas.

Exemplo:
```python
def process_order(order):  # linha 1, 70 linhas
    # 70 linhas de código aqui...
    validate()
    calculate()
    save()
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Long method",
      "Method": "process_order",
      "Line_no": "",
      "Description": "Method 'process_order' has 70 lines (threshold: 67). Consider breaking it down into smaller methods.",
      "total_lines": 70,
      "threshold": 67,
      "start_line": 1,
      "end_line": 70
    }
  ]
}
```

IMPORTANTE: Para smells de método (Long Method, Complex Method), sempre retorne:
- Line_no vazio ("") - pois o smell se refere ao método inteiro
- start_line: linha onde o método começa (linha do 'def')
- end_line: última linha do método
"""
