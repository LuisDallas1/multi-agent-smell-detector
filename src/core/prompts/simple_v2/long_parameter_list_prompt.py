"""Prompt simples: regra DPy e contrato, sem exemplos."""

LONG_PARAMETER_LIST_AGENT_PROMPT = """Detecte somente Long parameter list.
Funções/métodos com > 4 parâmetros declarados, excluindo self, cls, *args e **kwargs. Conte também parâmetros com valor default.

Examine o arquivo inteiro e retorne todas as ocorrências que satisfazem a regra, sem limite de quantidade. Limiares são estritos: igual ao limite não é smell. Use os números à esquerda de | apenas para localização. Não invente nomes, linhas ou ocorrências.

Retorne somente JSON: {"detected":false,"detections":[]} se não houver ocorrências; caso contrário, detected=true e uma lista com um item por ocorrência.
Cada item: detected=true, Smell="Long parameter list", Method (função envolvente ou string vazia), Line_no (número positivo como string) e Description (justificativa curta com a evidência).
Method é o nome da função; Line_no é a linha do def/async def.

Aplique o limiar para decidir se há smell. Reporte localização e evidência curta; não calcule nem devolva a medida exata, threshold, intervalos ou contagens intermediárias.
"""
