# Multi-Agent Code Smell Detector

Sistema de detecção de code smells em Python usando múltiplos agentes especializados baseados em LLM.

## 📚 Sobre o Projeto

Trabalho de Conclusão de Curso (TCC) que implementa um sistema multi-agente para detecção automática de 11 tipos de code smells em código Python, seguindo as definições acadêmicas de renomados autores da Engenharia de Software.

### 🎯 Objetivo

Desenvolver um sistema baseado em LLM multi-agente capaz de detectar code smells em código Python com alta precisão, combinando análise estática e inteligência artificial.

## 📊 Resultados

### Performance (Claude Sonnet 4.5)

| Métrica | Prompts Elaborados | Prompts Simples | DPy (Estático) |
|---------|-------------------|-----------------|----------------|
| **F1-Score** | **70.21%** | 67.08% | 48.59% |
| Precision | 67.36% | 57.19% | 39.22% |
| Recall | 73.30% | 81.11% | 63.98% |
| True Positives | 291 | 322 | 254 |

### Research Questions

- **RQ1:** O sistema atinge F1-Score de 70.21% na detecção de code smells
- **RQ2:** Prompts elaborados superam simples em +3.1pp (diferença estatisticamente significativa, p < 0.05)
- **RQ3:** Multi-agentes supera DPy em +21.6pp no F1-Score
- **RQ4:** 10 de 11 agentes atingem F1 > 50%
- **RQ5:** Custo total de $5.79 (~$0.02 por True Positive)

## 🏗️ Arquitetura do Sistema

### Visão Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                        API FastAPI                               │
│                    (POST /api/analyze)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CodeSmellSupervisor                            │
│  • Coordena 11 agentes (paralelo ou sequencial)                 │
│  • Usa LLM (DeepSeek/GPT-4o-mini) com structured output         │
│  • Enriquece detecções com metadados (AST)                      │
│  • Filtra falsos positivos                                       │
│  • Limites: 500 linhas, 50KB por arquivo                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Complexidade │    │  Estrutura   │    │ Nomenclatura │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ Long Method  │    │ Long Param   │    │ Long ID      │
│ Complex Meth │    │ Message Chain│    │ Magic Number │
│ Complex Cond │    └──────────────┘    └──────────────┘
└──────────────┘             │
                             ▼
                    ┌──────────────┐
                    │  Statements  │
                    ├──────────────┤
                    │ Long Stmt    │
                    │ Empty Catch  │
                    │ Missing Def  │
                    │ Long Lambda  │
                    └──────────────┘
