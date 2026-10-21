# Definições de Implementation Smells - Ferramenta DPy

# Resumo Executivo

Este documento apresenta as definições operacionais adotadas nesta versão e referências bibliográficas dos **11 Implementation Smells** suportados pela ferramenta DPy para Python, identificando suas fontes originais na literatura.

---

## IMPLEMENTATION SMELLS (11 total)

### 1. Long Method

**Fonte Original:**

- **Fowler, M.** (1999). *Refactoring: Improving the Design of Existing Code*. Addison-Wesley Professional. Capítulo 3, página 64.
- **Chen et al.** (2016) 

**Definição (Fowler, 1999):**
Uma função ou método excessivamente longo, cujo tamanho dificulta compreensão e manutenção.

**Regra de Detecção DPy:**

- Quando o tamanho de uma função é **maior que 67 linhas**.
- O limite é estrito: 67 linhas não qualificam. O prompt identifica a própria função e sua linha de definição; não usa o tamanho do arquivo ou da classe.

**Por que é problemático:**

1. Dificulta compreensão
2. Viola Single Responsibility Principle
3. Dificulta reuso de código
4. Aumenta duplicação
5. Complica testes
6. Esconde bugs

---

### 2. Long Parameter List

**Fonte Original:**

- **Fowler, M.** (1999). *Refactoring: Improving the Design of Existing Code*. Addison-Wesley Professional. Capítulo 3, página 65.
- **Chen et al.** (2016) 

**Definição (Fowler, 1999):**
Uma função com um número excessivo de parâmetros de entrada.

**Regra de Detecção DPy:**

- Quando uma função recebe **mais de 4 parâmetros**.
- Na implementação atual dos prompts, `self`, `cls`, `*args` e `**kwargs` não entram na contagem. Exatamente 4 não qualifica.

**Por que é problemático:**

1. Dificulta compreensão
2. Propenso a erros (ordem errada de argumentos)
3. Alto acoplamento
4. Dificulta mudanças
5. Duplicação de listas de parâmetros
6. Testabilidade reduzida

---

### 3. Long Statement

**Fonte Original:**

- **PEP 8** - Style Guide for Python Code (Van Rossum, Warsaw, & Coghlan)
- Mencionado em estudos de simulação por Habib et al. (2024) como um smell prevalente em Python

**Definição:**
Uma instrução de código excessivamente longa. A unidade adotada pelo prompt é a instrução completa, que pode ocupar mais de uma linha física.

**Regra de Detecção DPy:**

- Quando uma instrução possui **mais de 80 caracteres**.
- O prompt examina a instrução completa, incluindo strings de dados em instruções multilinha; não conta a numeração adicionada ao código, comentários isolados ou docstrings isoladas.
- Exatamente 80 caracteres não qualifica. A localização é a linha inicial da instrução.

**Por que é problemático:**

1. **Dificulta leitura:** Linhas longas são difíceis de ler e compreender
2. **Viola PEP 8:** O guia de estilo oficial Python recomenda máximo de 79 caracteres
3. **Problemas de visualização:** Dificulta visualização em diferentes editores/telas
4. **Indica complexidade:** Pode indicar expressões complexas que deveriam ser decompostas
5. **Dificulta code review:** Linhas longas são difíceis de revisar em ferramentas de diff

**Relação com PEP 8:**
O PEP 8 (Python Enhancement Proposal 8) estabelece: *"Limit all lines to a maximum of 79 characters"*. Este limite histórico vem da necessidade de compatibilidade com terminais de 80 colunas e facilita a visualização lado-a-lado de múltiplos arquivos.

**Evidência Empírica:**
Habib et al. (2024) em estudo sobre sistemas de simulação encontrou que Long Statement é **62.77% mais prevalente** em sistemas de simulação Python comparado a sistemas tradicionais.

---

### 4. Long Identifier

**Fonte Original:**

- Prática documentada em convenções de nomenclatura de código
- Relacionado aos princípios de Clean Code (Martin, 2008)
- Conceito de "meaningful names" discutido por diversos autores

**Definição:**
Um identificador excessivamente longo: nome de função, classe, campo ou variável local.

**Regra de Detecção DPy:**

