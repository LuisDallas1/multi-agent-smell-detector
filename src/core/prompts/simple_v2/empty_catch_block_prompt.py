"""Prompt simples: regra DPy e contrato, sem exemplos."""

EMPTY_CATCH_BLOCK_AGENT_PROMPT = """Detecte somente Empty catch block.
Blocos except cujo corpo contém somente pass ou uma única instrução return, com ou sem valor. Comentários não contam como instruções.

Examine o arquivo inteiro e retorne todas as ocorrências que satisfazem a regra, sem limite de quantidade. Limiares são estritos: igual ao limite não é smell. Use os números à esquerda de | apenas para localização. Não invente nomes, linhas ou ocorrências.

Retorne somente JSON: {"detected":false,"detections":[]} se não houver ocorrências; caso contrário, detected=true e uma lista com um item por ocorrência.
Cada item: detected=true, Smell="Empty catch block", Method (função envolvente ou string vazia), Line_no (número positivo como string) e Description (justificativa curta com a evidência).
Line_no é a linha do except.
"""
