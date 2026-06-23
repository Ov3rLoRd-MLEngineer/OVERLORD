"""
agents/schema_validator.py — Agent Validateur de Schéma V1.60
Valide la structure de tout objet JSON critique avant transmission.
Refuse les workflows ComfyUI corrompus, scripts invalides, storyboards incomplets.
Ne laisse JAMAIS passer un JSON corrompu vers ComfyUI.
"""

import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

LOG_DIR = Path("workspace/logs")

# ── Schémas de validation ─────────────────────────────────────────────

SCHEMA_COMFYUI_WORKFLOW = {
    "type": "dict",
    "required_keys": [],          # node IDs variables
    "each_value": {
        "type": "dict",
        "required_keys": ["class_type", "inputs"],
        "forbidden_values": {
            "class_type": [None, "", "Lora Loader (LoraManager)",
                           "TriggerWord Toggle (LoraManager)", "Reroute",
                           "PrimitiveNode"]
        }
    }
}

SCHEMA_SCRIPT = {
    "type": "dict",
    "required_keys": ["title", "synopsis", "acts"],
    "key_types": {
        "title":    str,
        "synopsis": str,
        "acts":     list,
    }
}

SCHEMA_STORYBOARD = {
    "type": "dict",
    "required_keys": ["shots"],
    "key_types": {"shots": list},
    "min_list_len": {"shots": 1}
}

SCHEMA_JOB = {
    "type": "dict",
    "required_keys": ["positive"],
    "key_types": {"positive": str}
}

SCHEMAS = {
    "comfyui_workflow": SCHEMA_COMFYUI_WORKFLOW,
    "script":           SCHEMA_SCRIPT,
    "storyboard":       SCHEMA_STORYBOARD,
    "job":              SCHEMA_JOB,
}


class ValidationResult:
    def __init__(self, valid: bool, errors: list[str], warnings: list[str],
                 schema_name: str, checksum: str = ""):
        self.valid     = valid
        self.errors    = errors
        self.warnings  = warnings
        self.schema    = schema_name
        self.checksum  = checksum
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "valid":     self.valid,
            "errors":    self.errors,
            "warnings":  self.warnings,
            "schema":    self.schema,
            "checksum":  self.checksum,
            "timestamp": self.timestamp,
        }

    def __bool__(self):
        return self.valid


def _checksum(data: Any) -> str:
    try:
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]
    except Exception:
        return "?"


def _validate_against_schema(data: Any, schema: dict,
                               path: str = "") -> tuple[list, list]:
    errors   = []
    warnings = []

    if schema.get("type") == "dict":
        if not isinstance(data, dict):
            errors.append(f"{path}: attendu dict, reçu {type(data).__name__}")
            return errors, warnings

        # Clés requises
        for k in schema.get("required_keys", []):
            if k not in data:
                errors.append(f"{path}: clé requise manquante '{k}'")

        # Types des clés
        for k, expected_type in schema.get("key_types", {}).items():
            if k in data and not isinstance(data[k], expected_type):
                errors.append(
                    f"{path}.{k}: type attendu {expected_type.__name__}, "
                    f"reçu {type(data[k]).__name__}"
                )

        # Valeurs interdites
        for k, forbidden in schema.get("forbidden_values", {}).items():
            if k in data and data[k] in forbidden:
                errors.append(
                    f"{path}.{k}: valeur interdite '{data[k]}' "
                    f"(LoraManager/Reroute/None non supportés en mode API)"
                )

        # Longueur min des listes
        for k, min_len in schema.get("min_list_len", {}).items():
            if k in data and isinstance(data[k], list) and len(data[k]) < min_len:
                errors.append(f"{path}.{k}: liste vide (min {min_len} élément)")

        # Validation récursive des valeurs
        if "each_value" in schema:
            sub_schema = schema["each_value"]
            for k, v in data.items():
                sub_errors, sub_warns = _validate_against_schema(
                    v, sub_schema, path=f"{path}[{k}]"
                )
                errors   += sub_errors
                warnings += sub_warns

    elif schema.get("type") == "list":
        if not isinstance(data, list):
            errors.append(f"{path}: attendu list, reçu {type(data).__name__}")

    return errors, warnings