- Quando o comprimento de um identificador é **maior que 20 caracteres**.
- O prompt informa o nome exato e reporta uma ocorrência por escopo de definição, não por uso. Imports e strings não são definições; nomes dunder não são excluídos apenas por essa característica.

**Por que é problemático:**

1. **Dificulta leitura:** Nomes muito longos tornam o código verboso
2. **Pode indicar múltiplas responsabilidades:** Classes/métodos fazendo coisas demais
3. **Aumenta complexidade visual:** Torna expressões difíceis de escanear
4. **Viola princípio de simplicidade:** Good names should be concise yet descriptive
5. **Dificulta refatoração:** Nomes longos tornam mudanças mais trabalhosas

**Contexto - Balance entre Descritivo e Conciso:**
Robert C. Martin em Clean Code defende nomes descritivos, mas também adverte contra verbosidade excessiva. O princípio é: *"Choose names at the appropriate level of abstraction"* e *"Use long names for long scopes"* - ou seja, variáveis com escopo longo podem ter nomes longos, mas variáveis locais devem ser concisas.

**Nota Importante:**
Deve-se balancear com o princípio de nomes descritivos. Um nome muito curto (cryptic) também é problemático. O ideal é encontrar o ponto de equilíbrio onde o nome é suficientemente descritivo sem ser excessivamente verbose.

---

### 5. Empty Catch Block

**Fonte Original:**

- **Robert C. Martin** (2008). *Clean Code: A Handbook of Agile Software Craftsmanship*. Prentice Hall. Capítulo 7: Error Handling.
- Amplamente documentado em guias de boas práticas de programação
- Reconhecido por ferramentas como SonarQube, Checkstyle, e PMD

**Definição (Martin, Clean Code):**
Um bloco `except` cujo corpo contém somente `pass` ou uma única instrução `return`, sem outra instrução de tratamento.

**Regra de Detecção DPy:**

- O corpo do `except` contém **somente `pass` ou uma única instrução `return`**, com ou sem valor.
- `return`, `return None` e `return False` qualificam. Logging, `raise`, atribuições ou qualquer outra instrução no corpo impedem a classificação. Comentários não são instruções.
- Não há threshold numérico. A localização pedida é a linha do `except`.

**Por que é problemático:**

1. **Silencia erros críticos:** Esconde problemas que deveriam ser tratados ou propagados
2. **"Silent failures":** Erros ocorrem sem deixar rastro, tornando debugging extremamente difícil
3. **Viola princípios de robustez:** Programa parece funcionar mas falha silenciosamente
4. **Má prática de engenharia:** Viola o princípio de que erros devem ser tratados explicitamente
5. **Pode mascarar bugs críticos:** Problemas sérios passam despercebidos
6. **Dificulta manutenção:** Impossível rastrear quando/onde falhas ocorrem

**Citação de Robert C. Martin (Clean Code):***"Functions should do one thing. Error handing is one thing. Thus, a function that handles errors should do nothing else."*

Martin também defende que try-catch blocks devem definir o escopo da "transação" e que o catch deve sempre deixar o programa em um estado consistente.

**Quando Empty Catch é aceitável (raríssimo):**
Segundo discussões na comunidade e documentação do XP123:

- Quando closing resources que já falharam (e não há ação possível)
- Deve SEMPRE ter comentário explicando o porquê
- Mesmo nesses casos, logging é preferível

**Exemplo correto vs incorreto:**

```python
# ❌ Empty Catch Block (smell)
try:
    risky_operation()
except Exception:
    pass  # Silencia todos os erros!

# ✅ Tratamento adequado
try:
    risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    # Tomar ação apropriada ou re-raise
    raise

```

---

### 6. Complex Method

**Fonte Original:**
Baseado em McCabe (1976) - "A complexity measure"

**Definição:**
Uma função excessivamente complexa em termos de fluxo de controle, medida pela Complexidade Ciclomática de McCabe.

**Regra de Detecção DPy:**

- Quando a Complexidade Ciclomática de McCabe de uma função é **maior que 7**.
- Exatamente 7 não qualifica. O prompt informa a medida e localiza a definição da função.

**Complexidade Ciclomática de McCabe:**
Métrica que conta o número de caminhos linearmente independentes através do código de um programa. Calculada como:

- CC = E - N + 2P
    - E = número de arestas no grafo de fluxo
    - N = número de nós
    - P = número de componentes conectados

**Por que é problemático:**

1. Difícil de entender
2. Difícil de testar (muitos caminhos possíveis)
3. Propenso a bugs
4. Difícil de manter
5. Viola princípio de simplicidade

**Referência Original:**

- **McCabe, T.** (1976). "A complexity measure". *IEEE Transactions on Software Engineering*, SE-2(4), pp. 308-320.

---

### 7. Complex Conditional

**Fonte Original:**

- **Fowler, M.** (2018). *Refactoring: Improving the Design of Existing Code* (2nd Edition). [Referência 2 do DPy]

**Definição:**
Uma condição com um número excessivo de operadores lógicos `and` e `or`.

**Regra de Detecção DPy:**

- Quando o número de operadores `and` e `or` é **maior que 2 na mesma condição**.
- Conta operadores, não operandos ou comparações. Exatamente 2 operadores não qualifica.

**Por que é problemático:**

1. Dificulta compreensão da lógica
2. Propenso a erros de lógica booleana
3. Dificulta testes (muitas combinações)
4. Viola princípio da simplicidade

**Refatoração sugerida:**

- Extrair condições complexas para variáveis ou métodos bem nomeados
- Usar o padrão "Decompose Conditional" (Fowler)

**Exemplo:**

```python
# ❌ Complex Conditional
if (user.age > 18 and user.country == "BR" and user.verified == True and user.balance > 100):
    process()

# ✅ Refatorado
is_adult = user.age > 18
is_brazilian = user.country == "BR"
is_verified_with_balance = user.verified and user.balance > 100

if is_adult and is_brazilian and is_verified_with_balance:
    process()

```

---

### 8. Missing Default

**Fonte Original:**

- **CWE-478:** "Missing Default Case in Multiple Condition Expression" - Common Weakness Enumeration (MITRE)
- Documentado em ferramentas de análise estática (Checkstyle, SonarQube, ReSharper)
- Prática de engenharia de software defensiva

**Definição:**
Uma instrução Python `match-case` sem um caso padrão `case _`.

**CWE-478 Classification:**
O MITRE classifica este problema como uma fraqueza (weakness) de software que pode levar a:

- Comportamento inesperado do sistema
- Falhas silenciosas
- Vulnerabilidades de segurança em casos extremos

**Regra de Detecção DPy:**

- Quando não há um caso padrão **`case _`** na instrução `match-case`.
- Não há threshold numérico. A localização pedida é a linha inicial do `match`.

**Por que é problemático:**

1. **Casos não tratados:** Valores inesperados podem não ser tratados, levando a falhas silenciosas
2. **Comportamento imprevisível:** Sistema pode falhar silenciosamente ou ter comportamento indefinido
3. **Falta de robustez:** Código menos resiliente a mudanças e valores inesperados
4. **Dificulta debugging:** Casos não cobertos podem não gerar erros explícitos
5. **Violação de programação defensiva:** Não antecipa todos os cenários possíveis
6. **Potencial problema de segurança:** Em alguns contextos, pode ser explorado

**Contexto - Programação Defensiva:**
A prática de sempre incluir um caso default faz parte da **programação defensiva** - antecipar e tratar graciosamente situações inesperadas ao invés de deixar o programa em estado indefinido.

**Nota sobre Python match-case:**
O `match-case` foi introduzido no **Python 3.10 (PEP 634 - Structural Pattern Matching)**. O caso default é representado pelo padrão universal `case _:`.

**Exemplo correto vs incorreto:**

```python
# ❌ Missing Default
match status:
    case "active":
        activate()
    case "inactive":
        deactivate()
    # Falta: case _: handle_unknown()
    # Se status="unknown", nada acontece!

# ✅ Com default (defensivo)
match status:
    case "active":
        activate()
    case "inactive":
        deactivate()
    case _:
        logger.warning(f"Unknown status: {status}")
        handle_unknown_status()

```

**Referências:**

- **MITRE Corporation.** CWE-478: Missing Default Case in Multiple Condition Expression. Common Weakness Enumeration. https://cwe.mitre.org/data/definitions/478.html

---

### 9. Long Lambda Function

**Fonte Original:**

