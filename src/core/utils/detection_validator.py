"""Validador pós-processamento para filtrar falsos positivos das detecções."""

import re
import math
from core.smell_rules import THRESHOLDS, MAGIC_NUMBER_EXCEPTIONS
from typing import Any, Dict


class DetectionValidator:
    """Valida detecções para remover falsos positivos óbvios."""

    TRIVIAL_MAGIC_NUMBERS = {"0", "1", "-1", "0.0", "1.0", "-1.0"}

    # Módulos/bibliotecas comuns que não são message chains
    MODULE_PREFIXES = {
        "os.", "sys.", "re.", "json.", "math.", "random.", "datetime.",
        "pathlib.", "collections.", "itertools.", "functools.", "typing.",
        "jax.", "np.", "numpy.", "torch.", "tf.", "tensorflow.",
        "optax.", "flax.", "haiku.", "chex.",
        "pd.", "pandas.", "plt.", "matplotlib.",
        "urllib.", "http.", "socket.", "subprocess.",
    }

    # Identificadores que são de bibliotecas, não do usuário
    LIBRARY_IDENTIFIERS = {
        "jax", "numpy", "np", "torch", "tensorflow", "tf", "optax", "flax",
        "pandas", "pd", "matplotlib", "plt", "scipy", "sklearn",
    }

    @staticmethod
    def validate_detection(detection: Dict[str, Any]) -> bool:
        """
        Valida se uma detecção é realmente um smell válido.

        Returns:
            True se a detecção é válida, False se deve ser filtrada.
        """
        smell = detection.get("Smell", "").lower()

        smell_normalized = smell.strip()

        if "long identifier" in smell_normalized:
            return DetectionValidator._validate_long_identifier(detection)

        if "long method" in smell_normalized:
            return DetectionValidator._validate_long_method(detection)

        if "long statement" in smell_normalized:
            return DetectionValidator._validate_long_statement(detection)

        if "magic number" in smell_normalized:
            return DetectionValidator._validate_magic_number(detection)

        if "long lambda" in smell_normalized:
            return DetectionValidator._validate_long_lambda(detection)

        if "complex method" in smell_normalized:
            return DetectionValidator._validate_complex_method(detection)

        if "long parameter" in smell_normalized:
            return DetectionValidator._validate_long_parameter_list(detection)

        if (
            "long message chain" in smell_normalized
            or "message chain" in smell_normalized
        ):
            return DetectionValidator._validate_long_message_chain(detection)

        if "complex conditional" in smell_normalized:
            return DetectionValidator._validate_complex_conditional(detection)

        return True

    @staticmethod
    def _validate_long_identifier(detection: Dict[str, Any]) -> bool:
        """Valida Long Identifier: só aceitar se estritamente > threshold e não for de biblioteca."""
        length = detection.get("length", 0)
        threshold = THRESHOLDS['long identifier']
        identifier_name = detection.get("identifier_name", "")
        description = detection.get("Description", "")

        try:
            length_val = float(length) if length else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Se não tiver length, tentar extrair da descrição
        if length_val == 0:
            match = re.search(r"(\d+)\s*characters?", description, re.IGNORECASE)
            if match:
                try:
                    length_val = float(match.group(1))
                except (ValueError, TypeError):
                    # Se não conseguir extrair, deixar passar
                    return True
            else:
                # Não conseguiu determinar o tamanho - deixar passar para não perder TPs
                return True

        # Verificar se é identifier de biblioteca (apenas se tiver nome)
        return length_val > threshold_val

    @staticmethod
    def _validate_long_statement(detection: Dict[str, Any]) -> bool:
        """Valida Long Statement: só aceitar se estritamente > threshold."""
        line_length = detection.get("line_length", 0)
        threshold = THRESHOLDS['long statement']
        description = detection.get("Description", "")

        try:
            length_val = float(line_length) if line_length else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Se não tiver line_length, tentar extrair da descrição
        if length_val == 0:
            match = re.search(r"(\d+)\s*characters?", description, re.IGNORECASE)
            if match:
                try:
                    length_val = float(match.group(1))
                except (ValueError, TypeError):
                    return True
            else:
                # Não conseguiu determinar - deixar passar
                return True

        # Filtrar descrições que indicam que não é smell
        desc_lower = description.lower()
        if any(
            phrase in desc_lower
            for phrase in [
                "under threshold",
                "no violation",
                "within acceptable",
            ]
        ):
            return False

        return length_val > threshold_val

    @staticmethod
    def _validate_magic_number(detection: Dict[str, Any]) -> bool:
        """As unicas excecoes numericas sao 0, 1 e -1."""
        value = detection.get("number")
        if value is None:
            match = re.search(r"Magic number\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)",
                              str(detection.get("Description", "")), re.IGNORECASE)
            value = match.group(1) if match else None
        if value is None:
            return True  # Politica original; sem evidencia numerica nao ha TP no avaliador.
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return math.isfinite(number) and number not in MAGIC_NUMBER_EXCEPTIONS

    @staticmethod
    def _validate_long_lambda(detection: Dict[str, Any]) -> bool:
        """Valida Long Lambda: só aceitar se estritamente > threshold."""
        lambda_length = detection.get("lambda_length", 0)
        threshold = THRESHOLDS['long lambda function']
        description = detection.get("Description", "")

        try:
            length_val = float(lambda_length) if lambda_length else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Se não tiver lambda_length, tentar extrair da descrição
        if length_val == 0:
            match = re.search(r"(\d+)\s*characters?", description, re.IGNORECASE)
            if match:
                try:
                    length_val = float(match.group(1))
                except (ValueError, TypeError):
                    return True
            else:
                # Não conseguiu determinar - deixar passar
                return True

        return length_val > threshold_val

    @staticmethod
    def _validate_complex_method(detection: Dict[str, Any]) -> bool:
        """Valida Complex Method: só aceitar se estritamente > threshold (CC > 7)."""
        cc = detection.get("cyclomatic_complexity", 0)
        threshold = THRESHOLDS['complex method']
        description = detection.get("Description", "")

        try:
            cc_val = float(cc) if cc else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Se não tiver cyclomatic_complexity, tentar extrair da descrição
        if cc_val == 0:
            patterns = [
                r"cyclomatic complexity of (\d+)",
                r"CC\s*=?\s*(\d+)",
                r"complexity\s*(?:of|is|:)?\s*(\d+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    try:
                        cc_val = float(match.group(1))
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Se não conseguiu extrair, deixar passar
            if cc_val == 0:
                return True

        return cc_val > threshold_val

    @staticmethod
    def _validate_long_parameter_list(detection: Dict[str, Any]) -> bool:
        """Valida Long Parameter List: só aceitar se estritamente > threshold (> 4)."""
        param_count = detection.get("parameter_count", 0)
        threshold = THRESHOLDS['long parameter list']
        description = detection.get("Description", "")

        try:
            count_val = float(param_count) if param_count else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Se não tiver parameter_count, tentar extrair da descrição
        if count_val == 0:
            patterns = [
                r"has (\d+) parameters?",
                r"(\d+)\s*parameters?",
            ]
            for pattern in patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    try:
                        count_val = float(match.group(1))
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Se não conseguiu extrair, deixar passar
            if count_val == 0:
                return True

        return count_val > threshold_val

    @staticmethod
    def _validate_long_message_chain(detection: Dict[str, Any]) -> bool:
        """Valida Long Message Chain: só aceitar se > 2 métodos encadeados."""
        chain_length = detection.get("chain_length", 0)
        threshold = THRESHOLDS['long message chain']
        description = detection.get("Description", "")

        try:
            length_val = float(chain_length) if chain_length else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Se não tiver chain_length, tentar extrair da descrição
        if length_val == 0:
            # Tentar vários padrões
            patterns = [
                r"has (\d+) chained methods?",
                r"chain.*?(\d+)\s*methods?",
                r"(\d+)\s*chained",
            ]
            for pattern in patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    try:
                        length_val = float(match.group(1))
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Se ainda não encontrou, deixar passar para não perder TPs
            if length_val == 0:
                return True

        return length_val > threshold_val

    @staticmethod
    def _validate_complex_conditional(detection: Dict[str, Any]) -> bool:
        """Valida Complex Conditional: só aceitar se > 2 operadores lógicos."""
        logical_operators = detection.get("logical_operators", 0)
        threshold = THRESHOLDS['complex conditional']
        description = detection.get("Description", "")

        try:
            ops_val = float(logical_operators) if logical_operators else 0
            threshold_val = float(threshold)
        except (ValueError, TypeError):
            return True

        # Tentar extrair da descrição se não tiver o campo
        if ops_val == 0:
            patterns = [
                r"has (\d+) logical operators?",
                r"(\d+)\s*logical\s*operators?",
                r"(\d+)\s*(?:and|or)\s*operators?",
            ]
            for pattern in patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    try:
                        ops_val = float(match.group(1))
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Se não conseguiu extrair, deixar passar
            if ops_val == 0:
                return True

        return ops_val > threshold_val

    @staticmethod
    def _validate_long_method(detection: Dict[str, Any]) -> bool:
        value = detection.get("total_lines")
        if value is None:
            return True
        try:
            return math.isfinite(float(value)) and float(value) > THRESHOLDS['long method']
        except (TypeError, ValueError):
            return False

    @staticmethod
    def filter_detections(detections: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """
        Filtra uma lista de detecções, removendo falsos positivos.

        Args:
            detections: Lista de detecções (dicts ou objetos Pydantic)

        Returns:
            Lista filtrada de detecções válidas
        """
        filtered = []
        validator = DetectionValidator()

        for detection in detections:
            if hasattr(detection, "model_dump"):
                detection_dict = detection.model_dump()
            elif hasattr(detection, "dict"):
                detection_dict = detection.dict()
            else:
                detection_dict = detection

            if validator.validate_detection(detection_dict):
                filtered.append(detection)

        return filtered
