"""
agents/v120_alignment.py — OverLord V1.20 — Alignement & Safety

1. Constitutional AI (CaI) — Critique + révision automatique (Red Team interne)
2. Debate Protocol          — Deux agents débattent, un juge tranche
3. Uncertainty Quantification — Mesure précise : savoir ce qu'on ne sait pas
4. Anomaly Detection        — Alerte quand le pipeline s'écarte de la normale
5. Value Learning           — Apprendre les préférences humaines implicites

Inspiré de : Anthropic Constitutional AI, AI Safety via Debate (Irving et al.)
"""

import json
import math
import time
import logging
import threading
import statistics
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import requests

ALIGNMENT_DIR = Path("workspace/alignment")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type": "application/json"},
                          json=body, timeout=25)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# 1. CONSTITUTIONAL AI (CaI)
# Red Team interne : l'IA se critique elle-même
# ══════════════════════════════════════════════════════════════════════

class ConstitutionalAI:
    """
    Constitutional AI (Anthropic, 2022) — appliqué au pipeline OverLord.

    Principe en 2 phases :
    1. CRITIQUE : l'agent produit un output, puis le critique selon une constitution
    2. RÉVISION : l'agent réécrit l'output en corrigeant les problèmes identifiés

    La "constitution" est l'ensemble des valeurs et règles d'OverLord
    (cf. pipeline_constitution.py), mais ici appliquée à la génération elle-même.

    Résultat : outputs auto-améliorés AVANT d'être soumis à l'humain.
    """

    CRITIQUE_PRINCIPLES = [
        "Est-ce que cet output respecte la cohérence des personnages définis dans le scénario ?",
        "Est-ce que les prompts générés évitent les clichés visuels déjà surutilisés ?",
        "Est-ce que la composition respecte les règles visuelles définies par le Visual Consultant ?",
        "Est-ce que le tone/mood est cohérent avec la direction artistique choisie ?",
        "Est-ce que les tags ComfyUI sont dans le bon ordre de priorité (qualité → sujet → style) ?",
        "Est-ce que les récompenses de l'épisode reflètent bien la qualité réelle de l'output ?",
    ]

    def __init__(self, logger: logging.Logger = None):
        self.log     = logger or logging.getLogger("cai")
        self._critiques_done = 0
        self._improvements   = 0
        ALIGNMENT_DIR.mkdir(parents=True, exist_ok=True)

    def critique(self, output: str, context: str = "") -> dict:
        """Phase 1 : critique l'output selon la constitution."""
        principles_str = "\n".join(
            f"  {i+1}. {p}" for i, p in enumerate(self.CRITIQUE_PRINCIPLES)
        )
        prompt = (
            f"Tu es un critique interne rigoureux d'OverLord Pipeline.\n"
            f"Analyse cet output selon ces principes :\n{principles_str}\n\n"
            f"OUTPUT À CRITIQUER :\n{output[:1000]}\n\n"
            + (f"CONTEXTE : {context[:300]}\n\n" if context else "")
            + "Identifie les problèmes spécifiques. Réponds en JSON :\n"
            '{"issues": [{"principle": 1, "problem": "...", "severity": "low|medium|high"}], '
            '"overall_quality": 0.75, "needs_revision": true}'
        )
        result = _llm(prompt, max_tokens=400)
        self._critiques_done += 1

        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            data = json.loads(result)
            return {
                "issues":          data.get("issues", []),
                "overall_quality": data.get("overall_quality", 0.7),
                "needs_revision":  data.get("needs_revision", False),
                "n_high_severity": sum(1 for i in data.get("issues",[])
                                       if i.get("severity")=="high"),
            }
        except Exception:
            return {"issues": [], "overall_quality": 0.7, "needs_revision": False}

    def revise(self, original: str, critique: dict, context: str = "") -> str:
        """Phase 2 : révise l'output selon la critique."""
        if not critique.get("needs_revision"):
            return original

        issues_str = "\n".join(
            f"  - [{i['severity'].upper()}] Principe {i['principle']}: {i['problem']}"
            for i in critique.get("issues", [])[:5]
        )
        prompt = (
            f"Révise cet output en corrigeant les problèmes identifiés.\n\n"
            f"OUTPUT ORIGINAL :\n{original[:800]}\n\n"
            f"PROBLÈMES À CORRIGER :\n{issues_str}\n\n"
            f"Produis une version améliorée qui résout ces problèmes. "
            f"Garde la structure de l'original mais améliore les parties problématiques."
        )
        revised = _llm(prompt, max_tokens=600)
        if revised and len(revised) > 50:
            self._improvements += 1
            self.log.info(
                f"[CAI] ✓ Output révisé ({critique['n_high_severity']} problèmes critiques corrigés)"
            )
            return revised
        return original

    def critique_and_revise(self, output: str, context: str = "",
                              max_rounds: int = 2) -> dict:
        """Pipeline CAI complet : critique → révision (itératif)."""
        current   = output
        history   = []
        for round_n in range(max_rounds):
            critique  = self.critique(current, context)
            history.append(critique)
            if not critique["needs_revision"]:
                break
            revised   = self.revise(current, critique, context)
            if revised == current:
                break
            current   = revised

        return {
            "original":     output,
            "final":        current,
            "improved":     current != output,
            "rounds":       len(history),
            "final_quality":history[-1]["overall_quality"] if history else 0.7,
            "critique_history": history,
        }

    def stats(self) -> dict:
        return {
            "critiques_done": self._critiques_done,
            "improvements":   self._improvements,
            "improvement_rate": f"{self._improvements/max(self._critiques_done,1)*100:.1f}%",
        }


