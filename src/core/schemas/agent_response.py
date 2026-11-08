"""Schemas Pydantic para respostas estruturadas dos agentes."""

import math
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from core.smell_rules import THRESHOLDS


class CodeSmellDetection(BaseModel):
    """Schema base para todas as detecções de code smell."""

    Project: str = Field(default="Code")
    Package: str = Field(default="Code")
    Module: str = Field(default="unknown")
    Class: str = Field(default="")
    Smell: str = Field(default="", alias="code_smell")
    Method: str = Field(default="")
    Line_no: Union[str, int] = Field(default="")
    File: str = Field(default="")
    Description: str = Field(default="", alias="description")

    detected: bool = Field(default=True)

    @field_validator("Line_no", mode="before")
    @classmethod
    def convert_line_no(cls, v):
        """Converte Line_no para string se for int."""
        if v is None:
            return ""
        return str(v)

    class Config:
        populate_by_name = True


class ComplexMethodDetection(CodeSmellDetection):
    Smell: str = Field(default="Complex method")
    cyclomatic_complexity: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['complex method'])
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class LongMethodDetection(CodeSmellDetection):
    Smell: str = Field(default="Long method")
    total_lines: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['long method'])
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class ComplexConditionalDetection(CodeSmellDetection):
    Smell: str = Field(default="Complex conditional")
    logical_operators: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['complex conditional'])


class LongParameterListDetection(CodeSmellDetection):
    Smell: str = Field(default="Long parameter list")
    parameter_count: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['long parameter list'])


class LongStatementDetection(CodeSmellDetection):
    Smell: str = Field(default="Long statement")
    # Leitura de dados históricos: não pedidos na inferência nem usados como filtro.
    line_length: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['long statement'])


class LongIdentifierDetection(CodeSmellDetection):
    Smell: str = Field(default="Long identifier")
    identifier_name: Optional[str] = None
    length: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['long identifier'])


class MagicNumberDetection(CodeSmellDetection):
    Smell: str = Field(default="Magic number")
    number: Optional[Union[int, float]] = None


class EmptyCatchBlockDetection(CodeSmellDetection):
    Smell: str = Field(default="Empty catch block")


class MissingDefaultDetection(CodeSmellDetection):
    Smell: str = Field(default="Missing default")


class LongLambdaFunctionDetection(CodeSmellDetection):
    Smell: str = Field(default="Long lambda function")
    lambda_length: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['long lambda function'])


class LongMessageChainDetection(CodeSmellDetection):
    Smell: str = Field(default="Long message chain")
    chain_length: Optional[int] = None
    threshold: int = Field(default=THRESHOLDS['long message chain'])



# Os DTOs individuais continuam legíveis para dados históricos; toda resposta
# nova passa pelo envelope, que exige os campos de inferência explicitamente.
CONTRACT_VERSION = "occurrence-v4-identity-location"
FILTER_VERSION = "structural-v4-no-semantic-postfilter"
INFERENCE_SCHEMA_VERSION = "lean-v4-identity-location"
LEGACY_MEASURE_FIELDS = {
    "complex method": "cyclomatic_complexity", "long method": "total_lines",
    "complex conditional": "logical_operators", "long parameter list": "parameter_count",
    "long identifier": "length",
    "long lambda function": "lambda_length", "long message chain": "chain_length",
    "long statement": "line_length",
}
# Nenhuma medida exata é pedida à LLM. Os DTOs ainda leem campos históricos.
MEASURE_FIELDS = {}
LEGACY_OUTPUT_FIELDS = frozenset(LEGACY_MEASURE_FIELDS.values()) | {"threshold", "start_line", "end_line"}


