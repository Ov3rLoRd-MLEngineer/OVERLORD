# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# session_manager.py — Ov3rLoRd Pipeline
# Gestion état de session : seed, IPAdapter source, SSIM, statut, rollback
# Format A compatible — py -3.12

import json
from pathlib import Path
from datetime import datetime

SESSION_STATE_VERSION = "1.0"


# ─────────────────────────────────────────────
#  INIT / LOAD / SAVE
# ─────────────────────────────────────────────

def load_session(path: str) -> dict | None:
    """Charge une session existante depuis son fichier JSON."""
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_session(state: dict, path: str) -> None:
    """Sauvegarde la session sur disque (écrasement atomique)."""
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    Path(tmp).replace(path)


def create_session(
    output_dir: str,
    global_anchor: str,
    shots_config: list[dict],
    session_path: str | None = None,
) -> dict:
    """
    Crée une nouvelle session.

    shots_config exemple :
        [{"shot_id": 1, "frame_start": 0, "frame_end": 143,
          "seed": -1, "ipadapter_source": None}, ...]
    """
    state = {
        "version": SESSION_STATE_VERSION,
        "created_at": datetime.now().isoformat(),
        "global_anchor": str(global_anchor),
        "output_dir": str(output_dir),
        "shots": [],
    }

    for s in shots_config:
        state["shots"].append({
            "shot_id":          s["shot_id"],
            "seed":             s.get("seed", -1),
            "ipadapter_source": s.get("ipadapter_source") or str(global_anchor),
            "frame_start":      s["frame_start"],
            "frame_end":        s["frame_end"],
            "status":           "pending",   # pending / running / done / failed
            "rollback_point":   None,        # frame_id de la dernière frame validée
            "keyframe_anchor":  None,        # keyframe maître validée humainement
            "frames":           [],
        })

    if session_path:
        save_session(state, session_path)

    return state


# ─────────────────────────────────────────────
#  ACCESSEURS
# ─────────────────────────────────────────────

def get_shot(state: dict, shot_id: int) -> dict | None:
    for s in state["shots"]:
        if s["shot_id"] == shot_id:
            return s
    return None


def get_shot_for_frame(state: dict, frame_id: int) -> dict | None:
    for s in state["shots"]:
        if s["frame_start"] <= frame_id <= s["frame_end"]:
            return s
    return None


# ─────────────────────────────────────────────
#  MISE À JOUR FRAME
# ─────────────────────────────────────────────

def update_frame(
    state: dict,
    shot_id: int,
    frame_id: int,
    status: str,
    ssim_score: float | None = None,
    drift_flag: bool = False,
    seed: int | None = None,
    ipadapter_source: str | None = None,
) -> None:
    """
    status : generated | validated | rejected | reprendre
    En cas de status == 'validated', met à jour rollback_point du shot.
    """
    shot = get_shot(state, shot_id)
    if shot is None:
        return

    # Mise à jour si la frame existe déjà
    for f in shot["frames"]:
        if f["frame_id"] == frame_id:
            f["status"]     = status
            f["drift_flag"] = drift_flag
            if ssim_score is not None:
                f["ssim_score"] = ssim_score
            if seed is not None:
                f["seed"] = seed
            if ipadapter_source is not None:
                f["ipadapter_source"] = ipadapter_source
            f["updated_at"] = datetime.now().isoformat()
            if status == "validated":
                shot["rollback_point"] = frame_id
            return

    # Nouvelle entrée
    entry = {
        "frame_id":        frame_id,
        "status":          status,
        "ssim_score":      ssim_score,
        "drift_flag":      drift_flag,
        "seed":            seed,
        "ipadapter_source": ipadapter_source,
        "generated_at":    datetime.now().isoformat(),
    }
    shot["frames"].append(entry)
    if status == "validated":
        shot["rollback_point"] = frame_id


# ─────────────────────────────────────────────
#  ROLLBACK & REPRISE
# ─────────────────────────────────────────────

def get_rollback_frame(state: dict, shot_id: int) -> int | None:
    """Retourne le frame_id du dernier point de rollback validé pour ce shot."""
    shot = get_shot(state, shot_id)
    if shot is None:
        return None
    return shot["rollback_point"]


def get_resume_frame(state: dict, shot_id: int) -> int:
    """
    Retourne le frame_id depuis lequel reprendre la génération.
    = rollback_point + 1, ou frame_start si aucun point validé.
    """
    shot = get_shot(state, shot_id)
    if shot is None:
        return 0
    rb = shot["rollback_point"]
    if rb is None:
        return shot["frame_start"]
    return rb + 1


def mark_shot_for_resume(state: dict, shot_id: int, from_frame: int | None = None) -> None:
    """
    Marque un shot pour reprise depuis from_frame
    (ou depuis rollback_point si from_frame=None).
    Réinitialise les frames >= from_frame à status 'reprendre'.
    """
    shot = get_shot(state, shot_id)
    if shot is None:
        return

    start = from_frame if from_frame is not None else get_resume_frame(state, shot_id)
    shot["status"] = "pending"

    for f in shot["frames"]:
        if f["frame_id"] >= start:
            f["status"] = "reprendre"
            f["drift_flag"] = True


def rollback_shot(state: dict, shot_id: int, to_frame: int) -> None:
    """
    Rollback dur : supprime toutes les entrées de frame > to_frame pour ce shot.
    Met à jour rollback_point = to_frame.
    """
    shot = get_shot(state, shot_id)
    if shot is None:
        return
    shot["frames"] = [f for f in shot["frames"] if f["frame_id"] <= to_frame]
    shot["rollback_point"] = to_frame
    shot["status"] = "pending"


