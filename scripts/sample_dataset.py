"""Amostragem estratificada e deterministica do dataset de code smells.

Le a saida BRUTA do DPy (dataset_implementation_smells.csv), conta os smells por
arquivo, escolhe arquivos ate bater uma cota de ocorrencias por tipo de smell,
copia os .py escolhidos e gera o gabarito so da amostra.

Sem argumentos, usa os caminhos padrao relativos a raiz do projeto
(scripts/ ao lado de dataset_full/, results/dpy/jsons/ e dataset/).

Exemplo:
    python sample_dataset.py \
        --root dataset_full \
        --dpy-json dpy_jsons/ \
        --out dataset --total 450 --seed 42
"""

import argparse
import json
import math
import random
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent  # raiz do projeto (scripts/ fica dentro dela)

# Nome de exibicao -> chave (minuscula) como o DPy escreve no CSV
SMELLS = [
    "Complex method",
    "Long parameter list",
    "Long method",
    "Complex conditional",
    "Empty catch block",
    "Long identifier",
    "Long statement",
    "Magic number",
    "Missing default",
    "Long lambda function",
    "Long message chain",
]
KEYS = [s.lower() for s in SMELLS]

# Mesmos limites do CodeSmellSupervisor: arquivos maiores seriam rejeitados
MAX_FILE_LINES = 3000
MAX_FILE_SIZE_KB = 500


def allocate(amount: int, weights: dict, caps: dict) -> dict:
    """Reparte `amount` inteiros proporcionalmente a `weights` (maior resto),
    respeitando o teto `caps` de cada chave e redistribuindo o que sobrar."""
    out = {k: 0 for k in weights}
    active = [k for k in weights if caps[k] > 0 and weights[k] > 0]
    while amount > 0 and active:
        wsum = sum(weights[k] for k in active)
        raw = {k: amount * weights[k] / wsum for k in active}
        base = {k: min(int(raw[k]), caps[k] - out[k]) for k in active}
        for k in active:
            out[k] += base[k]
        amount -= sum(base.values())
        for k in sorted(active, key=lambda x: (-(raw[x] - int(raw[x])), x)):
            if amount <= 0:
                break
            if out[k] < caps[k]:
                out[k] += 1
                amount -= 1
        active = [k for k in active if out[k] < caps[k]]
    return out


def project_matrix(files: dict, projects: list) -> np.ndarray:
    """Matriz (smell x projeto) de ocorrencias disponiveis."""
    return np.array([[sum(c[k] for r, c in files.items() if project_of(r) == p)
                      for p in projects] for k in KEYS], dtype=float)


def project_caps(M: np.ndarray, quotas: dict, max_share: float):
    """Teto de ocorrencias por projeto para cada smell: floor(cota * max_share).
    Se a soma dos tetos nao alcanca a cota (poucos projetos com o smell), sobe o teto
    ate caber. Devolve ({smell: teto}, [smells relaxados])."""
    caps, relaxed = {}, []
    for i, k in enumerate(KEYS):
        q = int(quotas[k])
        if q <= 0:
            caps[k] = 0
            continue
        if max_share >= 1.0:
            caps[k] = q
            continue
        cap0 = max(1, int(q * max_share))
        cap = cap0
        while np.minimum(M[i], cap).sum() < q and cap < M[i].max():
            cap += 1
        if cap > cap0:
            relaxed.append(k)
        caps[k] = cap
    return caps, relaxed


def project_quotas(files: dict, quotas: dict, projects: list,
                   rng: random.Random, jitter: float = 0.0,
                   max_share: float = 0.25) -> dict:
    """Cotas por (smell, projeto) via raking (IPF). `jitter` multiplica o peso de cada
    celula por exp(N(0, jitter)) antes do arredondamento: 0 = determinístico.
    `max_share`: nenhum projeto recebe mais que essa fracao da cota de um smell
    (relaxado so se for impossivel fechar a cota respeitando o teto)."""
    M = project_matrix(files, projects)
    row = np.array([quotas[k] for k in KEYS], dtype=float)

    # C = capacidade por celula: disponivel, limitado ao teto de cada smell
    caps, relaxed = project_caps(M, quotas, max_share)
    for k in relaxed:
        print(f"AVISO: teto de {max_share:.0%} inviavel para '{k}'; "
              f"relaxado para {caps[k]} ocorrencias/projeto")
    C = np.array([np.minimum(M[i], caps[k]) if row[i] > 0 else M[i]
                  for i, k in enumerate(KEYS)])

    col = M.sum(axis=0)
    col = col / col.sum() * row.sum()
    X = C.copy()
    for _ in range(500):
        X *= (row / np.maximum(X.sum(axis=1), 1e-9))[:, None]
        X *= (col / np.maximum(X.sum(axis=0), 1e-9))[None, :]
        X = np.minimum(X, C)

    def weight(i, j):
        if C[i, j] <= 0:
            return 0.0
        jit = math.exp(rng.gauss(0, jitter)) if jitter > 0 else 1.0
        return (X[i, j] + 1e-6) * jit  # epsilon: celulas com folga nunca ficam fora da redistribuicao

    return {
        k: allocate(int(row[i]),
                    {p: weight(i, j) for j, p in enumerate(projects)},
                    {p: int(C[i, j]) for j, p in enumerate(projects)})
        for i, k in enumerate(KEYS)
    }