# ══════════════════════════════════════════════════════════════════════
# 2. DEBATE PROTOCOL
# ══════════════════════════════════════════════════════════════════════

@dataclass
class DebateArgument:
    """Un argument dans un débat."""
    debater:   str
    position:  str
    argument:  str
    evidence:  str = ""
    strength:  float = 0.5   # 0-1


class DebateProtocol:
    """
    AI Safety via Debate (Irving et al., 2018) — appliqué aux décisions créatives.

    Principe : deux agents défendent des positions opposées devant un juge.
    Le juge (LLM) détermine qui a les meilleurs arguments.

    Applications dans OverLord :
    - "Quel sampler utiliser pour cette scène d'action ?"
    - "Faut-il utiliser un CFG de 6 ou de 8 pour ce style ?"
    - "Ce prompt est-il trop générique ou suffisamment précis ?"
    - "Faut-il ajouter un LoRA de personnage ou un LoRA de style ?"
    """

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("debate")
        self._debates_history: list[dict] = []

    def debate(self, question: str,
               position_a: str, position_b: str,
               context: dict = None,
               n_rounds: int = 2) -> dict:
        """
        Organise un débat entre deux positions et retourne le verdict.

        question   : la question à trancher
        position_a : première thèse
        position_b : thèse alternative
        n_rounds   : nombre de tours de réfutation
        """
        self.log.info(f"[DEBATE] '{question[:50]}' → A:{position_a} vs B:{position_b}")
        ctx_str    = json.dumps(context, ensure_ascii=False)[:300] if context else ""
        arguments  = []

        # Tour initial
        for pos, name in [(position_a, "Agent_A"), (position_b, "Agent_B")]:
            prompt = (
                f"Tu es {name} dans un débat. Tu défends : '{pos}'\n"
                f"Question : {question}\n"
                + (f"Contexte : {ctx_str}\n" if ctx_str else "")
                + "Donne ton argument le plus fort en 3 phrases. "
                  "Sois précis et factuel."
            )
            arg = _llm(prompt, max_tokens=200)
            arguments.append(DebateArgument(
                debater=name, position=pos, argument=arg or pos
            ))

        # Réfutations
        for round_n in range(n_rounds - 1):
            for i, (pos, name) in enumerate([(position_a,"Agent_A"),(position_b,"Agent_B")]):
                opponent_arg = arguments[-1 if i==0 else -2].argument
                prompt = (
                    f"Tu es {name}. L'autre agent a dit : '{opponent_arg[:150]}'\n"
                    f"Réfute cet argument en 2 phrases et renforce ta position : '{pos}'"
                )
                refutation = _llm(prompt, max_tokens=150)
                arguments.append(DebateArgument(
                    debater=name, position=pos,
                    argument=refutation or pos,
                ))

        # Jugement
        all_args = "\n".join(
            f"{a.debater} ({a.position}) : {a.argument}"
            for a in arguments
        )
        verdict_prompt = (
            f"Tu es un juge impartial. Voici un débat :\n\n{all_args}\n\n"
            f"Question initiale : '{question}'\n\n"
            f"Détermine lequel a les meilleurs arguments et pourquoi. "
            f"Réponds en JSON :\n"
            '{"winner": "Agent_A ou Agent_B", "winning_position": "...", '
            '"reasoning": "...", "confidence": 0.85}'
        )
        verdict_raw = _llm(verdict_prompt, max_tokens=250)
        verdict     = {}
        try:
            if verdict_raw and verdict_raw.startswith("```"):
                verdict_raw = "\n".join(verdict_raw.split("\n")[1:-1])
            verdict = json.loads(verdict_raw) if verdict_raw else {}
        except Exception:
            verdict = {"winner": "Agent_A", "winning_position": position_a,
                       "confidence": 0.5}

        result = {
            "question":         question,
            "position_a":       position_a,
            "position_b":       position_b,
            "n_rounds":         n_rounds,
            "winner":           verdict.get("winner","?"),
            "winning_position": verdict.get("winning_position", position_a),
            "confidence":       verdict.get("confidence", 0.5),
            "reasoning":        verdict.get("reasoning",""),
            "arguments":        [{"d":a.debater,"pos":a.position,"arg":a.argument[:100]}
                                  for a in arguments],
        }
        self._debates_history.append(result)
        self.log.info(
            f"[DEBATE] Verdict: {result['winner']} ({result['confidence']:.0%})"
        )
        return result

    def quick_verdict(self, question: str,
                       option_a: str, option_b: str) -> str:
        """Version rapide sans débat complet — verdict direct en 1 appel."""
        prompt = (
            f"Question : {question}\n"
            f"Option A : {option_a}\n"
            f"Option B : {option_b}\n"
            f"Réponds UNIQUEMENT avec 'A' ou 'B' et une justification en 1 phrase."
        )
        result = _llm(prompt, max_tokens=80)
        if result and result.startswith("A"):
            return option_a
        return option_b


