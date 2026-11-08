"""Contrato agrupado e execução real do motor com LLM simulada, sem credenciais."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))
sys.path.insert(0, str(BASE / "scripts"))
from core.single_agent import SingleAgentDetector
from core.single_agent.schema import AllSmellsResponse
from core.single_agent.prompts import build_prompt
from core.supervisor import CodeSmellSupervisor
from core.supervisor.agent_config import AGENTS, get_agent_configs
from core.execution.engine import DetectionEngine
from core.execution.contract import SYSTEM_PREFIX
from core.prompt_strategies import SINGLE_PROMPT_SOURCES, resolve_prompt_types
import run_experiment


def empty():
    return {name: {"detected": False, "detections": []} for name in AGENTS}


def positive():
    payload = empty()
    payload["long_statement"] = dict(detected=True, detections=[dict(
        detected=True, Smell="Long statement", Method="f", Description="Instrução longa.",
        Line_no="2", line_length=90, threshold=80)])
    return payload


class FakeModel:
    def __init__(self, responses):
        self.responses = responses
        self.messages = []

    def model_copy(self, update):
        return self

    def with_structured_output(self, schema, method, include_raw):
        assert schema is AllSmellsResponse and method == "json_mode" and include_raw
        return self

    async def ainvoke(self, messages, config):
        self.messages.append(messages)
        await config["callbacks"][0].on_llm_end(SimpleNamespace(llm_output={
            "token_usage": dict(prompt_tokens=10, completion_tokens=20, total_tokens=30, cost=0.001)}))
        return dict(raw=SimpleNamespace(content=json.dumps(self.responses.pop(0)),
                                       response_metadata={"finish_reason": "stop"}, usage_metadata={}),
                    parsed=None, parsing_error=None)


def detector(responses, retries=1):
    instance = SingleAgentDetector.__new__(SingleAgentDetector)
    instance.model = FakeModel(responses)
    instance.parallel = True
    instance.response_format = "json_mode"
    instance.json_normalization = "markdown_fence"
    instance.initial_max_tokens = 8192
    instance.max_retry_tokens = 16384
    instance.response_retries = retries
    instance._agent_semaphore = asyncio.Semaphore(2)
    instance.agent_configs = instance._get_agent_configs("complete_v2")
    return instance


class SingleAgentTests(unittest.TestCase):
    def test_all_eleven_groups_required_and_no_extra_group(self):
        self.assertEqual(set(AllSmellsResponse.model_fields), set(AGENTS))
        AllSmellsResponse.model_validate(empty())
        missing = empty()
        del missing["magic_number"]
        with self.assertRaises(ValueError):
            AllSmellsResponse.model_validate(missing)
        extra = empty()
        extra["invented_smell"] = {"detected": False, "detections": []}
        with self.assertRaises(ValueError):
            AllSmellsResponse.model_validate(extra)

    def test_inconsistent_group_or_wrong_smell_rejected(self):
        wrong = positive()
        wrong["long_statement"]["detected"] = False
        with self.assertRaises(ValueError):
            AllSmellsResponse.model_validate(wrong)
        wrong = positive()
        wrong["long_statement"]["detections"][0]["Smell"] = "Magic number"
        with self.assertRaises(ValueError):
            AllSmellsResponse.model_validate(wrong)

    def test_single_call_covers_all_smells_and_flattens_predictions(self):
        agent = detector([positive()])
        result = asyncio.run(agent.analyze_code("def f():\n    pass\n", "file.py", "project"))
        self.assertEqual(result["agents_executed"], 1)
        self.assertEqual(result["agent_errors"], {})
        self.assertEqual(len(agent.model.messages), 1)
        self.assertEqual(len(result["code_smells"]), 1)
        self.assertEqual(result["code_smells"][0]["Smell"], "Long statement")
        self.assertEqual(result["code_smells"][0]["Line no"], "2")
        self.assertIn("all eleven required groups", agent.model.messages[0][0]["content"])
        self.assertEqual(result["token_usage"]["total_tokens"], 30)

    def test_all_groups_and_legacy_measure_evidence_survive_without_semantic_filter(self):
        payload = empty()
        for name, config in get_agent_configs('complete_v2').items():
            schema = config['schema'].model_fields['detections'].annotation.__args__[0]
            smell = schema.model_fields['Smell'].default
            payload[name] = dict(detected=True, detections=[dict(
                Smell=smell, Method='f', detected=True, Line_no='2', Description='Audit occurrence.')])
        from core.schemas.agent_response import MEASURE_FIELDS
        from core.smell_rules import THRESHOLDS
        for name, group in payload.items():
            item = group['detections'][0]
            smell = item['Smell'].lower()
            if smell in MEASURE_FIELDS:
                item.update({MEASURE_FIELDS[smell]: THRESHOLDS[smell] + 1, 'threshold': THRESHOLDS[smell]})
            if name == 'long_identifier': item['identifier_name'] = 'a_very_long_identifier_name'
            if name == 'magic_number': item['number'] = 7
            if name in {'long_method','complex_method'}: item.update(start_line=2,end_line=71)
        # A wrong self-reported measure must not erase the predicted occurrence.
        payload['long_lambda_function']['detections'][0]['lambda_length'] = 80
        agent = detector([payload], retries=0)
        result = asyncio.run(agent.analyze_code('def f():\n    pass\n', 'file.py', 'project'))
        metric = result['agent_metrics']['all_smells']
        self.assertEqual(metric['detections_before_metadata'], 11)
        self.assertEqual(len(result['code_smells']), 11)
        original = json.loads(metric['attempts'][0]['raw_response_text'])
        self.assertEqual(original, payload)
        self.assertEqual(set(original), set(AGENTS))
        self.assertEqual(original['long_lambda_function']['detections'][0]['lambda_length'], 80)

    def test_missing_group_retries_entire_response_without_partial_results(self):
        missing = positive()
        del missing["magic_number"]
        agent = detector([missing, empty()])
        result = asyncio.run(agent.analyze_code("pass\n", "file.py", "project"))
        self.assertEqual(result["code_smells"], [])
        metrics = result["agent_metrics"]["all_smells"]
        self.assertTrue(metrics["recovered"])
        self.assertEqual(len(metrics["attempts"]), 2)
        self.assertEqual(metrics["attempts"][0]["error"], "InvalidStructuredResponse")
        self.assertEqual(result["token_usage"]["total_tokens"], 60)
        self.assertEqual(agent.model.messages[0], agent.model.messages[1])

    def test_invalid_location_in_one_group_rejects_whole_response(self):
        invalid = positive()
        invalid["long_statement"]["detections"][0]["Line_no"] = "unknown"
        agent = detector([invalid], retries=0)
        result = asyncio.run(agent.analyze_code("pass\n", "file.py", "project"))
        self.assertEqual(result["code_smells"], [])
        self.assertEqual(result["agent_errors"], {"all_smells": "InvalidStructuredResponse"})

    def test_prompts_preserve_corresponding_rules_and_examples(self):
        for kind, source in SINGLE_PROMPT_SOURCES.items():
            prompt = build_prompt(kind)
            for name, config in get_agent_configs(source).items():
                self.assertIn(f"## GRUPO {name}", prompt)
                self.assertIn(config["prompt"], prompt)
            self.assertEqual(prompt, build_prompt(kind))
            self.assertIn("CONTRATO FINAL OBRIGATÓRIO", prompt)

    def test_separate_architectures_share_engine_but_not_tasks(self):
        self.assertIs(CodeSmellSupervisor.__bases__[0], DetectionEngine)
        self.assertIs(SingleAgentDetector.__bases__[0], DetectionEngine)
        multi = CodeSmellSupervisor.__new__(CodeSmellSupervisor)
        self.assertEqual(len(multi._get_agent_configs("complete_v2")), 11)
        single = SingleAgentDetector.__new__(SingleAgentDetector)
        self.assertEqual(set(single._get_agent_configs("complete_v2")), {"all_smells"})
        self.assertEqual(run_experiment.parser().parse_args([]).architecture, "multiagent")
        self.assertEqual(run_experiment.parser().parse_args(["--architecture", "single"]).architecture, "single")

    def test_exactly_two_paired_strategies_and_no_original_complete_for_single(self):
        self.assertEqual(resolve_prompt_types("single", "all"), ["simple_v2", "complete_v2"])
        self.assertEqual(resolve_prompt_types("single", "paired"), ["simple_v2", "complete_v2"])
        self.assertEqual(resolve_prompt_types("multiagent", "paired"), ["simple_v2", "complete_v2"])
        for name, source in SINGLE_PROMPT_SOURCES.items():
            self.assertEqual(resolve_prompt_types("single", source), [name])
            self.assertEqual(resolve_prompt_types("multiagent", name), [source])
            self.assertEqual(build_prompt(name), build_prompt(source))
        with self.assertRaises(ValueError):
            build_prompt("complete_estevam")

    def test_generation_retry_filter_and_metadata_are_the_same_methods(self):
        for method in ("__init__", "analyze_code", "_call_agent", "_call_agent_inner",
                       "_add_metadata", "_format_code_with_line_numbers", "_build_agent_message",
                       "_strict_response_schema", "_unwrap_markdown_fence", "_validate_code_size"):
            self.assertIs(getattr(SingleAgentDetector, method), getattr(CodeSmellSupervisor, method), method)
        single = detector([empty()])
        self.assertTrue(single.agent_configs["all_smells"]["system_prompt"].startswith(SYSTEM_PREFIX))
        self.assertTrue(CodeSmellSupervisor._system_message().startswith(SYSTEM_PREFIX))

    def test_each_group_uses_exact_specialist_schema_and_same_rejections(self):
        for name, config in get_agent_configs("complete_v2").items():
            schema = config["schema"]
            self.assertIs(AllSmellsResponse.model_fields[name].annotation, schema)
            expected = schema.model_fields["detections"].annotation.__args__[0].model_fields["Smell"].default
            valid = {"detected": True, "detections": [{"detected": True, "Smell": expected,
                     "Line_no": "1", "Description": "Ocorrência de controle."}]}
            cases = [valid, {"detected": False, "detections": []},
                     {"detected": False, "detections": valid["detections"]},
                     {"detected": True, "detections": [dict(valid["detections"][0], Smell="Invented smell")]},
                     {"detected": True, "detections": [dict(valid["detections"][0], detected=False)]},
                     {"detected": False, "detections": [], "unexpected_field": 1}]
            for local in cases:
                grouped = empty()
                grouped[name] = local
                accepted = []
                for model, payload in ((schema, local), (AllSmellsResponse, grouped)):
                    try:
                        model.model_validate(payload)
                        accepted.append(True)
                    except ValueError:
                        accepted.append(False)
                self.assertEqual(accepted[0], accepted[1], (name, local))

    def test_same_prediction_gets_same_filter_and_file_metadata(self):
        response = AllSmellsResponse.model_validate(positive())
        single = SingleAgentDetector.__new__(SingleAgentDetector)
        multi = CodeSmellSupervisor.__new__(CodeSmellSupervisor)
        a = single._add_metadata(single._extract_detections(response), "def f():\n    pass\n", "file.py", "project")
        b = multi._add_metadata(multi._extract_detections(response.long_statement), "def f():\n    pass\n", "file.py", "project")
        self.assertEqual([x.model_dump() for x in a], [x.model_dump() for x in b])

    def test_strict_schema_keeps_all_groups_required(self):
        schema = DetectionEngine._strict_response_schema(AllSmellsResponse)["schema"]
        self.assertEqual(set(schema["required"]), set(AGENTS))
        self.assertFalse(schema["additionalProperties"])
        for definition in schema["$defs"].values():
            if "Method" in definition.get("properties", {}):
                self.assertNotIn("File", definition["properties"])

    def test_runner_counts_one_task_and_saves_single_architecture(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "dataset"
            dataset.mkdir()
            (dataset / "file.py").write_text("pass\n", encoding="utf-8")
            args = run_experiment.parser().parse_args([
                "--architecture", "single", "--dataset", str(dataset),
                "--generation-profile", "normalized", "--response-format", "json_mode",
                "--json-normalization", "markdown_fence"])
            files = run_experiment.select_files(args)
            output = Path(temporary) / "run"
            summary = asyncio.run(run_experiment.execute(
                args, files, ["gpt-6-luna"], ["complete_v2"], output,
                factory=lambda **kwargs: detector([empty()])))
            self.assertEqual(summary[0]["expected_tasks"], 1)
            self.assertEqual(summary[0]["valid_tasks"], 1)
            self.assertEqual(summary[0]["architecture"], "single")
            self.assertTrue(summary[0]["cost_complete"])
            self.assertAlmostEqual(summary[0]["total_cost_usd"], 0.001)
            self.assertEqual(json.loads((output / "protocol.json").read_text())["architecture"], "single")
            prompt_path = output / "01_gpt-6-luna/complete_v2/prompt_all_smells.txt"
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), build_prompt("complete_v2"))

    def test_single_failure_marks_all_selected_pairs_including_negatives(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "dataset"
            dataset.mkdir()
            (dataset / "file.py").write_text("pass\n", encoding="utf-8")
            truth = Path(temporary) / "truth.csv"
            truth.write_text("File,Smell,Line no,Description\nfile.py,Magic number,1,Magic number 7 used here.\n", encoding="utf-8")
            pairs = Path(temporary) / "pairs.csv"
            pairs.write_text("File,Smell,Count\nfile.py,Magic number,1\nfile.py,Long statement,0\n", encoding="utf-8")
            args = run_experiment.parser().parse_args([
                "--architecture", "single", "--dataset", str(dataset), "--allow-incomplete"])
            args.evaluate = True
            args.evaluation_pairs = pairs
            args.ground_truth = truth
            files = run_experiment.select_files(args)
            output = Path(temporary) / "run"
            invalid = empty()
            del invalid["magic_number"]
            asyncio.run(run_experiment.execute(
                args, files, ["gpt-6-luna"], ["complete_v2"], output,
                factory=lambda **kwargs: detector([invalid], retries=0)))
            result = json.loads((output / "01_gpt-6-luna/complete_v2/evaluation.json").read_text())
            self.assertEqual(result["technical_status"], "incomplete")
            self.assertEqual(result["architecture"], "single")
            self.assertEqual(len(result["failed_evaluated_pairs"]), 2)
            self.assertTrue(all(x["error"] == "InvalidStructuredResponse"
                                for x in result["failed_evaluated_pairs"]))


if __name__ == "__main__":
    unittest.main()
