"""Referencia DPy e correspondencia um a um; sem credenciais ou acesso a rede."""
import ast
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

METHOD_SMELLS = {'long method', 'complex method', 'long parameter list'}


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0


def line_number(value):
    match = re.fullmatch(r'\s*(\d+)(?:\s*-\s*\d+)?\s*', str(value))
    return int(match.group(1)) if match else None


class Reference:
    VERSION = 'occurrence-v1'

    def __init__(self, dataset, ground_truth):
        self.dataset = Path(dataset)
        self.rows = defaultdict(list)
        self.contexts = {}
        for row in read_csv(ground_truth):
            self.rows[(row['File'], row['Smell'].strip().lower())].append(row)

    def context(self, rel):
        if rel not in self.contexts:
            tree = ast.parse((self.dataset / rel).read_text(encoding='utf-8'))
            parents = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[child] = node
            functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            self.contexts[rel] = tree, parents, functions
        return self.contexts[rel]

    def function_at(self, rel, line):
        if line is None:
            return None
        functions = self.context(rel)[2]
        candidates = [f for f in functions if f.lineno <= line <= f.end_lineno]
        return min(candidates, key=lambda f: f.end_lineno - f.lineno) if candidates else None

    def method_identity(self, rel, line):
        function = self.function_at(rel, line)
        return function.lineno if function else None

    def block_candidates(self, rel, smell):
        tree = self.context(rel)[0]
        if smell == 'empty catch block':
            return [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
                    and len(n.body) == 1 and isinstance(n.body[0], (ast.Pass, ast.Return))]
        if smell == 'missing default':
            return [n for n in ast.walk(tree) if isinstance(n, ast.Match)
                    and not any(isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None
                                and c.pattern.name is None and c.guard is None for c in n.cases)]
        return []

    def matches(self, rel, smell, prediction, truth):
        pline = line_number(prediction.get('Line_no'))
        gline = line_number(truth.get('Line no'))
        if pline is None or gline is None:
            return False
        if smell in METHOD_SMELLS:
            function = self.function_at(rel, gline)
            # Apenas linha inicial da funcao: uma linha interna nao identifica
            # uma funcao prevista com localizacao correta.
            return function is not None and pline == function.lineno and prediction.get('Method') == function.name
        if smell == 'long identifier':
            match = re.search(r"Identifier\s*['\"]([^'\"]+)['\"]", truth.get('Description', ''), re.I)
            if not match or prediction.get('identifier_name') != match.group(1):
                return False
            # DPy usa a linha da funcao para identificadores locais. A identidade
            # e nome + funcao, sem tolerancia numerica arbitraria entre linhas.
            scope = self.method_identity(rel, gline)
            if scope is None:
                return pline == gline
            if self.method_identity(rel, pline) != scope:
                return False
            function = self.function_at(rel, gline)
            name = match.group(1)
            names = {n.id for n in ast.walk(function) if isinstance(n, ast.Name)}
            names.update(n.arg for n in ast.walk(function) if isinstance(n, ast.arg))
            names.update(n.attr for n in ast.walk(function) if isinstance(n, ast.Attribute))
            names.update(n.name for n in ast.walk(function) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            return name in names
        if smell in {'empty catch block', 'missing default'}:
            candidates = self.block_candidates(rel, smell)
            predicted_block = next((n for n in candidates if n.lineno == pline), None)
            if predicted_block is None:
                return False
            # Se DPy anota o proprio bloco, exige igualdade. Se anota a funcao,
            # aceita bloco qualificante naquela funcao (resolucao do gabarito).
            if any(n.lineno == gline for n in candidates):
                return pline == gline
            function = self.function_at(rel, gline)
            return (function is not None and gline == function.lineno
                    and self.method_identity(rel, pline) == function.lineno)
        if smell == 'magic number':
            if pline != gline:
                return False
            match = re.search(r'Magic number\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)', truth.get('Description', ''), re.I)
            if not match:
                return False
            expected = float(match.group(1))
            value = prediction.get('number')
            if value is None:
                evidence = re.search(r'Magic number\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)', prediction.get('Description', ''), re.I)
                value = evidence.group(1) if evidence else None
            if value is None or isinstance(value, bool):
                return False
            try:
                return float(value) == expected
            except (ValueError, TypeError):
                return False
        return pline == gline

    def validate(self, sample):
        for rel, smells in sample.items():
            self.context(rel)  # Falha antes da inferencia se o codigo nao e analisavel.
            for smell, count in smells.items():
                rows = self.rows[(rel, smell)]
                if len(rows) != count:
                    raise ValueError(f'Gabarito/manifesto divergentes: {rel}, {smell}: {len(rows)} != {count}')
                for row in rows:
                    if line_number(row.get('Line no')) is None:
                        raise ValueError(f'Gabarito sem localizacao: {rel}, {smell}')
                    if smell == 'long identifier' and not re.search(r"Identifier\s*['\"]([^'\"]+)['\"]", row.get('Description', ''), re.I):
                        raise ValueError(f'Gabarito sem nome do identificador: {rel}')

    def evaluate(self, detections, sample):
        per = defaultdict(lambda: dict(tp=0, fp=0, fn=0, oos=0, positive_cells=0, negative_cells=0))
        predicted = defaultdict(list)
        details, presence = [], Counter()
        for index, detection in enumerate(detections):
            rel, smell = detection['rel'], detection['smell_key']
            if smell not in sample.get(rel, {}):
                per[smell]['oos'] += 1
                details.append(dict(status='out_of_scope', prediction_index=index, prediction=detection))
            else:
                predicted[(rel, smell)].append((index, detection))
        for rel, smells in sample.items():
            for smell, count in smells.items():
                truth = self.rows[(rel, smell)]
                if len(truth) != count:
                    raise ValueError(f'Contagem do manifesto diverge do gabarito: {rel}, {smell}')
                preds = predicted[(rel, smell)]
                per[smell]['positive_cells' if count else 'negative_cells'] += 1
                presence['tp' if count and preds else 'fn' if count else 'fp' if preds else 'tn'] += 1
                edges = [[j for j, row in enumerate(truth) if self.matches(rel, smell, d, row)] for _, d in preds]
                assigned = {}

                def augment(i, seen):
                    for j in edges[i]:
                        if j in seen:
                            continue
                        seen.add(j)
                        if j not in assigned or augment(assigned[j], seen):
                            assigned[j] = i
                            return True
                    return False

                for i in range(len(preds)):
                    augment(i, set())
                inverse = {i: j for j, i in assigned.items()}
                per[smell]['tp'] += len(assigned)
                per[smell]['fp'] += len(preds) - len(assigned)
                per[smell]['fn'] += len(truth) - len(assigned)
                for i, (index, d) in enumerate(preds):
                    details.append(dict(status='tp' if i in inverse else 'fp', prediction_index=index,
                                        prediction=d, truth=truth[inverse[i]] if i in inverse else None))
                for j, row in enumerate(truth):
                    if j not in assigned:
                        details.append(dict(status='fn', truth=row))
        tp, fp, fn = (sum(v[k] for v in per.values()) for k in ('tp', 'fp', 'fn'))
        p, r, f = prf(tp, fp, fn)
        # Tipos com positivos OU erros entram no macro; negativos perfeitos
        # isoladamente nao criam um F1 artificial de 1.
        macro_types = [v for v in per.values() if v['tp'] + v['fp'] + v['fn']]
        for value in per.values():
            value['precision'], value['recall'], value['f1'] = prf(value['tp'], value['fp'], value['fn'])
        return dict(precision=p, recall=r, f1=f, tp=tp, fp=fp, fn=fn,
                    macro_f1=sum(v['f1'] for v in macro_types) / len(macro_types) if macro_types else 0.0,
                    macro_smells=len(macro_types), out_of_scope=sum(v['oos'] for v in per.values()),
                    per_smell=dict(per), presence={**presence, 'f1': prf(presence['tp'], presence['fp'], presence['fn'])[2]},
                    details=details, evaluation_version=self.VERSION)
