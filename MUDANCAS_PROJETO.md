# Mudanças nos demais arquivos — Estevam → versão 2.0

Base de comparação: código original de Estevam, commit `afb065c`. Organização dos 33 prompts e mudanças do complete V2 estão em `MUDANCAS_PROMPTS.md`. Arquivos de dados são descritos por conjunto, não individualmente.

## Arquivos de código modificados

### `src/core/supervisor/supervisor.py`

- Mantidos supervisor determinístico, 11 especialistas, LangChain, JSON mode e respostas Pydantic.
- Adicionados parâmetros `model_name`, `max_tokens`, `temperature`, `timeout`, `max_retries`, `concurrency`, `reasoning` e `provider`.
- Limite padrão de saída: 4.096 → 8.192 tokens.
- Adicionado semáforo de concorrência; padrão de dois especialistas simultâneos.
- Adicionados `agent_errors`, `agent_metrics` e `fatal_error` ao resultado.
- Registrados tokens disponíveis no callback mesmo após falha de parsing.
- Falhas de autenticação/permissão interrompem a rodada e impedem chamadas pendentes.
- Truncamentos continuam descartando a resposta incompleta, mas agora são registrados como falha; corrigida a mensagem que sugeria retorno parcial.
- Registros de erro inesperado passam a usar o tipo da exceção.
- Reiniciados os registros de falha e métricas a cada arquivo.

### `src/core/schemas/agent_response.py`

- Importados thresholds de `core.smell_rules`.
- `ComplexConditionalDetection.threshold`: 3 → 2.
- `LongStatementDetection.threshold`: 120 → 80.
- Demais thresholds mantidos numericamente e centralizados.
- Adicionado `MagicNumberDetection.number`, opcional, inteiro ou decimal.
- Preservados envelopes, nomes dos schemas e política de campos opcionais.

### `src/core/utils/detection_validator.py`

- Thresholds dos filtros passaram a vir de `core.smell_rules`, sem aceitar limiar definido pela resposta do modelo.
- Long statement: 120 → 80.
- Exceções de Magic number limitadas a `0`, `1` e `-1`.
- Magic number usa `number`; se ausente, tenta obter o valor da descrição da própria previsão.
- Rejeitados valores numéricos não finitos em Magic number.
- Removida exclusão automática de identificadores dunder.
- Adicionado filtro de Long method para medida declarada `> 67`.
- Preservados os demais filtros e fallbacks de medidas ausentes; não foi implementado um novo detector estático.

### `src/core/supervisor/agent_config.py`

- Seleção explícita entre `simple_estevam`, `complete_estevam` e `complete_v2`.
- Mantidos os 11 agentes e os mesmos schemas.
- Importação direta do módulo de prompt do conjunto escolhido.
- Nomes desconhecidos geram erro, sem fallback silencioso.

## Novos arquivos de código

### `src/core/smell_rules.py`

- Tabela dos oito thresholds numéricos.
- Exceções de Magic number: `{0, 1, -1}`.
- Identificação das regras: `2.0`.

### `scripts/run_experiment.py`

- Comando principal que instancia diretamente `CodeSmellSupervisor`.
- Seleção por `--max-files`, `--all-files`, `--seed` ou `--files-from`.
- Dataset padrão local: `dataset/`.
- Mesma seleção para todos os modelos e conjuntos de prompts; `--prompt-type all` executa os três conjuntos.
- Padrão experimental: `complete_v2`.
- Limites de tamanho de arquivo e parâmetros de chamada configuráveis.
- Dry-run sem credenciais, LLMs ou gravação de resultados.
- Carregamento interno de credenciais somente na execução real.
- Validação prévia dos pares e ocorrências do gabarito.
- Congelamento da seleção, prompts, configuração, código e gabarito por hashes/cópias.
- Registro incremental de detecções, tempos, tokens e falhas; execução do F1 ao final.
- Sem estimativa presumida de custo em dólares.

### `scripts/experiment_evaluation.py`

- Correspondência um a um entre previsões e ocorrências DPy.
- Identificação por caminho relativo completo e tipo de smell.
- Regras de correspondência por linha, função, identificador ou valor numérico, conforme o smell.
- Resolução por AST de registros DPy ancorados na função.
- Previsões extras em pares avaliados contam como FP; duplicatas não criam TPs adicionais.
- Previsões fora dos pares selecionados são registradas e não pontuadas.
- Micro-F1 por ocorrência; macro-F1 sobre tipos com positivos ou erros; presença complementar.

