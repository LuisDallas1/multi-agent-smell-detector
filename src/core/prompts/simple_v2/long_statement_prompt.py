"""Prompt simples: regra DPy e contrato, sem exemplos."""

LONG_STATEMENT_AGENT_PROMPT = """Detecte somente Long statement.
Instrução normalizada com >80 bytes UTF-8, não linha física. Considere instruções multilinha como uma ocorrência na linha inicial; não conte numeração, comentários ou espaços supérfluos. Strings, docstrings de módulo/função e atribuições globais podem qualificar. Exclua assinaturas de def/async def, cabeçalhos de controle, docstrings e campos diretamente em classe e instruções no corpo de case de match. Ignore imports diretamente no módulo; imports dentro de função ou de if no módulo podem qualificar. Uma atribuição com string multilinha é UMA instrução, não uma ocorrência por linha do conteúdo.

Examine o arquivo inteiro e retorne todas as ocorrências que satisfazem a regra, sem limite de quantidade. Limiares são estritos: igual ao limite não é smell. Use os números à esquerda de | apenas para localizar. Decida se a instrução excede o limite; não calcule nem devolva seu comprimento exato, somas de bytes ou contagens intermediárias. Não invente nomes ou linhas.

Retorne somente JSON: {"detected":false,"detections":[]} se não houver ocorrências; caso contrário, detected=true e uma lista com um item por ocorrência.
Cada item: detected=true, Smell="Long statement", Method (função envolvente ou string vazia), Line_no (número positivo como string) e Description (justificativa curta com a evidência).
Description deve apontar a evidência no código, sem medida numérica. Line_no é a linha inicial da instrução.
"""
