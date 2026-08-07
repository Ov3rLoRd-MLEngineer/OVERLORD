"""
agents/critic.py — Agent Critique OverLord
Intercepte et valide TOUS les échanges entre agents.

Rôles :
  1. validate_handoff()   → vérifie que la sortie d'un bloc est consommable par le suivant
  2. watch_loopback()     → détecte les boucles infinies et les dégradations de score
  3. critique_with_llm()  → demande à Claude d'analyser un échange suspect
  4. escalate()           → décision forcée si le système est bloqué

Le Critique est appelé par maestro.py à chaque transition de bloc.
Il peut :
  - PASS   → tout est bon, continuer
  - WARN   → problème mineur, continuer avec avertissement
  - REPAIR → tentative de réparation automatique
  - REJECT → le bloc doit être relancé
  - HALT   → arrêt du pipeline, problème irrécupérable
"""

import json
import logging
import time
import requests
import hashlib
from pathlib import Path
from datetime import datetime
import os
from enum import Enum

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

def _get_api_key() -> str:
    import os
    from pathlib import Path
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key
CLAUDE_MODEL      = "claude-sonnet-4-6"
CRITIC_LOG_DIR    = Path("workspace/critic_logs")
MEDIA_TYPES_VALID = {"anime","manga","comics","3d","photoreal","art","game","short","film"}


# ============================================================
# VERDICTS
# ============================================================
class Verdict(Enum):
    PASS   = "PASS"    # OK, continuer
    WARN   = "WARN"    # Problème mineur, continuer en loggant
    REPAIR = "REPAIR"  # Réparation automatique appliquée
    REJECT = "REJECT"  # Bloc à relancer
    HALT   = "HALT"    # Arrêt pipeline


class CriticReport:
    """Rapport de l'Agent Critique sur un handoff ou un échange."""

    def __init__(self, handoff: str, verdict: Verdict,
                 issues: list = None, repairs: dict = None,
                 data_out: dict = None, score: float = 100.0):
        self.handoff  = handoff
        self.verdict  = verdict
        self.issues   = issues  or []
        self.repairs  = repairs or {}
        self.data_out = data_out        # données potentiellement réparées
        self.score    = score
        self.ts       = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "handoff":  self.handoff,
            "verdict":  self.verdict.value,
            "score":    self.score,
            "issues":   self.issues,
            "repairs":  self.repairs,
            "timestamp": self.ts,
        }

    def __repr__(self):
        return (f"CriticReport({self.handoff}) "
                f"[{self.verdict.value}] score={self.score:.0f} "
                f"issues={len(self.issues)}")


# ============================================================
# HISTORIQUE DES LOOPBACKS
# ============================================================
class LoopbackTracker:
    """
    Surveille les itérations d'un agent pour détecter :
    - Stagnation (score ne progresse plus)
    - Régression (score diminue)
    - Boucle infinie (même hash de contenu)
    """

    def __init__(self, agent_name: str, max_iterations: int = 5):
        self.agent_name     = agent_name
        self.max_iterations = max_iterations
        self.history        = []   # liste de {score, content_hash, timestamp}

    def record(self, score: float, content: dict) -> dict:
        content_hash = hashlib.md5(
            json.dumps(content, sort_keys=True, default=str).encode()
        ).hexdigest()

        entry = {
            "iteration":    len(self.history) + 1,
            "score":        score,
            "content_hash": content_hash,
            "timestamp":    time.time(),
        }
        self.history.append(entry)
        return entry

    def diagnose(self) -> dict:
        """Analyse l'historique et retourne un diagnostic."""
        if len(self.history) < 2:
            return {"status": "insufficient_data", "action": "continue"}

        scores = [h["score"] for h in self.history]
        hashes = [h["content_hash"] for h in self.history]

        # Boucle infinie : même contenu deux fois
        if len(set(hashes[-3:])) == 1 and len(hashes) >= 3:
            return {
                "status": "infinite_loop",
                "action": "halt",
                "reason": "Contenu identique sur 3 itérations consécutives",
            }

        # Régression : score diminue
        if len(scores) >= 3 and scores[-1] < scores[-3] - 10:
            return {
                "status": "regression",
                "action": "reject",
                "reason": f"Score en régression : {scores[-3]:.0f} → {scores[-1]:.0f}",
            }

        # Stagnation : moins de 2 points de progression sur 3 itérations
        if len(scores) >= 3 and abs(scores[-1] - scores[-3]) < 2:
            return {
                "status": "stagnation",
                "action": "escalate",
                "reason": f"Score stagnant : {scores[-3]:.0f} → {scores[-1]:.0f}",
            }

        # Dépassement du max
        if len(self.history) >= self.max_iterations:
            return {
                "status": "max_iterations",
                "action": "accept_best",
                "best_score": max(scores),
                "reason": f"Max itérations ({self.max_iterations}) atteint",
            }

        return {"status": "progressing", "action": "continue"}