### `scripts/evaluate_results.py`

- Congela pares e ocorrências antes da inferência.
- Verifica integridade do código e dos snapshots do gabarito.
- Normaliza campos declarados pelo modelo, sem completar previsões usando o gabarito.
- Calcula F1 por ocorrência, presença e diagnóstico por contagem.
- Mantém pares com falhas no F1 operacional.
- Permite reavaliação offline de uma rodada.
- Não exclui automaticamente falhas para produzir F1 condicional de respostas válidas.

### `scripts/sample_dataset.py`

- Lê saídas brutas DPy em CSV/JSON.
- Mapeia caminhos de origem para arquivos do corpus minerado.
- Amostragem determinística, com quotas e seleção por pares `(arquivo, smell)`.
- Copia arquivos selecionados e produz ocorrências, pares positivos, manifestos e estatísticas da amostra.
- Não executa chamadas a LLMs.

### Testes de desenvolvimento

- `tests/test_experiment_runner.py`: seleção, hashes, limites, compartilhamento da amostra e registro de falhas.
- `tests/test_evaluate_results.py`: avaliação de ocorrências e normalização.
- `tests/test_methodology.py`: thresholds, exemplos, schemas, LangChain/Pydantic, congelamento do gabarito e avaliação automática.
- `tests/test_prompt_sets.py`: integridade das cópias de Estevam, seleção dos três conjuntos e schemas compartilhados.
- O experimento não depende desses testes para executar.

## Dados e avaliação

- Substituído o dataset de Estevam pelo corpus amostrado do projeto.
- `dataset_full/`: corpus minerado de origem.
- `dataset/`: 182 arquivos disponíveis à execução.
- `dataset/ground_truth/sample_pairs.csv`: 312 pares positivos selecionados.
- `dataset/ground_truth/dpy_implementation_smells_sample.csv`: 450 ocorrências dos pares selecionados.
- `dataset/ground_truth/evaluation_pairs.csv`: 603 pares avaliados, sendo 312 positivos e 291 negativos.
- `dataset/ground_truth/evaluation_manifest.json`: política e metadados dos pares de avaliação.
- `dataset/sample_*.csv` e `dataset/sample_config.json`: proveniência da amostragem.
- `results/dpy/`: preservados os dados brutos que deram origem ao gabarito.
- Avaliação principal mudou de análises agregadas dos notebooks para correspondência por ocorrência nos pares do manifesto.
- Todos os especialistas continuam executados; custo/tokens abrangem todas as chamadas, inclusive fora dos pares avaliados.

## Arquivos removidos ou substituídos

- `scripts/run_with_model.py`, `run_complete_only.py`, `run_simple_only.py` e `run_complete_analysis.py`: substituídos por `run_experiment.py`.
- `scripts/convert_results_to_csv.py`: removido; o avaliador lê os resultados JSON diretamente.
- `scripts/generate_academic_figures.py`: removido por depender das análises antigas.
- `notebooks/research_questions_analysis.ipynb` e `notebooks/validation_by_count.ipynb`: retirados da base 2.0.
- Saídas históricas, gráficos e relatórios de experimentos não compõem a implementação 2.0. Novas rodadas ficam em `results/experiments/`.

## Configuração e documentação

- `.gitattributes`: código e documentação em LF; `dataset/`, `dataset_full/` e `results/` sem conversão de finais de linha, preservando bytes e hashes entre sistemas.
- `pyproject.toml`: versão `0.1.0` → `2.0.0`; descrição do projeto preenchida. Dependências declaradas preservadas.
- `uv.lock`: atualizada a versão do pacote local para `2.0.0`.
- `README.md`: instruções e metodologia da versão 2.0.
- `smells.md`: estrutura original restaurada; definições e thresholds atualizados.
- `MUDANCAS_PROMPTS.md`: mudanças de cada especialista.
- `MUDANCAS_PROJETO.md`: diferenças dos demais arquivos.

## Código preservado sem alteração

- `src/api/`: aplicação, rotas e modelos FastAPI.
- `src/config/`: settings e logging.
- `src/core/utils/code_parser.py`: parser e preparação do código.
- `src/core/utils/token_tracker.py`: callback de tokens.
- Arquivos `__init__.py` desses módulos.
- Nenhum agente único experimental foi acrescentado.
- Não há segunda camada de transporte HTTP nem adaptador para outra arquitetura.
