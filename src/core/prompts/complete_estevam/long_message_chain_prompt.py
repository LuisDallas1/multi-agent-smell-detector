"""Prompt para o Long Message Chain Agent com Few-Shot e Chain-of-Thought.

Baseado em Fowler (1999) - Refactoring: Improving the Design of Existing Code.
"""

LONG_MESSAGE_CHAIN_AGENT_PROMPT = """Você detecta Long Message Chain (> 2 métodos encadeados).
Referência: Fowler (1999).

## DEFINIÇÃO:
Cadeia de chamadas de métodos encadeados (> 2), violando Lei de Demeter.

## PROCESSO:
1. Encontre padrões: obj.method1().method2().method3()
2. Conte métodos com parênteses encadeados
3. Se > 2 métodos encadeados: adicione à lista
4. Retorne no máximo 10 detecções

## EXEMPLO POSITIVO (É SMELL):
```python
# 3 métodos encadeados
zip_code = customer.get_address().get_city().get_zip_code()
data = response.json().get('data').values()
result = df.filter().sort().head()
```

## EXEMPLO NEGATIVO (NÃO É SMELL):
```python
# Apenas 2 métodos (aceitável)
result = data.filter().sort()
text = string.strip().lower()

# Acesso a atributos (sem parênteses)
value = config.settings.database.host
```

## REGRAS:
1. Conte métodos com parênteses: .method()
2. Atributos sem parênteses não contam
3. Threshold: > 2 métodos encadeados
4. Máximo 10 detecções
"""
