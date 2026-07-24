# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
agents/cost_tracker.py — Suivi des Couts API en Temps Reel V1.46 + Context Bus V1.49
FIX V1.49d : parenthese non fermee ligne 159 corrigee.
"""
import json
import logging
import sys
import io
from pathlib import Path
from datetime import datetime, date
from typing import Optional

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("cost_tracker")
COST_DIR   = Path("workspace/cost_tracker")
COSTS_LOG  = COST_DIR / "api_costs.jsonl"
BUDGET_CFG = COST_DIR / "budget.json"

MODEL_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0,   "output": 15.0},
    "claude-opus-4-6":   {"input": 15.0,  "output": 75.0},
    "claude-haiku-4-5":  {"input": 0.25,  "output": 1.25},
    "gpt-4o":            {"input": 5.0,   "output": 15.0},
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "ollama/llama3":     {"input": 0.001, "output": 0.001},
    "ollama/mistral":    {"input": 0.001, "output": 0.001},
}

DEFAULT_BUDGET = {
    "daily_limit_usd":   5.0,
    "weekly_limit_usd":  20.0,
    "monthly_limit_usd": 50.0,
    "alert_threshold":   0.8,
}


class CostTracker:

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log
        COST_DIR.mkdir(parents=True, exist_ok=True)
        self.budget = self._load_budget()

    def _load_budget(self) -> dict:
        if BUDGET_CFG.exists():
            try:
                return json.loads(BUDGET_CFG.read_text(encoding="utf-8"))
            except Exception:
                pass
        b = DEFAULT_BUDGET.copy()
        BUDGET_CFG.write_text(json.dumps(b, indent=2), encoding="utf-8")
        return b

    def set_budget(self, daily: float = None, weekly: float = None, monthly: float = None):
        if daily   is not None: self.budget["daily_limit_usd"]   = daily
        if weekly  is not None: self.budget["weekly_limit_usd"]  = weekly
        if monthly is not None: self.budget["monthly_limit_usd"] = monthly
        BUDGET_CFG.write_text(json.dumps(self.budget, indent=2), encoding="utf-8")
        self.log.info(f"[COST] Budget mis a jour : {self.budget}")

    def log_call(self, model: str, input_tokens: int, output_tokens: int,
                 context: str = "", run_id: str = "") -> float:
        pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})
        cost    = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        entry = {
            "timestamp":     datetime.now().isoformat(),
            "date":          date.today().isoformat(),
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  input_tokens + output_tokens,
            "cost_usd":      round(cost, 6),
            "context":       context,
            "run_id":        run_id,
        }
        with open(COSTS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._check_budget_alerts(cost)
        self.log.debug(f"[COST] {model} : {input_tokens}+{output_tokens} tokens = ${cost:.4f}")
        return cost

    def _check_budget_alerts(self, new_cost: float):
        report    = self.get_report()
        daily_pct = report["daily_total"] / max(self.budget["daily_limit_usd"], 0.01)
        if daily_pct >= self.budget["alert_threshold"]:
            self.log.warning(
                f"[COST] Budget journalier a {daily_pct:.0%} "
                f"(${report['daily_total']:.3f} / ${self.budget['daily_limit_usd']})"
            )
        if daily_pct >= 1.0:
            self.log.error(f"[COST] Budget journalier DEPASSE — ${report['daily_total']:.3f}")
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("cost.daily_total",    report["daily_total"], agent_id="cost_tracker")
                bus.write("cost.daily_pct",      round(daily_pct, 3),   agent_id="cost_tracker")
                bus.write("cost.budget_ok",      daily_pct < 1.0,       agent_id="cost_tracker")
                bus.write("cost.preferred_model",
                          self._pick_cheapest_model(daily_pct),
                          agent_id="cost_tracker", confidence=0.75)
            except Exception:
                pass

    def _pick_cheapest_model(self, daily_pct: float) -> str:
        if daily_pct >= 0.9: return "ollama/llama3"
        if daily_pct >= 0.7: return "claude-haiku-4-5"
        return "claude-sonnet-4-6"

    def get_report(self, days: int = 30) -> dict:
        if not COSTS_LOG.exists():
            return {"daily_total": 0, "weekly_total": 0, "monthly_total": 0,
                    "total_calls": 0, "by_model": {}}
        entries = []
        try:
            for line in COSTS_LOG.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entries.append(json.loads(line))
        except Exception:
            return {}
        today      = date.today().isoformat()
        this_week  = [e for e in entries if e["date"] >= self._week_start()]
        this_month = [e for e in entries if e["date"][:7] == today[:7]]
        today_e    = [e for e in entries if e["date"] == today]
        by_model   = {}
        for e in entries[-500:]:
            m = e["model"]
            if m not in by_model:
                by_model[m] = {"calls": 0, "tokens": 0, "cost_usd": 0}
            by_model[m]["calls"]    += 1
            by_model[m]["tokens"]   += e.get("total_tokens", 0)
            by_model[m]["cost_usd"] += e.get("cost_usd", 0)
        return {
            "daily_total":   round(sum(e["cost_usd"] for e in today_e),    4),
            "weekly_total":  round(sum(e["cost_usd"] for e in this_week),  4),
            "monthly_total": round(sum(e["cost_usd"] for e in this_month), 4),
            "total_calls":   len(entries),
            "total_tokens":  sum(e.get("total_tokens", 0) for e in entries[-500:]),
            "by_model": {
                k: {**v, "cost_usd": round(v["cost_usd"], 4)}
                for k, v in by_model.items()
            },
            "budget": self.budget,
            "budget_status": {
                "daily_pct":   round(
                    sum(e["cost_usd"] for e in today_e)
                    / max(self.budget["daily_limit_usd"], 0.01) * 100, 1),
                "weekly_pct":  round(
                    sum(e["cost_usd"] for e in this_week)
                    / max(self.budget["weekly_limit_usd"], 0.01) * 100, 1),
                "monthly_pct": round(
                    sum(e["cost_usd"] for e in this_month)
                    / max(self.budget["monthly_limit_usd"], 0.01) * 100, 1),
            },
        }

    def _week_start(self) -> str:
        from datetime import timedelta
        today = date.today()
        return (today - timedelta(days=today.weekday())).isoformat()

    def print_dashboard(self):
        r   = self.get_report()
        bs  = r.get("budget_status", {})
        sep = "=" * 50
        print(f"\n{sep}")
        print("  Ov3rLoRd -- Suivi Couts API")
        print(sep)
        print(f"  Aujourd'hui  : ${r['daily_total']:.4f}  ({bs.get('daily_pct', 0):.0f}% budget)")
        print(f"  Cette semaine: ${r['weekly_total']:.4f}  ({bs.get('weekly_pct', 0):.0f}% budget)")
        print(f"  Ce mois      : ${r['monthly_total']:.4f}  ({bs.get('monthly_pct', 0):.0f}% budget)")
        print(f"  Total appels : {r['total_calls']}")
        print(f"\n  Par modele :")
        for model, data in r.get("by_model", {}).items():
            print(f"  {model:<30} {data['calls']:>4} appels  ${data['cost_usd']:.4f}")
        print(f"{sep}\n")


_tracker: Optional[CostTracker] = None

def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    t = CostTracker()
    t.set_budget(daily=2.0, weekly=10.0, monthly=30.0)
    for i in range(5):
        t.log_call("claude-sonnet-4-6", 800 + i*200, 1500 + i*300, context=f"run_{i}")
    t.log_call("ollama/llama3", 400, 800, context="fallback_test")
    t.print_dashboard()