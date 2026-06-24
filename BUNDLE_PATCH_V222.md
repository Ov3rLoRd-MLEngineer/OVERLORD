# BUNDLE PATCH V2.22 — Ov3rLoRd / Onibaku Gumi 鬼爆組

## Nouveaux fichiers (copier dans `agents/` ET racine)

- `prompt_override.py`
- `watchdog_config.py`
- `frame_extractor.py` (livré session précédente)

---

## PATCH 1 — `director.py`
### Publier scene_type + seuils watchdog sur le bus

Chercher la méthode qui publie sur le bus (`publish_to_bus` ou `_publish` ou `run()`).
Ajouter **après** les 10 clés existantes :

```python
# --- Scene context pour watchdog adaptatif ---
scene_type = self._resolve_scene_type()
bus.write("director.scene_type",     scene_type)
bus.write("director.expected_dark",  scene_type in ("action_dynamic", "cockpit_static", "contemplative"))
bus.write("director.motion_blur",    scene_type == "action_dynamic")
bus.write("director.luma_min",       0.15 if scene_type == "action_dynamic" else 0.35)
bus.write("director.luma_max",       0.98)
bus.write("director.clip_threshold", 0.72 if scene_type == "action_dynamic" else 0.80)
bus.write("director.max_rejects",    2)
```

Ajouter la méthode dans la classe `Director` :

```python
def _resolve_scene_type(self) -> str:
    if hasattr(self, 'scene_type') and self.scene_type:
        return self.scene_type
    universe = (getattr(self, 'universe', '') or '').lower()
    action   = (getattr(self, 'action',   '') or '').lower()
    dynamic_keywords = ['combat', 'run', 'fight', 'battle', 'chase', 'fall', 'jump', 'course']
    static_keywords  = ['cockpit', 'sit', 'contemplat', 'think', 'interieur']
    for kw in dynamic_keywords:
        if kw in universe or kw in action:
            return "action_dynamic"
    for kw in static_keywords:
        if kw in universe or kw in action:
            return "cockpit_static"
    return "default"
```

**Impact :** zero regression — fallback sur `"default"` si bus indisponible.

---

## PATCH 2 — `agents/clip_validator.py`
### Seuil cosinus adaptatif depuis watchdog_config

Ajouter en haut du fichier, après les imports existants :

```python
try:
    from watchdog_config import load_config as _load_watchdog_cfg
    _WD_CFG = _load_watchdog_cfg()
    CLIP_THRESHOLD = _WD_CFG.get("clip_threshold", 0.80)
except Exception:
    CLIP_THRESHOLD = 0.80
```

Remplacer toutes les occurrences du seuil hardcodé :

```python
# AVANT
if similarity < 0.85:
# APRES
if similarity < CLIP_THRESHOLD:
```

**Impact :** `action_dynamic` → 0.72 / `default` → 0.80 / `cockpit_static` → 0.85

---

## PATCH 3 — `agents/visual_validator.py`
### Prompts QwenVL dynamiques + échange bus

Ajouter en haut du fichier, après les imports existants :

```python
try:
    from watchdog_config import load_config as _load_wd, qwenvl_prompts_for_scene
    _WD_CFG     = _load_wd()
    _SCENE_TYPE = _WD_CFG.get("scene_type", "default")
    try:
        import sys, os
        from pathlib import Path
        sys.path.insert(0, str(Path(os.environ.get("OVERLORD_ROOT", r"D:\OVERLORD"))))
        from agents.context_bus import get_bus as _get_bus
        _bus        = _get_bus()
        _CHARACTER  = _bus.read("director.character") or "asuka"
        _override_pos = _bus.read("qwenvl.prompt_positive") or ""
        _override_neg = _bus.read("qwenvl.prompt_negative") or ""
    except Exception:
        _CHARACTER    = "asuka"
        _override_pos = ""
        _override_neg = ""
    _QWEN_PROMPTS = qwenvl_prompts_for_scene(_SCENE_TYPE, _CHARACTER)
    if _override_pos:
        _QWEN_PROMPTS["positive"] = _override_pos
    if _override_neg:
        _QWEN_PROMPTS["negative"] = _override_neg
except Exception:
    _QWEN_PROMPTS = {
        "positive": "correct anatomy, single character, masterpiece quality",
        "negative": "extra limbs, deformed, multiple characters, low quality",
        "focus":    "overall quality",
    }
```

Remplacer le prompt système QwenVL hardcodé par :

```python
QWENVL_SYSTEM = (
    "You are a quality control expert for anime production. "
    "Analyze the image and check: "
    f"EXPECT: {_QWEN_PROMPTS['positive']}. "
    f"REJECT IF: {_QWEN_PROMPTS['negative']}. "
    f"FOCUS ON: {_QWEN_PROMPTS['focus']}. "
    'Reply with JSON: {"pass": true/false, "score": 0-100, "issues": [...]}'
)
```

---

## PATCH 4 — `maestro.py`
### Ajouter `--scene-type` + `--qwenvl-pos/neg` au CLI

Dans le bloc `argparse`, ajouter :

```python
parser.add_argument(
    "--scene-type",
    default=None,
    choices=["default", "action_dynamic", "cockpit_static", "contemplative"],
    help="Type de scene pour adapter les seuils watchdog/CLIP/QwenVL"
)
parser.add_argument(
    "--qwenvl-pos",
    default=None,
    help="Prompt positif QwenVL custom"
)
parser.add_argument(
    "--qwenvl-neg",
    default=None,
    help="Prompt negatif QwenVL custom"
)
```

Après `args = parser.parse_args()`, ajouter :

```python
if args.scene_type:
    try:
        from agents.context_bus import get_bus
        bus = get_bus()
        bus.write("director.scene_type", args.scene_type)
        if args.qwenvl_pos:
            bus.write("qwenvl.prompt_positive", args.qwenvl_pos)
        if args.qwenvl_neg:
            bus.write("qwenvl.prompt_negative", args.qwenvl_neg)
    except Exception as e:
        print(f"[WARN] Bus write failed: {e}")
```

---

## Commandes de test

```batch
:: Verifier watchdog_config
py -3.12 watchdog_config.py action_dynamic

:: Generer fichier exemple prompt_override
py -3.12 agents\prompt_override.py --example

:: Lister le contenu du fichier override
py -3.12 agents\prompt_override.py --file prompt_override.txt --list

:: Run Asuka demo complet
run.bat --media-type anime --universe "evangelion asuka running" ^
        --scene-type action_dynamic ^
        --pose "workspace\poses\asuka_skeleton.png"
```

---

## Recap architectural

```
run.bat --scene-type action_dynamic
    └── maestro.py          -> bus.write("director.scene_type", "action_dynamic")
        └── director.py     -> publie luma_min=0.15, clip_threshold=0.72, motion_blur=True
            ├── watchdog         -> lit bus -> seuils relaches
            ├── clip_validator   -> lit bus -> threshold=0.72
            ├── visual_validator -> lit bus -> prompts QwenVL adaptes (Asuka running)
            └── inpaint_queue    -> lit bus -> ne rejette pas le motion blur
```

*Ov3rLoRd V2.22 — Onibaku Gumi 鬼爆組 — Japan Expo 2026* 🔥