# ─────────────────────────────────────────────
#  IPADAPTER SOURCE LOGIC
# ─────────────────────────────────────────────

def get_ipadapter_source(
    state: dict,
    shot_id: int,
    frame_id: int,
    mode: str = "rolling",       # "fixed" | "rolling" | "hybrid"
    hybrid_prev_weight: float = 0.70,
) -> dict:
    """
    Retourne la source IPAdapter à utiliser pour frame_id.

    Retourne un dict :
        {
          "mode": "fixed" | "rolling" | "hybrid",
          "primary": path_str,          # ancre globale ou frame N-1 validée
          "secondary": path_str | None, # pour hybrid : ancre globale
          "primary_weight": float,
          "secondary_weight": float,
        }
    """
    global_anchor = state["global_anchor"]
    shot = get_shot(state, shot_id)

    if mode == "fixed" or shot is None:
        return {
            "mode": "fixed",
            "primary": global_anchor,
            "secondary": None,
            "primary_weight": 1.0,
            "secondary_weight": 0.0,
        }

    # Cherche la dernière frame validée < frame_id
    validated = [
        f for f in shot["frames"]
        if f["status"] == "validated" and f["frame_id"] < frame_id
    ]

    if not validated:
        # Pas encore de frame validée → ancre globale
        return {
            "mode": "fixed",
            "primary": global_anchor,
            "secondary": None,
            "primary_weight": 1.0,
            "secondary_weight": 0.0,
        }

    last_validated = max(validated, key=lambda x: x["frame_id"])
    output_dir = state["output_dir"]
    prev_path = str(
        Path(output_dir) / f"frame_{last_validated['frame_id']:04d}_00001_.png"
    )

    # Vérification existence fichier
    if not Path(prev_path).exists():
        prev_path = global_anchor

    if mode == "rolling":
        return {
            "mode": "rolling",
            "primary": prev_path,
            "secondary": None,
            "primary_weight": 1.0,
            "secondary_weight": 0.0,
        }

    # mode == "hybrid"
    return {
        "mode": "hybrid",
        "primary": prev_path,
        "secondary": global_anchor,
        "primary_weight": hybrid_prev_weight,
        "secondary_weight": round(1.0 - hybrid_prev_weight, 2),
    }


# ─────────────────────────────────────────────
#  KEYFRAME PRE-VALIDATION (3 frames test)
# ─────────────────────────────────────────────

def get_prevalidation_frames(state: dict, shot_id: int) -> list[int]:
    """
    Retourne les 3 frame_ids à générer en pré-validation avant batch complet :
    début, milieu, fin du shot.
    """
    shot = get_shot(state, shot_id)
    if shot is None:
        return []
    s = shot["frame_start"]
    e = shot["frame_end"]
    mid = (s + e) // 2
    return [s, mid, e]


def prevalidation_passed(state: dict, shot_id: int) -> bool:
    """True si les 3 frames de pré-validation sont toutes validées."""
    targets = set(get_prevalidation_frames(state, shot_id))
    shot = get_shot(state, shot_id)
    if not shot:
        return False
    validated_ids = {
        f["frame_id"] for f in shot["frames"]
        if f["status"] == "validated"
    }
    return targets.issubset(validated_ids)


# ─────────────────────────────────────────────
#  RAPPORT SESSION
# ─────────────────────────────────────────────

def session_report(state: dict) -> str:
    lines = [
        f"=== SESSION Ov3rLoRd — {state.get('created_at', '?')} ===",
        f"Ancre globale : {state['global_anchor']}",
        "",
    ]
    for shot in state["shots"]:
        total = shot["frame_end"] - shot["frame_start"] + 1
        done  = sum(1 for f in shot["frames"] if f["status"] == "validated")
        drift = sum(1 for f in shot["frames"] if f.get("drift_flag"))
        rb    = shot["rollback_point"]
        lines.append(
            f"Shot {shot['shot_id']:02d} | frames {shot['frame_start']:04d}→{shot['frame_end']:04d}"
            f" | validées {done}/{total}"
            f" | drift {drift}"
            f" | rollback frame {rb if rb is not None else 'N/A'}"
            f" | status : {shot['status']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    # Test rapide
    from agents.session_manager import create_session, update_frame, session_report, get_ipadapter_source

    SHOTS = [
        {"shot_id": 1, "frame_start": 0,   "frame_end": 143,  "seed": -1},
        {"shot_id": 2, "frame_start": 144,  "frame_end": 287,  "seed": -1},
        {"shot_id": 3, "frame_start": 288,  "frame_end": 431,  "seed": -1},
        {"shot_id": 4, "frame_start": 432,  "frame_end": 623,  "seed": -1},
        {"shot_id": 5, "frame_start": 624,  "frame_end": 815,  "seed": -1},
        {"shot_id": 6, "frame_start": 816,  "frame_end": 1007, "seed": -1},
    ]

    state = create_session(
        output_dir=r"D:\Ov3rLoRd AI\ComfyUI\output\asuka_run",
        global_anchor=r"D:\OVERLORD\DEMO\frame_0000_00001_.png",
        shots_config=SHOTS,
        session_path=r"D:\OVERLORD\DEMO\session_state.json",
    )

    update_frame(state, 1, 0,  "validated", ssim_score=1.0, seed=42)
    update_frame(state, 1, 1,  "validated", ssim_score=0.82, seed=42)
    update_frame(state, 1, 72, "validated", ssim_score=0.76, seed=42)

    print(session_report(state))
    ipa = get_ipadapter_source(state, 1, 5, mode="rolling")
    print(f"IPAdapter pour frame 5 : {ipa}")
