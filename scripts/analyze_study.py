"""Analise offline completa de uma matriz; nao importa settings nem chama LLMs."""
import argparse
from collections import Counter, defaultdict
import csv
import html
import itertools
import json
from pathlib import Path
import statistics
import sys

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from core.execution.evidence import EvidenceStore
from core.supervisor.agent_config import AGENTS
from evaluate_results import normalize
from experiment_evaluation import Reference, read_csv
from result_layout import canonical_prompt, result_files
from study_metrics import occurrence, presence, ratio, distribution, paired_bootstrap, interval, bootstrap_difference, mcnemar, holm

VERSION='study-analysis-v1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path,value):
    from checkpointing import write_json
    write_json(path,value)


def csv_export(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list,tuple)) else v for k,v in row.items()})


def valid_cell(metric,smell,architecture):
    if metric is None or metric.get('error'):return False
    agent='all_smells' if architecture=='single' else smell.replace(' ','_')
    detail=metric.get('agent_metrics',{}).get(agent,{})
    history=detail.get('attempts',[])
    return not (metric.get('agent_errors',{}).get(agent) or detail.get('error')) and bool(history) and not history[-1].get('error')


def attempts_for(folder,metrics):
    rows={};events_available=(folder/'evidence').is_dir()
    selected={}
    for metric in metrics:
        for agent,detail in metric.get('agent_metrics',{}).items():
            for i,attempt in enumerate(detail.get('attempts',[]),1):
                identifier=attempt.get('evidence_id') or f"legacy:{metric['file']}:{agent}:{i}"
                rows[identifier]=dict(attempt,attempt_id=identifier,file=metric['file'],agent=agent,
                    attempt=i,committed=True,elapsed_seconds=None)
                if i==len(detail['attempts']) and not attempt.get('error'):
                    selected[(metric['file'],agent)]=identifier
    raw_final={};last={};raw_available=False
    for event in EvidenceStore.iter_events(folder):
        identifier=event['attempt_id'];stage=event['stage'];p=event['payload']
        if not identifier:continue
        row=rows.setdefault(identifier,dict(attempt_id=identifier,file=event['file_context'].get('file'),
            committed=False,cost_usd=None))
        if stage=='attempt_started':row.update(agent=p['agent'],attempt=p['number'],max_tokens=p['max_tokens'])
        if stage=='attempt_completed':
            row.update(p['metrics']);row['completed']=True
            if not p['metrics'].get('error'):
                key=(row['file'],row.get('agent'));last[key]=identifier
                raw_final[identifier]=p['extracted_detections'];raw_available=True
        if stage=='attempt_interrupted':row['interrupted']=True
        if stage=='attempt_closed':row['elapsed_seconds']=p['elapsed_seconds']
        if stage=='http_response':
            row['http_status']=p['status_code']
            try:
                body=json.loads(p['body']['text']);usage=body.get('usage') or {}
                row['provider_generation_id']=body.get('id');row['returned_model']=body.get('model')
                if usage.get('cost') is not None:row['cost_usd']=usage['cost']
                row['token_usage']=usage
                row['cached_tokens']=(usage.get('prompt_tokens_details') or {}).get('cached_tokens')
                row['reasoning_tokens']=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens',row.get('reasoning_tokens'))
            except (ValueError,AttributeError):row['http_body_parseable']=False
    # Only the final validated attempt per committed task enters the before-filter diagnostic.
    raw=[];committed_files={m['file'] for m in metrics}
    for (rel,agent),identifier in selected.items():
        if rel not in committed_files:continue
        for detection in raw_final.get(identifier,[]):
            item=dict(detection,File=rel);item['Line no']=item.pop('Line_no','');raw.append(item)
    return list(rows.values()),raw if raw_available else None,events_available


