"""Shim de compatibilite -- module deplace vers agents/legacy_v1xx/core.py
Voir PROPOSITION_REORGANISATION_FICHIERS.md. Fonctionne pour `from agents.core_legacy import X`
ET pour une invocation directe (`python agents/core_legacy.py --args`) grace a runpy.run_path
qui preserve le __name__ d'execution (donc le bloc if __name__=="__main__" du fichier
reel se declenche normalement quand ce shim est lance comme script).

Renomme depuis agents/core.py le 2026-08-03 : ce nom collisionnait avec le
paquet agents/core/ (nouveau domaine "coeur pipeline" issu de la reorg
Phase C) -- `import agents.core` resolvait silencieusement vers le paquet
(agents/core/__init__.py, vide) plutot que vers ce shim, le rendant
inaccessible par import (fonctionnait encore en execution directe
`python agents/core.py`). Voir memoire "reorg-preferences" cote Claude Code.
"""
import runpy as _runpy, os as _os
_target = _os.path.join(_os.path.dirname(__file__), "legacy_v1xx", "core.py")
globals().update(_runpy.run_path(_target, run_name=__name__))
