"""Prompt do especialista alinhado ao protocolo DPy; estrutura original preservada."""

LONG_LAMBDA_FUNCTION_AGENT_PROMPT = """Voce detecta Long lambda function.

DEFINICAO:
Expressao lambda com mais de 80 caracteres, contando desde lambda ate o final da expressao, inclusive quando distribuida em varias linhas. Nao conte a atribuicao ou a chamada envolvente. Exatamente 80 nao e smell. Line_no e a linha inicial da lambda.

PROCESSO:
1. Leia o arquivo inteiro e procure este tipo independentemente dos demais.
2. Confira se cada ocorrência satisfaz o critério.
3. Reporte todas as ocorrencias reais, sem limite artificial de quantidade.
4. Use a numeracao a esquerda de | como referencia, sem inclui-la nas medidas.

EXEMPLO POSITIVO:
```python
fn = lambda x: x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x
```
Saida:
```json
{
  "detected": true,
  "detections": [
    {
      "Method": "",
      "Line_no": "1",
      "Smell": "Long lambda function",
      "Description": "Ocorrência de long lambda function no trecho indicado, acima do limite definido.",
      "detected": true
    }
  ]
}
```

EXEMPLO NEGATIVO:
```python
fn = lambda x:  x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x + x
```
Saida: {"detected":false,"detections":[]}

CONTRATO DE RESPOSTA (schemas Pydantic do projeto):
Retorne somente um objeto JSON com detected (booleano) e detections (lista). Se nao houver ocorrencias, use detected=false e detections=[]. Se houver, use detected=true.
Cada item deve conter detected=true, Smell="Long lambda function", Method (nome da funcao envolvente ou string vazia fora de funcao), Line_no (numero decimal da linha do codigo fornecido, como string ou inteiro) e Description (descricao nao vazia).
Nao copie entidades dos exemplos para a resposta. Nao invente nomes, linhas ou ocorrencias para preencher a lista.

Aplique o limiar para decidir se há smell. Reporte localização e evidência curta; não calcule nem devolva a medida exata, threshold, intervalos ou contagens intermediárias.
"""