def compute_quotas(total: int, avail: dict, min_per: int = 30) -> dict:
    """Piso fixo de `min_per` por smell + o restante proporcional a sqrt(disponivel).
    Smells com menos ocorrencias que o piso ficam com tudo que existe."""
    pos = [k for k in KEYS if avail[k] > 0]
    floors = {k: min(min_per, avail[k]) for k in pos}
    quotas = {k: 0 for k in KEYS}
    if sum(floors.values()) > total:  # sem espaco pro piso: divide igualmente
        quotas.update(allocate(total, {k: 1.0 for k in pos}, {k: avail[k] for k in pos}))
        return quotas
    quotas.update(floors)
    extra = allocate(
        total - sum(floors.values()),
        {k: math.sqrt(avail[k]) for k in pos},
        {k: avail[k] - floors[k] for k in pos},
    )
    for k, v in extra.items():
        quotas[k] += v
    return quotas


def select_files(files: dict, quotas: dict, rng: random.Random, pool_per_smell: int,
                 mode: str = "cover"):
    """Escolhe arquivos para atingir as cotas por smell. Devolve (arquivos, totais obtidos).

    Pool: para cada smell, ate `pool_per_smell` arquivos sorteados (seed) que o contem.

    mode="cover" (padrao): as cotas sao MINIMOS. Guloso de cobertura: a cada passo pega o
        arquivo com maior (falta de cota que ele cobre) / (total de smells que ele traz),
        ate todos os minimos serem atingidos; depois remove arquivos redundantes. Garante o
        piso, mas o total passa do alvo porque os smells co-ocorrem nos mesmos arquivos.
    mode="balance": minimiza o erro relativo quadratico (falta e excesso pesam igual).
        Total mais perto do alvo, mas smells raros tendem a ficar abaixo da cota.
    """
    active = [k for k in KEYS if quotas[k] > 0]
    pool = set()
    for k in active:
        cands = sorted(r for r, c in files.items() if c[k] > 0)
        rng.shuffle(cands)
        pool.update(cands[:pool_per_smell])
    rels = sorted(pool)
    rng.shuffle(rels)  # desempate reprodutivel
    if not rels:
        return [], Counter()

    M = np.array([[files[r][k] for k in KEYS] for r in rels], dtype=float)
    q = np.array([quotas[k] for k in KEYS], dtype=float)
    act = q > 0
    w = np.where(act, 1.0 / np.maximum(q, 1.0), 0.0)  # falta relativa a cota; sem cota = ignorado
    T = np.zeros(len(KEYS))
    free = np.ones(len(rels), dtype=bool)
    sel = []

    if mode == "balance":
        cur = float((w ** 2 * (T - q) ** 2).sum())
        while free.any():
            loss = (w ** 2 * (T + M - q) ** 2).sum(axis=1)
            loss[~free] = np.inf
            i = int(np.argmin(loss))
            if loss[i] >= cur:
                break
            sel.append(i)
            T += M[i]
            free[i] = False
            cur = float(loss[i])
    else:
        cost = np.maximum(M.sum(axis=1), 1.0)
        while free.any():
            gain = (np.minimum(M, np.maximum(q - T, 0.0)) * w).sum(axis=1)
            ratio = np.where(free & (gain > 0), gain / cost, -1.0)
            i = int(np.argmax(ratio))
            if ratio[i] <= 0:
                break
            sel.append(i)
            T += M[i]
            free[i] = False
        # poda: remove arquivos (os mais pesados primeiro) que nao fazem falta pro piso
        floor = np.minimum(q, T)
        for i in sorted(sel, key=lambda x: (-M[x].sum(), x)):
            if np.all((T - M[i])[act] >= floor[act]):
                T -= M[i]
                sel.remove(i)

    return [rels[i] for i in sel], Counter({k: int(T[j]) for j, k in enumerate(KEYS)})