def validate(data: Any, schema_name: str,
             logger: logging.Logger = None) -> ValidationResult:
    """
    Valide data contre le schéma nommé.
    Retourne ValidationResult — booléen si utilisé dans un if.
    """
    log      = logger or logging.getLogger("schema_validator")
    schema   = SCHEMAS.get(schema_name)
    checksum = _checksum(data)

    if schema is None:
        log.warning(f"[VALIDATOR] Schéma inconnu '{schema_name}' — validation ignorée")
        return ValidationResult(True, [], [f"Schéma '{schema_name}' non défini"], schema_name, checksum)

    errors, warnings = _validate_against_schema(data, schema, path=schema_name)

    result = ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        schema_name=schema_name,
        checksum=checksum,
    )

    if result.valid:
        log.debug(f"[VALIDATOR] ✓ {schema_name} | checksum={checksum} | {len(warnings)} warnings")
    else:
        log.error(f"[VALIDATOR] ✗ {schema_name} | {len(errors)} erreurs | checksum={checksum}")
        for e in errors:
            log.error(f"  → {e}")

    for w in warnings:
        log.warning(f"[VALIDATOR] ⚠ {w}")

    # Log sur le bus
    if BUS_OK:
        try:
            get_bus().write(
                f"validator.{schema_name}.last",
                result.to_dict(),
                agent_id="schema_validator"
            )
        except Exception:
            pass

    return result


def validate_comfyui_workflow(workflow: dict,
                               logger: logging.Logger = None) -> ValidationResult:
    """Validation spécialisée workflow ComfyUI."""
    log = logger or logging.getLogger("schema_validator")
    result = validate(workflow, "comfyui_workflow", logger=log)

    # Checks additionnels spécifiques ComfyUI
    extra_errors = []
    if isinstance(workflow, dict):
        # Vérifier que les node IDs supervisor existent
        required_nodes = ["62", "87", "99", "111", "112", "75", "77", "334"]
        missing = [n for n in required_nodes if n not in workflow]
        if missing:
            extra_errors.append(f"Node IDs supervisor manquants : {missing}")

        # Vérifier aucun class_type None
        null_nodes = [k for k, v in workflow.items()
                      if isinstance(v, dict) and v.get("class_type") is None]
        if null_nodes:
            extra_errors.append(f"Nodes avec class_type=None : {null_nodes}")

    if extra_errors:
        result.errors.extend(extra_errors)
        result.valid = False
        for e in extra_errors:
            log.error(f"[VALIDATOR] ✗ comfyui_workflow : {e}")

    return result


def validate_jobs(jobs: list[dict],
                  logger: logging.Logger = None) -> ValidationResult:
    """Valide une liste de jobs supervisor."""
    log    = logger or logging.getLogger("schema_validator")
    errors = []

    if not isinstance(jobs, list):
        return ValidationResult(False, ["jobs: doit être une liste"], [], "jobs", _checksum(jobs))
    if len(jobs) == 0:
        return ValidationResult(False, ["jobs: liste vide"], [], "jobs", "empty")

    for i, job in enumerate(jobs):
        r = validate(job, "job", logger=log)
        if not r.valid:
            errors.extend([f"job[{i}]: {e}" for e in r.errors])

    result = ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=[],
        schema_name="jobs",
        checksum=_checksum(jobs),
    )
    log.info(f"[VALIDATOR] Jobs : {len(jobs) - len(errors)}/{len(jobs)} valides")
    return result


def load_and_validate_workflow(path: str,
                                logger: logging.Logger = None) -> tuple[dict | None, ValidationResult]:
    """Charge un fichier JSON workflow et le valide."""
    log = logger or logging.getLogger("schema_validator")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        err = f"Impossible de charger {path} : {e}"
        log.error(f"[VALIDATOR] {err}")
        return None, ValidationResult(False, [err], [], "comfyui_workflow")

    result = validate_comfyui_workflow(data, logger=log)
    return data if result.valid else None, result


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG)

    # Test workflow OK
    wf_ok = {
        "62":  {"class_type": "LoraLoader",            "inputs": {"lora_name": "test.safetensors"}},
        "87":  {"class_type": "CLIPTextEncode",        "inputs": {"text": "masterpiece"}},
        "99":  {"class_type": "CLIPTextEncode",        "inputs": {"text": "masterpiece"}},
        "111": {"class_type": "CLIPTextEncode",        "inputs": {"text": "bad quality"}},
        "112": {"class_type": "Seed (rgthree)",        "inputs": {"seed": 42}},
        "75":  {"class_type": "easy int",              "inputs": {"value": 1024}},
        "77":  {"class_type": "easy int",              "inputs": {"value": 1536}},
        "334": {"class_type": "SaveImage",             "inputs": {"filename_prefix": "out"}},
    }
    r = validate_comfyui_workflow(wf_ok)
    print(f"Workflow OK  : valid={r.valid} | errors={r.errors}")

    # Test workflow corrompu
    wf_bad = {"62": {"class_type": "Lora Loader (LoraManager)", "inputs": {}}}
    r2 = validate_comfyui_workflow(wf_bad)
    print(f"Workflow BAD : valid={r2.valid} | errors={r2.errors[:2]}")

    # Test script
    script_ok = {"title": "Test", "synopsis": "A story", "acts": [{"act": 1}]}
    r3 = validate(script_ok, "script")
    print(f"Script OK    : valid={r3.valid}")
