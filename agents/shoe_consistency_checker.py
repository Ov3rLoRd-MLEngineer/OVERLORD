"""Shim de compatibilite -- module deplace vers agents/qc_validation/shoe_consistency_checker.py
Voir PROPOSITION_REORGANISATION_FICHIERS.md. Fonctionne pour `from agents.shoe_consistency_checker import X`
ET pour une invocation directe (`python agents/shoe_consistency_checker.py --args`) grace a runpy.run_path
qui preserve le __name__ d'execution (donc le bloc if __name__=="__main__" du fichier
reel se declenche normalement quand ce shim est lance comme script).
"""
import runpy as _runpy, os as _os
_target = _os.path.join(_os.path.dirname(__file__), "qc_validation", "shoe_consistency_checker.py")
globals().update(_runpy.run_path(_target, run_name=__name__))