def select_per_smell(files: dict, quotas: dict, rng: random.Random, max_share: float,
                     cell_quotas: dict, proj_caps: dict, reuse: bool = False,
                     n_lines: dict = None, prefer_small: bool = False, size_target: float = None):
    """Escolhe pares (arquivo, smell) por celula (smell x projeto).
    `proj_caps[k]`: teto duro de ocorrencias do smell k em um unico projeto; nenhuma etapa
    o ultrapassa. Se uma celula nao fecha a cota (faltam candidatos), o deficit e repassado
    a outros projetos com folga, para o total do smell chegar na cota."""
    by_proj = {}
    for r in files:
        by_proj.setdefault(project_of(r), {})[r] = files[r]

    assign, totals = {}, Counter()
    picked = set()  # arquivos ja escolhidos para algum smell (so conta com reuse=True)
    if reuse:  # raros primeiro: tem poucos candidatos; os comuns reaproveitam os arquivos deles
        order = sorted(KEYS, key=lambda k: (sum(1 for c in files.values() if c[k] > 0), KEYS.index(k)))
    else:
        order = KEYS

    def size_key(r):
        if not n_lines:
            return 0
        if prefer_small:
            return n_lines[r]
        if size_target:  # distancia (em escala log) ao tamanho alvo
            return abs(math.log(max(n_lines[r], 1) / size_target))
        return 0

    def prio(r):  # menor = tentado antes. sort estavel; sem as flags e constante (nada muda)
        return (0 if (reuse and r in picked) else 1, size_key(r))

    for k in order:
        pcap = proj_caps[k]
        fcap_k = max(1, math.ceil(quotas[k] * max_share))  # teto por arquivo
        chosen, tp = {}, {}
        for p, q in sorted(cell_quotas[k].items()):
            if q <= 0:
                continue
            sub = by_proj[p]
            cap = max(1, min(fcap_k, q))
            cands = sorted(r for r, c in sub.items() if 0 < c[k] <= cap)
            rng.shuffle(cands)
            cands.sort(key=prio)
            got, t = [], 0
            for r in cands:
                if t >= q:
                    break
                if t + sub[r][k] <= q:
                    got.append(r)
                    t += sub[r][k]
            if t < q:
                used = set(got)
                rest = [
                    r for r, c in sub.items()
                    if 0 < c[k] <= cap and r not in used
                ]
                rng.shuffle(rest)
                rest.sort(key=lambda r: prio(r) + (sub[r][k],))  # estável: empates ficam na ordem sorteada
                for r in rest:
                    if t >= q:
                        break
                    if t + sub[r][k] > pcap:  # nunca passa do teto por projeto
                        continue
                    got.append(r)
                    t += sub[r][k]
            chosen[p] = got
            tp[p] = t

        # repasse do deficit (celulas sem candidatos suficientes) para projetos com folga
        deficit = quotas[k] - sum(tp.values())
        if deficit > 0:
            unused = {}
            for p in sorted(by_proj):
                used = set(chosen.get(p, []))
                c = [r for r in sorted(by_proj[p]) if r not in used and 0 < by_proj[p][r][k] <= fcap_k]
                rng.shuffle(c)
                c.sort(key=prio)
                unused[p] = c
            while deficit > 0:
                best = None
                for p in sorted(unused):
                    head = pcap - tp.get(p, 0)
                    if head <= 0:
                        continue
                    opts = [r for r in unused[p] if by_proj[p][r][k] <= head]
                    if not opts:
                        continue
                    fit = [r for r in opts if by_proj[p][r][k] <= deficit]
                    r = (max(fit, key=lambda x: by_proj[p][x][k]) if fit
                         else min(opts, key=lambda x: by_proj[p][x][k]))
                    score = (1 if fit else 0, head)  # prefere encaixe exato e mais folga
                    if best is None or score > best[0]:
                        best = (score, p, r)
                if best is None:
                    break
                _, p, r = best
                unused[p].remove(r)
                chosen.setdefault(p, []).append(r)
                tp[p] = tp.get(p, 0) + by_proj[p][r][k]
                deficit -= by_proj[p][r][k]

        assign[k] = sorted(r for v in chosen.values() for r in v)
        picked.update(assign[k])
        totals[k] = sum(tp.values())
    return assign, totals


def file_loc(path: Path):
    """(linhas fisicas, linhas de codigo nao vazias e que nao sao so comentario)."""
    lines = path.read_text(encoding="utf-8").split("\n")
    sloc = sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))
    return len(lines), sloc


def loc_dist(v):
    """Resumo da distribuicao de LOC por arquivo."""
    a = np.asarray(list(v), dtype=float)
    if a.size == 0:
        return {}
    return {"n": int(a.size), "mean": round(float(a.mean()), 1), "median": round(float(np.median(a)), 1),
            "p90": round(float(np.percentile(a, 90)), 1), "min": int(a.min()), "max": int(a.max())}


def project_of(rel: str) -> str:
    return rel.split("/")[0] if "/" in rel else "(raiz)"


