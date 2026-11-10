# Detector de implementation smells — TCC 2.0

Comparação entre supervisor com 11 especialistas e agente único para detectar 11 implementation smells em Python, usando o DPy como referência operacional. As duas arquiteturas usam LangChain, respostas validadas com Pydantic e o mesmo motor de execução, persistência e avaliação. A coleta definitiva foi encerrada em 10/11/2026: as 12 condições processaram os mesmos 182 arquivos (2.184 análises de arquivo). Houve 95 falhas finais de tarefas, preservadas na avaliação; por isso o status técnico é `incomplete`, com `analysis_status: complete`.

Este README reúne a documentação ativa.

## Resultados definitivos

- Relatório incluído no pacote de resultados: `final_experiment/analysis/report.html`.
- Métricas e custos: `final_experiment/analysis/conditions.csv`; desempenho por categoria: `final_experiment/analysis/by_smell.csv`.
- Protocolo executado incluído no pacote: `final_experiment/frozen_protocol.json`.
- A auditoria final verificou os 2.184 checkpoints e os journals das 12 condições. O custo conhecido foi US$ 19,4133473586; oito tentativas têm custo desconhecido, logo a cobrança total não é determinada.
- As respostas brutas, prompts enviados, schemas, checkpoints e journals foram preservados integralmente.
- Os resultados foram movidos da pasta externa `TCC-results/final_experiment` para `final_experiment/` neste projeto. Caminhos absolutos nos manifestos registram a localização original e não foram reescritos.
- Há alterações locais posteriores ao congelamento em cinco prompts completos. Esta limpeza não as modificou; não se deve apresentar automaticamente o código atual como idêntico ao executado. Os prompts efetivamente enviados estão nos artefatos de cada condição.


## Downloads dos dados e resultados