- **Chen et al.** (2016). "Detecting code smells in python programs". *International Conference on Software Analysis, Testing and Evolution (SATE)*. 

**Definição:**
Uma expressão lambda excessivamente longa.

**Regra de Detecção DPy:**

- Quando o comprimento da expressão lambda é **maior que 80 caracteres**.
- O prompt conta desde `lambda` até o final da expressão, inclusive quando distribuída em várias linhas; não inclui a atribuição ou chamada envolvente. Exatamente 80 não qualifica.
- A localização pedida é a linha inicial da lambda.

**Por que é problemático:**

1. **Viola filosofia das lambdas:** Lambdas devem ser simples e inline
2. **Dificulta leitura:** Expressões longas são difíceis de entender
3. **Dificulta reuso:** Lógica complexa deveria estar em função nomeada
4. **Dificulta debugging:** Lambdas não têm nome descritivo
5. **Dificulta testes:** Lambdas inline não podem ser testadas isoladamente

**Filosofia Python:**
Lambdas em Python devem ser expressões simples. Para lógica complexa, use funções nomeadas.

**Exemplo:**

```python
# ❌ Long Lambda Function
result = map(lambda number: number * 2 if number > 0 else number * -1 if number < 0 else 0 if number == 0 else None, numbers)

# ✅ Função nomeada
def transform_number(x):
    if x > 0:
        return x * 2
    elif x < 0:
        return x * -1
    else:
        return 0

result = map(transform_number, numbers)

```

---

### 10. Long Message Chain

**Fonte Original:**

- **Fowler, M.** (1999). *Refactoring: Improving the Design of Existing Code*. Addison-Wesley Professional.
- **Chen et al.** (2016) 

**Definição (Fowler):**
Um encadeamento excessivamente longo de acessos a objetos. Conceitualmente, o smell é descrito como uma longa série de chamadas encadeadas; o critério operacional desta versão procura acessos consecutivos a atributos de dados, conforme as saídas DPy disponíveis.

**Regra de Detecção DPy:**

- Threshold operacional: **mais de 2 elementos**, contando a base e os atributos consecutivos. `obj.a` tem 2; `obj.a.b` tem 3; `obj.a.b.c` tem 4.
- O prompt distingue atributos de dados de métodos invocados. Chamadas e indexações interrompem a sequência; não se somam argumentos nem expressões independentes.
- São examinados argumentos e alvos de atribuição: `consume(obj.a.b)` e `obj.a.b = value` qualificam. Reporta-se a cadeia maximal, sem duplicar seus prefixos.
- Essa interpretação operacional foi inferida das saídas DPy; não constitui certificação de equivalência com seu código-fonte. O threshold numérico continua sendo 2.

**Por que é problemático:**

1. **Alto acoplamento:** Código cliente conhece estrutura interna profunda
2. **Frágil:** Mudanças na estrutura interna quebram o código
3. **Viola Law of Demeter:** "Fale apenas com amigos imediatos"
4. **Dificulta testes:** Necessário mockar toda a cadeia
5. **Dificulta compreensão:** Não é claro o que está sendo obtido

**Law of Demeter:**
Um objeto deve apenas chamar métodos de:

- Si mesmo
- Objetos passados como parâmetros
- Objetos que ele cria
- Seus componentes diretos

**Exemplo:**

```python
# ❌ Long Message Chain
zip_code = customer.address.zip_code

# ✅ Refatorado (Hide Delegate)
zip_code = customer.zip_code

```

**Refatoração sugerida:**

- Hide Delegate (Fowler): Criar método intermediário que encapsula a cadeia

---

### 11. Magic Number

**Fontes Originais:**

- **Martin Fowler** (1999, 2018). *Refactoring: Improving the Design of Existing Code*. "Replace Magic Number with Symbolic Constant" refactoring
- **Robert C. Martin** (2008). *Clean Code: A Handbook of Agile Software Craftsmanship*. Prentice Hall. Capítulo 2: Meaningful Names
- Amplamente documentado na literatura de Clean Code e boas práticas

**Definição (Fowler):**
Um literal numérico usado diretamente no código sem constante nomeada que expresse seu significado.

**Definição (Robert C. Martin):**
Em Clean Code, Martin enfatiza: *"Replace magic numbers with named constants"* como parte fundamental de escrever nomes significativos. Ele argumenta que números literais não comunicam intenção e dificultam manutenção.