def condition(run,path,dataset=None):
    selection=load(run/'sample.json');files={f['File']:f for f in selection['files']}
    dataset=Path(dataset or selection['dataset']);config=load(run/'config.json')
    reference=Reference(dataset,run/'evaluation_reference.csv');scope={}
    for row in read_csv(run/'evaluation_pairs.csv'):scope.setdefault(row['File'],{})[row['Smell'].lower()]=int(row['Count'])
    reference.validate(scope)
    predictions=[normalize(p,files)[0] for p in load(path)]
    evaluation=reference.evaluate(predictions,scope)
    folder=path.parent
    usage=load(next(folder.glob('token_usage_*_prompts.json')))
    metrics=load(next(folder.glob('file_metrics_*_prompts.json')))
    architecture=config['architecture'];model=usage['model'];prompt=canonical_prompt(usage['prompt_type'])
    key=f'{model}|{architecture}|{prompt}'
    by_file={m['file']:m for m in metrics}
    counts=defaultdict(Counter);pred_count=Counter((p['rel'],p['smell_key']) for p in predictions)
    for d in evaluation['details']:
        rel=d['truth']['File'] if d['status']=='fn' else d['prediction']['rel']
        smell=d['truth']['Smell'].lower() if d['status']=='fn' else d['prediction']['smell_key']
        counts[(rel,smell)][d['status']]+=1
    cells=[];file_rows=[];project_counts=defaultdict(Counter);valid_counts=Counter();presence_counts=Counter()
    for rel,smells in scope.items():
        file_counts=Counter();valid_file=True
        for smell,truth in smells.items():
            values=counts[(rel,smell)];valid=valid_cell(by_file.get(rel),smell,architecture)
            cell=dict(file=rel,project=rel.split('/')[0],smell=smell,truth_count=truth,
                prediction_count=pred_count[(rel,smell)],valid=valid,**{k:values[k] for k in ('tp','fp','fn')})
            cells.append(cell);file_counts.update({k:values[k] for k in ('tp','fp','fn')})
            if valid:
                valid_counts.update({k:values[k] for k in ('tp','fp','fn')})
                presence_counts['tp' if truth and cell['prediction_count'] else 'fn' if truth else 'fp' if cell['prediction_count'] else 'tn']+=1
            valid_file &= valid
        project_counts[rel.split('/')[0]].update(file_counts)
        file_rows.append(dict(file=rel,project=rel.split('/')[0],valid_evaluated_cells=valid_file,
            **occurrence(file_counts['tp'],file_counts['fp'],file_counts['fn']),
            elapsed_seconds=(by_file.get(rel) or {}).get('elapsed_seconds'),
            out_of_scope=sum(v['out_of_scope'] for (r,_),v in counts.items() if r==rel)))
    by_smell=[]
    for smell in sorted({s for _,s in counts}|{s for ss in scope.values() for s in ss}):
        v=evaluation['per_smell'].get(smell,{})
        by_smell.append(dict(smell=smell,**occurrence(v.get('tp',0),v.get('fp',0),v.get('fn',0)),
            out_of_scope=v.get('oos',0),positive_cells=v.get('positive_cells',0),negative_cells=v.get('negative_cells',0)))
    for rows,dimension in [(by_smell,'smell'),(file_rows,'file')]:
        for row in rows:
            subset=[c for c in cells if c[dimension]==row[dimension]]
            binary=Counter()
            for c in subset:
                if c['valid']:binary['tp' if c['truth_count'] and c['prediction_count'] else 'fn' if c['truth_count'] else 'fp' if c['prediction_count'] else 'tn']+=1
            row['valid_presence']=presence(**{k:binary[k] for k in ('tp','fp','fn','tn')})
            errors=[c['prediction_count']-c['truth_count'] for c in subset]
            row['count_mae']=statistics.mean(abs(x) for x in errors) if errors else None
            row['count_rmse']=statistics.mean(x*x for x in errors)**.5 if errors else None
            row['count_exact_rate']=ratio(sum(x==0 for x in errors),len(errors))
    projects=[dict(project=p,**occurrence(v['tp'],v['fp'],v['fn'])) for p,v in sorted(project_counts.items())]
    attempts,raw,raw_available=attempts_for(folder,metrics)
    for row in file_rows:
        relevant=[a for a in attempts if a.get('file')==row['file']]
        row['known_cost_usd']=sum(a.get('cost_usd') or 0 for a in relevant)
        row['cost_complete']=bool(relevant) and all(a.get('cost_usd') is not None for a in relevant)
        row['attempts']=len(relevant)
        row['valid_all_tasks']=all(valid_cell(by_file.get(row['file']),name.replace('_',' '),architecture) for name in AGENTS)
    errors=[c['prediction_count']-c['truth_count'] for c in cells]
    abs_errors=[abs(v) for v in errors]
    count_diag=dict(mae=statistics.mean(abs_errors),rmse=(statistics.mean(v*v for v in errors))**.5,
        mean_signed_error=statistics.mean(errors),max_absolute_error=max(abs_errors),
        exact_count_rate=ratio(sum(v==0 for v in errors),len(errors)),evaluated_cells=len(cells),
        note='Count agreement ignores identity/location; not the primary occurrence F1.')
    costs=[a.get('cost_usd') for a in attempts]
    known=sum(v for v in costs if isinstance(v,(int,float)))
    if not raw_available:known=usage.get('known_cost_usd',known)
    resource=dict(reported_total_cost_usd=usage.get('total_cost_usd'),known_cost_usd=known,
        cost_complete=usage.get('cost_complete',False),cost_coverage=ratio(sum(v is not None for v in costs),len(costs)),
        cost_per_file_usd=ratio(usage['total_cost_usd'],len(files)) if usage.get('total_cost_usd') is not None else None,
        cost_per_tp_usd=ratio(usage['total_cost_usd'],evaluation['tp']) if usage.get('total_cost_usd') is not None else None,
        file_seconds=distribution(m.get('elapsed_seconds') for m in metrics),
        attempt_seconds=distribution(a.get('elapsed_seconds') for a in attempts),
        token_usage=usage.get('token_usage'),
        reasoning_tokens_reported=sum(a.get('reasoning_tokens') or 0 for a in attempts),
        reasoning_token_coverage=ratio(sum(a.get('reasoning_tokens') is not None for a in attempts),len(attempts)),
        cached_tokens_reported=sum(a.get('cached_tokens') or 0 for a in attempts),
        cache_metadata_coverage=ratio(sum(a.get('cached_tokens') is not None for a in attempts),len(attempts)),
        note='Known cost is a lower bound when incomplete; never add journal and checkpoint totals. Timings include local instrumentation.')
    technical={k:usage.get(k) for k in ('status','expected_tasks','valid_tasks','valid_response_rate','attempted_calls',
        'failed_attempts','agent_failures','not_executed_tasks','files_with_errors','normalized_responses','usage_complete')}
    technical.update(failure_rate=ratio((usage.get('expected_tasks',0)-usage.get('valid_tasks',0)),usage.get('expected_tasks',0)),
        attempt_failure_rate=ratio(usage.get('failed_attempts',0),usage.get('attempted_calls',0)),
        failure_types=dict(Counter(a.get('error') for a in attempts if a.get('error'))),
        recovered_tasks=sum(bool(d.get('recovered')) for m in metrics for d in m.get('agent_metrics',{}).values()),
        completed_files=len(metrics),valid_evaluated_pairs=sum(c['valid'] for c in cells),total_evaluated_pairs=len(cells))
    primary=occurrence(evaluation['tp'],evaluation['fp'],evaluation['fn'])
    active=[x for x in by_smell if x['tp']+x['fp']+x['fn']]
    primary.update(macro_f1=evaluation['macro_f1'],macro_precision=statistics.mean(x['precision'] or 0 for x in active) if active else None,
        macro_recall=statistics.mean(x['recall'] or 0 for x in active) if active else None,
        weighted_f1=ratio(sum((x['f1'] or 0)*x['support'] for x in by_smell),sum(x['support'] for x in by_smell)),
        out_of_scope=evaluation['out_of_scope'])
    # Compare the actual selection and reference directly, without fingerprints.
    cohort=json.dumps(dict(files=sorted(files),scope=scope,
        truth=read_csv(run/'evaluation_reference.csv')),sort_keys=True)
    return dict(id=key,model=model,architecture=architecture,prompt=prompt,run=str(run),directory=str(folder),
        cohort=cohort,primary=primary,valid_only_occurrence=occurrence(valid_counts['tp'],valid_counts['fp'],valid_counts['fn']),
        valid_only_presence=presence(**{k:presence_counts[k] for k in ('tp','fp','fn','tn')}),
        count_diagnostic=count_diag,technical=technical,resources=resource,
        by_file=file_rows,by_smell=by_smell,by_project=projects,cells=cells,attempts=attempts,
        occurrence_details=evaluation['details'],
        before_filters=reference.evaluate([normalize(p,files)[0] for p in raw],scope) if raw is not None else None,
        unavailable=dict(roc_auc='No continuous prediction scores.',pr_auc='No continuous prediction scores.',
            calibration='No predictive probabilities.',occurrence_accuracy='No finite annotated occurrence-level TN universe.',
            llm_run_variance='One generation per condition does not estimate repeated-call variance.'))