def validate_inference_item(item, smell):
    if smell not in set(THRESHOLDS) | {"magic number", "empty catch block", "missing default"}:
        raise ValueError("UnknownSmell")
    required = {"detected", "Smell", "Method", "Line_no", "Description"}
    if smell == "long identifier": required.add("identifier_name")
    if smell == "magic number": required.add("number")
    supplied = dict(item)
    for canonical, alias in [("Smell", "code_smell"), ("Description", "description")]:
        if canonical not in supplied and alias in supplied: supplied[canonical] = supplied[alias]
    missing = sorted(k for k in required if k not in supplied or supplied[k] is None)
    if missing: raise ValueError("MissingInferenceFields: " + ", ".join(missing))
    if supplied["detected"] is not True or not isinstance(supplied["Smell"], str) or supplied["Smell"].strip().lower() != smell:
        raise ValueError("InvalidDetectionIdentity")
    if not isinstance(supplied["Method"], str) or not isinstance(supplied["Description"], str) or not supplied["Description"].strip():
        raise ValueError("InvalidDetectionText")
    line = supplied["Line_no"]
    if isinstance(line, bool) or not str(line).isdigit() or int(line) <= 0: raise ValueError("InvalidDetectionLine")
    if smell == "magic number":
        number = supplied["number"]
        if type(number) not in (int, float) or not math.isfinite(number): raise ValueError("InvalidNumber")
    if smell == "long identifier":
        name = supplied["identifier_name"]
        if not isinstance(name, str) or not name.isidentifier(): raise ValueError("InvalidIdentifierName")


class ResponseContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        definition = super().model_json_schema(*args, **kwargs)
        def visit(node):
            if not isinstance(node, dict): return
            properties = node.get("properties", {})
            label = properties.get("Smell", {}).get("default", "")
            smell = label.lower()
            if smell and "Line_no" in properties:
                # Keep the identity available after removing defaults below.
                properties["Smell"]["const"] = label
                for field in LEGACY_OUTPUT_FIELDS:
                    properties.pop(field, None)
                required = {"detected", "Smell", "Method", "Line_no", "Description"}
                if smell == "magic number": required.add("number")
                if smell == "long identifier": required.add("identifier_name")
                if "description" in properties: required.discard("Description"); required.add("description")
                node["required"] = sorted(required)
                for name in required:
                    field = properties[name]
                    field.pop("default", None)
                    if "anyOf" in field:
                        variants = [v for v in field["anyOf"] if v.get("type") != "null"]
                        field["anyOf"] = variants
            for value in node.values():
                if isinstance(value, dict): visit(value)
                elif isinstance(value, list):
                    for item in value: visit(item)
        visit(definition)
        return definition


class SmellResponse(ResponseContract):
    """Mesma validação de envelope e identidade em ambas as arquiteturas."""

    @model_validator(mode="before")
    @classmethod
    def check_inference_fields(cls, payload):
        if isinstance(payload, dict):
            detection_type = cls.model_fields["detections"].annotation.__args__[0]
            smell = detection_type.model_fields["Smell"].default.lower()
            if not isinstance(payload.get("detections", []), list): raise ValueError("DetectionsMustBeArray")
            for item in payload.get("detections", []):
                # Validation must inspect the raw types before Pydantic coercion.
                if not isinstance(item, dict): raise ValueError("DetectionMustBeObject")
                validate_inference_item(item, smell)
            # Os valores antigos continuam no HTTP/decoded_payload preservado.
            # Na inferência atual, não os interprete nem deixe que invalidem
            # uma previsão de ocorrência. Não mutar a resposta original.
            payload = dict(payload, detections=[
                {key: value for key, value in item.items() if key not in LEGACY_OUTPUT_FIELDS}
                for item in payload.get("detections", [])])
        return payload

    @model_validator(mode="after")
    def check_detection_contract(self):
        if self.detected != bool(self.detections):
            raise ValueError("Envelope detected/detections inconsistente")
        for item in self.detections:
            expected = type(item).model_fields["Smell"].default
            if not item.detected or item.Smell.strip().lower() != expected.strip().lower():
                raise ValueError("Detecção incompatível com o schema de smell")
        return self


class MultipleComplexMethodResponse(SmellResponse):
    detections: list[ComplexMethodDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongMethodResponse(SmellResponse):
    detections: list[LongMethodDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleComplexConditionalResponse(SmellResponse):
    detections: list[ComplexConditionalDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongParameterListResponse(SmellResponse):
    detections: list[LongParameterListDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongStatementResponse(SmellResponse):
    detections: list[LongStatementDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongIdentifierResponse(SmellResponse):
    detections: list[LongIdentifierDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleMagicNumberResponse(SmellResponse):
    detections: list[MagicNumberDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongMessageChainResponse(SmellResponse):
    detections: list[LongMessageChainDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongLambdaResponse(SmellResponse):
    detections: list[LongLambdaFunctionDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleEmptyCatchBlockResponse(SmellResponse):
    detections: list[EmptyCatchBlockDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleMissingDefaultResponse(SmellResponse):
    detections: list[MissingDefaultDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)
