"""Supervisor para coordenação de agentes especializados."""

import asyncio
import logging
from typing import Any, Dict, List

from langchain_core.exceptions import LangChainException
from langchain_openai import ChatOpenAI

from config.settings import settings
from core.supervisor.agent_config import get_agent_configs
from core.utils.code_parser import CodeParser
from core.utils.token_tracker import TokenUsageCallback

logger = logging.getLogger(__name__)


class CodeSmellSupervisor:
    """Coordena 11 agentes especializados para detectar code smells."""

    MAX_FILE_LINES = 3000
    MAX_FILE_SIZE_KB = 500

    def __init__(self, parallel: bool = True, prompt_type: str = "simple_estevam", *,
                 model_name: str | None = None, max_tokens: int = 8192,
                 temperature: float = 0, timeout: float = 120,
                 max_retries: int = 0, concurrency: int = 2,
                 reasoning: str | None = None, provider: str | None = None):
        self.parallel = parallel
        self.prompt_type = prompt_type
        self.agent_configs = get_agent_configs(prompt_type)
        self.agent_errors = {}
        self.agent_metrics = {}
        self.fatal_agent_error = None
        self._agent_semaphore = asyncio.Semaphore(concurrency)
        extra = {}
        if reasoning is not None:
            extra["reasoning"] = ({"enabled": False} if reasoning == "off" else {"effort": reasoning})
        if provider:
            extra["provider"] = {"order": [provider], "allow_fallbacks": False}
        self.model = ChatOpenAI(
            model=model_name or settings.OPENROUTER_API_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            extra_body=extra,
        )

    def _validate_code_size(self, code: str) -> tuple[bool, str]:
        """Valida tamanho do código."""
        lines = code.split("\n")
        size_kb = len(code.encode("utf-8")) / 1024

        if len(lines) > self.MAX_FILE_LINES:
            return (
                False,
                f"Arquivo muito grande: {len(lines)} linhas (max: {self.MAX_FILE_LINES})",
            )

        if size_kb > self.MAX_FILE_SIZE_KB:
            return (
                False,
                f"Arquivo muito grande: {size_kb:.1f}KB (max: {self.MAX_FILE_SIZE_KB}KB)",
            )

        return True, ""

    def _format_code_with_line_numbers(self, code: str) -> str:
        """Formata código com numeração de linhas para facilitar identificação."""
        lines = code.split("\n")
        numbered_lines = []
        for i, line in enumerate(lines, start=1):
            numbered_lines.append(f"{i:4d} | {line}")
        return "\n".join(numbered_lines)

    def _build_agent_message(self, prompt: str, code: str) -> str:
        """Constrói mensagem completa para o agente."""
        numbered_code = self._format_code_with_line_numbers(code)
        return (
            f"{prompt}\n\n"
            f"## CODE (com numeração de linhas):\n"
            f"```python\n{numbered_code}\n```\n\n"
            "IMPORTANTE: Use o número da linha à esquerda (ex: '  7 |') "
            "para identificar a linha correta no campo Line_no."
        )

    def _add_metadata(
        self, detections: List[Any], code: str, file_path: str, project: str
    ) -> List[Any]:
        """Adiciona metadados básicos às detecções e filtra falsos positivos."""
        from ..utils.detection_validator import DetectionValidator

        parser = CodeParser(code, file_path)
        valid = []
        validator = DetectionValidator()

        for d in detections:
            # Verificar se tem Description (campo obrigatório de detecções individuais)
            if not hasattr(d, "Description"):
                continue
            
            # Verificar se detected está True (default é True)
            detected = getattr(d, "detected", True)
            if not detected:
                continue
            
            # Pular detecções sem descrição
            if not d.Description:
                continue

            if hasattr(d, "Smell") and d.Smell:
                d.Smell = d.Smell.strip()

            detection_dict = d.model_dump() if hasattr(d, "model_dump") else d.dict()
            if not validator.validate_detection(detection_dict):
                continue

            d.Project = project
            d.Package = parser.get_package_name()
            d.Module = parser.get_module_name()
            d.File = file_path
            valid.append(d)

        return valid

    def _extract_detections(self, response: Any) -> List[Any]:
        """Extrai lista de detecções da resposta do agente."""
        # Se for um Multiple*Response, extrair a lista de detecções
        if hasattr(response, "detections") and response.detected:
            return response.detections
        
        # Se for uma detecção única (schema antigo) com Description
        if hasattr(response, "Description") and response.detected:
            return [response]
        
        return []

    def _try_extract_array_response(self, error_msg: str, schema: Any) -> List[Any]:
        """Tenta extrair detecções de resposta em formato de array.
        
        Quando o LLM retorna um array diretamente ao invés de {"detections": [...], "detected": true},
        tenta converter para o schema esperado.
        """
        import json
        import re
        
        # Procurar o array JSON na mensagem de erro
        match = re.search(r"input_value=(\[.*?\])", error_msg, re.DOTALL)
        if not match:
            return []
        
        try:
            # Extrair o array do erro é complicado porque está truncado
            # Tentar encontrar o JSON completo entre "[{" e "}]"
            json_start = error_msg.find("input_value=[{")
            if json_start == -1:
                return []
            
            # Buscar o JSON completo antes do truncamento
            # O formato é: input_value=[{...}, {...}], input_type=list
            json_part = error_msg[json_start + len("input_value="):]
            
            # Encontrar o fim do array
            bracket_count = 0
            end_pos = 0
            for i, char in enumerate(json_part):
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i + 1
                        break
            
            if end_pos == 0:
                return []
            
            json_str = json_part[:end_pos]
            
            # Tentar parsear o JSON
            data = json.loads(json_str)
            
            if not isinstance(data, list):
                return []
            
            # Criar detecções válidas a partir dos dados
            # Obter o tipo de detecção individual do schema
            detection_type = None
            if hasattr(schema, "__annotations__") and "detections" in schema.__annotations__:
                field_type = schema.__annotations__["detections"]
                # Extrair o tipo da lista (ex: list[LongIdentifierDetection])
                if hasattr(field_type, "__args__") and field_type.__args__:
                    detection_type = field_type.__args__[0]
            
            if detection_type is None:
                return []
            
            valid_detections = []
            for item in data:
                try:
                    # Criar instância da detecção
                    det = detection_type(**item)
                    det.detected = True
                    valid_detections.append(det)
                except Exception:  # pylint: disable=broad-except
                    continue
            
            return valid_detections
            
        except (json.JSONDecodeError, ValueError, TypeError):
            return []

    async def _call_agent(self, agent_name, config, code):
        async with self._agent_semaphore:
            if self.fatal_agent_error:
                self.agent_errors[agent_name] = "SkippedAfterAuthenticationFailure"
                return [], self._create_empty_token_usage()
            detections, usage = await self._call_agent_inner(agent_name, config, code)
            if self.agent_errors.get(agent_name) in {"AuthenticationError", "PermissionDeniedError"}:
                self.fatal_agent_error = self.agent_errors[agent_name]
        self.agent_metrics[agent_name] = {
            "detections_before_metadata": len(detections),
            "token_usage": usage,
            "error": self.agent_errors.get(agent_name),
        }
        return detections, usage

    async def _call_agent_inner(
        self, agent_name: str, config: Dict, code: str
    ) -> tuple[List[Any], Dict[str, int]]:
        """Executa um agente individual. Retorna (detections, token_usage)."""
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        token_callback = TokenUsageCallback()
        try:
            structured_model = self.model.with_structured_output(
                config["schema"], method="json_mode"
            )
            message = self._build_agent_message(config["prompt"], code)

            logger.info("[%s] Executando...", agent_name)

            response = await structured_model.ainvoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a code smell detector. "
                            "ALWAYS respond with valid JSON only. "
                            "Never respond with explanations or questions. "
                            "If no smells are found, return {\"detections\": [], \"detected\": false}. "
                            "If smells are found, return {\"detections\": [...], \"detected\": true}."
                        ),
                    },
                    {"role": "user", "content": message},
                ],
                config={"callbacks": [token_callback]},
            )

            detections = self._extract_detections(response)
            token_usage = token_callback.token_usage

            logger.info(
                "[%s] %s detecções | Tokens: %s",
                agent_name,
                len(detections),
                token_usage.get("total_tokens", 0),
            )

            return detections, token_usage

        except (ValueError, AttributeError, KeyError) as e:
            error_msg = str(e)
            # Tentar extrair detecções se o LLM retornou array diretamente
            if "input_type=list" in error_msg:
                detections = self._try_extract_array_response(error_msg, config["schema"])
                if detections:
                    logger.info("[%s] Recuperado %s detecções de resposta em array", agent_name, len(detections))
                    return detections, token_usage
            logger.error("[%s] Erro de validação/atributo: %s", agent_name, e)
            self.agent_errors[agent_name] = type(e).__name__
            return [], token_callback.token_usage
        except LangChainException as e:
            error_msg = str(e)
            # Tentar extrair detecções se o LLM retornou array diretamente
            if "input_type=list" in error_msg:
                detections = self._try_extract_array_response(error_msg, config["schema"])
                if detections:
                    logger.info("[%s] Recuperado %s detecções de resposta em array", agent_name, len(detections))
                    return detections, token_usage
            # Tratar erro de parsing (LLM retornou formato inválido ou detecções inválidas)
            if "OUTPUT_PARSING_FAILURE" in error_msg or "parsing" in error_msg.lower():
                logger.warning(
                    "[%s] Erro de parsing da resposta do LLM. "
                    "Possível detecção inválida (ex: length <= threshold). Ignorando.",
                    agent_name,
                )
            else:
                logger.error("[%s] Erro do LangChain: %s", agent_name, e)
            self.agent_errors[agent_name] = type(e).__name__
            return [], token_callback.token_usage
        except Exception as e:  # pylint: disable=broad-except
            error_msg = str(e)
            # Tratar especificamente erro de limite de tokens
            if "length limit was reached" in error_msg or "LengthFinishReasonError" in error_msg:
                logger.warning(
                    "[%s] Limite configurado de tokens de resposta atingido. "
                    "Resposta incompleta descartada e registrada como falha.",
                    agent_name,
                )
                # Tentar extrair detecções parciais se possível
                # Por enquanto, retornar vazio para evitar dados incompletos
                self.agent_errors[agent_name] = type(e).__name__
                return [], token_callback.token_usage
            logger.error("[%s] Erro inesperado: %s", agent_name, type(e).__name__)
            self.agent_errors[agent_name] = type(e).__name__
            return [], token_callback.token_usage

    def _create_empty_token_usage(self) -> Dict[str, int]:
        """Cria dicionário vazio para uso de tokens."""
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _aggregate_token_usage(
        self, total: Dict[str, int], usage: Dict[str, int]
    ) -> None:
        """Agrega uso de tokens ao total."""
        total["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total["completion_tokens"] += usage.get("completion_tokens", 0)
        total["total_tokens"] += usage.get("total_tokens", 0)

    async def _analyze_parallel(
        self, code: str, file_path: str, project: str
    ) -> tuple[List[Any], Dict[str, int]]:
        """Executa agentes em paralelo. Retorna (detections, total_token_usage)."""
        tasks = [
            self._call_agent(name, cfg, code)
            for name, cfg in self.agent_configs.items()
        ]

        logger.info("Executando %s agentes em PARALELO...", len(tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_detections = []
        total_token_usage = self._create_empty_token_usage()

        for (name, _), result in zip(self.agent_configs.items(), results):
            if isinstance(result, Exception):
                logger.error("[%s] Falhou: %s", name, result)
                self.agent_errors[name] = type(result).__name__
                continue

            detections, token_usage = result
            all_detections.extend(
                self._add_metadata(detections, code, file_path, project)
            )
            self._aggregate_token_usage(total_token_usage, token_usage)

        return all_detections, total_token_usage

    async def _analyze_sequential(
        self, code: str, file_path: str, project: str
    ) -> tuple[List[Any], Dict[str, int]]:
        """Executa agentes sequencialmente. Retorna (detections, total_token_usage)."""
        all_detections = []
        total_token_usage = self._create_empty_token_usage()

        for name, config in self.agent_configs.items():
            detections, token_usage = await self._call_agent(name, config, code)
            all_detections.extend(
                self._add_metadata(detections, code, file_path, project)
            )
            self._aggregate_token_usage(total_token_usage, token_usage)
            await asyncio.sleep(0.3)

        return all_detections, total_token_usage

    async def analyze_code(
        self,
        python_code: str,
        file_path: str = "unknown.py",
        project_name: str = "Code",
    ) -> Dict[str, Any]:
        """Analisa código e retorna code smells detectados."""
        self.agent_errors = {}
        self.agent_metrics = {}
        self.fatal_agent_error = None
        valid, error = self._validate_code_size(python_code)
        if not valid:
            logger.warning("Arquivo rejeitado: %s", error)
            return {
                "total_smells_detected": 0,
                "code_smells": [],
                "agents_executed": 0,
                "error": error,
                "token_usage": self._create_empty_token_usage(),
            }

        detections, token_usage = await (
            self._analyze_parallel(python_code, file_path, project_name)
            if self.parallel
            else self._analyze_sequential(python_code, file_path, project_name)
        )

        results = []
        for d in detections:
            data = d.model_dump()
            data["Line no"] = data.pop("Line_no", "")
            results.append(data)

        return {
            "total_smells_detected": len(results),
            "code_smells": results,
            "agents_executed": len(self.agent_configs),
            "agent_errors": dict(self.agent_errors),
            "agent_metrics": dict(self.agent_metrics),
            "fatal_error": self.fatal_agent_error,
            "token_usage": token_usage,
        }


def get_supervisor(
    parallel: bool = True, prompt_type: str = "simple_estevam"
) -> CodeSmellSupervisor:
    """Factory para criar supervisor."""
    return CodeSmellSupervisor(parallel=parallel, prompt_type=prompt_type)


async def analyze_code(
    python_code: str,
    file_path: str = "unknown.py",
    project_name: str = "Code",
    parallel: bool = True,
    prompt_type: str = "simple_estevam",
) -> Dict[str, Any]:
    """Analisa código Python e retorna code smells.

    Args:
        python_code: Código Python a ser analisado
        file_path: Caminho do arquivo
        project_name: Nome do projeto
        parallel: Se True, executa agentes em paralelo
        prompt_type: "simple_estevam", "complete_estevam" ou "complete_v2"
    """
    return await get_supervisor(
        parallel=parallel, prompt_type=prompt_type
    ).analyze_code(python_code, file_path, project_name)