# ============================================================
# VALIDATIONS STRUCTURELLES PAR HANDOFF
# ============================================================
def _validate_trend_report(data: dict) -> tuple:
    """Valide la sortie du bloc Sourcing avant passage au Scénario."""
    issues  = []
    repairs = {}
    score   = 100.0

    if not data.get("media_type") or data["media_type"] not in MEDIA_TYPES_VALID:
        issues.append(f"media_type invalide : '{data.get('media_type')}'")
        repairs["media_type"] = "anime"
        data["media_type"]    = "anime"
        score -= 20

    if not data.get("brief") or len(data.get("brief","")) < 10:
        issues.append("Brief trop court ou absent")
        repairs["brief"] = "Production standard animé"
        data["brief"]    = "Production standard animé"
        score -= 15

    if not data.get("hot_keywords"):
        issues.append("hot_keywords vide")
        repairs["hot_keywords"] = ["anime","action","adventure"]
        data["hot_keywords"]    = ["anime","action","adventure"]
        score -= 10

    return issues, repairs, score, data


def _validate_script(data: dict) -> tuple:
    """Valide la sortie du Scénario avant passage au Storyboard."""
    issues  = []
    repairs = {}
    score   = 100.0

    # Erreur de génération explicite
    if "error" in data:
        issues.append(f"Script contient une erreur : {data['error']}")
        score -= 80
        return issues, repairs, score, data

    if not data.get("title") or data["title"].lower() in ("untitled",""):
        issues.append("Titre absent ou générique")
        repairs["title"] = "Production Ov3rLoRd"
        data["title"]    = "Production Ov3rLoRd"
        score -= 5

    acts = data.get("acts", [])
    if not acts:
        issues.append("Aucun acte dans le script")
        score -= 60
        return issues, repairs, score, data

    total_scenes = sum(len(a.get("scenes",[])) for a in acts)
    if total_scenes == 0:
        issues.append("Aucune scène dans les actes")
        score -= 50

    # Vérifier les visual_prompt_hint
    missing_prompts = 0
    for act in acts:
        for scene in act.get("scenes", []):
            if not scene.get("visual_prompt_hint","").strip():
                missing_prompts += 1
    if missing_prompts > 0:
        issues.append(f"{missing_prompts} scènes sans visual_prompt_hint")
        score -= min(30, missing_prompts * 5)

    # Vérifier les personnages
    chars = data.get("characters", [])
    if not chars:
        issues.append("Aucun personnage défini")
        score -= 15
    else:
        missing_vp = [c["name"] for c in chars if not c.get("visual_prompt","").strip()]
        if missing_vp:
            issues.append(f"Personnages sans visual_prompt : {missing_vp}")
            score -= len(missing_vp) * 5

    return issues, repairs, score, data