**Regra de Detecção DPy:**

- Quando há um literal numérico sem constante nomeada, **exceto 0, 1 e -1**, incluindo representações decimais equivalentes.
- `2`, `-2`, `10` e `100` não são exceções. Testes, índices, loops, argumentos e comparações não são excluídos automaticamente. Dígitos em strings e comentários não são literais numéricos de código.
- O prompt informa o valor em `number` e sua linha. Não há threshold de magnitude.

**Por que é problemático:**

1. **Falta de contexto:** Não é claro o que o número representa ou por que foi escolhido
2. **Dificulta manutenção:** Mudanças requerem encontrar todas as ocorrências manualmente
3. **Propenso a erros:** Pode-se alterar um uso e esquecer outros, ou digitar valor errado (typo)
4. **Duplicação implícita:** Mesmo valor "mágico" pode aparecer em múltiplos lugares
5. **Reduz legibilidade:** Números sozinhos não comunicam intenção do programador
6. **Viola DRY:** Violação do princípio "Don't Repeat Yourself"

**Exceções aceitáveis (DPy):**

- `0`: Zero é geralmente auto-explicativo em muitos contextos
- `1`: Um é geralmente auto-explicativo
- `-1`: Menos um é comumente usado para indicar "não encontrado" ou último elemento em arrays

Mesmo para estes, se o significado não for óbvio no contexto, use constantes nomeadas.

**Exemplo clássico (Fowler):**

```python
# ❌ Magic Number
def potential_energy(mass, height):
    return mass * 9.81 * height  # O que é 9.81???

# ✅ Constante nomeada
STANDARD_GRAVITY = 9.81  # m/s² - Aceleração gravitacional padrão da Terra

def potential_energy(mass, height):
    return mass * STANDARD_GRAVITY * height

```

**Outro exemplo (Martin - Clean Code):**

```python
# ❌ Magic Numbers
def calculate_discount(price, quantity):
    if quantity >= 100:
        return price * 0.9  # O que é 0.9? 10% desconto?
    if quantity >= 50:
        return price * 0.95  # E 0.95?
    return price

# ✅ Constantes nomeadas (Clean Code)
MIN_QUANTITY_FOR_10_PERCENT_DISCOUNT = 100
MIN_QUANTITY_FOR_5_PERCENT_DISCOUNT = 50
TEN_PERCENT_DISCOUNT_MULTIPLIER = 0.90
FIVE_PERCENT_DISCOUNT_MULTIPLIER = 0.95

def calculate_discount(price, quantity):
    if quantity >= MIN_QUANTITY_FOR_10_PERCENT_DISCOUNT:
        return price * TEN_PERCENT_DISCOUNT_MULTIPLIER
    if quantity >= MIN_QUANTITY_FOR_5_PERCENT_DISCOUNT:
        return price * FIVE_PERCENT_DISCOUNT_MULTIPLIER
    return price

```

**Benefícios de Eliminar Magic Numbers:**

1. **Autodocumentação:** O nome da constante explica o propósito
2. **Manutenção centralizada:** Mudar em um único lugar
3. **Previne typos:** Proteção contra erros de digitação
4. **Melhora testabilidade:** Fácil de mockar/alterar valores em testes
5. **Segue convenções:** Alinha com DRY e Clean Code principles

**Evidência Empírica:**
Habib et al. (2024) encontrou que Magic Number é **62.77% mais prevalente** em sistemas de simulação Python comparado a sistemas tradicionais, demonstrando que é um problema real e mensurável.

**Referências:**

- **Fowler, M.** (1999). *Refactoring: Improving the Design of Existing Code*. Addison-Wesley Professional.
- **Fowler, M.** (2018). *Refactoring: Improving the Design of Existing Code* (2nd Edition). Addison-Wesley Professional.
- **Martin, R. C.** (2008). *Clean Code: A Handbook of Agile Software Craftsmanship*. Prentice Hall.
- **Habib, M. et al.** (2024). "On the Prevalence, Evolution, and Impact of Code Smells in Simulation Modelling Software". arXiv:2409.03957v1

---

## Tabela Resumo: Fontes Bibliográficas