def read_valid(path: Path, max_lines: int = MAX_FILE_LINES):
    """Retorna n_linhas se o arquivo e utilizavel pelo supervisor, senao None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    n = len(text.split("\n"))
    if n > max_lines or len(text.encode("utf-8")) / 1024 > MAX_FILE_SIZE_KB:
        return None
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=BASE / "dataset_full",
                    help="pasta com todos os .py (padrao: <projeto>/dataset_full)")
    ap.add_argument("--dpy-csv", type=Path, nargs="+", default=[],
                    help="CSV(s) bruto(s) de implementation smells do DPy")
    ap.add_argument("--dpy-json", type=Path, nargs="+", default=[],
                    help="JSON(s) do DPy (um por projeto) ou pastas com .json")
    ap.add_argument("--out", type=Path, default=BASE / "dataset",
                    help="pasta de saida (padrao: <projeto>/dataset)")
    ap.add_argument("--total", type=int, default=450, help="ocorrencias alvo")
    # ------------------------------------- Seed ------------------------------------
    ap.add_argument("--seed", type=int, default=1) 
    # -------------------------------------------------------------------------------
    ap.add_argument("--min-per-smell", type=int, default=30,
                    help="piso de ocorrencias por smell; o resto do --total e proporcional a sqrt(disponivel)")
    ap.add_argument("--select-mode", choices=["per-smell", "cover", "balance"], default="per-smell",
                    help="per-smell: amostra pares (arquivo, smell) com cotas por (smell x projeto), "
                    "total ~= --total, piso garantido e %projeto proximo da populacao; "
                    "cover/balance: amostram arquivos inteiros (todos os smells do arquivo entram)")
    ap.add_argument("--max-file-share", type=float, default=0.25,
                    help="per-smell: maximo da cota de um smell que um unico arquivo pode dar")
    ap.add_argument("--max-project-share", type=float, default=1,
                    help="per-smell: maximo da cota de um smell que um unico projeto pode receber")
    ap.add_argument("--pool-per-smell", type=int, default=500,
                    help="arquivos candidatos sorteados por smell antes da selecao gulosa")
    ap.add_argument("--negatives", type=int, default=0,
                    help="arquivos sem nenhum smell no DPy a incluir")
    ap.add_argument("--min-lines", type=int, default=20,
                    help="tamanho minimo (linhas) de TODOS os arquivos candidatos (com e sem smell). "
                    "Use 0 para desligar")
    ap.add_argument("--quotas", type=Path,
                    help='JSON opcional com cotas fixas, ex: {"Magic number": 50}')
    ap.add_argument("--jitter", type=float, default=0.6,
                    help="per-smell: variacao aleatoria (por seed) nas cotas por projeto; 0 = determinístico")
    ap.add_argument("--reuse-files", action="store_true",
                    help="per-smell: processa smells do mais raro ao mais comum e prefere arquivos ja "
                    "escolhidos para outro smell (menos arquivos para as mesmas cotas)")
    ap.add_argument("--prefer-small", action="store_true",
                    help="per-smell: entre candidatos equivalentes, prefere arquivos menores (menos LOC)")
    ap.add_argument("--prefer-loc", default=None, metavar="N|median|mean",
                    help="per-smell: entre candidatos equivalentes, prefere arquivos com LOC proximo a N "
                    "(ou a mediana/media da populacao). Excludente com --prefer-small")
    ap.add_argument("--seed-search", type=int, default=1, metavar="K",
                    help="per-smell: testa K seeds (seed, seed+1, ...) e fica com a que deixa media/mediana/p90 "
                    "de LOC mais proximas da populacao. Reproduza depois com --seed <escolhida>")
    ap.add_argument("--max-lines", type=int, default=MAX_FILE_LINES,
                    help="descarta arquivos com mais linhas que isso (padrao: limite do supervisor)")
    args = ap.parse_args()
    if not args.dpy_csv and not args.dpy_json:
        args.dpy_json = [BASE / "results" / "dpy" / "jsons"]
    if not args.root.is_dir():
        raise SystemExit(f"--root nao encontrado: {args.root}")

    # Protecoes: evita misturar a amostra com o dataset completo ou com saidas antigas
    out_res, root_res = args.out.resolve(), args.root.resolve()
    if out_res == root_res or out_res in root_res.parents or root_res in out_res.parents:
        raise SystemExit("--out nao pode conter nem estar dentro de --root")
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"--out ({args.out}) ja existe e nao esta vazia; apague ou use outra pasta")

    # ---------- 1. le o DPy e mapeia cada linha para um arquivo de --root ----------
    frames = [pd.read_csv(p) for p in args.dpy_csv]
    json_files = []
    for p in args.dpy_json:
        if not p.exists():
            raise SystemExit(
                f"--dpy-json nao encontrado: {p}\n"
                "Coloque os JSONs do DPy nessa pasta ou passe o caminho com --dpy-json."
            )
        found = sorted(p.glob("*.json")) if p.is_dir() else [p]
        if not found:
            raise SystemExit(f"Nenhum .json em {p}")
        json_files += found
    for p in args.dpy_csv:
        if not p.exists():
            raise SystemExit(f"--dpy-csv nao encontrado: {p}")
    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        if data:
            frames.append(pd.DataFrame(data))
    if not frames:
        raise SystemExit("Passe --dpy-csv e/ou --dpy-json")
    print(f"Lidos: {len(args.dpy_csv)} CSV(s) e {len(json_files)} JSON(s)")
    df = pd.concat(frames, ignore_index=True)
    for col in ("Package", "Module", "Smell", "File"):
        if col not in df.columns:
            raise SystemExit(f"Coluna ausente no CSV do DPy: {col}")
    df["key"] = df["Smell"].str.strip().str.lower()
    unknown = sorted(set(df["key"]) - set(KEYS))
    if unknown:
        print(f"AVISO: smells ignorados (fora dos 11 agentes): {unknown}")
        df = df[df["key"].isin(KEYS)].copy()

    rel_set = {
        p.relative_to(args.root).as_posix()
        for p in args.root.rglob("*.py")
        if "ground_truth" not in p.parts
    }

    def to_rel(f: str):
        # File no CSV e um caminho absoluto da maquina onde o DPy rodou:
        # pega o maior sufixo dele que existe dentro de --root
        parts = [p for p in str(f).replace("\\", "/").split("/") if p]
        for i in range(len(parts)):
            cand = "/".join(parts[i:])
            if cand in rel_set:
                return cand
        return None

    mapping = {f: to_rel(f) for f in df["File"].unique()}
    df["rel"] = df["File"].map(mapping)
    n_unmatched = df.loc[df["rel"].isna(), "File"].nunique()
    df = df[df["rel"].notna()].copy()

    counts_df = df.groupby(["rel", "key"]).size().unstack(fill_value=0).reindex(columns=KEYS, fill_value=0)

    # ---------- 2. filtra arquivos que o supervisor aceitaria ----------
    files, n_lines, invalid, too_small = {}, {}, 0, 0
    for rel in sorted(counts_df.index):
        n = read_valid(args.root / rel, args.max_lines)
        if n is None:
            invalid += 1
            continue
        if n < args.min_lines:
            too_small += 1
            continue
        n_lines[rel] = n
        files[rel] = {k: int(counts_df.loc[rel, k]) for k in KEYS}

    print(f"Arquivos .py em --root: {len(rel_set)} | com smell no DPy: {len(counts_df)} | utilizaveis: {len(files)}")
    print(f"  arquivos do CSV sem correspondente em --root: {n_unmatched}")
    print(f"  invalidos (muito grandes / encoding): {invalid}")
    print(f"  pequenos demais (< {args.min_lines} linhas, --min-lines): {too_small}")

    avail = {k: sum(c[k] for c in files.values()) for k in KEYS}
    if args.quotas:
        raw = json.loads(args.quotas.read_text())
        quotas = {k: int({kk.lower(): v for kk, v in raw.items()}.get(k, 0)) for k in KEYS}
    else:
        quotas = compute_quotas(args.total, avail, args.min_per_smell)

    # ---------- 3. selecao (seed fixa; --seed-search tenta varias seeds) ----------
    if args.seed_search > 1 and args.select_mode != "per-smell":
        raise SystemExit("--seed-search so funciona no modo per-smell.")
    if args.prefer_loc and args.prefer_small:
        raise SystemExit("--prefer-loc e --prefer-small sao excludentes.")
    pop_ref = loc_dist([n_lines[r] for r in files])
    size_target = None
    if args.prefer_loc:
        size_target = {"median": pop_ref["median"], "mean": pop_ref["mean"]}.get(args.prefer_loc) \
            or float(args.prefer_loc)
        print(f"Alvo de tamanho (--prefer-loc): {size_target:.0f} linhas")
    seeds = [args.seed + i for i in range(max(1, args.seed_search))]
    cands = []
    for cur_seed in seeds:
        rng = random.Random(cur_seed)
        pairs = set()
        cell_quotas = None
        if args.select_mode == "per-smell":
            # projetos calculados ANTES de adicionar negativos (so arquivos com smell)
            projects = sorted({project_of(r) for r in files})
            cell_quotas = project_quotas(files, quotas, projects, rng, args.jitter,
                                         args.max_project_share)
            proj_caps, _ = project_caps(project_matrix(files, projects), quotas, args.max_project_share)
            assign, totals = select_per_smell(files, quotas, rng, args.max_file_share, cell_quotas,
                                              proj_caps, reuse=args.reuse_files, n_lines=n_lines,
                                              prefer_small=args.prefer_small, size_target=size_target)
            pairs = {(r, k) for k, rels_k in assign.items() for r in rels_k}
            selected = sorted({r for r, _ in pairs})
            if args.negatives:
                print("AVISO: --negatives nao e usado no modo per-smell (ignorado).")
                args.negatives = 0
        else:
            selected, totals = select_files(files, quotas, rng, args.pool_per_smell, args.select_mode)

        # ---------- 3.1 validacao da selecao ----------
        validation_errors = []

        total_obtained = sum(totals.values())
        if total_obtained != args.total:
            validation_errors.append(
                f"total obtido {total_obtained} != alvo {args.total}"
            )

        quota_errors = []
        for k in KEYS:
            if totals[k] != quotas[k]:
                quota_errors.append((k, quotas[k], totals[k]))

        if quota_errors:
            for k, expected, obtained in quota_errors:
                validation_errors.append(
                    f"{k}: cota {expected}, obtido {obtained}"
                )

        file_cap_violations = []
        file_cap_summary = []

        if args.select_mode == "per-smell":
            for k in KEYS:
                cap = math.ceil(quotas[k] * args.max_file_share)

                selected_for_smell = [
                    (r, files[r][k])
                    for r, smell in pairs
                    if smell == k
                ]

                max_contribution = max(
                    (value for _, value in selected_for_smell),
                    default=0
                )

                max_file = next(
                    (r for r, value in selected_for_smell
                     if value == max_contribution),
                    None
                )

                file_cap_summary.append({
                    "smell": k,
                    "quota": quotas[k],
                    "cap": cap,
                    "max_contribution": max_contribution,
                    "max_file": max_file,
                })

                for r, contribution in selected_for_smell:
                    if contribution > cap:
                        file_cap_violations.append({
                            "smell": k,
                            "file": r,
                            "contribution": contribution,
                            "cap": cap,
                        })

            if file_cap_violations:
                validation_errors.append(
                    f"{len(file_cap_violations)} violacao(oes) do limite por arquivo"
                )

        if validation_errors and len(seeds) > 1:
            print(f"  seed {cur_seed}: rejeitada ({len(validation_errors)} erro(s))")
            continue
        if validation_errors:
            print("\nERRO: selecao invalida")
            for error in validation_errors:
                print(f"  {error}")

            if file_cap_violations:
                print("\nViolacoes do limite por arquivo:")
                for v in file_cap_violations:
                    print(f"  {v['smell']:<22}{v['file']:<55}"
                          f"{v['contribution']:>4} > {v['cap']}")

            raise SystemExit("Seed rejeitada.")

        if len(seeds) > 1:
            sd = loc_dist([n_lines[r] for r in selected])
            score = sum(abs(math.log(sd[k] / pop_ref[k])) for k in ("mean", "median", "p90"))
            cands.append({"seed": cur_seed, "score": score, "files": len(selected), "pairs": len(pairs),
                          "loc": sum(n_lines[r] for r in selected), "sd": sd,
                          "state": (selected, pairs, totals, cell_quotas, file_cap_summary,
                                    file_cap_violations, total_obtained, quota_errors, assign, proj_caps)})

    seed_search_info = None
    if len(seeds) > 1:
        if not cands:
            raise SystemExit("Nenhuma seed valida no intervalo testado.")
        cands.sort(key=lambda c: c["score"])
        print(f"\nBusca de seed: {len(cands)}/{len(seeds)} validas. Melhores (LOC media/mediana/p90 vs populacao):")
        print(f"{'seed':>10}{'arqs':>6}{'pares':>7}{'LOC':>9}{'media':>8}{'mediana':>9}{'p90':>8}{'score':>8}")
        for c in cands[:5]:
            print(f"{c['seed']:>10}{c['files']:>6}{c['pairs']:>7}{c['loc']:>9}{c['sd']['mean']:>8}"
                  f"{c['sd']['median']:>9}{c['sd']['p90']:>8}{c['score']:>8.3f}")
        print(f"{'populacao':>10}{'':>22}{pop_ref['mean']:>8}{pop_ref['median']:>9}{pop_ref['p90']:>8}")
        best = cands[0]
        (selected, pairs, totals, cell_quotas, file_cap_summary, file_cap_violations,
         total_obtained, quota_errors, assign, proj_caps) = best["state"]
        args.seed = best["seed"]
        seed_search_info = {"tried": len(seeds), "valid": len(cands), "score": round(best["score"], 4)}
        print(f"Escolhida: --seed {args.seed} (reproduza com essa seed, sem --seed-search)\n")

    # Negativos: .py validos, sem nenhuma linha no DPy (nao sao __init__ nem minusculos)
    n_neg = 0
    if args.negatives:
        clean = []
        for rel in sorted(rel_set - set(counts_df.index)):
            if rel.endswith("__init__.py"):
                continue
            n = read_valid(args.root / rel, args.max_lines)
            if n is not None and n >= args.min_lines:
                clean.append(rel)
        rng.shuffle(clean)
        for rel in clean[: args.negatives]:
            files[rel] = {k: 0 for k in KEYS}
            selected.append(rel)
            n_neg += 1

    # ---------- 4. saida ----------
    args.out.mkdir(parents=True, exist_ok=True)
    gt_dir = args.out / "ground_truth"
    gt_dir.mkdir(exist_ok=True)

    sel = set(selected)
    meta = df.drop_duplicates("rel").set_index("rel")[["Package", "Module"]]
    manifest = []
    for rel in sorted(selected):
        dst = args.out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.root / rel, dst)
        pkg, mod = (meta.loc[rel, "Package"], meta.loc[rel, "Module"]) if rel in meta.index else ("", Path(rel).stem)
        row = {"file": rel, "Package": pkg, "Module": mod, **files[rel]}
        if pairs:
            row["assigned_smells"] = "; ".join(k for k in KEYS if (rel, k) in pairs)
        manifest.append(row)

    # (a) linhas originais do DPy da amostra (com Line no e Description), File relativo
    if pairs:  # per-smell: so as linhas dos pares (arquivo, smell) sorteados
        mask = pd.MultiIndex.from_frame(df[["rel", "key"]]).isin(pairs)
        sub = df[mask].copy()
        pd.DataFrame(
            [(r, k.title(), files[r][k]) for r, k in sorted(pairs)], columns=["File", "Smell", "Count"]
        ).to_csv(gt_dir / "sample_pairs.csv", index=False)
    else:
        sub = df[df["rel"].isin(sel)].copy()
    sub["File"] = sub["rel"]
    sub.drop(columns=["key", "rel"]).to_csv(gt_dir / "dpy_implementation_smells_sample.csv", index=False)

    # (b) formato Module,Smell,Count (mesmo formato do _filtered)
    long = sub.groupby(["Module", "key"]).size().rename("Count").reset_index()
    long["Smell"] = long["key"].str.title()
    long = long[["Module", "Smell", "Count"]].sort_values(["Module", "Smell"])
    long.to_csv(gt_dir / "implementation_smells_dpy_filtered.csv", index=False)

    pd.DataFrame(manifest).to_csv(args.out / "sample_manifest.csv", index=False)

    # (c) cotas por (smell x projeto) planejadas, para documentar na metodologia
    if cell_quotas is not None:
        pd.DataFrame(cell_quotas).T.reindex(index=KEYS).fillna(0).astype(int) \
            .rename_axis("smell").to_csv(args.out / "sample_cell_quotas.csv")

    # (d) obtido por (smell x projeto) e checagem do teto por projeto (so per-smell)
    cell_obtained, over_cap = {}, []
    if args.select_mode == "per-smell":
        cell_obtained = {k: Counter() for k in KEYS}
        for r, k in pairs:
            cell_obtained[k][project_of(r)] += files[r][k]
        pd.DataFrame({k: dict(v) for k, v in cell_obtained.items()}).T.reindex(index=KEYS) \
            .fillna(0).astype(int).sort_index(axis=1).rename_axis("smell") \
            .to_csv(args.out / "sample_cell_obtained.csv")
        for k in KEYS:
            tot_k = sum(cell_obtained[k].values())
            if tot_k <= 0:
                continue
            for p, v in cell_obtained[k].items():
                if v / tot_k > args.max_project_share + 1e-9:
                    over_cap.append((k, p, v, tot_k))

    # (e) validacao do limite por arquivo
    if args.select_mode == "per-smell":
        pd.DataFrame(file_cap_summary).to_csv(
            args.out / "sample_file_cap_validation.csv",
            index=False
        )

    # ---------- 5. estatisticas: LOC e origem por projeto ----------
    projects = sorted({project_of(r) for r in rel_set})
    st = {pj: {"files": 0, "loc": 0, "sloc": 0, "smells": 0, **{k: 0 for k in KEYS}} for pj in projects}
    loc_by_file, bytes_by_file = {}, {}
    for rel in selected:
        loc, sloc = file_loc(args.root / rel)
        loc_by_file[rel] = loc
        bytes_by_file[rel] = (args.root / rel).stat().st_size
        d = st[project_of(rel)]
        d["files"] += 1
        d["loc"] += loc
        d["sloc"] += sloc
        for k in KEYS:
            if not pairs or (rel, k) in pairs:  # per-smell: so os pares sorteados contam
                d[k] += files[rel][k]
                d["smells"] += files[rel][k]
    av_files, av_smells, av_loc = Counter(), Counter(), Counter()
    pop_loc = []  # LOC de cada arquivo da populacao (com smell, utilizavel)
    for rel, c in files.items():
        if sum(c.values()) > 0:  # ignora os negativos adicionados
            av_loc[project_of(rel)] += n_lines.get(rel, 0)
            if rel in n_lines:
                pop_loc.append(n_lines[rel])
            av_files[project_of(rel)] += 1
            av_smells[project_of(rel)] += sum(c.values())
    tot_loc = sum(d["loc"] for d in st.values())
    tot_sloc = sum(d["sloc"] for d in st.values())
    tot_smells = sum(d["smells"] for d in st.values())
    tot_av = sum(av_smells.values())

    def per_kloc(n, loc):
        return round(1000 * n / loc, 2) if loc else 0.0

    dist = loc_dist

    sel_dist, pop_dist = dist(list(loc_by_file.values())), dist(pop_loc)

    rows = []
    for pj in projects:
        d = st[pj]
        rows.append({
            "project": pj, "files_selected": d["files"], "loc": d["loc"], "sloc": d["sloc"],
            "smells_selected": d["smells"],
            "loc_per_file": round(d["loc"] / d["files"], 1) if d["files"] else 0.0,
            "pop_loc_per_file": round(av_loc[pj] / av_files[pj], 1) if av_files[pj] else 0.0,
            "share_of_sample_pct": round(100 * d["smells"] / tot_smells, 1) if tot_smells else 0.0,
            "smells_per_kloc": per_kloc(d["smells"], d["loc"]),
            "files_available": av_files[pj], "smells_available": av_smells[pj],
            "share_of_population_pct": round(100 * av_smells[pj] / tot_av, 1) if tot_av else 0.0,
            **{k: d[k] for k in KEYS},
        })
    pd.DataFrame(rows).to_csv(args.out / "sample_stats_by_project.csv", index=False)

    # MAE entre %amostra e %populacao (em pontos percentuais), so projetos com smells na populacao
    rows_mae = [r for r in rows if r["smells_available"] > 0]
    mae = float(np.mean([abs(r["share_of_sample_pct"] - r["share_of_population_pct"]) for r in rows_mae])) \
        if rows_mae else 0.0

    n_files, n_kinds = len(selected), len(KEYS)
    tot_bytes = sum(bytes_by_file.values())
    arch = {
        "agente_unico": {"chamadas": n_files, "loc_enviadas": tot_loc, "tokens_codigo_aprox": tot_bytes // 4},
        "multiagente_completo": {"chamadas": n_kinds * n_files, "loc_enviadas": n_kinds * tot_loc,
                                 "tokens_codigo_aprox": n_kinds * tot_bytes // 4},
    }
    if pairs:
        arch["multiagente_assigned"] = {
            "chamadas": len(pairs),
            "loc_enviadas": sum(loc_by_file[r] for r, _ in pairs),
            "tokens_codigo_aprox": sum(bytes_by_file[r] for r, _ in pairs) // 4}

    pd.DataFrame([{"file": r, "project": project_of(r), "loc": loc_by_file[r], "bytes": bytes_by_file[r],
                   "n_pairs": sum(1 for k in KEYS if (r, k) in pairs) if pairs else "",
                   "assigned_smells": "; ".join(k for k in KEYS if (r, k) in pairs) if pairs else ""}
                  for r in sorted(selected)]).to_csv(args.out / "sample_file_stats.csv", index=False)

    summary = {
        "loc_per_file_sample": sel_dist, "loc_per_file_population": pop_dist, "by_architecture": arch,
        "total_loc": tot_loc, "total_sloc": tot_sloc, "smells_selected": tot_smells,
        "smells_per_kloc": per_kloc(tot_smells, tot_loc),
        "smells_per_kloc_by_smell": {k: per_kloc(totals[k], tot_loc) for k in KEYS},
        "mae_share_pp": round(mae, 3),
        "by_project": {r["project"]: {kk: vv for kk, vv in r.items() if kk != "project"} for r in rows},
    }
    (args.out / "sample_config.json").write_text(json.dumps({
        "seed": args.seed, "total": args.total, "min_per_smell": args.min_per_smell,
        "pool_per_smell": args.pool_per_smell, "select_mode": args.select_mode,
        "max_file_share": args.max_file_share, "max_project_share": args.max_project_share,
        "reuse_files": args.reuse_files, "prefer_small": args.prefer_small, "max_lines": args.max_lines,
        "min_lines": args.min_lines, "prefer_loc": args.prefer_loc, "seed_search": seed_search_info,
        "negatives": n_neg,
        "quotas": quotas, "available": avail,
        "cell_quotas": cell_quotas,
        "obtained": {k: totals[k] for k in KEYS}, "files_selected": len(selected),
        "validation": {
            "valid": True,
            "total_obtained": total_obtained,
            "total_target": args.total,
            "quota_errors": [],
            "file_cap_violations": len(file_cap_violations),
        },
        "stats": summary,
    }, indent=2))

    print(f"\nArquivos selecionados: {len(selected)} ({n_neg} negativos)")
    if pairs:
        print(f"Pares (arquivo, smell): {len(pairs)} | pares/arquivo: {len(pairs) / len(selected):.2f}")
    print(f"{'smell':<22}{'disponivel':>11}{'cota':>7}{'obtido':>8}")
    for k in KEYS:
        print(f"{k:<22}{avail[k]:>11}{quotas[k]:>7}{totals[k]:>8}")
    print(f"{'TOTAL':<22}{sum(avail.values()):>11}{sum(quotas.values()):>7}{sum(totals.values()):>8}")
    print(f"\nLOC dos arquivos selecionados: {tot_loc} ({tot_sloc} sem brancos/comentarios) | "
          f"{per_kloc(tot_smells, tot_loc)} smells por 1000 LOC")
    print(f"\nLOC por arquivo (amostra):   media {sel_dist['mean']} | mediana {sel_dist['median']} | "
          f"p90 {sel_dist['p90']} | min {sel_dist['min']} | max {sel_dist['max']}")
    print(f"LOC por arquivo (populacao): media {pop_dist['mean']} | mediana {pop_dist['median']} | "
          f"p90 {pop_dist['p90']} | min {pop_dist['min']} | max {pop_dist['max']}  "
          f"(arquivos com smell e utilizaveis, n={pop_dist['n']})")
    print(f"\n{'projeto':<28}{'arqs':>6}{'LOC':>9}{'LOC/arq':>9}{'pop':>8}{'smells':>8}{'%amostra':>9}{'/KLOC':>8}{'%popul.':>9}")
    for r in rows:
        print(f"{r['project']:<28}{r['files_selected']:>6}{r['loc']:>9}{r['loc_per_file']:>9}{r['pop_loc_per_file']:>8}"
              f"{r['smells_selected']:>8}{r['share_of_sample_pct']:>9}{r['smells_per_kloc']:>8}{r['share_of_population_pct']:>9}")
    print("\nVolume por configuracao (so o codigo; some o prompt por chamada). tokens = bytes/4, aproximado:")
    print(f"{'arquitetura':<24}{'chamadas':>10}{'LOC enviadas':>14}{'tokens aprox.':>15}")
    for name, a in arch.items():
        print(f"{name:<24}{a['chamadas']:>10}{a['loc_enviadas']:>14}{a['tokens_codigo_aprox']:>15}")
    print(f"\nMAE (%amostra vs %popul.): {mae:.2f} p.p. ({len(rows_mae)} projetos)")
    below = [k for k in KEYS if totals[k] < quotas[k]]
    if below:
        print(f"\nAVISO: abaixo da cota: {below}")
    if over_cap:
        print(f"\nAVISO: projeto acima de {args.max_project_share:.0%} do smell obtido "
              "(estouro do ultimo arquivo ou teto relaxado por inviabilidade):")
        for k, p, v, t in over_cap:
            print(f"  {k:<22}{p:<28}{v:>4}/{t:<4} = {v / t:.0%}")
    if args.select_mode == "per-smell":
        print("\nNOTA: so contam as ocorrencias dos pares em ground_truth/sample_pairs.csv. "
              "Ao avaliar, filtre os resultados do LLM por (File, Smell) desses pares.")
    elif sum(totals.values()) > 1.2 * sum(quotas.values()):
        print(f"AVISO: total obtido ({sum(totals.values())}) bem acima do alvo ({sum(quotas.values())}): "
              "os smells co-ocorrem nos mesmos arquivos. O modo per-smell evita isso.")

    print(f"\n[OK] total={total_obtained}, cotas=OK, limite_arquivo=OK")

    coll = sub.groupby("Module")["rel"].nunique()
    coll = coll[coll > 1].index.tolist()
    if coll:
        print(f"\nAVISO: modulos com mesmo nome em arquivos diferentes (se fundem no _filtered): {coll}")


if __name__ == "__main__":
    main()