def _validate_shotlist(shotlist: dict, jobs: list) -> tuple:
    """Valide la ShotList + Jobs avant passage à la Production."""
    issues  = []
    repairs = {}
    score   = 100.0

    if not shotlist or "error" in shotlist:
        issues.append("Shotlist invalide ou erreur de génération")
        score -= 80
        return issues, repairs, score, shotlist, jobs

    shots = shotlist.get("shots", [])
    if not shots:
        issues.append("Shotlist vide")
        score -= 70
        return issues, repairs, score, shotlist, jobs

    # Jobs vides
    if not jobs:
        issues.append("Aucun job généré depuis la shotlist")
        score -= 60
        # Réparation : générer des jobs depuis tous les shots
        repairs["jobs_regenerated"] = True
        jobs = _repair_jobs_from_shots(shots)
        score += 30  # récupération partielle

    # Vérifier la qualité des prompts
    empty_prompts = []
    zero_dims     = []
    for j in jobs:
        sid = j.get("shot_id","?")
        if not j.get("positive","").strip():
            empty_prompts.append(sid)
        if not j.get("width") or not j.get("height"):
            zero_dims.append(sid)

    if empty_prompts:
        issues.append(f"Prompts positifs vides : {empty_prompts[:5]}")
        score -= min(40, len(empty_prompts) * 8)
        # Réparation : prompt par défaut
        for j in jobs:
            if not j.get("positive","").strip():
                j["positive"] = "masterpiece, best quality, anime style"
        repairs["default_prompts_applied"] = len(empty_prompts)

    if zero_dims:
        issues.append(f"Dimensions manquantes : {zero_dims[:5]}")
        score -= min(20, len(zero_dims) * 5)
        for j in jobs:
            j.setdefault("width",  1024)
            j.setdefault("height", 576)
        repairs["default_dims_applied"] = len(zero_dims)

    # Doublons de shot_id
    ids = [j.get("shot_id") for j in jobs]
    dupes = [x for x in ids if ids.count(x) > 1]
    if dupes:
        issues.append(f"shot_id dupliqués : {list(set(dupes))}")
        score -= 10

    return issues, repairs, score, shotlist, jobs


def _repair_jobs_from_shots(shots: list) -> list:
    """Génère des jobs minimaux depuis les shots bruts."""
    jobs = []
    for shot in shots:
        jobs.append({
            "shot_id":  shot.get("shot_id", f"SHOT_{len(jobs):03d}"),
            "positive": shot.get("comfyui_positive", "masterpiece, best quality, anime style"),
            "negative": shot.get("comfyui_negative", "bad quality, blurry, deformed"),
            "width":    shot.get("comfyui_width",  1024),
            "height":   shot.get("comfyui_height", 576),
            "lora":     "",
            "strength": 1.0,
            "is_key_frame": True,
        })
    return jobs


def _validate_production_results(results: dict, archive_dir: Path) -> tuple:
    """Valide les résultats de production avant Post-Prod."""
    issues  = []
    repairs = {}
    score   = 100.0

    total   = results.get("total",   0)
    success = results.get("success", 0)
    failed  = results.get("failed",  0)

    if total == 0:
        issues.append("Aucun job soumis à la production")
        score -= 80
        return issues, repairs, score

    fail_rate = failed / total if total > 0 else 0
    if fail_rate > 0.5:
        issues.append(f"Taux d'échec critique : {fail_rate:.0%} ({failed}/{total})")
        score -= 50
    elif fail_rate > 0.2:
        issues.append(f"Taux d'échec élevé : {fail_rate:.0%} ({failed}/{total})")
        score -= 20

    if success == 0:
        issues.append("Aucune image produite avec succès")
        score -= 60
        return issues, repairs, score

    # Vérifier que les images existent réellement
    if archive_dir.exists():
        png_files = list(archive_dir.rglob("*.png"))
        if not png_files:
            issues.append("Dossier archive vide — images non trouvées")
            score -= 40
        else:
            score_bonus = min(10, len(png_files))
            score = min(100, score + score_bonus)
    else:
        issues.append("Dossier archive inexistant")
        score -= 30

    return issues, repairs, score