| # | Smell | Fonte Principal | Referência |
| --- | --- | --- | --- |
| 1 | Long Method | Fowler (1999) | Refactoring, Cap. 3, p. 64 |
| 2 | Long Parameter List | Fowler (1999) | Refactoring, Cap. 3, p. 65 |
| 3 | Long Statement | PEP 8 + Habib et al. (2024) | PEP 8 Style Guide + arXiv:2409.03957v1 |
| 4 | Long Identifier | Martin (2008) + Convenções | Clean Code, Cap. 2 |
| 5 | Empty Catch Block | Martin (2008) | Clean Code, Cap. 7 |
| 6 | Complex Method | McCabe (1976) | IEEE Trans. Soft. Eng. |
| 7 | Complex Conditional | Fowler (2018) | Refactoring, 2nd Ed. |
| 8 | Missing Default | CWE-478 (MITRE) | Common Weakness Enumeration |
| 9 | Long Lambda Function | Chen et al. (2016) | SATE 2016 |
| 10 | Long Message Chain | Fowler (1999) | Refactoring |
| 11 | Magic Number | Fowler (1999, 2018) + Martin (2008) | Refactoring + Clean Code |

---

## Categorização por Origem

### 📚 Martin Fowler (Refactoring - 1999, 2018)

- Long Method
- Long Parameter List
- Complex Conditional
- Long Message Chain
- Magic Number (refactoring "Replace Magic Number with Symbolic Constant")

### 👴 Robert C. Martin "Uncle Bob" (Clean Code - 2008)

- Empty Catch Block (Capítulo 7: Error Handling)
- Magic Number (Capítulo 2: Meaningful Names)
- Long Identifier (princípios de nomenclatura)

### 🔬 Thomas McCabe (Complexity Measure - 1976)

- Complex Method (Complexidade Ciclomática)

### 🐍 Chen et al. (Python-specific - 2016)

- Long Lambda Function (específico Python)
- Long Message Chain (threshold para Python)

### 🔒 MITRE Corporation (Common Weakness Enumeration)

- Missing Default (CWE-478)

### 📋 PEP 8 & Convenções Python

- Long Statement (PEP 8 - 79 caracteres limite)

### 🔬 Estudos Empíricos

- Habib et al. (2024) - Evidências sobre prevalência de Long Statement e Magic Number em Python

---

## Thresholds Aplicados pelo DPy

| Smell | Threshold | Justificativa |
| --- | --- | --- |
| Long Method | > 67 linhas | Adaptado de Java (100 linhas × 0.67 fator verbosidade) |
| Long Parameter List | > 4 parâmetros | Consenso na literatura |
| Long Statement | > 80 caracteres | Baseado em PEP 8 (79 chars) |
| Long Identifier | > 20 caracteres | Convenção |
| Complex Method | CC > 7 | McCabe + Almashfi & Lu (2020) |
| Complex Conditional | > 2 operadores lógicos | Baseado em Fowler |
| Long Lambda | > 80 caracteres | Chen et al. (2016) |
| Long Message Chain | > 2 elementos no acesso a atributos de dados | Critério operacional inferido das saídas DPy |

---

## Referências Bibliográficas Completas

### Livros Fundamentais

1. **Fowler, M.** (1999). *Refactoring: Improving the Design of Existing Code*. Addison-Wesley Professional. ISBN: 0-201-48567-2.
2. **Fowler, M.** (2018). *Refactoring: Improving the Design of Existing Code* (2nd Edition). Addison-Wesley Professional. ISBN: 978-0134757599.
3. **Martin, R. C.** (2008). *Clean Code: A Handbook of Agile Software Craftsmanship*. Prentice Hall. ISBN: 978-0132350884.

### Artigos Científicos

1. **McCabe, T. J.** (1976). "A complexity measure". *IEEE Transactions on Software Engineering*, SE-2(4), pp. 308-320. DOI: 10.1109/TSE.1976.233837
2. **Chen, Z., Chen, L., Ma, W., & Xu, B.** (2016). "Detecting code smells in python programs". *International Conference on Software Analysis, Testing and Evolution (SATE)*, pp. 18-23. DOI: 10.1109/SATE.2016.10
3. **Almashfi, N., & Lu, L.** (2020). "Code smell detection tool for java script programs". *5th International Conference on Computer and Communication Systems (ICCCS)*, pp. 172-176. DOI: 10.1109/ICCCS49078.2020.9118428
4. **Habib, M., Nehéz, K., Maffei, C., & Kazakov, D.** (2024). "On the Prevalence, Evolution, and Impact of Code Smells in Simulation Modelling Software". arXiv preprint arXiv:2409.03957v1. https://arxiv.org/abs/2409.03957

