"""Prompt para o Empty Catch Block Agent com Few-Shot e Chain-of-Thought.

Baseado em Martin (2008) - Clean Code, Capítulo 7.
"""

EMPTY_CATCH_BLOCK_AGENT_PROMPT = """Você detecta Empty Catch Block (except vazio ou só com pass).
Referência: Martin (2008).

## DEFINIÇÃO:
Bloco except que não trata a exceção (vazio ou apenas 'pass'), silenciando erros.

O QUE É: except: pass, except Exception: pass, except ValueError: (vazio)
O QUE NÃO É: except com logging, re-raise, ou tratamento (return default_value)

## PROCESSO:
1. Encontre blocos try-except
2. Verifique se except está vazio ou só tem 'pass'
3. Retorne no máximo 10 detecções

## EXEMPLO:
```python
def load_data():  # linha 10
    try:
        risky_operation()
    except Exception:  # linha 13
        pass
```

Saída:
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

## REGRAS:
1. Detecte apenas except vazio ou com 'pass'
2. Ignore except com tratamento (logging, re-raise, return)
"""