# ============================================================
# RÉPARATION VIA LLM (pour les cas complexes)
# ============================================================
def _critique_with_llm(handoff: str, data_in: dict, issues: list,
                       logger: logging.Logger) -> dict:
    """
    Demande à Claude d'analyser un handoff problématique et de proposer
    une réparation ou une instruction de correction pour le bloc suivant.
    """
    issues_text = "\n".join(f"- {i}" for i in issues)
    data_sample = json.dumps(data_in, ensure_ascii=False, default=str)[:2000]

    system = (
        "Tu es un agent critique expert en pipelines de production IA. "
        "Tu analyses des données défectueuses et proposes des réparations minimales "
        "pour permettre au pipeline de continuer. "
        "Réponds UNIQUEMENT en JSON valide."
    )
    prompt = f"""
Handoff analysé : {handoff}

Problèmes détectés :
{issues_text}

Données (extrait) :
{data_sample}

Propose une réparation minimale. Retourne ce JSON :
{{
  "can_repair": true/false,
  "repaired_fields": {{"field_name": "valeur_réparée", ...}},
  "correction_instruction": "Instruction précise pour le bloc qui a produit ces données",
  "severity": "low|medium|high|critical",
  "recommendation": "continue|retry|halt"
}}
"""
    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model":      CLAUDE_MODEL,
                "max_tokens": 1000,
                "system":     system,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        if resp.status_code == 200:
            raw = resp.json()["content"][0]["text"].strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"[CRITIQUE LLM] Erreur : {e}")

    return {
        "can_repair":    False,
        "severity":      "medium",
        "recommendation": "retry",
        "correction_instruction": "Relancer le bloc avec les mêmes paramètres",
    }


