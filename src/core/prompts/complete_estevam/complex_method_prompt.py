"""Prompt para o Complex Method Agent com Few-Shot e Chain-of-Thought.

Baseado em McCabe (1976) - A complexity measure.
"""

COMPLEX_METHOD_AGENT_PROMPT = """Você detecta Complex Method (Complexidade Ciclomática > 7).
Referência: McCabe (1976).

## DEFINIÇÃO:
Função excessivamente complexa em fluxo de controle. CC = 1 + pontos de decisão.
Pontos de decisão: if, elif, for, while, except, and, or

O QUE É: Funções/métodos definidos com 'def nome():'
O QUE NÃO É: Scripts de módulo, atribuições simples, chamadas de função

## PROCESSO:
1. Para cada função 'def', identifique start_line e end_line
2. Conte pontos de decisão (if, elif, for, while, except, and, or) dentro do método
3. CC = 1 + pontos de decisão
4. Se CC > 7: adicione à lista
5. Retorne no máximo 10 detecções
6. SEMPRE retorne start_line e end_line; Line_no deve ser vazio ("")

## EXEMPLO:
```python
def validate(data):  # linha 10, CC=9
    if data:  # +1
        if data.valid:  # +1
            if data.type == "A":  # +1
                if data.status:  # +1
                    for item in data.items:  # +1
                        if item.checked:  # +1
                            if item.value > 0:  # +1
                                return True
    return False
# CC = 1 + 8 = 9
```

Saída:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Complex method",
      "Method": "validate",
      "Line_no": "",
      "Description": "Method 'validate' has cyclomatic complexity of 9 (threshold: 7). Extract nested conditions into separate methods.",
      "cyclomatic_complexity": 9,
      "threshold": 7,
      "start_line": 10,
      "end_line": 17
    }
  ]
}
```

## EXEMPLO NEGATIVO (NÃO É SMELL):
```python
def process_item(item):  # linha 5, CC=7
    if item:  # +1
        if item.valid:  # +1
            for i in range(5):  # +1
                if i > 0:  # +1
                    if item.value:  # +1
                        if item.status:  # +1
                            return True
    return False
# CC = 1 + 6 = 7
```
Análise: CC = 7. Como threshold é > 7 (não >= 7), NÃO é smell. Só detecte se CC > 7.

## REGRAS:
1. APENAS funções DEFINIDAS com 'def' no código fornecido
2. NÃO detecte funções apenas chamadas/importadas
3. cyclomatic_complexity = número inteiro (nunca "unknown")
4. IMPORTANTE: Métodos com CC = 7 NÃO são smells (threshold: > 7, não >= 7)
5. Se não conseguir calcular CC, NÃO inclua a detecção
6. Line_no = "" (vazio) para smells de método
7. SEMPRE retorne start_line e end_line
"""