O Git versiona o código, testes, dependências e o dataset selecionado (`dataset/`, com os 182 arquivos e o gabarito). As pastas completas `dataset_full/` e `final_experiment/` são distribuídas em dois anexos da [Release v2.0-tcc](https://github.com/LuisDallas1/multi-agent-smell-detector/releases/tag/v2.0-tcc):

| Anexo | Conteúdo |
| --- | --- |
| [dataset_full.zip](https://github.com/LuisDallas1/multi-agent-smell-detector/releases/download/v2.0-tcc/dataset_full.zip) | Dataset completo, DPy e configuração; sem os diretórios `.git` dos projetos internos |
| [final_experiment.zip](https://github.com/LuisDallas1/multi-agent-smell-detector/releases/download/v2.0-tcc/final_experiment.zip) | Coleta completa das 12 condições, protocolos, referências, prompts, respostas, checkpoints, journals e análise consolidada |

Os links passam a funcionar após a publicação da Release. Baixe os dois anexos e extraia-os **na raiz deste repositório**. Cada ZIP já contém a pasta de mesmo nome; não crie uma pasta adicional ao extrair. A estrutura esperada é:

```text
multi-agent-smell-detector/
  src/
  scripts/
  dataset/
  dataset_full/          # extraido de dataset_full.zip
  final_experiment/      # extraido de final_experiment.zip
```

No PowerShell, com os ZIPs baixados em Downloads e o terminal na raiz do projeto:

```powershell
Expand-Archive -LiteralPath (Join-Path $HOME 'Downloads/dataset_full.zip') -DestinationPath .
Expand-Archive -LiteralPath (Join-Path $HOME 'Downloads/final_experiment.zip') -DestinationPath .
python -B scripts/analyze_study.py --study final_experiment --dataset dataset
```

Use uma pasta de projeto sem uma coleta prévia para evitar misturar arquivos. Os manifestos históricos mantêm seus caminhos originais. A opção `--dataset dataset` aponta a análise para os arquivos locais, sem editar esses manifestos nem as previsões. A análise regrava seus relatórios derivados; use `--output outra-pasta` se quiser preservar também os relatórios originais.

Para preparar os anexos e publicar uma nova versão, consulte [RELEASING.md](RELEASING.md).

## Experimento

| Item | Configuração |
| --- | --- |
| Arquiteturas | Multiagente: supervisor determinístico e 11 especialistas; único: uma tarefa com 11 grupos obrigatórios |
| Estratégias | `simple_v2`, com regras curtas e contrato; `complete_v2`, com definições, processo e exemplos |
| Matriz | 3 LLMs × 2 arquiteturas × 2 prompts = 12 condições |
| Repetições | Uma execução por condição |
| Dataset | Mesmos 182 arquivos em todas as condições |
| Avaliação selecionada | 603 células (arquivo, smell): 312 positivas e 291 negativas; 450 ocorrências de referência |
| Métrica principal | Micro-F1 por ocorrência nos pares selecionados |
| Tarefas iniciais | 2.002 por condição multiagente; 182 por condição única; total 13.104 |
| Ordem | Multiagente antes do único; GPT → DeepSeek → Haiku; simples antes do completo; arquivos sequenciais |

Todos os 11 especialistas são executados em cada arquivo. O agente único procura todos os tipos. O gabarito só entra na avaliação posterior; não seleciona agentes, não fornece localizações ao modelo e não corrige previsões. O custo abrange a execução completa, inclusive previsões fora do escopo e tentativas inválidas.

As arquiteturas reutilizam o motor em `src/core/execution`, schemas e avaliador. Os prompts de `src/core/prompts/simple_v2` e `complete_v2` contêm suas regras diretamente. O agente único incorpora integralmente essas seções pelo builder em `src/core/single_agent/prompts`, alterando o envelope para os 11 grupos. Não há adaptador HTTP substituindo LangChain, segmentação automática dos arquivos ou ferramentas de análise estática fornecidas à LLM. São tetos de tokens por chamada distintos por arquitetura, não computação equivalente.

## Modelos e parâmetros

| Apelido | ID enviado | Endpoint fixo | Raciocínio | Temperatura | Seed |
| --- | --- | --- | --- | --- | --- |
| `gpt-6-luna` | `openai/gpt-6-luna` | `openai` | low | omitida | 42 |
| `deepseek-v4.1-flash` | `deepseek/deepseek-v4.1-flash` | `deepinfra/fp8` | low | 0 | 42 |
| `claude-haiku-5.5` | `anthropic/claude-haiku-5.5` | `anthropic` | low | omitida | omitida |

Parâmetros omitidos seguem a política de capacidades adotada, não equivalem a zero. Low não significa a mesma quantidade de computação nos três modelos. Temperatura e seed não garantem reprodução exata. O endpoint é fixado sem fallback. O preflight público verifica capacidades antes de carregar credenciais na execução real; o dry-run é offline e não faz essa consulta.

| Política | Multiagente | Agente único |
| --- | --- | --- |
| Tokens iniciais | 8.192 por especialista | 32.768 para os 11 grupos |
| Recuperação por truncamento | diretamente 32.768 | 32.768 |
| Repetições adicionais de resposta | 1 | 1 |
| Retries SDK | 0 | 0 |
| Concorrência de tarefas | 2 | 2 (há só uma tarefa por arquivo) |
| Timeout configurado no cliente | 120 segundos | 120 segundos |
| Formato | JSON mode + Pydantic | JSON mode + Pydantic |

O timeout do cliente não é um teto global de duração da tarefa. Respostas inválidas podem usar a repetição prevista; o orçamento aumenta somente por truncamento. A normalização remove apenas uma cerca Markdown externa; não repara JSON parcial. O contrato `occurrence-v4-identity-location` exige identidade, localização e evidência curta, sem medidas exatas. `identifier_name` e `number` continuam obrigatórios para seus tipos. Não há pós-filtro numérico para excluir previsões erradas.

## Dataset, gabarito e F1

`dataset/` contém os arquivos selecionados. `dataset_full/` conserva os repositórios de origem, o executável DPy e sua configuração. Não regenere a amostra durante a coleta.

| Insumo | Uso |
| --- | --- |
| `dataset/ground_truth/evaluation_pairs.csv` | Define exatamente quais células serão avaliadas e sua contagem |
| `dataset/ground_truth/dpy_implementation_smells_sample.csv` | Ocorrências DPy dessas células |
| `dataset/ground_truth/evaluation_manifest.json` | Proveniência e configuração da avaliação |
| `dataset/ground_truth/dpy_raw/` | Exportações originais DPy preservadas, usadas na auditoria do gabarito |
| `dataset/sample_config.json`, quando presente | Proveniência da amostragem |

Uma célula é um par (arquivo, tipo de smell), não uma ocorrência. Na célula positiva, as ocorrências de referência participam da correspondência um a um: previsão correspondente = TP; referência sem previsão = FN; previsão sem referência = FP. A correspondência usa a identidade/localização específica do tipo no avaliador compartilhado, não a quantidade total detectada nem a medida numérica declarada pelo modelo.

Na célula negativa, uma ocorrência prevista é FP; ausência de previsão numa resposta válida confirma ausência na análise por presença. Uma tarefa falha não confirma TN. Células não selecionadas são ignoradas no F1, mesmo que o modelo encontre nelas ocorrências reais; suas previsões e custos permanecem registrados. TN é uma noção por presença/célula, não por ocorrência individual; não se calcula uma infinidade de TN por linhas sem smell.

O F1 operacional é `2TP / (2TP + FP + FN)`, acompanhado de taxa de respostas válidas, falhas e cobertura. Falhas sem previsões podem deixar referências como FN no resultado operacional, sem afirmar que a resposta válida teria sido negativa. Análises de respostas válidas e subconjuntos comuns são complementares e precisam declarar a cobertura. Compare condições nos mesmos arquivos/células, usando reamostragem pareada por arquivo.

A amostragem não torna representativos todos os repositórios Python. Há arquivos usados na exploração dentro dos 182 arquivos finais: o conjunto não é independente do desenvolvimento dos prompts. O DPy é a referência operacional escolhida, não uma certificação de verdade universal. Não atribuir ao artigo todas as peculiaridades descobertas no executável.

## Definições dos smells

Os limiares são estritos: igualdade não qualifica. As regras abaixo resumem os prompts; o conteúdo congelado dos próprios arquivos determina as instruções enviadas.

| Smell | Critério |
| --- | --- |
| Long lambda function | Expressão lambda com mais de 80 caracteres |
| Long statement | Instrução normalizada com mais de 80 bytes UTF-8 nos controles do detector; não linha física |
| Long method | Função com mais de 67 linhas |
| Long parameter list | Mais de 4 parâmetros; prompts excluem self, cls, *args e **kwargs |
| Long identifier | Identificador com mais de 20 caracteres |
| Complex method | Complexidade ciclomática de McCabe maior que 7 |
| Complex conditional | Mais de 2 operadores and/or na mesma condição |
| Long message chain | Mais de 2 elementos nos contextos operacionais elegíveis, com particularidades abaixo |
| Empty catch block | Except contendo somente pass ou uma instrução return |
| Missing default | Match sem case _ incondicional |
| Magic number | Literal numérico no escopo elegível, exceto 0, 1, -1 e equivalentes decimais |

Particularidades confirmadas por controles caixa-preta:

- **Statement:** pode ser multilinha. Strings, docstrings de módulo/função e atribuições globais podem qualificar. Excluem-se assinaturas de funções, cabeçalhos de controle, docstrings e campos diretamente em classe e instruções no corpo de case. Imports diretamente no módulo foram excluídos; imports dentro de função ou de if no módulo podem qualificar. Numeração, comentários e espaços supérfluos não entram. `ast.unparse` não foi demonstrado equivalente à normalização interna do detector.
- **Chain:** atribuições diretas (valores/alvos), expressões avulsas e argumentos posicionais qualificaram. `obj.a.b`, `cls.a.b` e `this.a.b` qualificaram; `self.a.b` não, mas `self.a.b.c` sim. Cadeias usadas como alvo de chamada não qualificaram, nem seus prefixos: `obj.a.b.c.d()` foi negativo. Condições de if, iteráveis de for, return, argumentos nomeados, expressões binárias, indexações e acessos fora de funções foram negativos nos casos testados. Não contar todo ponto como elemento elegível.
- **Magic number:** a política atual inclui defaults, índices, fatias, testes e cálculos no escopo de funções; exclui booleanos, literais fora de funções e dentro de chamadas, inclusive argumentos. Maiúsculas locais não isentam. Para negativo, a saída identifica o literal interno sem o sinal unário; ocorrências repetidas são preservadas.
- **Catch:** logging, raise, atribuição ou outro comando adicional impede a classificação pela regra de corpo isolado.

A investigação do DPy não dá acesso à implementação interna nem prova equivalência completa para todos os programas. Os prompts não pedem que a LLM conheça o nome/versão do detector; as regras relevantes são explícitas.

## Execução

Use o ambiente com as dependências de `pyproject.toml`/`uv.lock` e o runtime do manifesto. A conferência verifica seleção, existência dos arquivos e runtime; não calcula hashes de conteúdo. A instalação de dependências é separada; o dry-run não instala nem atualiza pacotes.

O plano é gerado diretamente de `dataset/ground_truth/evaluation_pairs.csv` e do gabarito atual. Não é necessário preparar nem manter uma pasta externa de protocolo. Cada nova coleta salva seu próprio `frozen_protocol.json`, `sample.json` e referência na pasta de saída; a retomada usa esses arquivos da própria rodada. Conferência sem credenciais, rede LLM ou custo:

```powershell
python -B scripts/frozen_study.py
python -B scripts/run_study.py --dry-run
python -B scripts/audit_dpy.py
```

Coleta completa, com chamadas pagas. O exemplo abaixo define uma pasta de saída no diretório pessoal do usuário; a variável `$saida` é reutilizada nos comandos de retomada e análise:

```powershell
$saida = Join-Path $HOME 'TCC-results/final_experiment'
python -B scripts/run_study.py --output-dir "$saida"
```

O destino padrão dos executores é a pasta `TCC-results` no diretório pessoal do usuário. Use `--output-dir` para escolher outro destino e não sobrescreva uma pasta de coleta existente. As credenciais são carregadas internamente somente na execução real; não integram manifestos, logs ou snapshots. O `.env` não deve ser exibido, versionado ou arquivado.

Para executar uma arquitetura/LLM de cada vez sem alterar a seleção, use o executor nativo. Exemplo pago do multiagente, GPT e ambos os prompts:

```powershell
python -B scripts/frozen_study.py
python -B scripts/run_experiment.py --architecture multiagent --model gpt-6-luna --prompt-type paired --generation-profile experiment --response-format json_mode --json-normalization markdown_fence --output-layout flat --files-from dataset/ground_truth/evaluation_pairs.csv --all-files --max-tokens 8192 --max-retry-tokens 32768 --response-retries 1 --max-retries 0 --concurrency 2 --timeout 120 --output-dir "$saida/gpt-6-luna/multiagent"
```

No agente único, trocar arquitetura para `single`, `--max-tokens` para 32768 e a pasta correspondente. Conservar os demais parâmetros e usar os IDs ativos. O orquestrador `run_study.py` gera o plano ao iniciar e verifica sua seleção e runtime durante a coleta. Não misture execuções manuais com o orquestrador sem conferir seu estado de retomada.

## Falhas, persistência e retomada

Cada tentativa preserva mensagens/prompt, pedido e resposta HTTP, fragmentos recebidos, metadados, JSON antes/depois de validação, detecções, decisões de extração, erros, tokens, custo e tempos disponíveis. O journal `evidence/` usa eventos numerados, índice, temporário, flush e troca atômica. Checkpoints por arquivo permitem reconstruir agregados. Bloqueios transitórios específicos do Windows têm repetição de gravação limitada, sem repetir a API. Erro permanente de escrita interrompe novas chamadas.

Não é possível garantir a preservação de uma resposta que o serviço não entregou nem de dados ainda não confirmados antes de uma falha física. Chamadas em voo podem ter custo desconhecido. Credenciais e cabeçalhos de autenticação são excluídos; a chave conhecida é redigida. Custo ausente é desconhecido, não zero. `usage.cost` inclui retries quando informado. Não somar custo do journal ao dos checkpoints: há sobreposição. Não inventar rateio por smell no agente único.

Retomada da coleta:

```powershell
python -B scripts/run_study.py --resume "$saida"
```

A retomada usa a seleção, os parâmetros e o protocolo salvos na própria rodada; runtime e prompts enviados continuam sendo conferidos. Arquivos confirmados não são repetidos, inclusive os com falha final. Para repetir arquivo interrompido, é necessário acrescentar explicitamente `--retry-interrupted`; isso pode repetir chamadas já cobradas. Não há retomada automática somente dos especialistas restantes dentro desse arquivo. Não use repetição ilimitada para obter resposta melhor. Autenticação, falta de crédito e permissões bloqueiam a continuidade; trabalho recebido permanece salvo.

Cópias na mesma unidade protegem contra exclusão acidental, mas não contra perda física do dispositivo. Guardar o pacote congelado e resultados também em outro local é uma ação separada.

## Organização e análise dos resultados

```text
final_experiment/
  sample.json, evaluation_pairs.csv, evaluation_reference.csv
  frozen_protocol.json, study.json, study_status.json
  gpt-6-luna/
    multiagent/simple_v2/ e complete_v2/
    single/simple_v2/ e complete_v2/
  deepseek-v4.1-flash/ (mesma organização)
  claude-haiku-5.5/ (mesma organização)
  analysis/
```

Cada condição contém previsões, métricas, custos, falhas, prompts, schemas, respostas, journal e checkpoints. A análise pode ser refeita offline sem novas chamadas:

```powershell
python -B scripts/analyze_study.py --study "$saida"
```

O pacote gera JSON/CSV/HTML com precisão, recall, micro/macro-F1 e métricas complementares por smell, arquivo, projeto e célula; presença e contagem são análises secundárias. Inclui cobertura técnica, erros por tipo/tentativa, recuperação, tokens, latência, custos conhecidos/desconhecidos e comparações pareadas. A análise registra completude; resultado parcial não vira coleta completa.

Bootstrap pareado por arquivo, 10.000 reamostras, seed 20261106 e IC95% descreve sensibilidade à amostra de arquivos. Não mede variabilidade de novas chamadas LLM, pois há uma execução por condição. Sensibilidade por projeto, McNemar/Holm por presença e fronteiras custo/desempenho são complementares/exploratórias. AUC e calibração não são estimáveis sem escores; não se inventam métricas indisponíveis.

## Scripts mantidos

| Script | Finalidade |
| --- | --- |
| `run_study.py` | Orquestrar coleta congelada, dry-run e retomada |
| `run_experiment.py` | Executor nativo por arquitetura, modelo e prompts; limites de arquivos e dry-run |
| `frozen_study.py` | Mostrar o plano atual; opcionalmente salvar ou verificar um protocolo informado por `--manifest` |
| `generation_protocol.py` | Preflight e parâmetros padronizados |
| `checkpointing.py` | Persistência e retomada por arquivo |
| `evaluate_results.py`, `experiment_evaluation.py` | Avaliação compartilhada por ocorrência e referência |
| `analyze_study.py`, `study_metrics.py` | Consolidação e estatísticas offline |
| `result_layout.py` | Organização e leitura dos resultados |
| `audit_dpy.py` | Conferir gabarito selecionado contra exportações brutas e fontes |
| `check_provider.py` | Diagnóstico pago de um arquivo/especialista e endpoint, separado do experimento |
| `run_validation.py` | Matriz exploratória reduzida; sem congelamento final |
| `package_release.py` | Empacotar e verificar os dois anexos da Release, sem alterar os dados de origem |
| `sample_dataset.py` | Reproduzir amostragem; não executar sobre o dataset congelado |

Os testes offline estão em `tests/` e cobrem preservação, interrupção, retomada, avaliação e pareamento. Execute com `python -B -m unittest discover -s tests`. A API em `src/api` é um componente opcional; o ponto de entrada da coleta é `scripts/run_study.py`.

## Proveniência e versão executada

O experimento reutiliza a estrutura supervisor/especialistas e LangChain/Pydantic do trabalho predecessor, com novo conjunto minerado/amostrado, agente único, avaliação por ocorrência e registro de falhas e custos. Os resultados não constituem reprodução direta das métricas históricas, pois dados, modelos e avaliação diferem.

A preparação incluiu ensaios exploratórios e auditoria das regras operacionais do DPy; Qwen e Gemini não integram as 12 condições definitivas. Esses ensaios permanecem no arquivo externo e não são misturados aos resultados finais.

Os artefatos históricos preservam o registro da versão executada. Mudanças posteriores em fontes, prompts ou documentação não devem sobrescrever nem alterar os registros originais da coleta. Nenhuma nova chamada LLM foi realizada durante esta limpeza.

O código atual não gera nem exige SHA. Os campos de hash dos artefatos históricos são ignorados na leitura e permanecem intactos nos arquivos originais. Checkpoints, logs, métricas, validação de estrutura e conferência dos parâmetros de retomada continuam disponíveis; não há mais verificação criptográfica de alterações de conteúdo. A análise compara diretamente a seleção e a referência entre condições.