# ============================================================
# AGENT CRITIQUE PRINCIPAL
# ============================================================
class CriticAgent:
    # Élise — la critique sévère et juste (V1.30)
    _ELISE_INJECTION = (
        "Tu es Élise, critique d'art exigeante. Tu évalues non seulement la qualité "
        "technique mais aussi la cohérence artistique, l'impact émotionnel, et la "
        "fidélité à la vision de la série. Un score de 80 n'est bon que si l'intention "
        "artistique est respectée. Tu cites des exemples concrets dans tes évaluations."
    )

    @staticmethod
    def _get_personality_context() -> str:
        """Récupère le contexte de personnalité V1.30 pour Élise."""
        try:
            from agents.v130_agent_personality import get_personality_manager
            mgr = get_personality_manager()
            return mgr.inject("elise", CriticAgent._ELISE_INJECTION)
        except Exception:
            return CriticAgent._ELISE_INJECTION


    """
    Agent Critique — intercepte tous les échanges inter-blocs.
    Instancié une fois par run dans maestro.py.
    """

    def __init__(self, run_id: str, logger: logging.Logger,
                 use_llm: bool = True):
        self.run_id   = run_id
        self.logger   = logger
        self.use_llm  = use_llm
        self.reports  = []
        self.trackers = {}    # agent_name → LoopbackTracker
        CRITIC_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Enregistrement des loopbacks ────────────────────────────────
    def get_tracker(self, agent_name: str,
                    max_iter: int = 5) -> LoopbackTracker:
        if agent_name not in self.trackers:
            self.trackers[agent_name] = LoopbackTracker(agent_name, max_iter)
        return self.trackers[agent_name]

    def watch_loopback(self, agent_name: str, score: float,
                       content: dict) -> dict:
        """
        Enregistre une itération de loopback et retourne un diagnostic.
        Appelé à chaque itération interne d'un agent.
        """
        tracker = self.get_tracker(agent_name)
        tracker.record(score, content)
        diagnosis = tracker.diagnose()

        if diagnosis["action"] != "continue":
            self.logger.warning(
                f"[CRITIQUE/LOOPBACK] {agent_name} → "
                f"{diagnosis['status']} : {diagnosis.get('reason','')}"
            )
        return diagnosis

    # ─── Validation des handoffs ─────────────────────────────────────
    def validate_handoff(self, handoff: str, data: dict,
                         extra: dict = None) -> CriticReport:
        """
        Point d'entrée principal. Valide le handoff entre deux blocs.

        handoff : "sourcing→scenario" | "scenario→storyboard" |
                  "storyboard→production" | "production→postprod"
        data    : données produites par le bloc source
        extra   : données supplémentaires (ex: jobs pour storyboard→production)
        """
        self.logger.info(f"[CRITIQUE] Validation : {handoff}")
        issues  = []
        repairs = {}
        score   = 100.0
        data_out = data

        # ── Validation structurelle selon le handoff ──
        if handoff == "sourcing→scenario":
            issues, repairs, score, data_out = _validate_trend_report(data)

        elif handoff == "scenario→storyboard":
            issues, repairs, score, data_out = _validate_script(data)

        elif handoff == "storyboard→production":
            jobs = extra.get("jobs", []) if extra else []
            issues, repairs, score, data_out, jobs = _validate_shotlist(data, jobs)
            if extra is not None:
                extra["jobs"] = jobs  # mise à jour in-place

        elif handoff == "production→postprod":
            archive = Path(extra.get("archive_dir","workspace/archive")) if extra else Path("workspace/archive")
            issues, repairs, score = _validate_production_results(data, archive)

        # ── Déterminer le verdict ──
        verdict = self._score_to_verdict(score, issues)

        # ── Si problème sérieux et LLM disponible → analyse approfondie ──
        if verdict in (Verdict.REJECT, Verdict.HALT) and self.use_llm and issues:
            self.logger.info(f"[CRITIQUE] Problème sérieux → analyse LLM")
            llm_report = _critique_with_llm(handoff, data, issues, self.logger)

            # Appliquer les réparations LLM
            if llm_report.get("can_repair") and llm_report.get("repaired_fields"):
                for field, value in llm_report["repaired_fields"].items():
                    if field in data_out:
                        data_out[field] = value
                        repairs[f"llm_{field}"] = value
                        self.logger.info(f"[CRITIQUE/LLM] Réparation : {field} = {value}")

            # Réévaluer le verdict selon la recommandation LLM
            rec = llm_report.get("recommendation", "retry")
            if rec == "continue" and verdict == Verdict.REJECT:
                verdict = Verdict.WARN
            elif rec == "halt":
                verdict = Verdict.HALT

        # ── Construire le rapport ──
        report = CriticReport(
            handoff  = handoff,
            verdict  = verdict,
            issues   = issues,
            repairs  = repairs,
            data_out = data_out,
            score    = score,
        )
        self.reports.append(report.to_dict())
        self._log_report(report)
        self._save_report(report)

        return report

    # ─── Validation cohérence inter-frames ───────────────────────────
    def validate_frame_sequence(self, frames: list,
                                palette: list = None,
                                style_desc: str = "") -> CriticReport:
        """
        Valide la cohérence d'une séquence de frames.
        frames : liste de dicts {shot_id, filename, laplacian_score, path}
        palette: liste de couleurs hex de référence
        """
        self.logger.info(f"[CRITIQUE/FRAMES] Validation séquence ({len(frames)} frames)")
        issues  = []
        repairs = {}
        score   = 100.0

        if not frames:
            return CriticReport(
                "frame_sequence", Verdict.HALT,
                issues=["Aucune frame à valider"], score=0.0
            )

        # 1. Score de netteté moyen
        sharp_scores = [f.get("laplacian_score", 0) for f in frames if f.get("laplacian_score")]
        if sharp_scores:
            avg_sharp = sum(sharp_scores) / len(sharp_scores)
            poor = [f["shot_id"] for f in frames
                    if f.get("laplacian_score", 999) < 50]
            if poor:
                issues.append(f"Frames floues ({len(poor)}) : {poor[:5]}")
                score -= min(30, len(poor) * 5)
        else:
            issues.append("Scores de netteté non disponibles")
            score -= 10

        # 2. Cohérence des dimensions
        dims = set((f.get("width"), f.get("height")) for f in frames
                   if f.get("width") and f.get("height"))
        if len(dims) > 1:
            issues.append(f"Dimensions incohérentes entre frames : {dims}")
            score -= 15

        # 3. Frames manquantes (trous dans la séquence)
        shot_ids = [f.get("shot_id","") for f in frames]
        missing  = [sid for sid in shot_ids if not sid]
        if missing:
            issues.append(f"{len(missing)} frames sans shot_id")
            score -= 10

        # 4. Taux de frames valides
        valid = [f for f in frames if f.get("laplacian_score", 0) >= 50]
        valid_rate = len(valid) / len(frames)
        if valid_rate < 0.7:
            issues.append(
                f"Taux de frames valides insuffisant : {valid_rate:.0%} "
                f"({len(valid)}/{len(frames)})"
            )
            score -= 25

        verdict = self._score_to_verdict(score, issues)
        report  = CriticReport(
            handoff  = "frame_sequence",
            verdict  = verdict,
            issues   = issues,
            repairs  = repairs,
            score    = score,
        )
        self.reports.append(report.to_dict())
        self._log_report(report)
        return report

    # ─── Escalade ────────────────────────────────────────────────────
    def escalate(self, context: str, reason: str) -> dict:
        """
        Décision forcée quand aucun loopback ne peut résoudre le problème.
        Appelé par le maestro quand le critique retourne HALT.
        """
        self.logger.error(
            f"[CRITIQUE/ESCALADE] {context} — {reason}\n"
            f"  Décision : abandon du bloc, reprise au prochain run possible."
        )
        return {
            "action":  "skip_block",
            "context": context,
            "reason":  reason,
            "ts":      datetime.utcnow().isoformat(),
        }

    # ─── Rapport de santé global ─────────────────────────────────────
    def health_summary(self) -> dict:
        """Résumé de tous les verdicts émis durant le run."""
        counts = {v.value: 0 for v in Verdict}
        for r in self.reports:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

        total_issues = sum(len(r.get("issues",[])) for r in self.reports)
        avg_score    = (
            sum(r.get("score",0) for r in self.reports) / len(self.reports)
            if self.reports else 100.0
        )
        return {
            "run_id":       self.run_id,
            "total_checks": len(self.reports),
            "verdicts":     counts,
            "avg_score":    round(avg_score, 1),
            "total_issues": total_issues,
            "pipeline_health": (
                "CRITICAL" if counts.get("HALT",0) > 0
                else "DEGRADED" if counts.get("REJECT",0) > 0
                else "STABLE"   if counts.get("WARN",0)  > 0
                else "OPTIMAL"
            )
        }

    # ─── Utilitaires privés ──────────────────────────────────────────
    def _score_to_verdict(self, score: float, issues: list) -> Verdict:
        if score >= 85 and not issues:
            return Verdict.PASS
        if score >= 70:
            return Verdict.WARN if issues else Verdict.PASS
        if score >= 45:
            return Verdict.REPAIR if issues else Verdict.WARN
        if score >= 20:
            return Verdict.REJECT
        return Verdict.HALT

    def _log_report(self, report: CriticReport):
        icon = {
            Verdict.PASS:   "✓",
            Verdict.WARN:   "⚠",
            Verdict.REPAIR: "🔧",
            Verdict.REJECT: "✗",
            Verdict.HALT:   "🛑",
        }.get(report.verdict, "?")

        level = (logging.ERROR   if report.verdict == Verdict.HALT
                 else logging.WARNING if report.verdict in (Verdict.REJECT, Verdict.REPAIR)
                 else logging.INFO)

        self.logger.log(
            level,
            f"[CRITIQUE] {icon} {report.handoff} | "
            f"score={report.score:.0f} | {report.verdict.value} | "
            f"{len(report.issues)} problème(s)"
        )
        for issue in report.issues:
            self.logger.log(level, f"  → {issue}")
        for field, val in report.repairs.items():
            self.logger.info(f"  🔧 Réparé : {field} = {val}")

    def _save_report(self, report: CriticReport):
        ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = CRITIC_LOG_DIR / f"{self.run_id}_{ts}_{report.handoff.replace('→','_')}.json"
        try:
            path.write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass


# ============================================================
# POINT D'ENTRÉE STANDALONE (test)
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger("critic_test")

    critic = CriticAgent("test_run", log, use_llm=False)

    # Test 1 : TrendReport valide
    good_report = {
        "media_type": "anime",
        "brief": "Dragon Ball domine les tendances cette semaine",
        "hot_keywords": ["dragon ball", "super saiyan"],
    }
    r = critic.validate_handoff("sourcing→scenario", good_report)
    print(r)

    # Test 2 : Script problématique
    bad_script = {
        "title": "",
        "acts": [],
        "characters": [],
        "error": "json_parse_failed",
    }
    r2 = critic.validate_handoff("scenario→storyboard", bad_script)
    print(r2)

    # Test 3 : Loopback tracker
    tracker = critic.get_tracker("scenario", max_iter=3)
    for i, score in enumerate([60, 62, 62, 62]):
        tracker.record(score, {"iteration": i, "content": "same"})
    diag = tracker.diagnose()
    print(f"Diagnostic loopback : {diag}")

    # Résumé santé
    print(json.dumps(critic.health_summary(), indent=2))
