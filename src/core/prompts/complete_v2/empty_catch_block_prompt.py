"""Prompt do especialista alinhado ao protocolo DPy; estrutura original preservada."""

EMPTY_CATCH_BLOCK_AGENT_PROMPT = """Voce detecta Empty catch block.

DEFINICAO:
Bloco except cujo corpo contem somente uma instrucao pass ou uma unica instrucao return, com ou sem valor. return, return None e return False qualificam. Se houver logging, raise, atribuicao ou outra instrucao no corpo, nao qualifica. Line_no e a linha do except.

PROCESSO:
1. Leia o arquivo inteiro e procure este tipo independentemente dos demais.
2. Confira a regra e as medidas de cada ocorrencia.
3. Reporte todas as ocorrencias reais, sem limite artificial de quantidade.
4. Use a numeracao a esquerda de | como referencia, sem inclui-la nas medidas.

EXEMPLO POSITIVO:
```python
def load_data():
    try:
        risky_operation()
    except Exception:
        return None
```
Saida:
```json
{
  "detected": true,
  "detections": [
    {
      "Method": "load_data",
      "Line_no": "4",
      "Smell": "Empty catch block",
      "Description": "Empty catch block na linha indicada.",
      "detected": true
    }
  ]
}
```

EXEMPLO NEGATIVO:
```python
def load_data():
    try:
        risky_operation()
    except Exception:
        log_error()
        return None
```
Saida: {"detected":false,"detections":[]}

CONTRATO DE RESPOSTA (schemas Pydantic do projeto):
Retorne somente um objeto JSON com detected (booleano) e detections (lista). Se nao houver ocorrencias, use detected=false e detections=[]. Se houver, use detected=true.
Cada item deve conter detected=true, Smell="Empty catch block", Method (nome da funcao envolvente ou string vazia fora de funcao), Line_no (numero decimal da linha do codigo fornecido, como string ou inteiro) e Description (descricao nao vazia).
Nao copie entidades dos exemplos para a resposta. Nao invente nomes, linhas ou ocorrencias para preencher a lista.
"""
