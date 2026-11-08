"""Composição determinística; nenhuma chamada LLM nem consulta ao gabarito."""
import json
from core.supervisor.agent_config import get_agent_configs
from core.prompt_strategies import SINGLE_PROMPT_SOURCES, resolve_prompt_types
from core.execution.contract import system_prompt

SYSTEM_PROMPT = system_prompt(
    "Return one object with all eleven required groups. "
    "Each group contains detected (boolean) and detections (array). "
    "An empty group must contain detected=false and detections=[]. "
    "Do not return a top-level detected/detections envelope."
)


def build_prompt(prompt_type):
    strategy = resolve_prompt_types("single", prompt_type)
    if len(strategy) != 1:
        raise ValueError("Selecione uma estratégia por chamada")
    configs = get_agent_configs(SINGLE_PROMPT_SOURCES[strategy[0]])
    contract = json.dumps({name: {"detected": False, "detections": []}
                           for name in configs}, ensure_ascii=False, indent=2)
    sections = [
        "Você é um único agente responsável pelos 11 implementation smells no arquivo inteiro.",
        "Analise todos os tipos sem consultar gabarito ou selecionar apenas alguns deles. "
        "As seções abaixo preservam definições, critérios e exemplos da estratégia escolhida. "
        "Cada seção descreve o contrato LOCAL daquele grupo, não o objeto JSON final. "
        "Exemplos detected/detections pertencem somente ao grupo correspondente. "
        "Nenhum exemplo autoriza omitir os demais grupos na resposta final.",
    ]
    for name, config in configs.items():
        sections.append(f"## GRUPO {name}\n{config['prompt']}")
    sections.append(
        "## CONTRATO FINAL OBRIGATÓRIO\n"
        "Retorne somente um objeto JSON com exatamente as 11 chaves abaixo. "
        "O objeto abaixo ilustra todos os grupos vazios; preencha os grupos que tiverem ocorrências. "
        "Em cada grupo, detected deve corresponder à existência de itens em detections. "
        "Não use detected/detections na raiz. Não invente ocorrências para preencher grupos. "
        "Cada item deve seguir o schema da respectiva seção, conter detected=true, "
        "Smell correto, Description não vazia e Line_no positivo. "
        "Aplique os limiares, sem devolver medidas exatas ou contagens intermediárias. "
        "Retorne todas as ocorrências e use a numeração fornecida apenas para localização.\n"
        + contract
    )
    return "\n\n".join(sections)
