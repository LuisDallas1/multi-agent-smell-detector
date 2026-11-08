"""Motor comum: LangChain, validação, retries, metadados e métricas."""

import asyncio
import logging
import json
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from core.utils.code_parser import CodeParser
from core.utils.token_tracker import TokenUsageCallback

logger = logging.getLogger(__name__)


class DetectionEngine:
    """Executa as tarefas definidas por cada arquitetura com a mesma política."""

    MAX_FILE_LINES = 3000
    MAX_FILE_SIZE_KB = 500

    def __init__(self, parallel: bool = True, prompt_type: str = "simple_v2", *,
                 model_name: str | None = None, max_tokens: int = 8192,
                 temperature: float | None = 0, timeout: float = 120,
                 max_retries: int = 0, concurrency: int = 2,
                 reasoning: str | None = None, provider: str | None = None,
                 response_retries: int = 1, max_retry_tokens: int = 32768,
                 seed: int | None = None, require_parameters: bool = False,
                 response_format: str = "json_schema", json_normalization: str = "none",
                 evidence_store=None):
        self.evidence_store = evidence_store
        self._evidence_http_client = None
        if response_format not in {"json_mode", "json_schema"}:
            raise ValueError("Formato de resposta desconhecido")
        if json_normalization not in {"none", "markdown_fence"}:
            raise ValueError("Normalizacao JSON desconhecida")
        if json_normalization != "none" and response_format != "json_mode":
            raise ValueError("Normalizacao de cerca somente em json_mode")
        self.json_normalization = json_normalization
        self.response_format = response_format
        self.parallel = parallel
        self.prompt_type = prompt_type
        self.agent_configs = self._get_agent_configs(prompt_type)
        self.agent_errors = {}
        self.agent_metrics = {}
        self.agent_attempts = {}
        self.fatal_agent_error = None
        if response_retries < 0 or max_retry_tokens < max_tokens:
            raise ValueError("Retries devem ser nao negativos e max_retry_tokens >= max_tokens")
        self.response_retries = response_retries
        self.max_retry_tokens = max_retry_tokens
        self.initial_max_tokens = max_tokens
        self._agent_semaphore = asyncio.Semaphore(concurrency)
        extra = {}
        if reasoning is not None:
            extra["reasoning"] = ({"enabled": False} if reasoning == "off" else {"effort": reasoning})
        if provider:
            extra["provider"] = {"order": [provider], "only": [provider], "allow_fallbacks": False,
                                 "require_parameters": require_parameters}
        from config.settings import settings
        client_options = {}
        if evidence_store is not None:
            import httpx
            evidence_store.register_secret(settings.OPENROUTER_API_KEY)
            self._evidence_http_client = httpx.AsyncClient(
                event_hooks=evidence_store.hooks(), timeout=httpx.Timeout(timeout))
            client_options['http_async_client'] = self._evidence_http_client
        self.model = ChatOpenAI(
            model=model_name or settings.OPENROUTER_API_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            extra_body=extra,
            seed=seed,
            **client_options,
        )

    async def close_evidence_client(self):
        client = getattr(self, '_evidence_http_client', None)
        if client is not None:
            await client.aclose()

    def _record_evidence(self, stage, payload, **kwargs):
        store = getattr(self, 'evidence_store', None)
        if store is not None:
            store.emit(stage, payload, **kwargs)

    def _get_agent_configs(self, prompt_type):
        raise NotImplementedError("A arquitetura deve definir suas tarefas")

    @staticmethod
    def _system_message():
        from core.execution.contract import system_prompt
        return system_prompt(
            'If no smells are found, return {"detections": [], "detected": false}. '
            'If smells are found, return {"detections": [...], "detected": true}.'
        )

    def _response_envelopes(self, payload):
        return [payload]

    def _validate_code_size(self, code: str) -> tuple[bool, str]:
        """Valida tamanho do cÃƒÂ³digo."""
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
        """Formata cÃƒÂ³digo com numeraÃƒÂ§ÃƒÂ£o de linhas para facilitar identificaÃƒÂ§ÃƒÂ£o."""
        lines = code.split("\n")
        numbered_lines = []
        for i, line in enumerate(lines, start=1):
            numbered_lines.append(f"{i:4d} | {line}")
        return "\n".join(numbered_lines)

    def _build_agent_message(self, prompt: str, code: str) -> str:
        """Constroi a mensagem sem alterar o texto do codigo ou do prompt."""
        numbered_code = self._format_code_with_line_numbers(code)
        return (
            f"{prompt}\n\n"
            f"## CODE (com numeração de linhas):\n"
            f"```python\n{numbered_code}\n```\n\n"
            "IMPORTANTE: Use o número da linha à esquerda (ex: '  7 |') "
            "para identificar a linha correta no campo Line_no."
        )

    def _add_metadata(
        self, detections: List[Any], code: str, file_path: str, project: str, agent_name=None
    ) -> List[Any]:
        """Adiciona metadados bÃƒÂ¡sicos ÃƒÂ s detecÃƒÂ§ÃƒÂµes e filtra falsos positivos."""
        from core.utils.detection_validator import DetectionValidator

        parser = CodeParser(code, file_path)
        valid = []
        validator = DetectionValidator()

        def record_decision(detection, accepted, reason):
            attempts = getattr(self, 'agent_metrics', {}).get(agent_name, {}).get('attempts', [])
            identifier = attempts[-1].get('evidence_id') if attempts else None
            self._record_evidence('detection_decision', dict(agent=agent_name,
                detection=detection.model_dump() if hasattr(detection, 'model_dump') else str(detection),
                accepted=accepted, reason=reason), attempt_id=identifier)

        for d in detections:
            # Verificar se tem Description (campo obrigatÃƒÂ³rio de detecÃƒÂ§ÃƒÂµes individuais)
            if not hasattr(d, "Description"):
                record_decision(d, False, 'missing_description_field')
                continue
            
            # Verificar se detected estÃƒÂ¡ True (default ÃƒÂ© True)
            detected = getattr(d, "detected", True)
            if not detected:
                record_decision(d, False, 'detected_false')
                continue
            
            # Pular detecÃƒÂ§ÃƒÂµes sem descriÃƒÂ§ÃƒÂ£o
            if not d.Description:
                record_decision(d, False, 'empty_description')
                continue

            if hasattr(d, "Smell") and d.Smell:
                d.Smell = d.Smell.strip()

            detection_dict = d.model_dump() if hasattr(d, "model_dump") else d.dict()
            if not validator.validate_detection(detection_dict):
                record_decision(d, False, 'structural_identity_rejected')
                continue

            d.Project = project
            d.Package = parser.get_package_name()
            d.Module = parser.get_module_name()
            d.File = file_path
            record_decision(d, True, 'accepted_with_file_metadata')
            valid.append(d)

        return valid

    def _extract_detections(self, response: Any) -> List[Any]:
        """Extrai lista de detecÃƒÂ§ÃƒÂµes da resposta do agente."""
        # Se for um Multiple*Response, extrair a lista de detecÃƒÂ§ÃƒÂµes
        if hasattr(response, "detections") and response.detected:
            return response.detections
        
        # Se for uma detecÃƒÂ§ÃƒÂ£o ÃƒÂºnica (schema antigo) com Description
        if hasattr(response, "Description") and response.detected:
            return [response]
        
        return []

    def _try_extract_array_response(self, error_msg: str, schema: Any) -> List[Any]:
        """Tenta extrair detecÃƒÂ§ÃƒÂµes de resposta em formato de array.
        
        Quando o LLM retorna um array diretamente ao invÃƒÂ©s de {"detections": [...], "detected": true},
        tenta converter para o schema esperado.
        """
        import json
        import re
        
        # Procurar o array JSON na mensagem de erro
        match = re.search(r"input_value=(\[.*?\])", error_msg, re.DOTALL)
        if not match:
            return []
        
        try:
            # Extrair o array do erro ÃƒÂ© complicado porque estÃƒÂ¡ truncado
            # Tentar encontrar o JSON completo entre "[{" e "}]"
            json_start = error_msg.find("input_value=[{")
            if json_start == -1:
                return []
            
            # Buscar o JSON completo antes do truncamento
            # O formato ÃƒÂ©: input_value=[{...}, {...}], input_type=list
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
            
            # Criar detecÃƒÂ§ÃƒÂµes vÃƒÂ¡lidas a partir dos dados
            # Obter o tipo de detecÃƒÂ§ÃƒÂ£o individual do schema
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
                    # Criar instÃƒÂ¢ncia da detecÃƒÂ§ÃƒÂ£o
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
            total_usage = self._create_empty_token_usage()
            attempts = []
            budget = self.initial_max_tokens
            detections = []
            recoverable = {"TruncatedResponse", "InvalidJSON", "InvalidStructuredResponse",
                           "InvalidProviderResponse",
                           "MissingFinishReason", "APITimeoutError", "RateLimitError",
                           "APIConnectionError", "InternalServerError"}
            for index in range(self.response_retries + 1):
                if self.fatal_agent_error:
                    self.agent_errors[agent_name] = "SkippedAfterAuthenticationFailure"
                    break
                self.agent_errors.pop(agent_name, None)
                self.agent_attempts[agent_name] = {"attempt": index + 1, "max_tokens": budget}
                from contextlib import nullcontext
                evidence = getattr(self, 'evidence_store', None)
                context = evidence.attempt(agent_name, index + 1, budget) if evidence is not None else nullcontext()
                with context as identifier:
                    detections, usage = await self._call_agent_inner(agent_name, config, code, max_tokens=budget)
                    if evidence is not None:
                        self.agent_attempts[agent_name]['evidence_id'] = identifier
                        evidence.emit('attempt_completed', dict(
                            metrics=dict(self.agent_attempts[agent_name], error=self.agent_errors.get(agent_name), token_usage=usage),
                            extracted_detections=[d.model_dump() for d in detections]))
                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)
                error = self.agent_errors.get(agent_name)
                # Preserve successful responses too: processed detections cannot
                # establish whether parsing or filtering lost information.
                attempts.append(dict(self.agent_attempts[agent_name], error=error, token_usage=usage))
                if error in {"AuthenticationError", "PermissionDeniedError", "InsufficientCreditError"}:
                    self.fatal_agent_error = error
                if not error or error not in recoverable or index == self.response_retries:
                    break
                if error in {"RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError", "InvalidProviderResponse"}:
                    delay = attempts[-1].get("retry_after_seconds")
                    await asyncio.sleep(min(30, max(1, delay if delay is not None else 2 ** index)))
                if error == "TruncatedResponse":
                    # A single recovery must reach the configured recovery budget.
                    budget = self.max_retry_tokens
                logger.warning("[%s] Repetindo resposta invalida (%s), tentativa %s, limite %s",
                               agent_name, error, index + 2, budget)
        self.agent_metrics[agent_name] = {
            "detections_before_metadata": len(detections),
            "token_usage": total_usage,
            "error": self.agent_errors.get(agent_name),
            "attempts": attempts,
            "recovered": len(attempts) > 1 and agent_name not in self.agent_errors,
        }
        return detections, total_usage

    @staticmethod
    def _strict_response_schema(schema):
        """Schema de inferencia: sem metadados do arquivo; Pydantic original intacto."""
        definition = schema.model_json_schema(by_alias=False)
        def strict(node):
            if isinstance(node, dict):
                node.pop("default", None)
                properties = node.get("properties", {})
                if {"Method", "Line_no", "Description"} <= set(properties):
                    for field in ("Project", "Package", "Module", "Class", "File"):
                        properties.pop(field, None)
                if node.get("type") == "object" or "properties" in node:
                    node["additionalProperties"] = False
                    node["required"] = list(node.get("properties", {}))
                for value in node.values():
                    strict(value)
            elif isinstance(node, list):
                for value in node:
                    strict(value)
        strict(definition)
        return {"name": schema.__name__, "schema": definition, "strict": True}

    @staticmethod
    def _truncation_metrics(reasoning, completion, budget, ceiling):
        fraction = reasoning / completion if isinstance(reasoning, (int, float)) and completion else None
        return dict(
            truncation_cause="reasoning_dominated" if fraction is not None and fraction >= .95 else "output_or_unknown",
            reasoning_fraction=fraction, retry_at_token_ceiling=(budget == ceiling))

    @staticmethod
    def _unwrap_markdown_fence(content):
        """Remove so uma cerca que envolve a resposta inteira; nao repara JSON."""
        if not isinstance(content, str):
            return content, False
        lines = content.strip().splitlines()
        if (len(lines) >= 3 and lines[0] in {"```json", "```"} and lines[-1] == "```"
                and not any(line.lstrip().startswith("```") for line in lines[1:-1])):
            return "\n".join(lines[1:-1]), True
        return content, False

    @staticmethod
    def _reject_json_constant(value):
        raise ValueError("Constante JSON invalida")

    async def _call_agent_inner(
        self, agent_name: str, config: Dict, code: str, *, max_tokens=None
    ) -> tuple[List[Any], Dict[str, int]]:
        """Aceita somente JSON completo, termino normal e validacao Pydantic."""
        from core.schemas.agent_response import CONTRACT_VERSION
        token_callback = TokenUsageCallback()
        self.agent_attempts.setdefault(agent_name, {})
        try:
            # Copia por tentativa: nao altera o cliente compartilhado por outros agentes.
            model = self.model if max_tokens is None else self.model.model_copy(update={"max_tokens": max_tokens})
            if getattr(self, "response_format", "json_mode") == "json_schema":
                structured_model = model.with_structured_output(
                    self._strict_response_schema(config["schema"]), method="json_schema", strict=True, include_raw=True)
            else:
                structured_model = model.with_structured_output(
                    config["schema"], method="json_mode", include_raw=True)

            message = self._build_agent_message(config["prompt"], code)
            contract_schema = config["schema"].model_json_schema(by_alias=False)
            field_contract = []
            for node in contract_schema.get("$defs", {}).values():
                properties = node.get("properties", {})
                if "Smell" in properties and "Line_no" in properties:
                    field_contract.append(dict(Smell=properties["Smell"].get("const", properties["Smell"].get("default")),
                                               required=node.get("required", [])))
            # Explicit diagnostic ablation: validation and schema stay unchanged.
            if not config.get("diagnostic_omit_common_appendix", False):
                message += "\nCAMPOS OBRIGATÓRIOS POR TIPO: " + json.dumps(field_contract, ensure_ascii=False, separators=(",", ":"))
                message += "\nCONTRATO OBRIGATÓRIO: todos os campos pedidos são obrigatórios em cada detecção; " \
                           "não os substitua por texto em Description, não use null nos campos obrigatórios. " \
                           "number deve ser um número JSON e identifier_name deve conter o nome exato, quando pedidos. " \
                           "Aplique os critérios descritos e reporte a ocorrência, localização e evidência curta, " \
                           "sem calcular ou devolver comprimento exato, medidas, thresholds ou intervalos start_line/end_line. " \
                           "Não retorne contagens intermediárias, raciocínio ou código corrigido. Preserve todas as ocorrências."
            self._record_evidence('logical_request', dict(
                messages=[dict(role='system', content=config.get('system_prompt') or self._system_message()),
                          dict(role='user', content=message)],
                schema=contract_schema, semantic_contract_version=CONTRACT_VERSION,
                common_appendix_enabled=not config.get('diagnostic_omit_common_appendix', False),
                response_format=getattr(self, 'response_format', 'json_mode'), max_tokens=max_tokens))
            response = await structured_model.ainvoke(
                [
                    {"role": "system", "content": config.get("system_prompt") or self._system_message()},
                    {"role": "user", "content": message},
                ],
                config={"callbacks": [token_callback]},
            )
            raw = response.get("raw") if isinstance(response, dict) else None
            evidence = getattr(self, 'evidence_store', None)
            if evidence is not None and evidence.current_usage() is not None:
                token_callback.capture_cost(evidence.current_usage())
            self._record_evidence('llm_response', dict(
                raw=raw.model_dump(mode='json') if hasattr(raw, 'model_dump') else getattr(raw, '__dict__', None),
                parsing_error_type=type(response.get('parsing_error')).__name__
                    if isinstance(response, dict) and response.get('parsing_error') else None))
            metadata = getattr(raw, "response_metadata", {}) or {}
            finish = metadata.get("finish_reason")
            content = getattr(raw, "content", "")
            usage_metadata = getattr(raw, "usage_metadata", {}) or {}
            reasoning = (usage_metadata.get("output_token_details") or {}).get("reasoning")
            if reasoning is None:
                usage = metadata.get("token_usage", {}) or {}
                reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            self.agent_attempts[agent_name].update(
                raw_response_text=content,
                finish_reason=finish, output_characters=len(content) if isinstance(content, str) else None,
                cost_usd=token_callback.cost_usd, cost_source="OpenRouter usage.cost" if token_callback.cost_usd is not None else None,
                reasoning_tokens=reasoning, usage_available=token_callback.usage_available,
                returned_model=metadata.get("model_name", metadata.get("model")),
                system_fingerprint=metadata.get("system_fingerprint"),
                returned_provider=metadata.get("provider"),
                response_message_id=getattr(raw, "id", None),
            )
            if finish == "length":
                completion = token_callback.token_usage.get("completion_tokens", 0)
                self.agent_attempts[agent_name].update(self._truncation_metrics(
                    reasoning, completion, max_tokens, self.max_retry_tokens))
                self.agent_errors[agent_name] = "TruncatedResponse"
                return [], token_callback.token_usage
            if finish != "stop":
                self.agent_errors[agent_name] = "MissingFinishReason" if finish is None else "NonStopFinishReason"
                return [], token_callback.token_usage
            normalization_applied = False
            if getattr(self, "json_normalization", "none") == "markdown_fence":
                content, normalization_applied = self._unwrap_markdown_fence(content)
            self.agent_attempts[agent_name].update(normalization_applied=normalization_applied,
                normalization="markdown_fence" if normalization_applied else "none")
            if normalization_applied:
                self.agent_attempts[agent_name]["normalized_response_text"] = content
            # JSON mode/Pydantic podem tolerar JSON parcial. Verificacao estrita antes de aceitar.
            try:
                if not isinstance(content, str):
                    raise ValueError("Conteudo nao textual")
                payload = json.loads(content, parse_constant=self._reject_json_constant)
            except (ValueError, TypeError) as error:
                self.agent_attempts[agent_name]["validation_error"] = dict(
                    type=type(error).__name__, message=getattr(error, "msg", "Conteudo nao textual"),
                    line=getattr(error, "lineno", None), column=getattr(error, "colno", None))
                self.agent_errors[agent_name] = "InvalidJSON"
                return [], token_callback.token_usage
            self._record_evidence('decoded_payload', dict(payload=payload))
            for payload_group in self._response_envelopes(payload):
                if (not isinstance(payload_group, dict) or type(payload_group.get("detected")) is not bool
                        or not isinstance(payload_group.get("detections"), list)
                        or payload_group["detected"] != bool(payload_group["detections"])):
                    self.agent_errors[agent_name] = "InvalidStructuredResponse"
                    return [], token_callback.token_usage
                for item in payload_group["detections"]:
                    if not isinstance(item, dict):
                        self.agent_errors[agent_name] = "InvalidStructuredResponse"
                        return [], token_callback.token_usage
                    description = item.get("Description", item.get("description"))
                    line = item.get("Line_no")
                    if (not isinstance(description, str) or not description.strip()
                            or not str(line).isdigit() or int(str(line)) <= 0):
                        self.agent_errors[agent_name] = "InvalidStructuredResponse"
                        return [], token_callback.token_usage
            try:
                validated = config["schema"].model_validate(payload)
            except ValueError as error:
                self._record_evidence('pydantic_rejected', dict(error_type=type(error).__name__,
                    errors=error.errors(include_url=False) if hasattr(error, 'errors') else []))
                self.agent_errors[agent_name] = "InvalidStructuredResponse"
                return [], token_callback.token_usage
            self._record_evidence('pydantic_validated', dict(payload=validated.model_dump()))
            return self._extract_detections(validated), token_callback.token_usage
        except Exception as error:
            from core.execution.errors import diagnose_exception
            from types import SimpleNamespace
            import traceback
            diagnostic, recovered_usage = diagnose_exception(error)
            self._record_evidence('exception', dict(diagnostic=diagnostic,
                exception_message=str(error), traceback=''.join(traceback.format_exception(error))))
            self.agent_attempts[agent_name]['exception_diagnostic'] = diagnostic
            if not token_callback.usage_available:
                await token_callback.on_llm_error(error)
            if recovered_usage is not None:
                await token_callback.on_llm_error(SimpleNamespace(
                    completion=SimpleNamespace(usage=recovered_usage)))
            evidence = getattr(self, 'evidence_store', None)
            if evidence is not None and evidence.current_usage() is not None:
                usage = evidence.current_usage()
                token_callback.capture_cost(usage)
                if not token_callback.usage_available and any(key in usage for key in ('prompt_tokens', 'completion_tokens')):
                    await token_callback.on_llm_error(SimpleNamespace(completion=SimpleNamespace(usage=usage)))
            name = diagnostic.get('classification', type(error).__name__)
            status = getattr(error, "status_code", None) or diagnostic.get('provider_error_code')
            if status == 402:
                name = "InsufficientCreditError"
            elif status == 429:
                name = "RateLimitError"
            elif isinstance(status, int) and status >= 500:
                name = "InternalServerError"
            retry_after = None
            headers = getattr(getattr(error, "response", None), "headers", {}) or {}
            try:
                retry_after = min(30, max(0, float(headers.get("retry-after"))))
            except (ValueError, TypeError):
                pass
            self.agent_attempts[agent_name].update(http_status=status, retry_after_seconds=retry_after)
            if name == "LengthFinishReasonError" or "length limit was reached" in str(error):
                name = "TruncatedResponse"
            self.agent_errors[agent_name] = name
            self.agent_attempts[agent_name].update(cost_usd=token_callback.cost_usd, usage_available=token_callback.usage_available,
                finish_reason="length" if name == "TruncatedResponse" else None,
                reasoning_tokens=token_callback.reasoning_tokens)
            if name == "TruncatedResponse":
                self.agent_attempts[agent_name].update(self._truncation_metrics(
                    token_callback.reasoning_tokens, token_callback.token_usage.get("completion_tokens", 0),
                    max_tokens, self.max_retry_tokens))
            logger.warning("[%s] Resposta rejeitada: %s", agent_name, name)
            return [], token_callback.token_usage

    def _create_empty_token_usage(self) -> Dict[str, int]:
        """Cria dicionÃƒÂ¡rio vazio para uso de tokens."""
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
            from core.execution.evidence import EvidenceWriteError
            from asyncio import CancelledError
            if isinstance(result, EvidenceWriteError):
                raise result
            if isinstance(result, CancelledError):
                raise result
            if isinstance(result, Exception):
                logger.error("[%s] Falhou: %s", name, result)
                self.agent_errors[name] = type(result).__name__
                continue

            detections, token_usage = result
            all_detections.extend(
                self._add_metadata(detections, code, file_path, project, agent_name=name)
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
                self._add_metadata(detections, code, file_path, project, agent_name=name)
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
        """Analisa cÃƒÂ³digo e retorna code smells detectados."""
        self.agent_errors = {}
        self.agent_metrics = {}
        self.agent_attempts = {}
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
        from core.schemas.agent_response import LEGACY_OUTPUT_FIELDS
        for d in detections:
            data = d.model_dump()
            for field in LEGACY_OUTPUT_FIELDS:
                if field not in d.model_fields_set:
                    data.pop(field, None)
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

