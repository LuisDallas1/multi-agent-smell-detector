"""Prompt simples: regra DPy e contrato, sem exemplos."""

MAGIC_NUMBER_AGENT_PROMPT = """Detecte somente Magic number.
Literais numéricos no escopo de funções/métodos, inclusive defaults, exceto 0, 1 e -1 e seus equivalentes decimais. Ignore booleanos, literais fora de funções e dentro de chamadas, inclusive expressões/coleções nos argumentos. Atribuição local em MAIÚSCULAS não isenta o literal; índices, fatias, testes e cálculos também não. Para -7, reporte number=7 (literal interno). Preserve ocorrências repetidas.

Examine o arquivo inteiro e retorne todas as ocorrências que satisfazem a regra, sem limite de quantidade. Limiares são estritos: igual ao limite não é smell. Use os números à esquerda de | apenas para localização. Não invente nomes, linhas ou ocorrências.

Retorne somente JSON: {"detected":false,"detections":[]} se não houver ocorrências; caso contrário, detected=true e uma lista com um item por ocorrência.
Cada item: detected=true, Smell="Magic number", Method (função envolvente ou string vazia), Line_no (número positivo como string) e Description (justificativa curta com a evidência).
Inclua obrigatoriamente o campo number (valor numérico JSON, nunca apenas na descrição). Line_no é a linha do literal; se houver vários na mesma linha, reporte cada um separadamente.
"""
