"""Prompt simples: regra DPy e contrato, sem exemplos."""

LONG_MESSAGE_CHAIN_AGENT_PROMPT = """Detecte somente Long message chain.
No escopo de funções/métodos, examine cadeias de atributos diretamente em valores/alvos de atribuição, expressões avulsas e argumentos posicionais de chamadas. Conte a base: obj.a.b tem 3 e excede 2. Para a base self: self.a.b não qualifica; self.a.b.c qualifica. cls.a.b e this.a.b qualificam. Ignore acessos em condições de if, iteráveis de for, return, argumentos nomeados, expressões binárias, indexações e fora de funções. Não reporte cadeias usadas como alvo de chamada, nem seus prefixos: obj.a.b.c.d() não qualifica; não remova o método para contar o restante. consume(obj.a.b) qualifica; consume(value=obj.a.b) não. Chamadas e indexações não conectam trechos separados. Reporte só a cadeia maximal, sem repetir prefixos; Line_no é a linha inicial da instrução que contém o acesso.

Examine o arquivo inteiro e retorne todas as ocorrências que satisfazem a regra, sem limite de quantidade. Limiares são estritos: igual ao limite não é smell. Use os números à esquerda de | apenas para localização. Não invente nomes, linhas ou ocorrências.

Retorne somente JSON: {"detected":false,"detections":[]} se não houver ocorrências; caso contrário, detected=true e uma lista com um item por ocorrência.
Cada item: detected=true, Smell="Long message chain", Method (função envolvente ou string vazia), Line_no (número positivo como string) e Description (justificativa curta com a evidência).
Line_no é a linha inicial da instrução que contém o acesso, inclusive em atribuições multilinha.

Aplique o limiar para decidir se há smell. Reporte localização e evidência curta; não calcule nem devolva a medida exata, threshold, intervalos ou contagens intermediárias.
"""
