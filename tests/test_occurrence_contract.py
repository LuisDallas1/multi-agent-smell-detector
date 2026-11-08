"""Regressões da resposta por ocorrência, sem medidas exatas ou chamadas pagas."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
sys.path.insert(0, str(BASE / 'scripts'))
from core.schemas.agent_response import LEGACY_OUTPUT_FIELDS
from core.supervisor.agent_config import get_agent_configs
from core.single_agent.schema import AllSmellsResponse
from core.execution.engine import DetectionEngine
from core.single_agent.prompts import build_prompt
from core.smell_rules import THRESHOLDS
from experiment_evaluation import Reference
from test_single_agent import detector, empty


def occurrence(config):
    cls = config['schema'].model_fields['detections'].annotation.__args__[0]
    item = dict(detected=True, Smell=cls.model_fields['Smell'].default,
                Method='f', Line_no='2', Description='Evidência no trecho indicado.')
    if item['Smell'] == 'Long identifier': item['identifier_name'] = 'some_identifier'
    if item['Smell'] == 'Magic number': item['number'] = 0
    return item


class OccurrenceContractTests(unittest.TestCase):
    def test_all_smells_work_in_both_architectures_without_exact_measures(self):
        payload = empty()
        for name, config in get_agent_configs('complete_v2').items():
            group = dict(detected=True, detections=[occurrence(config)])
            config['schema'].model_validate(group)
            payload[name] = group
        AllSmellsResponse.model_validate(payload)
        agent = detector([payload], retries=0)
        result = asyncio.run(agent.analyze_code('def f():\n    pass\n', 'file.py', 'project'))
        self.assertEqual(result['agent_errors'], {})
        self.assertEqual(len(result['code_smells']), 11)
        for item in result['code_smells']:
            self.assertFalse(LEGACY_OUTPUT_FIELDS.intersection(item))

    def test_legacy_measures_cannot_change_acceptance_and_original_data_survives(self):
        payload = empty()
        for name, config in get_agent_configs('simple_v2').items():
            item = occurrence(config)
            # Even malformed unrequested measures must not invalidate identity.
            item.update({key:'unknown' for key in LEGACY_OUTPUT_FIELDS})
            payload[name] = dict(detected=True, detections=[item])
        original = copy.deepcopy(payload)
        AllSmellsResponse.model_validate(payload)
        self.assertEqual(payload, original)
        agent = detector([payload], retries=0)
        result = asyncio.run(agent.analyze_code('def f():\n    pass\n', 'file.py', 'project'))
        self.assertEqual(result['agent_errors'], {})
        self.assertEqual(len(result['code_smells']), 11)
        raw = result['agent_metrics']['all_smells']['attempts'][0]['raw_response_text']
        self.assertEqual(json.loads(raw), original)

    def test_regular_and_strict_inference_schemas_do_not_request_legacy_fields(self):
        models = [AllSmellsResponse] + [c['schema'] for c in get_agent_configs('simple_v2').values()]
        for model in models:
            for schema in [model.model_json_schema(by_alias=False), DetectionEngine._strict_response_schema(model)['schema']]:
                for definition in schema.get('$defs', {}).values():
                    props = definition.get('properties', {})
                    if 'Smell' not in props: continue
                    self.assertFalse(LEGACY_OUTPUT_FIELDS.intersection(props))
                    self.assertTrue({'detected','Smell','Method','Line_no','Description'} <= set(definition['required']))

    def test_wrong_numeric_classification_is_false_positive_instead_of_disappearing(self):
        payload = empty()
        payload['magic_number'] = dict(detected=True,detections=[occurrence(get_agent_configs('simple_v2')['magic_number'])])
        agent = detector([payload], retries=0)
        result = asyncio.run(agent.analyze_code('def f():\n    x = 0\n','file.py','project'))
        self.assertEqual(len(result['code_smells']),1)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'file.py').write_text('def f():\n    x = 0\n',encoding='utf-8')
            truth=root/'truth.csv';truth.write_text('File,Smell,Method,Line no,Description\n',encoding='utf-8')
            prediction=dict(result['code_smells'][0],rel='file.py',smell_key='magic number',Line_no='2')
            score=Reference(root,truth).evaluate([prediction],{'file.py':{'magic number':0}})
            self.assertEqual((score['tp'],score['fp'],score['fn']),(0,1,0))

    def test_start_line_does_not_replace_missing_occurrence_location(self):
        config=get_agent_configs('simple_v2')['long_method']
        item=occurrence(config);item.pop('Line_no');item['start_line']=2
        with self.assertRaises(ValueError):
            config['schema'].model_validate(dict(detected=True,detections=[item]))

    def test_prompts_preserve_rules_but_never_request_measure_fields(self):
        for strategy in ['simple_v2','complete_v2']:
            prompt=build_prompt(strategy)
            for field in LEGACY_OUTPUT_FIELDS-{'threshold','start_line','end_line'}:
                self.assertNotIn(field,prompt)
            for config in get_agent_configs(strategy).values():
                self.assertIn(config['prompt'],prompt)
        self.assertEqual(THRESHOLDS, {'complex method':7,'complex conditional':2,'long method':67,
            'long parameter list':4,'long statement':80,'long identifier':20,
            'long lambda function':80,'long message chain':2})