```

### Fluxo de Execução

1. **Request** → API recebe código Python
2. **Validação** → Verifica tamanho (max 500 linhas, 50KB)
3. **Supervisor** → Coordena execução dos 11 agentes
4. **LLM** → Cada agente chama LLM com structured output (prompt + schema)
5. **Enrichment** → Adiciona metadados (Project, Package, Module, Line)
6. **Validação** → Filtra falsos positivos (ex: Long Identifier ≤ 20 chars)
7. **Response** → Retorna JSON com detecções

### ⚙️ Configurações

- **Modelo**: Claude Sonnet 4.5 / DeepSeek V3.2 / GPT-4o-mini (via OpenRouter)
- **Temperatura**: 0 (determinístico)
- **Modo**: Paralelo (11 requests simultâneos) ou Sequencial (delay 0.3s)
- **Limites**: 500 linhas, 50KB por arquivo
- **Validação**: Filtra falsos positivos automaticamente
- **Prompts**: Elaborados (com exemplos e regras) ou Simples (definição básica)

## 🤖 Code Smells Detectados

### Tabela de Thresholds

| # | Code Smell | Categoria | Threshold | Descrição |
|---|------------|-----------|-----------|----------|
| 1 | **Long Method** | Complexidade | > 67 linhas | Métodos com mais de 67 linhas |
| 2 | **Complex Method** | Complexidade | CC > 7 | Complexidade Ciclomática maior que 7 |
| 3 | **Complex Conditional** | Complexidade | > 2 operadores | Mais de 2 operadores lógicos (and/or) |
| 4 | **Long Parameter List** | Estrutura | > 4 parâmetros | Funções com mais de 4 parâmetros |
| 5 | **Long Message Chain** | Estrutura | > 2 métodos | Mais de 2 métodos encadeados |
| 6 | **Long Statement** | Statements | > 120 caracteres | Linhas com mais de 120 caracteres |
| 7 | **Long Identifier** | Nomenclatura | > 20 caracteres | Identificadores com mais de 20 caracteres |
| 8 | **Magic Number** | Nomenclatura | Literais (exceto 0,1,-1) | Números literais sem constante nomeada |
| 9 | **Empty Catch Block** | Statements | Bloco vazio | Blocos except vazios ou apenas com pass |
| 10 | **Missing Default** | Statements | Sem case _ | match-case sem caso padrão |
| 11 | **Long Lambda** | Statements | > 80 caracteres | Lambdas com mais de 80 caracteres |

### Referências Bibliográficas

| Code Smell | Referência | Localização |
|------------|------------|-------------|
| Long Method | Fowler (1999) | Cap. 3, p. 76 |
| Complex Method | McCabe (1976) | IEEE Trans. SE, p. 308 |
| Complex Conditional | Fowler (2018) | Cap. 10, p. 260 |
| Long Parameter List | Fowler (1999) | Cap. 3, p. 78 |
| Long Message Chain | Fowler (1999) | Cap. 3, p. 84 |
| Long Statement | PEP 8 | Seção "Maximum Line Length" |
| Long Identifier | Martin (2008) | Cap. 2, p. 18-25 |
| Magic Number | Fowler (1999) + Martin (2008) | Cap. 3, p. 219 / Cap. 17 |
| Empty Catch Block | Martin (2008) | Cap. 7, p. 106 |
| Missing Default | CWE-478 (MITRE) | Common Weakness Enumeration |
| Long Lambda | Chen et al. (2016) | SATE Conference, p. 18 |

### Detalhamento por Categoria

#### 🔴 Complexidade (3 smells)
- **Long Method**: Métodos muito longos são difíceis de entender e manter
- **Complex Method**: Alta complexidade ciclomática indica muitos caminhos de execução
- **Complex Conditional**: Condicionais com muitos operadores lógicos são difíceis de ler

#### 🔵 Estrutura (2 smells)
- **Long Parameter List**: Muitos parâmetros indicam responsabilidades excessivas
- **Long Message Chain**: Encadeamento excessivo viola Lei de Demeter

#### 🟢 Nomenclatura (2 smells)
- **Long Identifier**: Nomes muito longos prejudicam legibilidade
- **Magic Number**: Literais numéricos sem significado explícito

#### 🟡 Statements (4 smells)
- **Long Statement**: Linhas muito longas dificultam leitura
- **Empty Catch Block**: Exceções silenciadas escondem erros
- **Missing Default**: Switch/match sem caso padrão pode causar bugs
- **Long Lambda Function**: Lambdas complexas devem ser funções nomeadas

## 🚀 Instalação e Uso

### Pré-requisitos

- Python 3.12+
- uv ou Poetry
- Chave API da OpenAI (GPT-4o-mini) via OpenRouter

### Instalação

```bash
git clone <url-do-repositorio>
cd multi-agent-smell-detector
uv sync
```

### Configuração

Crie um arquivo `.env` na raiz:

```env
OPENROUTER_API_KEY=sua_chave_api_aqui
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_MODEL=openai/gpt-4o-mini
```

### Executando a API

```bash
python src/app.py
```

A API estará disponível em `http://localhost:8000`

Documentação interativa: `http://localhost:8000/docs`

## 📡 Uso da API

### Endpoint: POST /api/analyze

**Request:**
```json
{
  "python_code": "def long_function_name_that_exceeds_twenty_chars():\n    pass",
  "file_path": "example.py",
  "project_name": "MyProject"
}
```

**Response:**
```json
{
  "total_smells_detected": 1,
  "agents_executed": 11,
  "code_smells": [
    {
      "Project": "MyProject",
      "Package": "example",
      "Module": "example",
      "Class": "",
      "Smell": "Long identifier",
      "Method": "long_function_name_that_exceeds_twenty_chars",
      "Line no": "1",
      "File": "example.py",
      "Description": "Identifier 'long_function_name_that_exceeds_twenty_chars' has 45 characters (threshold: 20). Consider shortening.",
      "identifier_name": "long_function_name_that_exceeds_twenty_chars",
      "length": 45,
      "threshold": 20
    }
  ]
}
```

## 📊 Análise em Batch

```bash
# Executa análise com prompts elaborados
python scripts/run_complete_only.py

# Executa análise com prompts simples
python scripts/run_simple_only.py

# Converte resultados JSON para CSV
python scripts/convert_results_to_csv.py

# Gera figuras acadêmicas
python scripts/generate_academic_figures.py
```

## 📊 Estrutura do Projeto

