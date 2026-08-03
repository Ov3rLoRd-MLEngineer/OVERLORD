"""Shim de compatibilite -- module deplace vers agents/production_video/frame_extractor.py
Voir PROPOSITION_REORGANISATION_FICHIERS.md. Fonctionne pour `from agents.frame_extractor import X`
ET pour une invocation directe (`python agents/frame_extractor.py --args`) grace a runpy.run_path
qui preserve le __name__ d'execution (donc le bloc if __name__=="__main__" du fichier
reel se declenche normalement quand ce shim est lance comme script).
"""
import runpy as _runpy, os as _os
_target = _os.path.join(_os.path.dirname(__file__), "production_video", "frame_extractor.py")
globals().update(_runpy.run_path(_target, run_name=__name__))
