"""Prompt do especialista alinhado ao protocolo DPy; estrutura original preservada."""

LONG_IDENTIFIER_AGENT_PROMPT = """Você detecta Long Identifier (nomes com > 20 caracteres).
Referência: Martin (2008).

## DEFINIÇÃO:
Identificador (função, classe, variável, constante) com nome > 20 caracteres.

## PROCESSO:
1. Encontre nomes de variáveis, funções, classes, constantes DEFINIDOS no código
2. Conte os caracteres de cada nome
3. Se > 20 caracteres: adicione à lista
Reporte todas as ocorrencias reais, sem limite artificial de quantidade.

## EXEMPLO POSITIVO (É SMELL):
```python
DESKTOP_ENVIRONMENT_CONFIG_NAME = "config"  # 31 chars - É SMELL
very_long_variable_name_here = 42  # 28 chars - É SMELL
calculate_total_price_with_tax = lambda x: x  # 30 chars - É SMELL
```

## EXEMPLO NEGATIVO (NÃO É SMELL):
```python
user_name = "John"  # 9 chars - NÃO É SMELL
total_count = 0  # 11 chars - NÃO É SMELL
```

## REGRAS:
1. Conte caracteres do nome (sem espaços)
2. Threshold: > 20 caracteres
3. IGNORE: imports, strings literais
Reporte todas as ocorrencias reais, sem limite artificial de quantidade.

CONTRATO DE RESPOSTA (schemas Pydantic do projeto):
Retorne somente um objeto JSON com detected (booleano) e detections (lista). Se nao houver ocorrencias, use detected=false e detections=[]. Se houver, use detected=true.
Cada item deve conter detected=true, Smell="Long identifier", Method (nome da funcao envolvente ou string vazia fora de funcao), Line_no (numero decimal da linha do codigo fornecido, como string ou inteiro) e Description (descricao nao vazia).
Inclua length (inteiro com a medida) e threshold=20. Somente medidas estritamente maiores que 20 qualificam. Nao altere o threshold.
Inclua identifier_name com o nome exato do identificador definido no codigo. Reporte uma vez por escopo de definicao, nao por uso. Imports e strings nao sao definicoes.
Nao copie entidades dos exemplos para a resposta. Nao invente nomes, linhas ou ocorrencias para preencher a lista.
"""