def flatten(value,prefix=''):
    result={}
    for key,item in value.items():
        name=f'{prefix}{key}'
        if isinstance(item,dict):result.update(flatten(item,name+'.'))
        else:result[name]=item
    return result


def comparisons(conditions,bootstrap):
    rows=[]
    for a,b in itertools.combinations(conditions,2):
        dimensions=[d for d in ('model','architecture','prompt') if a[d]!=b[d]]
        if len(dimensions)!=1:continue
        base=dict(a=a['id'],b=b['id'],dimension=dimensions[0],cohort_matches=a['cohort']==b['cohort'])
        if not base['cohort_matches']:
            rows.append(dict(base,status='incompatible_reference'));continue
        ca={(c['file'],c['smell']):c for c in a['cells']};cb={(c['file'],c['smell']):c for c in b['cells']}
        common=[k for k in ca if ca[k]['valid'] and cb[k]['valid']]
        better_a=better_b=agreement=0;joint=Counter()
        common_counts={'a':Counter(),'b':Counter()}
        for key in common:
            x,y=ca[key],cb[key];px=x['prediction_count']>0;py=y['prediction_count']>0
            correct_a=px==(x['truth_count']>0);correct_b=py==(y['truth_count']>0)
            better_a+=correct_a and not correct_b;better_b+=correct_b and not correct_a
            agreement+=px==py;joint[(px,py)]+=1
            for side,c in [('a',x),('b',y)]:common_counts[side].update({k:c[k] for k in ('tp','fp','fn')})
        delta=(a['primary']['f1']-b['primary']['f1']) if a['primary']['f1'] is not None and b['primary']['f1'] is not None else None
        base.update(status='exploratory',f1_a=a['primary']['f1'],f1_b=b['primary']['f1'],f1_difference=delta,
            cost_a=a['resources']['reported_total_cost_usd'],cost_b=b['resources']['reported_total_cost_usd'],
            common_valid_cells=len(common),excluded_cells=len(ca)-len(common),
            common_valid_occurrence={s:occurrence(v['tp'],v['fp'],v['fn']) for s,v in common_counts.items()},
            presence_prediction_agreement=ratio(agreement,len(common)),
            presence_prediction_kappa=presence(joint[(True,True)],joint[(True,False)],joint[(False,True)],joint[(False,False)])['kappa'],
            mcnemar_a_correct_b_wrong=better_a,mcnemar_b_correct_a_wrong=better_b,
            mcnemar_presence_p=mcnemar(better_a,better_b))
        if bootstrap:
            base['paired_f1_interval']=bootstrap_difference(bootstrap[a['id']]['f1'],bootstrap[b['id']]['f1'])
        rows.append(base)
    adjusted=holm({str(i):r['mcnemar_presence_p'] for i,r in enumerate(rows) if 'mcnemar_presence_p' in r})
    for i,r in enumerate(rows):
        if str(i) in adjusted:r['mcnemar_presence_p_holm']=adjusted[str(i)]
    return rows


