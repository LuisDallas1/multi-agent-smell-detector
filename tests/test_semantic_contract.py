"""Regressões de contrato semântico, usando falhas reais como casos mínimos."""
import asyncio,copy,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from core.schemas.agent_response import MultipleMagicNumberResponse,MultipleLongIdentifierResponse,MultipleLongStatementResponse,MultipleLongLambdaResponse
from core.single_agent.schema import AllSmellsResponse
from test_single_agent import detector,empty
import test_response_validity as rv


def magic():
    return dict(detected=True,Smell='Magic number',Method='f',Line_no='2',Description='Literal 7 em cálculo.',number=7)


class SemanticContractTests(unittest.TestCase):
    def test_missing_identity_is_invalid_in_both_architectures(self):
        for schema,group,item in [(MultipleMagicNumberResponse,'magic_number',magic()),
            (MultipleLongIdentifierResponse,'long_identifier',dict(detected=True,Smell='Long identifier',Method='f',Line_no='2',Description='Nome longo.',identifier_name='very_long_identifier_name',length=25,threshold=20))]:
            field='number' if group=='magic_number' else 'identifier_name'
            item.pop(field)
            payload=dict(detected=True,detections=[item])
            with self.assertRaisesRegex(ValueError,field):schema.model_validate(payload)
            grouped=empty();grouped[group]=payload
            with self.assertRaisesRegex(ValueError,field):AllSmellsResponse.model_validate(grouped)

    def test_numbers_are_typed_not_parsed_from_description(self):
        for invalid in [None,True,'7',float('inf')]:
            with self.subTest(value=invalid),self.assertRaises(ValueError):
                MultipleMagicNumberResponse.model_validate(dict(detected=True,detections=[dict(magic(),number=invalid)]))
        self.assertEqual(MultipleMagicNumberResponse.model_validate(dict(detected=True,detections=[magic()])).detections[0].number,7)

    def test_measure_and_threshold_are_not_required_and_do_not_gate_predictions(self):
        item=dict(detected=True,Smell='Long lambda function',Method='f',Line_no='2',Description='Lambda longa.',lambda_length=90,threshold=80)
        for key in ['lambda_length','threshold']:
            broken=dict(item);broken.pop(key)
            MultipleLongLambdaResponse.model_validate(dict(detected=True,detections=[broken]))
        MultipleLongLambdaResponse.model_validate(dict(detected=True,detections=[dict(item,threshold=120)]))

    def test_long_statement_identity_without_measure_works_in_both_architectures(self):
        from core.utils.detection_validator import DetectionValidator
        item=dict(detected=True,Smell='Long statement',Method='f',Line_no='2',Description='Atribuição multilinha extensa.')
        payload=dict(detected=True,detections=[item])
        parsed=MultipleLongStatementResponse.model_validate(payload)
        grouped=empty();grouped['long_statement']=payload
        self.assertTrue(AllSmellsResponse.model_validate(grouped).long_statement.detected)
        self.assertTrue(DetectionValidator.validate_detection(parsed.detections[0].model_dump()))
        for field in ['Method','Line_no','Description','detected','Smell']:
            broken=dict(item);broken.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):
                MultipleLongStatementResponse.model_validate(dict(detected=True,detections=[broken]))

    def test_legacy_length_does_not_gate_long_statement_predictions(self):
        from core.utils.detection_validator import DetectionValidator
        for length in [None,0,80,81,999999]:
            self.assertTrue(DetectionValidator.validate_detection(dict(
                detected=True, Smell='Long statement',Method='f',Line_no='2',line_length=length,Description='80 characters')))

    def test_inference_schema_does_not_request_long_statement_measure_even_in_strict_mode(self):
        from core.execution.engine import DetectionEngine
        for schema in [MultipleLongStatementResponse,AllSmellsResponse]:
            for definition in [schema.model_json_schema(by_alias=False),DetectionEngine._strict_response_schema(schema)['schema']]:
                item=definition['$defs']['LongStatementDetection']
                self.assertNotIn('line_length',item['properties'])
                self.assertNotIn('threshold',item['properties'])
                self.assertEqual(item['properties']['Smell']['const'],'Long statement')
                self.assertIn('Line_no',item['required'])

    def test_long_statement_without_measure_still_counts_as_fp_in_negative_cell(self):
        import tempfile
        from experiment_evaluation import Reference
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'f.py').write_text('def f():\n    pass\n',encoding='utf-8')
            truth=root/'truth.csv';truth.write_text('File,Smell,Line no,Description\n',encoding='utf-8')
            result=Reference(root,truth).evaluate([dict(rel='f.py',smell_key='long statement',Line_no='2')],{'f.py':{'long statement':0}})
            self.assertEqual((result['tp'],result['fp'],result['fn']),(0,1,0))

    def test_shared_field_summary_has_real_smell_labels_and_location_only_contract(self):
        from core.supervisor.agent_config import get_agent_configs
        from core.single_agent.prompts import build_prompt
        item=dict(detected=True,Smell='Long statement',Method='f',Line_no='2',Description='Atribuição extensa.')
        grouped=empty();grouped['long_statement']=dict(detected=True,detections=[item])
        agent=detector([grouped],retries=0)
        result=asyncio.run(agent.analyze_code('def f():\n    pass\n','file.py','project'))
        self.assertEqual(result['agent_errors'],{})
        message=agent.model.messages[0][1]['content']
        summary=json.loads(message.split('CAMPOS OBRIGATÓRIOS POR TIPO: ',1)[1].split('\nCONTRATO',1)[0])
        self.assertEqual(len(summary),11)
        self.assertTrue(all(isinstance(row['Smell'],str) and row['Smell'] for row in summary))
        statement=next(row for row in summary if row['Smell']=='Long statement')
        self.assertNotIn('line_length',statement['required'])
        self.assertIn('sem calcular ou devolver comprimento exato',message)
        for strategy in ['simple_v2','complete_v2']:
            self.assertNotIn('line_length',get_agent_configs(strategy)['long_statement']['prompt'])
            self.assertNotIn('line_length',build_prompt(strategy))

    def test_schema_displays_required_fields_and_excludes_null(self):
        for schema,key in [(MultipleMagicNumberResponse,'number'),(AllSmellsResponse,'identifier_name')]:
            definition=schema.model_json_schema(by_alias=False)
            matches=[v for v in definition['$defs'].values() if key in v.get('properties',{})]
            self.assertTrue(matches)
            for item in matches:
                self.assertIn(key,item['required'])
                self.assertNotIn({'type':'null'},item['properties'][key].get('anyOf',[]))

    def test_missing_identity_retries_without_recovering_from_description(self):
        missing=empty();item=magic();item.pop('number');missing['magic_number']=dict(detected=True,detections=[item])
        valid=empty();valid['magic_number']=dict(detected=True,detections=[magic()])
        agent=detector([missing,valid])
        result=asyncio.run(agent.analyze_code('def f():\n    x = 7\n','file.py','project'))
        metrics=result['agent_metrics']['all_smells']
        self.assertTrue(metrics['recovered'])
        self.assertEqual(metrics['attempts'][0]['error'],'InvalidStructuredResponse')
        self.assertEqual(json.loads(metrics['attempts'][0]['raw_response_text']),missing)
        self.assertEqual(len(result['code_smells']),1)

    def test_reasoning_exhaustion_is_recorded_without_salvaging_partial_json(self):
        helper=rv.ResponseValidityTests()
        response=rv.reply(finish='length')
        response['raw'].usage_metadata={'output_token_details':{'reasoning':20}}
        response['raw'].response_metadata['token_usage']={'completion_tokens':20}
        instance=helper.make([response],retries=0)
        # Callback in this fixture reports 20 output tokens.
        helper.call(instance)
        attempt=instance.agent_metrics['long_statement']['attempts'][0]
        self.assertEqual(attempt['error'],'TruncatedResponse')
        self.assertEqual(attempt['truncation_cause'],'reasoning_dominated')
        self.assertEqual(instance.agent_metrics['long_statement']['detections_before_metadata'],0)

    def test_sdk_length_exception_uses_the_same_truncation_diagnostic(self):
        helper=rv.ResponseValidityTests()
        class LengthFinishReasonError(Exception):
            pass
        error=LengthFinishReasonError("length limit was reached")
        error.completion=SimpleNamespace(usage={"prompt_tokens":10,"completion_tokens":100,
            "total_tokens":110,"completion_tokens_details":{"reasoning_tokens":100},"cost":.001})
        instance=helper.make([error],retries=0)
        helper.call(instance)
        attempt=instance.agent_metrics['long_statement']['attempts'][0]
        self.assertEqual(attempt['error'],'TruncatedResponse')
        self.assertEqual(attempt['truncation_cause'],'reasoning_dominated')
        self.assertEqual(attempt['reasoning_fraction'],1)
        self.assertEqual(instance.agent_metrics['long_statement']['token_usage']['completion_tokens'],100)
        self.assertEqual(attempt['cost_usd'],.001)

    def test_real_sdk_length_error_preserves_usage_and_reasoning_classification(self):
        import httpx
        from langchain_openai import ChatOpenAI
        async def run():
            async def handle(request):
                return httpx.Response(200,json={"id":"offline-length","object":"chat.completion","created":0,"model":"offline",
                    "choices":[{"index":0,"finish_reason":"length","message":{"role":"assistant","content":None}}],
                    "usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30,"cost":.001,
                             "completion_tokens_details":{"reasoning_tokens":20}}})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                agent=detector([],retries=0)
                agent.model=ChatOpenAI(model='offline',api_key='offline-test-only',base_url='https://offline.invalid/v1',
                    http_async_client=client,max_retries=0,max_tokens=8192,temperature=None)
                result=await agent.analyze_code('pass\n','file.py','project')
                attempt=result['agent_metrics']['all_smells']['attempts'][0]
                self.assertEqual(attempt['exception_diagnostic']['exception_type'],'LengthFinishReasonError')
                self.assertEqual(attempt['error'],'TruncatedResponse')
                self.assertEqual(attempt['truncation_cause'],'reasoning_dominated')
                self.assertEqual(attempt['reasoning_fraction'],1)
                self.assertEqual(attempt['cost_usd'],.001)
                self.assertEqual(result['code_smells'],[])
        asyncio.run(run())

    def test_diagnostic_ablation_removes_only_common_text_and_keeps_validation(self):
        messages=[]
        for omit in [False,True]:
            missing=empty();item=magic();item.pop('number')
            missing['magic_number']=dict(detected=True,detections=[item])
            agent=detector([missing],retries=0)
            agent.agent_configs['all_smells']['diagnostic_omit_common_appendix']=omit
            result=asyncio.run(agent.analyze_code('pass\n','file.py','project'))
            self.assertEqual(result['agent_errors']['all_smells'],'InvalidStructuredResponse')
            messages.append(agent.model.messages[0])
        self.assertEqual(messages[0][0],messages[1][0])
        self.assertEqual(messages[0][1]['content'].split('\nCAMPOS OBRIGATÓRIOS POR TIPO:')[0],messages[1][1]['content'])
        self.assertIn('CONTRATO FINAL OBRIGATÓRIO',messages[1][1]['content'])