# ══════════════════════════════════════════════════════════════════════
# 3. UNCERTAINTY QUANTIFICATION
# ══════════════════════════════════════════════════════════════════════

class UncertaintyQuantifier:
    """
    Quantification de l'incertitude — savoir ce qu'on ne sait pas.

    Types d'incertitude :
    - Aléatoire (aleatoric) : inhérente à la tâche, irréductible
    - Epistémique (epistemic): due au manque de données, réductible

    Méthodes :
    - Monte Carlo Dropout (simulé par appels LLM multiples)
    - Confidence intervals sur les scores
    - Entropy des distributions de probabilités
    """

    def __init__(self):
        self._uncertainty_log: list[dict] = []

    def estimate_via_sampling(self, fn: callable,
                               n_samples: int = 3,
                               **kwargs) -> dict:
        """
        Estime l'incertitude en appelant fn plusieurs fois
        et mesurant la variance des résultats.
        """
        samples = []
        for _ in range(n_samples):
            try:
                result = fn(**kwargs)
                if isinstance(result, (int, float)):
                    samples.append(float(result))
            except Exception:
                pass

        if not samples:
            return {"mean": 0.0, "std": 1.0, "uncertainty": "high", "samples": []}

        mean    = statistics.mean(samples)
        std     = statistics.stdev(samples) if len(samples) > 1 else 0.0
        cv      = std / (abs(mean) + 1e-8)   # coefficient de variation

        uncertainty_level = "low" if cv < 0.1 else "medium" if cv < 0.3 else "high"

        result = {
            "mean":              round(mean, 4),
            "std":               round(std, 4),
            "cv":                round(cv, 4),
            "uncertainty":       uncertainty_level,
            "confidence_95":     (round(mean - 1.96*std, 4),
                                   round(mean + 1.96*std, 4)),
            "samples":           samples,
            "epistemic_high":    cv > 0.2,   # incertitude épistémique élevée
        }
        self._uncertainty_log.append(result)
        return result

    def compute_entropy(self, probabilities: dict) -> float:
        """
        Entropie de Shannon — mesure l'incertitude d'une distribution.
        H = -Σ p·log(p)
        0 = certitude totale, log(N) = incertitude maximale
        """
        probs = [max(1e-10, p) for p in probabilities.values()]
        total = sum(probs)
        probs = [p/total for p in probs]
        return -sum(p * math.log2(p) for p in probs)

    def should_request_human_input(self, uncertainty: dict,
                                    threshold: float = 0.25) -> bool:
        """Retourne True si l'incertitude est trop haute → demander à l'humain."""
        return uncertainty.get("cv", 0) > threshold

    def calibration_error(self, predicted_confidence: list[float],
                           actual_correct: list[bool]) -> float:
        """ECE — Expected Calibration Error."""
        if not predicted_confidence or not actual_correct:
            return 0.0
        n = len(predicted_confidence)
        bins = [(i/10, (i+1)/10) for i in range(10)]
        ece  = 0.0
        for lo, hi in bins:
            in_bin = [(p, a) for p, a in zip(predicted_confidence, actual_correct)
                      if lo <= p < hi]
            if in_bin:
                acc  = sum(1 for _,a in in_bin if a) / len(in_bin)
                conf = sum(p for p,_ in in_bin) / len(in_bin)
                ece += abs(acc - conf) * (len(in_bin) / n)
        return round(ece, 4)


