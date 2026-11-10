# TCC 2.0 — código, dataset completo e resultados

Comparação entre supervisor com 11 especialistas e agente único na detecção de 11 implementation smells em Python, com DPy como referência operacional.

- 182 arquivos; 603 pares avaliados; 450 ocorrências de referência.
- 12 condições: 3 modelos × 2 arquiteturas × 2 estratégias de prompt.
- 2.184 análises de arquivo e respectivos checkpoints.
- 95 falhas finais preservadas: coleta com status técnico `incomplete` e análise consolidada concluída.
- Custo conhecido de US$ 19,4133473586; oito tentativas sem custo conhecido.

## Anexos

- **dataset_full.zip** (388,3 MiB; 27.195 arquivos): dataset completo, DPy e configuração, sem diretórios `.git` internos.
- **final_experiment.zip** (797,5 MiB; 274.836 arquivos): resultados completos, incluindo respostas, prompts, schemas, checkpoints, journals, protocolos, gabarito salvo e análise.

Cada ZIP contém sua pasta raiz. Extraia ambos na raiz do repositório; consulte o README para instalação, caminhos históricos e análise offline. O relatório está em `final_experiment/analysis/report.html`.

Os resultados foram preservados como gerados. O código atual simplifica as verificações de integridade e permite iniciar ou retomar o experimento sem a antiga pasta externa de protocolo. Alterações posteriores em prompts não mudam os prompts efetivamente registrados na coleta.

Ambos os anexos foram conferidos por inventário e CRC. O pacote de resultados contém as 12 condições e os 2.184 checkpoints.
