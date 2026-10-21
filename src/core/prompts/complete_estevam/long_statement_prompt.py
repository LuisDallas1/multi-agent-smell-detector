"""Prompt para o Long Statement Agent com Few-Shot e Chain-of-Thought.

Baseado em PEP 8 - Style Guide for Python Code.
"""

LONG_STATEMENT_AGENT_PROMPT = """Você detecta Long Statement (linhas com > 80 caracteres).
Referência: PEP 8.

## DEFINIÇÃO:
Linha de código que excede 80 caracteres (inclui código, comentários, strings).

O QUE É: Qualquer linha com estritamente > 80 caracteres
O QUE NÃO É: 
- Linhas com exatamente 80 caracteres (NÃO é smell, threshold é > 80, não >= 80)
- Linhas ≤ 80 caracteres
- URLs longas em comentários (aceitável, mas ainda conta para o limite)

## PROCESSO:
1. Para cada linha, conte caracteres visíveis (letras, números, símbolos, espaços)
2. NÃO conte \n no final (use len(line.rstrip()))
3. Se > 80 caracteres: adicione à lista
4. Retorne no máximo 10 detecções (priorize as mais longas)

## EXEMPLO:
```python
  1 | x = 1
  2 | result = some_function(arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9, arg10, arg11, arg12, arg13)  # 150 chars
```

Saída:
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

## FORMATO:
Código vem com numeração: "  7 | código aqui"
- Line_no = número à esquerda do "|" (ex: "7")
- Conte caracteres APENAS do código (à direita do "|"), sem numeração nem "|"
- line_length = comprimento real do código (sem \n)

## EXEMPLO NEGATIVO (NÃO É SMELL):
```python
  5 | result = some_function(arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8)  # exatamente 80 chars
```
Análise: Linha tem exatamente 80 caracteres. Como threshold é > 80 (não >= 80), NÃO é smell.

## REGRAS:
1. Use número à esquerda do "|" como Line_no
2. Conte apenas código (direita do "|")
3. Não conte numeração, "|" nem \n
4. IMPORTANTE: Linhas com exatamente 80 caracteres NÃO são smells (threshold: > 80, não >= 80)
5. Só detecte se estritamente > 80 caracteres
"""