```
multi-agent-smell-detector/
├── src/
│   ├── api/                    # API FastAPI
│   │   ├── app.py              # Aplicação principal
│   │   ├── routes/             # Endpoints
│   │   └── models/             # Request/Response
│   │
│   ├── core/
│   │   ├── supervisor/         # Coordenador
│   │   │   ├── supervisor.py   # Lógica principal
│   │   │   ├── agent_config.py # Config dos 11 agentes
│   │   │   └── enricher.py     # Enriquecimento + validação
│   │   │
│   │   ├── prompts/            # 11 prompts especializados
│   │   ├── schemas/            # Schemas Pydantic
│   │   └── utils/              # Parser AST + Validator
│   │
│   └── config/                 # Configurações
│
├── scripts/
│   ├── run_complete_only.py    # Executa com prompts elaborados
│   ├── run_simple_only.py      # Executa com prompts simples
│   ├── convert_results_to_csv.py
│   └── generate_academic_figures.py  # Gera figuras para TCC
│
├── notebooks/
│   └── research_questions_analysis.ipynb  # Análise das RQs
│
├── dataset/
│   └── ground_truth/           # Ground truth para validação
│
├── results/
│   ├── csv/                    # Resultados em CSV
│   ├── json/                   # Resultados em JSON
│   ├── dpy/                    # Resultados DPy
│   └── figures/                # Figuras acadêmicas (PDF/PNG)
│
├── .env                        # Variáveis de ambiente
└── pyproject.toml              # Dependências
```

## 🛠️ Tecnologias

- **FastAPI**: API REST
- **LangChain**: Integração com LLMs
- **Claude Sonnet 4.5 / DeepSeek V3.2 / GPT-4o-mini**: Modelos LLM via OpenRouter
- **Pydantic**: Validação e structured output
- **Python AST**: Parser de código
- **Matplotlib/Seaborn**: Visualização de dados
- **Pandas/NumPy/SciPy**: Análise estatística
- **Python 3.12+**: Linguagem base

## 📈 Figuras Acadêmicas

O projeto gera 7 figuras acadêmicas para o TCC (PDF e PNG):

| Figura | Descrição |
|--------|-----------|
| `fig1_comparison_metrics` | Comparação de Precision, Recall, F1 entre abordagens |
| `fig2_prompt_impact` | Impacto da qualidade dos prompts no F1-Score |
| `fig3_f1_by_smell` | F1-Score por tipo de code smell |
| `fig4_smell_distribution` | Distribuição de smells no Ground Truth |
| `fig5_confusion_matrix` | Matriz de confusão (TP, FP, FN) |
| `fig6_cost_analysis` | Análise de custos (prompts elaborados vs simples) |
| `fig7_tp_fp_fn` | Comparação de TP, FP, FN entre abordagens |

Para gerar as figuras:
```bash
python scripts/generate_academic_figures.py
```

## 📖 Referências Bibliográficas

1. **Fowler, M.** (1999). *Refactoring: Improving the Design of Existing Code*. Addison-Wesley Professional. ISBN: 0-201-48567-2
2. **Fowler, M.** (2018). *Refactoring: Improving the Design of Existing Code* (2nd Edition). Addison-Wesley Professional. ISBN: 978-0134757599
3. **Martin, R. C.** (2008). *Clean Code: A Handbook of Agile Software Craftsmanship*. Prentice Hall. ISBN: 978-0132350884
4. **McCabe, T. J.** (1976). "A Complexity Measure". *IEEE Transactions on Software Engineering*, Vol. SE-2, No. 4, pp. 308-320. DOI: 10.1109/TSE.1976.233837
5. **Van Rossum, G., Warsaw, B., & Coghlan, N.** (2001). *PEP 8 – Style Guide for Python Code*. Python Enhancement Proposals. https://peps.python.org/pep-0008/
6. **Chen, Z., Chen, L., Ma, W., & Zhou, B.** (2016). "Detecting Code Smells in Python Programs". *International Conference on Software Analysis, Testing and Evolution (SATE)*, pp. 18-23. DOI: 10.1109/SATE.2016.10
7. **MITRE Corporation.** (2006). *CWE-478: Missing Default Case in Multiple Condition Expression*. Common Weakness Enumeration. https://cwe.mitre.org/data/definitions/478.html

## 👨💻 Autor

**Estevam** - Trabalho de Conclusão de Curso (TCC)  
Engenharia de Software - 2025

## 📄 Licença

Este projeto é parte de um Trabalho de Conclusão de Curso (TCC) acadêmico.
