"""Onze grupos obrigatórios usando os mesmos schemas de ocorrência."""
from pydantic import create_model
from core.supervisor.agent_config import AGENTS
from core.schemas import agent_response


class GroupedResponse(agent_response.ResponseContract):
    pass


AllSmellsResponse = create_model(
    "AllSmellsResponse", __base__=GroupedResponse,
    **{name: (getattr(agent_response, schema), ...) for name, schema in AGENTS.items()},
)
