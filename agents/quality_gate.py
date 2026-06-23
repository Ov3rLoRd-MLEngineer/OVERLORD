"""
agents/quality_gate.py — Agent Validation Workflow V1.60
Vérifie la santé d'un workflow ComfyUI JSON avant envoi.
Refuse et logue si nœuds corrompus, class_type manquants, inputs orphelins.
Pattern recommandé dans rapport_diag_final.txt.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

GATE_LOG = Path("workspace/logs/quality_gate.jsonl")

# Nœuds UI LiteGraph interdits en mode API
FORBIDDEN_CLASS_TYPES = {
    "Reroute", "Note", "PrimitiveNode",
    "Lora Loader (LoraManager)", "TriggerWord Toggle (LoraManager)",
    "LoraStackManager (LoraManager)",
}

# Node IDs attendus par agent_supervisor_v2.py
REQUIRED_NODE_IDS = [
    "62", "87", "99", "111", "112", "75", "77",
    "334", "303", "382", "301", "380", "68",
]


def validate_workflow(workflow: dict,
                      logger: logging.Logger = None) -> dict:
    """
    Valide un workflow ComfyUI API format.
    Retourne : {"valid": bool, "errors": list, "warnings": list, "node_count": int}
    """
    log = logger or logging.getLogger("quality_gate")
    errors   = []
    warnings = []

    if not isinstance(workflow, dict) or not workflow:
        errors.append("Workflow vide ou format invalide")
        return {"valid": False, "errors": errors, "warnings": warnings, "node_count": 0}

    node_count = len(workflow)

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errors.append(f"Node {node_id} : format invalide (pas un dict)")
            continue

        ct = node.get("class_type")

        # class_type None
        if ct is None:
            errors.append(f"Node {node_id} : class_type=None (nœud fantôme)")
            continue

        # Nœuds UI interdits
        if ct in FORBIDDEN_CLASS_TYPES:
            errors.append(f"Node {node_id} : class_type='{ct}' interdit en mode API")

        # Vérifier les inputs : références vers des nodes inexistants
        inputs = node.get("inputs", {})
        for inp_key, inp_val in inputs.items():
            if isinstance(inp_val, list) and len(inp_val) == 2:
                ref_node_id = str(inp_val[0])
                if ref_node_id not in workflow:
                    errors.append(
                        f"Node {node_id} ({ct}) input[{inp_key}] -> "
                        f"node {ref_node_id} INTROUVABLE (lien orphelin)"
                    )

    # Nodes IDs requis par le supervisor
    missing_required = [n for n in REQUIRED_NODE_IDS if n not in workflow]
    if missing_required:
        warnings.append(f"Node IDs supervisor manquants : {missing_required}")

    valid = len(errors) == 0
    result = {
        "valid":      valid,
        "errors":     errors,
        "warnings":   warnings,
        "node_count": node_count,
        "timestamp":  datetime.now().isoformat(),
    }

    if errors:
        log.error(f"[QUALITY_GATE] REJET — {len(errors)} erreur(s) | {node_count} nœuds")
        for e in errors:
            log.error(f"  ✗ {e}")
    else:
        log.info(f"[QUALITY_GATE] PASS — {node_count} nœuds | {len(warnings)} avertissement(s)")

    for w in warnings:
        log.warning(f"  ⚠ {w}")

    # Log JSONL
    GATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(GATE_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + '\n')

    if BUS_OK:
        try:
            get_bus().write("quality_gate.last_valid",    valid,       agent_id="quality_gate")
            get_bus().write("quality_gate.last_errors",   len(errors), agent_id="quality_gate")
        except Exception:
            pass

    return result


def validate_workflow_file(path: str | Path,
                            logger: logging.Logger = None) -> dict:
    """Charge et valide un fichier workflow JSON."""
    log = logger or logging.getLogger("quality_gate")
    p = Path(path)
    if not p.exists():
        return {"valid": False, "errors": [f"Fichier introuvable : {path}"],
                "warnings": [], "node_count": 0}
    try:
        wf = json.loads(p.read_text(encoding='utf-8'))
        return validate_workflow(wf, logger=log)
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"JSON invalide : {e}"],
                "warnings": [], "node_count": 0}


def auto_fix(workflow: dict, logger: logging.Logger = None) -> tuple:
    """
    Tente de corriger automatiquement les problèmes simples :
    - Supprime les nœuds class_type None
    - Supprime les nœuds UI interdits (Reroute, PrimitiveNode)
    - Supprime les liens orphelins en les remplaçant par ""
    Retourne (workflow_corrigé, nb_fixes_appliqués)
    """
    import copy
    log = logger or logging.getLogger("quality_gate.autofix")
    wf    = copy.deepcopy(workflow)
    fixes = 0

    # Supprimer nœuds interdits / fantômes
    to_remove = [
        nid for nid, node in wf.items()
        if not isinstance(node, dict) or
           node.get("class_type") is None or
           node.get("class_type") in FORBIDDEN_CLASS_TYPES
    ]
    for nid in to_remove:
        ct = wf[nid].get("class_type", "None") if isinstance(wf[nid], dict) else "?"
        log.warning(f"[QUALITY_GATE/AUTOFIX] Suppression node {nid} ({ct})")
        del wf[nid]
        fixes += 1

    # Remplacer les liens orphelins par "" (inline vide)
    node_ids = set(wf.keys())
    for node_id, node in wf.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        for inp_key, inp_val in list(inputs.items()):
            if isinstance(inp_val, list) and len(inp_val) == 2:
                ref = str(inp_val[0])
                if ref not in node_ids:
                    log.warning(
                        f"[QUALITY_GATE/AUTOFIX] Node {node_id} input[{inp_key}] "
                        f"-> node {ref} manquant : remplacement par ''"
                    )
                    inputs[inp_key] = ""
                    fixes += 1

    log.info(f"[QUALITY_GATE/AUTOFIX] {fixes} corrections appliquées")
    return wf, fixes


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    wf_path = "Combined_V35_API.json"
    print(f"Validation de {wf_path}...")
    result = validate_workflow_file(wf_path)
    print(f"Valide : {result['valid']}")
    print(f"Nœuds  : {result['node_count']}")
    if result['errors']:
        print("Erreurs :")
        for e in result['errors']:
            print(f"  {e}")
    if result['warnings']:
        print("Avertissements :")
        for w in result['warnings']:
            print(f"  {w}")