def analyze(study,output=None,iterations=10000,seed=20261106,dataset=None):
    study=Path(study).resolve();output=Path(output or study/'analysis').resolve()
    configs=[]
    for path in sorted(study.rglob('config.json')):
        item=load(path)
        if 'architecture' in item and 'parameters' in item:configs.append(path.parent)
    conditions=[]
    for run in configs:
        for path in result_files(run):conditions.append(condition(run,path,dataset=dataset))
    if not conditions:raise ValueError('Nenhuma condicao com resultados salvos')
    identifiers=[c['id'] for c in conditions]
    if len(set(identifiers))!=len(identifiers):raise ValueError('Mais de uma rodada por condicao: selecione uma matriz, sem misturar repeticoes')
    output.mkdir(parents=True,exist_ok=True)
    same_cohort=len({c['cohort'] for c in conditions})==1
    boot={};uncertainty={}
    if same_cohort:
        files=sorted(r['file'] for r in conditions[0]['by_file'])
        counts={c['id']:{r['file']:(r['tp'],r['fp'],r['fn']) for r in c['by_file']} for c in conditions}
        boot=paired_bootstrap(counts,files,iterations,seed)
        project_names=sorted(r['project'] for r in conditions[0]['by_project'])
        project_counts={c['id']:{r['project']:(r['tp'],r['fp'],r['fn']) for r in c['by_project']} for c in conditions}
        project_boot=paired_bootstrap(project_counts,project_names,iterations,seed+1)
        for c in conditions:
            uncertainty[c['id']]=dict(files={k:interval(v) for k,v in boot[c['id']].items()},
                projects_sensitivity={k:interval(v) for k,v in project_boot[c['id']].items()})
    pairs=comparisons(conditions,boot)
    for pair in pairs:
        if same_cohort and pair['status']=='exploratory':
            pair['project_cluster_f1_interval_sensitivity']=bootstrap_difference(project_boot[pair['a']]['f1'],project_boot[pair['b']]['f1'])
    for c in conditions:
        cost=c['resources']['reported_total_cost_usd'];score=c['primary']['f1']
        c['pareto_dominated']=any(d is not c and d['cohort']==c['cohort'] and cost is not None
            and d['resources']['reported_total_cost_usd'] is not None and score is not None
            and d['primary']['f1'] is not None and c['technical']['status']=='valid' and d['technical']['status']=='valid'
            and d['resources']['reported_total_cost_usd']<=cost and d['primary']['f1']>=score
            and (d['resources']['reported_total_cost_usd']<cost or d['primary']['f1']>score) for d in conditions)
    summaries=[];all_smells=[];all_files=[];all_projects=[];all_cells=[];all_attempts=[];agents=[];failures=[]
    details_path=output/'occurrence_details.jsonl'
    with details_path.open('w',encoding='utf-8') as stream:
        for c in conditions:
            context={k:c[k] for k in ('id','model','architecture','prompt')}
            summaries.append(dict(context,**flatten({k:c[k] for k in ('primary','technical','resources','valid_only_occurrence','valid_only_presence','count_diagnostic')}),pareto_dominated=c['pareto_dominated']))
            for source,target in [('by_smell',all_smells),('by_file',all_files),('by_project',all_projects),('cells',all_cells)]:
                target.extend(dict(context,**flatten(r)) for r in c[source])
            for d in c['occurrence_details']:stream.write(json.dumps(dict(context,**d),ensure_ascii=False)+'\n')
            for a in c['attempts']:
                row={k:v for k,v in a.items() if k not in ('raw_response_text','normalized_response_text')}
                row=dict(context,**flatten(row));all_attempts.append(row)
                if a.get('error') or a.get('interrupted'):failures.append(row)
            for agent in sorted({a.get('agent','unknown') for a in c['attempts']}):
                subset=[a for a in c['attempts'] if a.get('agent','unknown')==agent]
                complete=all(a.get('cost_usd') is not None for a in subset)
                agents.append(dict(context,agent=agent,attempts=len(subset),known_cost_usd=sum(a.get('cost_usd') or 0 for a in subset),
                    cost_complete=complete,total_cost_usd=sum(a['cost_usd'] for a in subset) if complete else None,
                    note='Single-agent cost belongs to all_smells; it is not divided among smells.'))
    for filename,rows in [('conditions.csv',summaries),('by_smell.csv',all_smells),('by_file.csv',all_files),
        ('by_project.csv',all_projects),('cells.csv',all_cells),('attempts.csv',all_attempts),
        ('cost_by_agent.csv',agents),('failures.csv',failures),('comparisons.csv',[flatten(p) for p in pairs])]:csv_export(output/filename,rows)
    known=sum(c['resources']['known_cost_usd'] for c in conditions)
    complete=all(c['resources']['cost_complete'] for c in conditions)
    planned=len(conditions)
    if (study/'study.json').exists():
        plan=load(study/'study.json');planned=len(plan['models'])*len(plan['architectures'])*len(plan['prompts'])
    elif (study/'validation_summary.json').exists():planned=load(study/'validation_summary.json').get('planned_combinations',planned)
    complete=complete and len(conditions)==planned
    report=dict(version=VERSION,primary_metric='operational occurrence micro-F1 on frozen selected pairs',
        conditions=len(conditions),planned_conditions=planned,missing_conditions=max(0,planned-len(conditions)),
        cohorts_match=same_cohort,all_tasks_valid=len(conditions)==planned and all(c['technical']['status']=='valid' for c in conditions),
        known_cost_usd=known,total_cost_usd=sum(c['resources']['reported_total_cost_usd'] for c in conditions) if complete else None,
        cost_complete=complete,bootstrap=dict(iterations=iterations,seed=seed,confidence=.95,method='percentile paired cluster bootstrap',
            note='Conditional sensitivity to sampled files/projects; not repeated-LLM variance or a population guarantee for quota sampling.'),
        conditions_summary=summaries,comparisons=pairs,uncertainty=uncertainty,
        unavailable=conditions[0]['unavailable'],
        before_filters={c['id']:{k:v for k,v in c['before_filters'].items() if k!='details'} if c['before_filters'] else None for c in conditions},
        definitions=dict(micro_f1='sum TP/FP/FN before computing F1',macro='Types with support or errors; undefined component is zero in active-type macro.',
            presence='Only technically valid evaluated cells; failures are not counted as TN.',mcnemar='Secondary presence correctness, not an F1 significance test; Holm correction within the comparison family.',
            undefined='null, never a fabricated perfect score.',pareto='Descriptive cost/F1 dominance among technically valid compatible conditions.'))
    inputs=[]
    for run in configs:
        inputs.extend(p for p in run.iterdir() if p.is_file() and p.suffix in ('.csv','.json'))
        for result in result_files(run):
            inputs.extend([result,*result.parent.glob('file_metrics_*.json'),*result.parent.glob('token_usage_*.json')])
            inputs.extend((result.parent/'evidence').rglob('head.json'))
    provenance=dict(version=VERSION,bootstrap=report['bootstrap'],
        sources=[p.name for p in [Path(__file__),BASE/'scripts/study_metrics.py',
            BASE/'scripts/experiment_evaluation.py',BASE/'scripts/evaluate_results.py']],
        inputs=[str(p) for p in sorted(set(inputs))])
    save(output/'analysis_provenance.json',provenance)
    save(output/'summary.json',report)
    save(output/'uncertainty.json',dict(parameters=report['bootstrap'],conditions=uncertainty,comparisons=pairs))
    title='Resultados do experimento — analise offline'
    columns=['model','architecture','prompt','primary.precision','primary.recall','primary.f1','primary.macro_f1',
             'technical.valid_response_rate','resources.reported_total_cost_usd','resources.cost_complete']
    labels=['LLM','Arquitetura','Prompt','Precisao','Recall','F1','Macro-F1','Validade tecnica','Custo USD','Custo completo']
    def display(value,key):
        if value is None:return 'nao informado'
        if isinstance(value,bool):return 'sim' if value else 'nao'
        if isinstance(value,float):return f'{value:.2%}' if key.startswith('primary.') or key.endswith('rate') else f'{value:.8f}'
        return str(value)
    table='<table><thead><tr>'+''.join(f'<th>{html.escape(k)}</th>' for k in labels)+'</tr></thead><tbody>'
    for row in summaries:table+='<tr>'+''.join('<td>'+html.escape(display(row.get(k),k))+'</td>' for k in columns)+'</tr>'
    table+='</tbody></table>'
    paired='<table><tr><th>A</th><th>B</th><th>Diferenca F1 (p.p.)</th><th>IC95 pareado (p.p.)</th><th>Celulas validas comuns</th></tr>'
    for pair in pairs:
        ci=pair.get('paired_f1_interval',{});delta=pair.get('f1_difference')
        bounds=f"[{100*ci['low']:.2f}, {100*ci['high']:.2f}]" if ci.get('low') is not None else 'indisponivel'
        values=[pair['a'],pair['b'],f'{100*delta:.2f}' if delta is not None else 'indisponivel',bounds,str(pair.get('common_valid_cells',''))]
        paired+='<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+'</tr>'
    paired+='</table>'
    links=''.join(f'<li><a href="{p.name}">{p.name}</a></li>' for p in sorted(output.glob('*')) if p.suffix in ('.csv','.json','.jsonl'))
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>'+title+'</title>'
        '<style>body{font:15px system-ui;margin:32px;max-width:1500px}table{border-collapse:collapse;font-size:13px}td,th{padding:8px;border:1px solid #ccd}th{background:#eef}td{font-variant-numeric:tabular-nums}</style>'
        '<h1>'+title+'</h1><p>F1 operacional por ocorrencia nos pares selecionados. Analises por presenca, contagem, custo e bootstrap sao complementares. '
        'Intervalos nao medem variacao de novas chamadas da LLM. Falhas e custos ausentes permanecem explicitos.</p>'
        f'<p>Condicoes observadas: {len(conditions)}/{planned}. Todas as tarefas validas: {report["all_tasks_valid"]}.</p>'
        +table+'<h2>Comparacoes pareadas exploratorias</h2>'+paired+'<h2>Dados e verificacoes</h2><ul>'+links+'</ul>',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--dataset',type=Path,help='dataset local; substitui caminhos historicos sem editar os resultados')
    parser.add_argument('--bootstrap',type=int,default=10000)
    parser.add_argument('--seed',type=int,default=20261106)
    args=parser.parse_args()
    if args.bootstrap<2:parser.error('--bootstrap deve ser >=2')
    result=analyze(args.study,args.output,args.bootstrap,args.seed,dataset=args.dataset)
    print(json.dumps({k:result[k] for k in ('conditions','all_tasks_valid','known_cost_usd','total_cost_usd','cost_complete')},indent=2))
