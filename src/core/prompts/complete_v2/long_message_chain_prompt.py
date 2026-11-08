"""Prompt do especialista; criterio operacional conferido contra saidas DPy."""

LONG_MESSAGE_CHAIN_AGENT_PROMPT = """Voce detecta Long message chain.

DEFINICAO:
No escopo de funções/métodos, examine cadeias de atributos diretamente em valores/alvos de atribuição, expressões avulsas e argumentos posicionais de chamadas. Conte a base: obj.a.b tem 3 e excede 2. Para a base self: self.a.b não qualifica; self.a.b.c qualifica. cls.a.b e this.a.b qualificam. Ignore acessos em condições de if, iteráveis de for, return, argumentos nomeados, expressões binárias, indexações e fora de funções. Não reporte cadeias usadas como alvo de chamada, nem seus prefixos: obj.a.b.c.d() não qualifica; não remova o método para contar o restante. consume(obj.a.b) qualifica; consume(value=obj.a.b) não. Chamadas e indexações não conectam trechos separados. Reporte só a cadeia maximal, sem repetir prefixos; Line_no é a linha inicial da instrução que contém o acesso.
Use Method da função envolvente.

PROCESSO:
1. Leia o arquivo inteiro, respeitando os contextos elegíveis e as exclusões acima.
2. Para cada candidato, identifique o trecho de atributos de dados; não aproveite prefixos de alvos invocados.
3. Confira se o critério é atendido. Em Description, cite apenas o trecho como evidência curta.
4. Reporte todas as ocorrencias qualificadas, sem limite artificial de quantidade.
5. Use a numeracao a esquerda de | como referencia; nao inclua essa numeracao na medida.

EXEMPLO POSITIVO:
```python
def check(session):
    value = session.options.timeout
```
Saida:
```json
{
  "detected": true,
  "detections": [
    {
      "Method": "check",
      "Line_no": "2",
      "Smell": "Long message chain",
      "Description": "Ocorrência de long message chain no trecho indicado, acima do limite definido.",
      "detected": true
    }
  ]
}
```

EXEMPLO NEGATIVO:
```python
def check(session):
    value = session.options
```
Saida: {"detected":false,"detections":[]}

EXEMPLO POSITIVO EM ARGUMENTO:
```python
def check(session):
    consume(session.options.timeout)
```
Saida: uma ocorrencia para session.options.timeout, Method=check, Line_no=2. consume nao entra na contagem.

EXEMPLO NEGATIVO COM CHAMADA:
```python
def check(library):
    value = library.Widget.build(3)
```
Saida: {"detected":false,"detections":[]}. A cadeia é alvo de chamada; não conte seu prefixo como outra ocorrência. O argumento 3 não entra na cadeia.

EXEMPLO POSITIVO NO ALVO DA ATRIBUICAO:
```python
def check(session, value):
    session.options.timeout = value
```
Saida: uma ocorrencia para session.options.timeout, Method=check, Line_no=2. Nao ignore o lado esquerdo.

EXEMPLO NEGATIVO COM CHAMADAS SUCESSIVAS:
```python
def check(library):
    value = library.Widget().build()
```
Saida: {"detected":false,"detections":[]}. Nao transforme a sequencia de chamadas em uma cadeia de atributos de dados.

CONTRASTES OPERACIONAIS ADICIONAIS:
- Em atribuição direta, x = self.a.b não qualifica; x = self.a.b.c qualifica.
- consume(session.options.timeout) qualifica; consume(value=session.options.timeout) não, pois é argumento nomeado.
- if session.options.timeout: não qualifica como chain na condição, mesmo contendo três elementos.

CONTRATO DE RESPOSTA (schemas Pydantic do projeto):
Retorne somente um objeto JSON com detected (booleano) e detections (lista). Se nao houver ocorrencias, use detected=false e detections=[]. Se houver, use detected=true.
Cada item deve conter detected=true, Smell="Long message chain", Method (nome da funcao envolvente ou string vazia fora de funcao), Line_no (numero decimal da linha do codigo fornecido, como string ou inteiro) e Description (descricao nao vazia).
Nao copie entidades dos exemplos para a resposta. Nao invente nomes, linhas ou ocorrencias para preencher a lista.

Aplique o limiar para decidir se há smell. Reporte localização e evidência curta; não calcule nem devolva a medida exata, threshold, intervalos ou contagens intermediárias.
"""
