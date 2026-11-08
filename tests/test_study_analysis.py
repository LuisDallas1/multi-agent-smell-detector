"""Metricas conhecidas, pareamento, layout novo e bloqueios do congelamento."""
import asyncio
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'scripts'))
import run_experiment as runner
import frozen_study
import run_study
from analyze_study import analyze, valid_cell
from study_metrics import occurrence,presence,paired_bootstrap,bootstrap_difference,mcnemar,holm
from generation_protocol import validate_controlled_limits
from test_resume import setup,factory,resumed,run


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


def fixture(root):
    data=root/'data';data.mkdir()
    (data/'a.py').write_text('def f():\n    return 7\n',encoding='utf-8')
    (data/'b.py').write_text('def g():\n    pass\n',encoding='utf-8')
    files=[dict(File=f,sha256=hashlib.sha256((data/f).read_bytes()).hexdigest()) for f in ('a.py','b.py')]
    study=root/'study';run=study/'mock/single'
    write(run/'config.json',dict(architecture='single',parameters={},models={'mock':'mock'}))
    write(run/'sample.json',dict(dataset=str(data),files=files))
    for name,rows in [('evaluation_pairs.csv',[dict(File='a.py',Smell='Magic number',Count=1),dict(File='b.py',Smell='Magic number',Count=0)]),
        ('evaluation_reference.csv',[dict(File='a.py',Smell='Magic number',**{'Line no':'2'},Description='Magic number 7.',Method='f')])]:
        with (run/name).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for kind,prompt in [('simple','simple'),('complete_v2','complete')]:
        folder=run/kind
        prediction=[dict(File='a.py',Smell='Magic number',**{'Line no':'2'},number=7,Description='Magic number 7.')] if kind=='simple' else []
        write(folder/f'results_{prompt}_prompts.json',prediction)
        metrics=[]
        for rel in ('a.py','b.py'):
            error='InvalidJSON' if kind=='simple' and rel=='b.py' else None
            attempt=dict(error=error,cost_usd=None if error else .001,token_usage={'prompt_tokens':10,'completion_tokens':5})
            metrics.append(dict(file=rel,elapsed_seconds=1,agent_errors={'all_smells':error} if error else {},
                agent_metrics={'all_smells':dict(error=error,attempts=[attempt])}))
        write(folder/f'file_metrics_{prompt}_prompts.json',metrics)
        write(folder/f'token_usage_{prompt}_prompts.json',dict(model='mock',prompt_type=prompt,
            status='incomplete' if kind=='simple' else 'valid',expected_tasks=2,valid_tasks=1 if kind=='simple' else 2,
            attempted_calls=2,failed_attempts=1 if kind=='simple' else 0,known_cost_usd=.001 if kind=='simple' else .002,
            cost_complete=kind!='simple',total_cost_usd=None if kind=='simple' else .002,token_usage={}))
    return study


class StudyAnalysisTests(unittest.TestCase):
    def test_occurrence_and_presence_known_values(self):
        result=occurrence(8,2,2)
        self.assertEqual(result['f1'],.8);self.assertEqual(result['precision'],.8)
        self.assertAlmostEqual(result['jaccard'],2/3)
        self.assertIsNone(occurrence(0,0,0)['f1'])
        binary=presence(2,0,0,2)
        self.assertEqual(binary['mcc'],1);self.assertEqual(binary['kappa'],1)
        self.assertIsNone(presence(0,0,0,0)['accuracy'])

    def test_paired_bootstrap_identical_conditions_have_exact_zero_difference(self):
        values={'a':{'x':(1,0,0),'y':(0,1,1)},'b':{'x':(1,0,0),'y':(0,1,1)}}
        a=paired_bootstrap(values,['x','y'],64,42)
        self.assertEqual(a,paired_bootstrap(values,['x','y'],64,42))
        difference=bootstrap_difference(a['a']['f1'],a['b']['f1'])
        self.assertEqual((difference['low'],difference['high']),(0,0))
        self.assertEqual(difference['win_score_with_half_ties'],.5)

    def test_secondary_mcnemar_and_holm(self):
        self.assertEqual(mcnemar(0,0),1)
        self.assertAlmostEqual(mcnemar(5,0),.0625)
        self.assertEqual(holm({'a':.01,'b':.04,'c':.03}),{'a':.03,'c':.06,'b':.06})

    def test_failed_negative_is_not_a_valid_tn(self):
        self.assertFalse(valid_cell(dict(agent_errors={'all_smells':'InvalidJSON'}),'magic number','single'))

    def test_offline_reports_keep_unknown_cost_and_exclude_failed_negative_from_presence(self):
        with tempfile.TemporaryDirectory() as temporary:
            study=fixture(Path(temporary));report=analyze(study,iterations=64)
            self.assertEqual(report['conditions'],2)
            self.assertFalse(report['all_tasks_valid']);self.assertIsNone(report['total_cost_usd'])
            self.assertAlmostEqual(report['known_cost_usd'],.003)
            simple=next(c for c in report['conditions_summary'] if c['prompt']=='simple_v2')
            self.assertEqual(simple['primary.f1'],1)
            self.assertEqual(simple['technical.valid_evaluated_pairs'],1)
            self.assertEqual(report['comparisons'][0]['common_valid_cells'],1)
            self.assertEqual(report['comparisons'][0]['excluded_cells'],1)
            self.assertTrue((study/'analysis/report.html').is_file())
            self.assertTrue((study/'analysis/attempts.csv').is_file())
            self.assertEqual(report['unavailable']['llm_run_variance'],'One generation per condition does not estimate repeated-call variance.')

    def test_analysis_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);study=fixture(root)
            (root/'data/a.py').write_text('changed',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Arquivo mudou'):analyze(study,iterations=16)

    def test_flat_layout_runs_and_resumes_without_duplicate_model_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            args,files,output=setup(temporary,'single');args.output_layout='flat'
            run(args,files,output,factory([]))
            self.assertTrue((output/'complete_v2/checkpoints').is_dir())
            self.assertFalse((output/'01_mock').exists())
            calls=[];run(*resumed(output),output,factory(calls))
            self.assertEqual(calls,[])

    def test_study_commands_keep_profile_and_flat_paths(self):
        for arch,budget in [('multiagent',8192),('single',32768)]:
            cmd=run_study.command('gpt-6-luna',arch,Path('results/study/gpt/'+arch),Path('files.json'),None)
            args=runner.parser().parse_args(cmd[4:]);validate_controlled_limits(args)
            self.assertEqual(args.output_layout,'flat');self.assertEqual(args.max_tokens,budget)
            self.assertEqual(args.prompt_type,'paired')

    def test_freeze_rejects_tampering_before_runtime_or_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'freeze.json';write(path,dict(freeze_id='bad',version='changed'))
            with patch.object(frozen_study.runner,'runtime_versions',side_effect=AssertionError('must not load')):
                with self.assertRaisesRegex(ValueError,'Manifesto'):frozen_study.verify(path)

    def test_freeze_rejects_changed_code_before_runtime_or_data_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'freeze.json'
            payload=dict(core_source_sha256={'script':'old'},prompt_source_sha256={})
            payload['freeze_id']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
            write(path,payload)
            with patch.object(frozen_study.runner,'source_snapshots',return_value=dict(core_source_sha256={'script':'new'},prompt_source_sha256={})), patch.object(frozen_study.runner,'runtime_versions',side_effect=AssertionError('must not load')):
                with self.assertRaisesRegex(ValueError,'Codigo'):frozen_study.verify(path)


if __name__=='__main__':unittest.main()
