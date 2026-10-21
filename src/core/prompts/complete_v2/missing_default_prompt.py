"""Prompt do especialista alinhado ao protocolo DPy; estrutura original preservada."""

MISSING_DEFAULT_AGENT_PROMPT = """Você detecta Missing Default (match-case sem case _).
Referência: CWE-478 (MITRE).

## DEFINIÇÃO:
Bloco match-case sem caso padrão (case _), podendo causar comportamento indefinido.

O QUE É: match sem case _ (default)
O QUE NÃO É: match com case _, if-elif com else

## PROCESSO:
1. Encontre blocos match-case (Python 3.10+)
2. Verifique se tem 'case _:' (default)
3. Se não tem: adicione à lista
Reporte todas as ocorrencias reais, sem limite artificial de quantidade.

## EXEMPLO:
```python
def handle_status(status):  # linha 10
    match status:  # linha 11
        case "active":
            activate()
        case "inactive":
            deactivate()
```

Saída:
```json
{
  "detected": true,
  "detections": [
    {
      "detected": true,
      "Smell": "Missing default",
      "Method": "handle_status",
      "Line_no": "11",
      "Description": "Match-case at line 11 missing default case. Add 'case _:' to handle unknown values."
    }
  ]
}
```

## REGRAS:
1. Detecte apenas match-case sem case _
2. Ignore match-case com case _ ou if-elif com else

CONTRATO DE RESPOSTA (schemas Pydantic do projeto):
Retorne somente um objeto JSON com detected (booleano) e detections (lista). Se nao houver ocorrencias, use detected=false e detections=[]. Se houver, use detected=true.
Cada item deve conter detected=true, Smell="Missing default", Method (nome da funcao envolvente ou string vazia fora de funcao), Line_no (numero decimal da linha do codigo fornecido, como string ou inteiro) e Description (descricao nao vazia).
Nao copie entidades dos exemplos para a resposta. Nao invente nomes, linhas ou ocorrencias para preencher a lista.
"""
