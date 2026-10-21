# Detector de implementation smells — versão 2.0

Esta versão parte da implementação de Estevam, substitui o dataset e introduz avaliação por ocorrência contra o gabarito DPy. Este documento descreve o código atual e suas diferenças em relação ao original; não apresenta resultados experimentais.

A base de desenvolvimento é `MeuProjeto/multi-agent-smell-detector`. `ProjetoEstevam/multi-agent-smell-detector` conserva o código original do commit `afb065c`, para consulta. Referências bibliográficas, corpus minerado e dados de origem foram preservados.

## Arquitetura preservada

O fluxo continua sendo: arquivo Python → supervisor → 11 especialistas → respostas Pydantic → filtros e metadados → resultados. Cada especialista procura um único smell. O supervisor coordena as chamadas deterministicamente; não é uma LLM adicional que escolhe os agentes ou julga as respostas.

Continuam em uso `langchain_openai.ChatOpenAI`, `with_structured_output(schema, method="json_mode")`, schemas Pydantic e três conjuntos de prompts identificados por origem. A API FastAPI original foi preservada; o experimento e sua avaliação são executados pelo comando abaixo, não pela API.

Todos os 11 especialistas recebem cada arquivo selecionado, mesmo quando determinado par não participa da avaliação. O gabarito não é enviado às LLMs. Tokens abrangem todas as chamadas, não apenas os pares avaliados. Ainda não há uma implementação experimental de agente único nesta base.

## Mudanças no código do Estevam

| Arquivo ou área | Mudança |
| --- | --- |
| `src/core/supervisor/supervisor.py` | Modelo, tokens, temperatura, timeout, retries, concorrência, reasoning e provedor passaram a ser parâmetros. Um semáforo limita especialistas simultâneos. Erros e tokens são registrados por agente. Autenticação inválida interrompe a rodada; truncamento descarta a resposta incompleta e é registrado como falha. |
| `src/core/schemas/agent_response.py` | Thresholds usam tabela comum. Complex conditional passou de 3 no schema para 2; Long statement passou de 120 para 80. Magic number ganhou `number` opcional. Estrutura Pydantic e campos opcionais originais foram preservados. |
| `src/core/smell_rules.py` | Novo módulo de thresholds fixos e exceções numéricas. O modelo não pode redefinir o limiar aplicado pelos filtros. |
| `src/core/utils/detection_validator.py` | Filtros alinhados aos thresholds; Magic number exclui somente 0, 1 e -1; identificadores dunder não são descartados apenas por serem dunder; acrescentado filtro de comprimento de Long method. Permanecem fallbacks originais que aceitam algumas respostas sem medida verificável. |
| `src/core/prompts/` | Três subpastas: `simple_estevam`, `complete_estevam` e `complete_v2`, com 11 prompts em cada. Os dois primeiros preservam o original com thresholds atualizados; o terceiro contém as revisões descritas abaixo. |
| `src/core/supervisor/agent_config.py` | Seleciona explicitamente um dos três conjuntos, mantendo os mesmos especialistas e schemas. Conjuntos desconhecidos geram erro. |
| `scripts/run_experiment.py` | Único comando principal, instancia diretamente o supervisor e seleciona arquivos. Substitui os quatro comandos redundantes de execução. Não há outro transporte ou detector intermediário. |
| `scripts/experiment_evaluation.py` | Correspondência um a um entre previsões e ocorrências DPy, com regras por smell. |
| `scripts/evaluate_results.py` | Congela o gabarito e calcula métricas automaticamente ou offline. Normaliza somente campos declarados pelo modelo. |
| `scripts/sample_dataset.py` | Prepara a amostra a partir do corpus e das saídas DPy, incluindo seleção de pares positivos por smell. Não é executado durante a detecção. |

Normalizar campos significa, por exemplo, usar `start_line` quando falta a linha de um método ou extrair o valor numérico da descrição da própria previsão. O avaliador não usa o gabarito para completar uma previsão. Não há adaptador de outra arquitetura nesta execução.

Padrões: 8.192 tokens de saída por chamada, temperatura 0, timeout de 120 segundos, dois especialistas simultâneos e zero retries adicionais. `--reasoning default` omite o parâmetro; não significa raciocínio desativado. `--provider` permite fixar o provedor sem fallback.

## Novo dataset

A amostra fornecida contém 182 arquivos, 312 pares positivos `(arquivo, smell)`, 450 ocorrências positivas e 291 pares negativos. O manifesto tem 603 pares. O balanceamento é dos pares selecionados, não de todos os smells existentes nos arquivos.

