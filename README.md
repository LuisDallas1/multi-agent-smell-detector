# Detector de implementation smells — TCC 2.0

Comparação entre supervisor com 11 especialistas e agente único para detectar 11 implementation smells em Python, usando o DPy como referência operacional. As duas arquiteturas usam LangChain, respostas validadas com Pydantic e o mesmo motor de execução, persistência e avaliação. A coleta definitiva ainda não começou.

Este README reúne a documentação ativa.

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

Use o ambiente com as dependências de `pyproject.toml`/`uv.lock` e o runtime do manifesto. Alterações em fontes, dependências, prompts, arquivos e runtime invalidam a verificação. A instalação de dependências é separada; o dry-run não instala nem atualiza pacotes.

O manifesto ativo é `experiment/final/frozen_protocol.json`, com seleção em `frozen_files.json`. Conferência sem credenciais, rede LLM ou custo:

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
python -B scripts/run_experiment.py --architecture multiagent --model gpt-6-luna --prompt-type paired --generation-profile experiment --response-format json_mode --json-normalization markdown_fence --output-layout flat --files-from experiment/final/frozen_files.json --all-files --max-tokens 8192 --max-retry-tokens 32768 --response-retries 1 --max-retries 0 --concurrency 2 --timeout 120 --output-dir "$saida/gpt-6-luna/multiagent"
```

No agente único, trocar arquitetura para `single`, `--max-tokens` para 32768 e a pasta correspondente. Conservar os demais parâmetros e usar os IDs ativos. Essa forma manual não executa a verificação do congelamento automaticamente a cada etapa como `run_study.py`; confira o manifesto antes de cada execução. Não misture execuções manuais com o orquestrador sem conferir seu estado de retomada.

## Falhas, persistência e retomada

Cada tentativa preserva mensagens/prompt, pedido e resposta HTTP, fragmentos recebidos, metadados, JSON antes/depois de validação, detecções, decisões de extração, erros, tokens, custo e tempos disponíveis. O journal `evidence/` usa eventos numerados, hashes encadeados, índice, temporário, flush e troca atômica. Checkpoints por arquivo permitem reconstruir agregados. Bloqueios transitórios específicos do Windows têm repetição de gravação limitada, sem repetir a API. Erro permanente de escrita interrompe novas chamadas.

Não é possível garantir a preservação de uma resposta que o serviço não entregou nem de dados ainda não confirmados antes de uma falha física. Chamadas em voo podem ter custo desconhecido. Credenciais e cabeçalhos de autenticação são excluídos; a chave conhecida é redigida. Custo ausente é desconhecido, não zero. `usage.cost` inclui retries quando informado. Não somar custo do journal ao dos checkpoints: há sobreposição. Não inventar rateio por smell no agente único.

Retomada da coleta:

```powershell
python -B scripts/run_study.py --resume "$saida"
```

Código, runtime, prompts e insumos precisam corresponder à rodada. Arquivos confirmados não são repetidos, inclusive os com falha final. Para repetir arquivo interrompido, é necessário acrescentar explicitamente `--retry-interrupted`; isso pode repetir chamadas já cobradas. Não há retomada automática somente dos especialistas restantes dentro desse arquivo. Não use repetição ilimitada para obter resposta melhor. Autenticação, falta de crédito e permissões bloqueiam a continuidade; trabalho recebido permanece salvo.

Cópias na mesma unidade protegem contra exclusão acidental, mas não contra perda física do dispositivo. Guardar o pacote congelado e resultados também em outro local é uma ação separada.

## Organização e análise dos resultados

```text
TCC-results/final_experiment/
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
| `frozen_study.py` | Criar e verificar manifestos por hashes, sem sobrescrever congelamento existente |
| `generation_protocol.py` | Preflight e parâmetros padronizados |
| `checkpointing.py` | Persistência e retomada por arquivo |
| `evaluate_results.py`, `experiment_evaluation.py` | Avaliação compartilhada por ocorrência e referência |
| `analyze_study.py`, `study_metrics.py` | Consolidação e estatísticas offline |
| `result_layout.py` | Organização e leitura dos resultados |
| `audit_dpy.py` | Conferir gabarito selecionado contra exportações brutas e fontes |
| `check_provider.py` | Diagnóstico pago de um arquivo/especialista e endpoint, separado do experimento |
| `run_validation.py` | Matriz exploratória reduzida; sem congelamento final |
| `sample_dataset.py` | Reproduzir amostragem; não executar sobre o dataset congelado |

