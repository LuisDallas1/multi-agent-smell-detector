# Publicar os dois anexos

1. Revise e faça commit das alterações de código/documentação e da retirada de `dataset_full/` do índice Git. Essa retirada mantém os arquivos locais. `final_experiment/` e os ZIPs também ficam fora dos commits.
2. Envie o commit para o GitHub.
3. Abra [Nova Release](https://github.com/LuisDallas1/multi-agent-smell-detector/releases/new).
4. Crie a tag **v2.0-tcc** apontando para o commit publicado; título: **TCC 2.0 — dataset e resultados completos**.
5. Cole o conteúdo de `RELEASE_NOTES.md` na descrição.
6. Anexe somente **dataset_full.zip** e **final_experiment.zip**, preparados fora do repositório.
7. Publique e confira os dois links de download no README.

A criação do commit não cria a Release nem envia os ZIPs. As etapas no GitHub são posteriores ao commit/push. Não é necessário usar Git LFS para esses dois anexos.

Para recriar os pacotes em uma pasta nova, sem sobrescrever anexos anteriores:

```powershell
python -B scripts/package_release.py --output-dir "E:/TCC/release-assets/v2.0-tcc"
```

O empacotador lê as pastas locais, exclui apenas entradas `.git` internas, preserva a estrutura raiz e verifica conteúdo e CRC dos arquivos ZIP. Não modifica nem apaga os dados de origem. Se os ZIPs já existirem, escolha outra pasta. Cada anexo precisa ficar abaixo de 2 GiB.

Mover dados para uma Release não remove cópias de commits anteriores. Esta preparação não reescreve o histórico nem renomeia commits publicados.