| Local | Finalidade |
| --- | --- |
| `dataset/` | Arquivos disponíveis ao experimento. |
| `dataset/ground_truth/sample_pairs.csv` | Pares positivos selecionados. |
| `dataset/ground_truth/evaluation_pairs.csv` | Pares positivos e negativos avaliados, com contagens. |
| `dataset/ground_truth/dpy_implementation_smells_sample.csv` | Ocorrências dos pares selecionados, com localização e descrição. |
| `dataset/ground_truth/evaluation_manifest.json` | Metadados e política de seleção dos pares. |
| `dataset/sample_*.csv` e `dataset/sample_config.json` | Estatísticas e proveniência da amostragem. |
| `dataset_full/` | Corpus minerado; não é o dataset padrão da execução. |
| `results/dpy/` | Saídas brutas DPy que deram origem ao gabarito; não são resultados desta versão. |

Um arquivo pode ter ocorrências fora de seus pares selecionados. Os 603 pares, portanto, não representam os 182 × 11 pares possíveis. Caminhos relativos completos identificam arquivos; módulos homônimos de projetos diferentes não são combinados.

O código original incluía análises em notebooks por presença e contagem agregada. A métrica principal desta versão compara ocorrências localizadas contra o DPy.

## Conjuntos de prompts

| Nome de execução | Pasta | Conteúdo |
| --- | --- | --- |
| `simple_estevam` | `src/core/prompts/simple_estevam/` | Simple original, alterando somente Long statement de 120 para 80. |
| `complete_estevam` | `src/core/prompts/complete_estevam/` | Complete original, alterando somente Long statement de 120 para 80. |
| `complete_v2` | `src/core/prompts/complete_v2/` | Complete revisado desta versão, preservado integralmente. |

Cada conjunto tem 11 especialistas. Os originais preservam exemplos, formato, teto de detecções e exclusões semânticas; não recebem as outras correções do V2. Schemas, filtros do supervisor e avaliação são compartilhados. As diferenças de definição além dos thresholds continuam presentes e fazem parte da comparação.

O padrão do comando experimental é `complete_v2`. `--prompt-type all` executa os três conjuntos nos mesmos arquivos. Resultados e cópias dos prompts são separados pelo nome do conjunto. A API e as funções auxiliares do supervisor usam `simple_estevam` por padrão.

## Mudanças no complete V2

A tabela abaixo descreve somente `complete_v2`. Ela não se aplica aos dois conjuntos preservados de Estevam. As definições de referência estão em `smells.md`.

| Smell | Critério e alteração relevante |
| --- | --- |
| Long lambda function | Mais de 80 caracteres; exemplos de comprimento coerente. |
| Long statement | Mais de 80 caracteres, substituindo 120. O prompt atual considera a instrução completa, inclusive multilinha e strings de dados, e pede a linha inicial. |
| Long method | Mais de 67 linhas; identifica a própria função, com `Line_no` e `start_line` na linha de `def`/`async def`. |
| Long parameter list | Mais de 4 parâmetros. Mantidas as exclusões originais de `self`, `cls`, `*args` e `**kwargs`. |
| Long identifier | Mais de 20 caracteres; resposta pede `identifier_name` e comprimento. |
| Complex method | Complexidade ciclomática de McCabe maior que 7; localização na definição da função. |
| Complex conditional | Mais de 2 operadores `and`/`or` na mesma condição; schema e contrato coerentes com esse limite. |
| Long message chain | Mais de 2 elementos no acesso a atributos de dados, contando base e atributos. O original contava métodos com parênteses e excluía atributos. Agora distingue nomes invocados de atributos de dados, interrompe a sequência em chamadas/indexações, procura em argumentos e alvos de atribuição e evita duplicar prefixos. O complete apresenta positivos e negativos em igual quantidade. Essa interpretação foi inferida das saídas DPy disponíveis, não certificada pelo código-fonte do detector. |
| Empty catch block | `except` com somente `pass` ou uma única instrução `return`, com ou sem valor. Outros comandos impedem a classificação. |
| Missing default | `match` sem `case _`. |
| Magic number | Literal sem constante nomeada, exceto 0, 1 e -1. Retiradas exclusões gerais do original para testes, índices, contadores, 2/10/100 e contextos matemáticos. Resposta inclui `number`. |

Foi removido o teto artificial de dez detecções. Os prompts pedem todas as ocorrências qualificadas, o que pode aumentar tokens e truncamentos. Foram explicitados `detected`, `detections`, `Smell`, `Method`, `Line_no`, `Description` e as medidas do schema. A numeração fornecida com o código serve somente para localização.

As medidas continuam propostas pela LLM e filtradas pelo código existente; não foi introduzido um detector estático completo para substituir as respostas. Contagem de linhas de funções, instruções, Magic number e Long message chain ainda exigem validação metodológica contra o DPy antes de conclusões do experimento.

## Avaliação

A métrica principal é micro-F1 por ocorrência nos pares do manifesto:

`Precisão = TP / (TP + FP)`

`Recall = TP / (TP + FN)`

