# Mudanças nos prompts — Estevam → versão 2.0

Base de comparação: código original de Estevam, commit `afb065c`.

## Organização dos três conjuntos

- `simple_estevam`: `src/core/prompts/simple_estevam/`; cópia do simple original com somente Long statement 120 → 80.
- `complete_estevam`: `src/core/prompts/complete_estevam/`; cópia do complete original com somente Long statement 120 → 80.
- `complete_v2`: `src/core/prompts/complete_v2/`; complete revisado preservado integralmente.
- Nos dois conjuntos de Estevam, os outros thresholds já coincidiam; nenhuma definição, exemplo, exclusão, limite de detecções ou contrato foi reescrito.
- O simple revisado não integra os três conjuntos solicitados.
- Seleção: `--prompt-type simple_estevam`, `complete_estevam`, `complete_v2` ou `all`.
- As seções abaixo descrevem exclusivamente as mudanças do **complete V2** em relação ao complete original.

## Mudanças comuns  V2

- Mantidos os 11 especialistas.
- O conjunto revisado contém 11 arquivos de prompts completos.
- Removido o limite artificial de dez detecções onde existia.
- Explicitado o objeto JSON com `detected` e `detections`; ausência de ocorrências usa `false` e lista vazia.
- Explicitados os campos de cada item: `detected`, `Smell`, `Method`, `Line_no` e `Description`.
- Explicitados os campos de medida e os thresholds fixos de cada schema.
- Adicionadas instruções para não copiar entidades dos exemplos nem inventar ocorrências.
- Nos prompts reescritos, explicitado que a numeração adicionada ao código serve para localização e não entra nas medidas.
- Simplificados cabeçalhos dos arquivos. As referências conceituais ficam documentadas em `smells.md`.

## 1. Complex conditional

Arquivos: `src/core/prompts/complete_v2/complex_conditional_prompt.py`.

- Mantido o critério `> 2` operadores `and`/`or` na mesma condição.
- Adicionado contrato com `logical_operators` e `threshold=2`.
- Removido o teto de detecções .

## 2. Complex method

Arquivos: `src/core/prompts/complete_v2/complex_method_prompt.py`.

- Mantido McCabe `> 7`.
- `Line_no` deixou de ser vazio e passou a indicar a linha de `def`/`async def`, igual a `start_line`.
- Mantidos `start_line` e `end_line`; explicitado `cyclomatic_complexity`.
- Corrigidos complexidade e limites de linha do exemplo complete: CC 9 → 8; fim 17 → 19.
- Removido o teto de detecções .

## 3. Empty catch block

Arquivos: `src/core/prompts/complete_v2/empty_catch_block_prompt.py`.

- Antes: `except` vazio/com `pass`; `return` tratado como tratamento válido.
- Agora: corpo com somente `pass` ou uma única instrução `return`, com ou sem valor.
- Explicitado que logging, `raise`, atribuição ou outro comando impedem a classificação.
- Linha solicitada: `except`.
- Exemplo positivo passou a incluir `return None`; inclui negativo com logging e retorno.

## 4. Long identifier

Arquivos: `src/core/prompts/complete_v2/long_identifier_prompt.py`.

- Mantido comprimento `> 20`.
- Removida a exclusão geral de nomes dunder .
- Explicitados `identifier_name`, `length` e `threshold=20`.
- Solicitada uma ocorrência por escopo de definição, não por uso.
- Mantida a distinção entre definições, imports e strings.
- Corrigida a contagem do identificador de exemplo : 31 → 30 caracteres.

## 5. Long lambda function

Arquivos: `src/core/prompts/complete_v2/long_lambda_function_prompt.py`.

- Mantido comprimento `> 80`.
- Explicitada a medida desde `lambda` até o final da expressão, sem atribuição ou chamada envolvente, inclusive em múltiplas linhas.
- Explicitado que exatamente 80 não qualifica.
- Linha solicitada: início da lambda.
- Substituído o exemplo positivo por uma lambda de 83 caracteres; inclui negativo de 80 caracteres.
- Explicitados `lambda_length` e `threshold=80`.

## 6. Long message chain

Arquivos: `src/core/prompts/complete_v2/long_message_chain_prompt.py`.

- Antes: `> 2` métodos com parênteses; atributos sem parênteses excluídos.
- Agora: `> 2` elementos em acessos a atributos de dados, contando base e atributos consecutivos.
- Explicitada a distinção entre atributo de dados e nome de método/funcão invocado.
- Chamadas e indexações interrompem a sequência; argumentos e expressões independentes não são somados.
- Incluídos acessos dentro de argumentos e no alvo de atribuições.
- Solicitada a cadeia maximal, sem duplicar prefixos.
- `Description` deve identificar o trecho e sua contagem; medida em `chain_length`, com `threshold=2`.
- Três exemplos positivos e três negativos.
- A interpretação operacional deriva das saídas DPy disponíveis; equivalência interna com o detector não foi comprovada.

## 7. Long method

Arquivos: `src/core/prompts/complete_v2/long_method_prompt.py`.

- Mantido comprimento `> 67` linhas.
- Solicitados início e fim da própria função, sem usar o tamanho do arquivo ou da classe.
- `Line_no` passou a indicar a definição, igual a `start_line`.
- Explicitados `total_lines`, `start_line`, `end_line` e `threshold=67`.
- Substituídos exemplos abreviados por uma função positiva real de 70 linhas; inclui uma função curta negativa.

## 8. Long parameter list

Arquivos: `src/core/prompts/complete_v2/long_parameter_list_prompt.py`.

- Mantido número de parâmetros `> 4`.
- Mantidas as exclusões de `self`, `cls`, `*args` e `**kwargs`.
- Adicionado contrato com `parameter_count` e `threshold=4`.
- Removido o teto de detecções .

## 9. Long statement

Arquivos: `src/core/prompts/complete_v2/long_statement_prompt.py`.

- Threshold 120 → 80 caracteres.
- Unidade solicitada: instrução completa, inclusive multilinha e strings de dados; não apenas cada linha física.
- Excluídos da medida a numeração adicionada, comentários isolados e docstrings isoladas.
- Linha solicitada: início da instrução.
- Substituído o exemplo positivo por uma instrução de 83 caracteres; inclui negativo curto.
- Explicitados `line_length` e `threshold=80`.

## 10. Magic number

Arquivos: `src/core/prompts/complete_v2/magic_number_prompt.py`.

- Exceções numéricas reduzidas a `0`, `1` e `-1`, incluindo equivalentes decimais.
- Retiradas isenções gerais de `2`, `-2`, `10`, `100`, testes, índices, loops e contextos matemáticos.
- Explicitado que dígitos em strings e comentários não são literais numéricos de código.
- Mantido o critério de literal sem constante nomeada.
- Adicionado `number` ao contrato e aos exemplos.
- Reescritos os exemplos para distinguir literal usado diretamente de constante nomeada.

## 11. Missing default

Arquivos: `src/core/prompts/complete_v2/missing_default_prompt.py`.

- Mantida a ausência de `case _` em `match-case`.
- Adicionado contrato JSON compatível com o schema existente.
- Removido o teto de detecções .