### Standards & Guidelines

1. **Van Rossum, G., Warsaw, B., & Coghlan, N.** PEP 8 – Style Guide for Python Code. Python Software Foundation. https://pep8.org/
2. **PEP 634** – Structural Pattern Matching. Python Enhancement Proposals. https://peps.python.org/pep-0634/
3. **MITRE Corporation.** CWE-478: Missing Default Case in Multiple Condition Expression. Common Weakness Enumeration. https://cwe.mitre.org/data/definitions/478.html

### Ferramenta DPy

1. **Boloori, A., & Sharma, T.** (2024). "DPy: Code Smells Detection Tool for Python". *Mining Software Repositories (MSR) 2025*. Zenodo. DOI: 10.5281/zenodo.14279535

---

## Observações Metodológicas

### Fator de Verbosidade Python

O DPy aplicou um estudo empírico comparando 1.226 problemas do RosettaCode com soluções em Java e Python:

- **Java:** ~47 LOC médio
- **Python:** ~31 LOC médio
- **Fator de verbosidade:** 0.67 (Python é 33% mais conciso)

Este fator foi usado para adaptar thresholds de Java para Python (ex: Long Method 100→67 linhas).

### Validação da Ferramenta

O DPy foi validado manualmente em 4 projetos Python:

- **Precision:** 0.96
- **Recall:** 0.93
- **Cohen's Kappa (inter-rater):** 0.87

---

## Conclusão

Dos 11 implementation smells do DPy:

### Distribuição por Fonte:

- **5 de Martin Fowler** (Long Method, Long Parameter List, Complex Conditional, Long Message Chain, Magic Number)
- **3 de Robert C. Martin** (Empty Catch Block, Magic Number - compartilhado com Fowler, Long Identifier)
- **1 de Thomas McCabe** (Complex Method - Complexidade Ciclomática)
- **2 específicos de Python por Chen et al.** (Long Lambda Function, adaptações de thresholds)
- **1 de MITRE/CWE** (Missing Default - CWE-478)
- **1 de PEP 8** (Long Statement)

### Observações Importantes:

1. **Fowler é a fonte dominante:** 5 dos 11 smells têm origem direta em seus livros de Refactoring (1999, 2018)
2. **Clean Code de Martin complementa Fowler:** Robert C. Martin ("Uncle Bob") contribui significativamente com 3 smells, especialmente relacionados a tratamento de erros e nomenclatura
3. **Fundamentação acadêmica sólida:** A maioria dos smells (9 de 11) tem fundamentação em literatura acadêmica clássica ou standards reconhecidos
4. **Adaptações para Python:** Chen et al. (2016) forneceu adaptações importantes para a natureza dinâmica do Python
5. **Evidências empíricas:** Estudos recentes como Habib et al. (2024) fornecem evidências quantitativas sobre a prevalência desses smells em código Python
6. **Standards oficiais:** PEP 8 e CWE-478 representam standards oficiais (Python e segurança, respectivamente)

### Relevância para o TCC:

Todos os 11 implementation smells do DPy têm **fundamentação sólida** em:

- Literatura acadêmica clássica (Fowler, Martin, McCabe)
- Standards oficiais (PEP 8, CWE)
- Pesquisa específica em Python (Chen et al. 2016)
- Evidências empíricas recentes (Habib et al. 2024)

Nenhum smell é "inventado" ou sem base teórica - todos são reconhecidos e validados pela comunidade de engenharia de software.

---

**Documento preparado para TCC**

**Base:** Artigo DPy (Boloori & Sharma, 2024) + Busca extensiva nas referências citadas + Literatura complementar

**Data:** Outubro 2025 (documento original)

**Última atualização:** 21 de outubro de 2026 — definições e thresholds da versão 2.0. A bibliografia foi preservada do documento original, sem nova revisão bibliográfica.