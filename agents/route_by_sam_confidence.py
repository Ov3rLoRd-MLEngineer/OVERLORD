"""Shim de compatibilite -- module deplace vers agents/qc_validation/route_by_sam_confidence.py
Voir PROPOSITION_REORGANISATION_FICHIERS.md. Fonctionne pour `from agents.route_by_sam_confidence import X`
ET pour une invocation directe (`python agents/route_by_sam_confidence.py --args`) grace a runpy.run_path
qui preserve le __name__ d'execution (donc le bloc if __name__=="__main__" du fichier
reel se declenche normalement quand ce shim est lance comme script).
"""
import runpy as _runpy, os as _os
_target = _os.path.join(_os.path.dirname(__file__), "qc_validation", "route_by_sam_confidence.py")
globals().update(_runpy.run_path(_target, run_name=__name__))
