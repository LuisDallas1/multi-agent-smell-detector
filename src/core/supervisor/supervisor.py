"""Arquitetura multiagente: supervisor determinístico e 11 especialistas."""
from typing import Any, Dict
from core.execution.engine import DetectionEngine
from core.supervisor.agent_config import get_agent_configs


class CodeSmellSupervisor(DetectionEngine):
    """Executa uma tarefa independente por especialista em cada arquivo."""

    def _get_agent_configs(self, prompt_type):
        return get_agent_configs(prompt_type)


def get_supervisor(
    parallel: bool = True, prompt_type: str = "simple_v2"
) -> CodeSmellSupervisor:
    """Factory para criar supervisor."""
    return CodeSmellSupervisor(parallel=parallel, prompt_type=prompt_type)


async def analyze_code(
    python_code: str,
    file_path: str = "unknown.py",
    project_name: str = "Code",
    parallel: bool = True,
    prompt_type: str = "simple_v2",
) -> Dict[str, Any]:
    """Analisa cÃƒÂ³digo Python e retorna code smells.

    Args:
        python_code: CÃƒÂ³digo Python a ser analisado
        file_path: Caminho do arquivo
        project_name: Nome do projeto
        parallel: Se True, executa agentes em paralelo
        prompt_type: "simple_v2" ou "complete_v2"
    """
    return await get_supervisor(
        parallel=parallel, prompt_type=prompt_type
    ).analyze_code(python_code, file_path, project_name)
