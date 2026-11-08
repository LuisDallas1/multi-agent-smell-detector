"""Prompt simples: regra DPy e contrato, sem exemplos."""

LONG_LAMBDA_FUNCTION_AGENT_PROMPT = """Detecte somente Long lambda function.
Expressões lambda com > 80 caracteres, de lambda até o final da expressão, inclusive quando multilinha. Não inclua a atribuição ou chamada envolvente.

Examine o arquivo inteiro e retorne todas as ocorrências que satisfazem a regra, sem limite de quantidade. Limiares são estritos: igual ao limite não é smell. Use os números à esquerda de | apenas para localização. Não invente nomes, linhas ou ocorrências.

Retorne somente JSON: {"detected":false,"detections":[]} se não houver ocorrências; caso contrário, detected=true e uma lista com um item por ocorrência.
Cada item: detected=true, Smell="Long lambda function", Method (função envolvente ou string vazia), Line_no (número positivo como string) e Description (justificativa curta com a evidência).
Line_no é a linha inicial da lambda.

Aplique o limiar para decidir se há smell. Reporte localização e evidência curta; não calcule nem devolva a medida exata, threshold, intervalos ou contagens intermediárias.
"""