`F1 = 2 × TP / (2 × TP + FP + FN)`

- TP: previsão corresponde a uma ocorrência ainda não utilizada do gabarito.
- FP: previsão sem correspondência em um par avaliado, inclusive se o par é negativo.
- FN: ocorrência do gabarito sem previsão correspondente.
- Fora do escopo: previsão em par não selecionado; não entra como TP nem FP.

A correspondência é um a um. Previsões duplicadas não criam TPs adicionais. Além do mesmo arquivo e smell, o avaliador usa:

- Métodos: linha da definição e nome da função.
- Identificadores: nome e função envolvente; fora de função, nome e linha. Isso acomoda registros DPy ancorados na função.
- Empty catch block e Missing default: bloco localizado por AST. Se o gabarito indica apenas a linha da função, associa um bloco qualificante daquela função, respeitando a resolução do gabarito.
- Magic number: linha e valor numérico.
- Demais tipos: linha inicial registrada.

Macro-F1 considera os tipos com positivos ou erros e informa quantos entraram na média. Tipos só negativos e perfeitamente classificados não recebem F1 artificial de 1. Presença e contagem são diagnósticos complementares.

Falhas técnicas são registradas separadamente. No F1 operacional, o par continua avaliado quando o agente falha; ocorrências não encontradas permanecem FN. São avaliadas as detecções após os filtros do supervisor; itens descartados antes da gravação não são recuperados.

Avaliar todos os smells de todos os arquivos exige outro manifesto e gabarito completo. Não basta ampliar os pares usando o CSV amostrado, pois ele omite ocorrências fora da seleção. Uma avaliação completa deve ser identificada separadamente.

## Como executar

Use a raiz deste projeto, com as dependências de `pyproject.toml` instaladas. O script de amostragem também requer NumPy e pandas. Configure credenciais localmente ou por variáveis de ambiente; elas não são gravadas nos resultados.

Conferir seleção, tarefas e gabarito sem carregar credenciais ou chamar LLMs:

```powershell
python scripts/run_experiment.py --model gpt-6-luna --max-files 5 --prompt-type complete_v2 --dry-run
```

Executar uma seleção limitada:

```powershell
python scripts/run_experiment.py --model gpt-6-luna --max-files 5 --seed 1 --prompt-type complete_v2
```

Executar três modelos na mesma seleção:

```powershell
python scripts/run_experiment.py --models gpt-6-luna deepseek-v4.1-flash gemini-3.5-flash-lite --max-files 20 --seed 1 --prompt-type complete_v2
```

Os apelidos são mapeamentos locais de IDs, não garantia de disponibilidade futura. Também é aceito `--model provedor/modelo`. O padrão é até cinco arquivos; `--all-files` seleciona todos os elegíveis. Limites padrão são 3.000 linhas e 500 KB; arquivos excluídos não entram na rodada. A lista efetiva e seus hashes ficam salvos.

Use `--files-from results/experiments/IDENTIFICADOR/sample.json --all-files` para repetir uma seleção verificando hashes. `--prompt-type all` executa os três conjuntos nos mesmos arquivos. Tarefas planejadas = arquivos × modelos × conjuntos de prompts × 11, sem retries.

Outras opções: `--dataset`, `--env-file`, `--max-tokens`, `--concurrency`, `--sequential`, `--timeout`, `--max-retries`, `--temperature`, `--reasoning`, `--provider`, `--output-dir`, `--evaluation-pairs`, `--ground-truth` e `--no-evaluate`. Consulte `--help`.

O F1 é automático quando manifesto e gabarito estão disponíveis. Para recalcular offline:

```powershell
python scripts/evaluate_results.py --run results/experiments/IDENTIFICADOR
```

Antes das chamadas são salvos seleção, configuração, prompts, hashes de código e cópias dos pares e ocorrências do gabarito. Depois são salvos detecções, tokens, tempos, falhas e métricas. `raw.jsonl` contém resultados por arquivo do supervisor, não o texto bruto das respostas da LLM. O custo em dólares permanece não preenchido; tokens não são convertidos com preços presumidos.

## Organização

Esta base mantém `src/`, quatro scripts (execução, duas partes da avaliação e amostragem), dataset, corpus minerado, dados DPy, configuração, dependências e `tests/`. Os testes verificam avaliação, seleção, thresholds e preservação de LangChain/Pydantic. São ferramentas de desenvolvimento; o experimento não depende deles.

Documentação complementar:

- [Definições e thresholds dos smells](smells.md).
- [Mudanças de cada prompt em relação ao Estevam](MUDANCAS_PROMPTS.md).
- [Mudanças dos demais arquivos em relação ao Estevam](MUDANCAS_PROJETO.md).

Novas rodadas são gravadas em `results/experiments/`. Análises e resultados do projeto original não integram a implementação da versão 2.0.