Os testes offline estão em `tests/` e cobrem preservação, interrupção, retomada, avaliação e pareamento. Execute com `python -B -m unittest discover -s tests`. A API em `src/api` é um componente opcional; o ponto de entrada da coleta é `scripts/run_study.py`.

## Histórico experimental consolidado e congelamento

O projeto mantém a estrutura de supervisor/especialistas e LangChain/Pydantic herdada do trabalho anterior. As mudanças centrais são novo dataset minerado/amostrado por pares, comparação com agente único, avaliação por ocorrência, contratos de saída e preservação/controle de falhas e custos. Não se afirma reprodução exata das métricas do trabalho anterior, pois dados e método de avaliação mudaram.

Durante a exploração foram comparados modelos/provedores e formatos de resposta. Qwen e Gemini não integram a seleção ativa. O DeepSeek ativo é o ID original, não o alias 1017. Os resultados antigos pertencem às respectivas versões e não serão reunidos como se fossem uma única coleta final.

Foram retiradas exigências de medidas numéricas exatas e filtros baseados nessas medidas; o contrato atual registra identidade/localização e deixa erros de detecção aparecerem como FP/FN. Raciocínio longo continuou causando truncamentos no DeepSeek. Uma falha de persistência com leitura simultânea revelou um problema de bloqueio/troca de índice no Windows; a escrita ganhou recuperação transitória limitada e o leitor passou a validar um snapshot consistente. A falha original não permite afirmar defeito físico do disco nem identificar seu errno original com certeza.

Na validação geral de três arquivos e 12 condições anterior às últimas correções, nove condições foram integralmente válidas: duas DeepSeek/multiagente tiveram falhas finais e uma Haiku/multiagente foi interrompida por persistência. O custo conhecido foi US$ 0,2945185492, com duas chamadas sem custo completo registrado; não é custo total exato. Essa rodada é evidência exploratória, não resultado definitivo.

A auditoria posterior do DPy 1.7.8 Trial em 36 exemplos mínimos e no arquivo MusicCast reproduziu todas as 18 ocorrências históricas do arquivo, incluindo dez Statement e zero Chain. Ela revelou diferenças de escopo nos prompts. As regras foram corrigidas diretamente no simples/completo e reutilizadas pelo agente único. No diagnóstico pago seguinte, Chain retornou zero ocorrências sem truncar (antes, 12 FP); Statement teve 9 TP, 3 FP e 1 FN (antes da correção de escopo: 9 TP, 8 FP, 1 FN), precisando de recuperação. A comparação é contra DPy bruto completo desse arquivo, fora da pontuação oficial das células selecionadas. Dois especialistas custaram US$ 0,0137619104. Uma rodada/arquivo de desenvolvimento não demonstra desempenho geral.

Depois disso, as referências ao nome/versão do detector foram retiradas dos textos enviados às LLMs, mantendo regras explícitas. A recuperação foi padronizada em 32.768 tokens. A versão atual passou nos 143 testes offline; a auditoria dos 603 pares e o dry-run das 12 condições nos 182 arquivos também foram exercitados na preparação da coleta. Os manifestos ativos estão em `experiment/final/`. Esses checks validam a configuração e as garantias exercitadas, sem garantir ausência de falhas nos serviços externos ou antecipar o desempenho da coleta definitiva.

Congelamento é uma decisão do autor. Seus hashes, runtime, seleção e referências tornam alterações detectáveis; serviços externos/aliases não são congeláveis localmente. Qualquer mudança posterior de fonte, prompt ou insumo requer nova decisão de versão, sem sobrescrever o histórico. 