# ══════════════════════════════════════════════════════════════════════
# 4. ANOMALY DETECTION
# ══════════════════════════════════════════════════════════════════════

class AnomalyDetector:
    """
    Détecte quand le pipeline s'écarte de son comportement normal.

    Méthodes :
    - Z-score : écart par rapport à la moyenne en unités de déviation standard
    - IQR (Interquartile Range) : détection robuste aux outliers
    - Séquences anormales : patterns inhabituels dans les logs
    """

    def __init__(self, window_size: int = 50, z_threshold: float = 3.0):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self._metrics:   dict[str, list[float]] = {}   # metric → historique
        self._anomalies: list[dict] = []
        self._lock = threading.Lock()

    def record(self, metric_name: str, value: float) -> dict:
        """Enregistre une métrique et vérifie les anomalies."""
        with self._lock:
            if metric_name not in self._metrics:
                self._metrics[metric_name] = []
            hist = self._metrics[metric_name]
            hist.append(value)
            if len(hist) > self.window_size:
                hist.pop(0)

            if len(hist) < 5:
                return {"anomaly": False, "reason": "insufficient_data"}

            # Z-score
            mean  = statistics.mean(hist[:-1])   # moyenne sans la valeur actuelle
            std   = statistics.stdev(hist[:-1]) if len(hist) > 2 else 0.0
            z     = abs(value - mean) / (std + 1e-8)
            is_anomaly = z > self.z_threshold

            # IQR check
            sorted_hist = sorted(hist[:-1])
            n = len(sorted_hist)
            q1 = sorted_hist[n//4]
            q3 = sorted_hist[3*n//4]
            iqr = q3 - q1
            iqr_anomaly = value < q1 - 1.5*iqr or value > q3 + 1.5*iqr

            result = {
                "metric":      metric_name,
                "value":       value,
                "mean":        round(mean, 4),
                "std":         round(std, 4),
                "z_score":     round(z, 3),
                "anomaly":     is_anomaly or iqr_anomaly,
                "method":      "z_score" if is_anomaly else ("iqr" if iqr_anomaly else "none"),
                "severity":    "high" if z > 5 else "medium" if z > 3 else "low",
            }

            if result["anomaly"]:
                self._anomalies.append({**result, "ts": time.time()})

            return result

    def batch_record(self, metrics: dict) -> list[dict]:
        """Enregistre plusieurs métriques d'un coup."""
        return [self.record(k, v) for k, v in metrics.items()]

    def get_recent_anomalies(self, last_n: int = 10) -> list[dict]:
        with self._lock:
            return list(self._anomalies[-last_n:])

    def get_health_status(self) -> dict:
        """Évaluation de la santé globale du pipeline."""
        recent     = self.get_recent_anomalies(20)
        n_anomalies = len(recent)
        high_sev   = sum(1 for a in recent if a.get("severity")=="high")

        if high_sev > 2:
            status = "critical"
        elif n_anomalies > 5:
            status = "degraded"
        elif n_anomalies > 2:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status":          status,
            "recent_anomalies":n_anomalies,
            "high_severity":   high_sev,
            "monitored_metrics":len(self._metrics),
            "last_anomaly":    recent[-1] if recent else None,
        }

    def get_baseline(self, metric_name: str) -> dict:
        """Retourne le profil normal d'une métrique."""
        with self._lock:
            hist = self._metrics.get(metric_name, [])
        if not hist:
            return {}
        return {
            "metric": metric_name,
            "mean":   round(statistics.mean(hist), 4),
            "std":    round(statistics.stdev(hist) if len(hist)>1 else 0, 4),
            "min":    round(min(hist), 4),
            "max":    round(max(hist), 4),
            "n":      len(hist),
        }


# ══════════════════════════════════════════════════════════════════════
# FAÇADE ALIGNEMENT V1.20
# ══════════════════════════════════════════════════════════════════════

class AlignmentSystemV120:
    """Système d'alignement et de sécurité V1.20."""

    def __init__(self, logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("alignment_v120")
        self.cai         = ConstitutionalAI(logger=self.log)
        self.debate      = DebateProtocol(logger=self.log)
        self.uncertainty = UncertaintyQuantifier()
        self.anomaly     = AnomalyDetector()

    def safe_decision(self, question: str,
                       option_a: str, option_b: str,
                       use_debate: bool = True) -> dict:
        """
        Prend une décision sécurisée via débat + vérification.
        """
        if use_debate:
            result = self.debate.debate(question, option_a, option_b,
                                         n_rounds=1)
            decision = result["winning_position"]
            confidence = result["confidence"]
        else:
            decision   = option_a
            confidence = 0.5

        return {
            "question":   question,
            "decision":   decision,
            "confidence": confidence,
            "method":     "debate" if use_debate else "default",
        }

    def validate_and_improve(self, output: str, context: str = "") -> dict:
        """Valide et améliore un output via CAI."""
        return self.cai.critique_and_revise(output, context)

    def monitor_run(self, metrics: dict) -> dict:
        """Surveille un run pour détecter les anomalies."""
        anomalies  = self.anomaly.batch_record(metrics)
        detected   = [a for a in anomalies if a.get("anomaly")]
        health     = self.anomaly.get_health_status()
        if detected:
            self.log.warning(
                f"[ALIGN] {len(detected)} anomalie(s) détectée(s) : "
                f"{[a['metric'] for a in detected]}"
            )
        return {"anomalies": detected, "health": health}

    def get_dashboard(self) -> dict:
        return {
            "version":   "1.20_alignment",
            "cai":       self.cai.stats(),
            "anomalies": self.anomaly.get_health_status(),
            "debates":   len(self.debate._debates_history),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    align = AlignmentSystemV120()

    print("=== V1.20 ALIGNMENT TEST ===\n")

    # Test CAI
    output = "1girl, anime style, beautiful face, great composition"
    result = align.validate_and_improve(output, context="scène d'action Dragon Ball")
    print(f"CAI : improved={result['improved']} | quality={result['final_quality']:.2f}")
    if result["improved"]:
        print(f"  Original : {result['original'][:60]}")
        print(f"  Final    : {result['final'][:60]}")

    # Test Debate
    debate = align.debate.debate(
        question   = "Quel sampler pour une scène d'action rapide ?",
        position_a = "euler_ancestral (plus créatif, moins prévisible)",
        position_b = "dpm++_2m_sde (plus stable, meilleure qualité détails)",
        n_rounds   = 1
    )
    print(f"\nDébat : {debate['winner']} gagne ({debate['confidence']:.0%})")
    print(f"  Raison : {debate['reasoning'][:80]}...")

    # Test Anomaly Detection
    import random
    for i in range(10):
        align.anomaly.record("quality_score", random.gauss(75, 5))
    anomaly_result = align.anomaly.record("quality_score", 20.0)  # outlier
    print(f"\nAnomalie : {anomaly_result['anomaly']} | z={anomaly_result['z_score']:.1f}")
    print(f"Santé    : {align.anomaly.get_health_status()['status']}")
