"""Prompt simplificado para o Magic Number Agent."""

MAGIC_NUMBER_AGENT_PROMPT = """Detecte Magic Number: literais numéricos (exceto 0, 1, -1) usados diretamente no código sem constante nomeada.

Exemplo:
```python
def calculate_energy(mass, height):  # linha 10
    return mass * 9.81 * height  # linha 11
```

Saída esperada:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Magic number",
      "Method": "calculate_energy",
      "Line_no": "11",
      "Description": "Magic number 9.81 found in 'calculate_energy'. Define as GRAVITY_CONSTANT = 9.81."
    }
  ]
}
```
"""
