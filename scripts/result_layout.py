"""Organizacao nativa dos resultados; mantem leitura das rodadas historicas."""
def canonical_prompt(name):
    return 'simple_v2' if name in ('simple', 'simple_estevam', 'simple_v2') else 'complete_v2' if name in ('complete', 'complete_v2') else name


def condition_directory(output, index, model, prompt, layout='legacy'):
    if layout == 'flat':
        return output / canonical_prompt(prompt)
    return output / f'{index+1:02d}_{model.replace("/", "__")}' / prompt


def result_files(run):
    return sorted(set(run.glob('*/results_*_prompts.json')) | set(run.glob('*/*/results_*_prompts.json')))


def evidence_summaries(run):
    return sorted(set(run.glob('*/evidence_summary.json')) | set(run.glob('*/*/evidence_summary.json')))
