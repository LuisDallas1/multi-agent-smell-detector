"""Uma tarefa por arquivo para os 11 smells; execução e custos compartilhados."""
from core.execution.engine import DetectionEngine
from core.supervisor.agent_config import AGENTS
from .prompts import build_prompt, SYSTEM_PROMPT
from .schema import AllSmellsResponse


class SingleAgentDetector(DetectionEngine):
    def _get_agent_configs(self, prompt_type):
        return {"all_smells": {"prompt": build_prompt(prompt_type),
                               "schema": AllSmellsResponse,
                               "system_prompt": SYSTEM_PROMPT}}

    def _response_envelopes(self, payload):
        if not isinstance(payload, dict) or set(payload) != set(AGENTS):
            return [None]  # Rejeitado pela validação comum, com retry limitado.
        return [payload[name] for name in AGENTS]

    def _extract_detections(self, response):
        return [item for name in AGENTS for item in getattr(response, name).detections]
