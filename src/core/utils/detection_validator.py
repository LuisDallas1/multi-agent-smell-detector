"""Validação estrutural compartilhada; classificações são avaliadas contra o DPy."""
from typing import Any, Dict
from core.schemas.agent_response import validate_inference_item


class DetectionValidator:
    """Não apaga previsões por contagens ou regras semânticas autodeclaradas.

    Os envelopes Pydantic validam a resposta original antes desta etapa.
    Uma classificação incorreta, inclusive Magic number 0/1/-1, permanece
    como previsão e pode ser FP no avaliador em vez de desaparecer.
    """

    @staticmethod
    def validate_detection(detection: Dict[str, Any]) -> bool:
        smell = str(detection.get("Smell", "")).strip().lower()
        if not smell:
            return False
        try:
            validate_inference_item(detection, smell)
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def filter_detections(detections: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return [d for d in detections if DetectionValidator.validate_detection(
            d.model_dump() if hasattr(d, "model_dump") else d)]
