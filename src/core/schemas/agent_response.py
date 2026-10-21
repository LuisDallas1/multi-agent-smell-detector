"""Schemas Pydantic para respostas estruturadas dos agentes."""

from typing import Optional, Union
from pydantic import BaseModel, Field, field_validator
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


class MultipleComplexMethodResponse(BaseModel):
    detections: list[ComplexMethodDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongMethodResponse(BaseModel):
    detections: list[LongMethodDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleComplexConditionalResponse(BaseModel):
    detections: list[ComplexConditionalDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongParameterListResponse(BaseModel):
    detections: list[LongParameterListDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongStatementResponse(BaseModel):
    detections: list[LongStatementDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongIdentifierResponse(BaseModel):
    detections: list[LongIdentifierDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleMagicNumberResponse(BaseModel):
    detections: list[MagicNumberDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongMessageChainResponse(BaseModel):
    detections: list[LongMessageChainDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleLongLambdaResponse(BaseModel):
    detections: list[LongLambdaFunctionDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleEmptyCatchBlockResponse(BaseModel):
    detections: list[EmptyCatchBlockDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)


class MultipleMissingDefaultResponse(BaseModel):
    detections: list[MissingDefaultDetection] = Field(default_factory=list)
    detected: bool = Field(default=False)
