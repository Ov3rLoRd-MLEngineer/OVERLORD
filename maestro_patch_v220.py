# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# maestro_patch_v220.py -- version corrigee
# Ov3rLoRd -- Ov3rLoRd
# maestro.py est a la RACINE D:/OVERLORD/ (pas dans agents/)
# Usage : python maestro_patch_v220.py  (depuis D:/OVERLORD/)


import sys
import ast
import shutil
from pathlib import Path
from datetime import datetime

# maestro.py est a la RACINE du projet, pas dans agents\
MAESTRO_PATH = Path(__file__).parent / "maestro.py"
BACKUP_DIR   = Path(__file__).parent / "workspace" / "archive"

# ── Snippets ──────────────────────────────────────────────────────────────────

IMPORTS_INJECT = (
    "\n"
    "# -- V2.20 : Quality Control -----------------------------------------\n"
    "try:\n"
    "    from agents.clip_validator import validate_run as _clip_validate_run\n"
    "    CLIP_QC_OK = True\n"
    "except Exception:\n"
    "    CLIP_QC_OK = False\n"
    "\n"
    "try:\n"
    "    from agents.inpaint_queue import process_clip_rejects as _inpaint_rejects\n"
    "    INPAINT_QC_OK = True\n"
    "except Exception:\n"
    "    INPAINT_QC_OK = False\n"
    "\n"
    "try:\n"
    "    from agents.pacing_engine import build_manifest_from_storyboard as _build_pacing\n"
    "    PACING_QC_OK = True\n"
    "except Exception:\n"
    "    PACING_QC_OK = False\n"
)

QC_METHOD = (
    "    def block_quality_control(self, run_id, storyboard=None):\n"
    '        """V2.20 -- QC : CLIP coherence + inpaint auto + pacing manifest."""\n'
    "        log.info('=' * 60)\n"
    "        log.info('  PHASE QC -- Quality Control')\n"
    "        log.info('=' * 60)\n"
    "        qc = {'clip': None, 'inpaint': None, 'pacing': None}\n"
    "\n"
    "        # 1. CLIP coherence inter-shots\n"
    "        if CLIP_QC_OK:\n"
    "            try:\n"
    "                rpt = _clip_validate_run(run_id)\n"
    "                qc['clip'] = rpt\n"
    "                st = rpt.get('stats', {})\n"
    "                log.info(f\"[QC] CLIP {rpt.get('status')} \"\n"
    "                         f\"mean={st.get('mean')} \"\n"
    "                         f\"rejets={st.get('n_rej',0)} \"\n"
    "                         f\"alertes={st.get('n_warn',0)}\")\n"
    "            except Exception as e:\n"
    "                log.error(f'[QC] CLIP erreur: {e}')\n"
    "        else:\n"
    "            log.info('[QC] clip_validator absent -- skipped')\n"
    "\n"
    "        # 2. Inpaint auto sur frames REJECT\n"
    "        clip_rpt  = qc.get('clip') or {}\n"
    "        n_rejects = len(clip_rpt.get('rejects', []))\n"
    "        if n_rejects > 0 and INPAINT_QC_OK:\n"
    "            try:\n"
    "                universe  = getattr(self, 'universe',  'evangelion')\n"
    "                character = getattr(self, 'character', 'asuka_plugsuit')\n"
    "                res = _inpaint_rejects(\n"
    "                    run_id, clip_rpt,\n"
    "                    universe=universe, character=character\n"
    "                )\n"
    "                qc['inpaint'] = res\n"
    "                ok   = sum(1 for r in res if r.get('status') == 'OK')\n"
    "                fail = sum(1 for r in res if r.get('status') == 'FAIL')\n"
    "                log.info(f'[QC] Inpaint OK:{ok} FAIL:{fail}')\n"
    "            except Exception as e:\n"
    "                log.error(f'[QC] inpaint erreur: {e}')\n"
    "        elif n_rejects == 0:\n"
    "            log.info('[QC] Aucun rejet -- inpaint non necessaire')\n"
    "\n"
    "        # 3. Pacing manifest\n"
    "        if PACING_QC_OK and storyboard:\n"
    "            try:\n"
    "                universe   = getattr(self, 'universe', 'evangelion')\n"
    "                output_dir = BASE / 'workspace' / 'reports'\n"
    "                mf = _build_pacing(\n"
    "                    run_id, storyboard,\n"
    "                    universe=universe, output_dir=output_dir\n"
    "                )\n"
    "                qc['pacing'] = mf\n"
    "                log.info(f\"[QC] Pacing {mf.get('total_duration',0):.1f}s\"\n"
    "                         f\" | {len(mf.get('shots',[]))} shots\")\n"
    "            except Exception as e:\n"
    "                log.error(f'[QC] pacing erreur: {e}')\n"
    "        else:\n"
    "            log.info('[QC] Pacing skipped')\n"
    "\n"
    "        log.info('[QC] OK Quality Control termine')\n"
    "        return qc\n"
    "\n"
)

CLI_FLAG = (
    '    parser.add_argument("--no-qc", action="store_true",\n'
    '                        help="Sauter le Quality Control (CLIP+inpaint+pacing)")\n'
)

QC_CALL = (
    "        # -- V2.20 Quality Control ------------------------------------\n"
    "        if not getattr(self, '_no_qc', False):\n"
    "            _sb = getattr(self, '_last_storyboard', None)\n"
    "            self.block_quality_control(\n"
    "                run_id=self._run_id, storyboard=_sb\n"
    "            )\n"
    "        else:\n"
    "            log.info('[QC] --no-qc -- skipped')\n"
)


# ── Utilitaire ────────────────────────────────────────────────────────────────
def _find(src, candidates):
    for c in candidates:
        if c in src:
            return c
    return ""


# ══════════════════════════════════════════════════════════════════════════════
def patch_maestro():
    if not MAESTRO_PATH.exists():
        print(f"[PATCH] ERREUR maestro.py introuvable : {MAESTRO_PATH}")
        print("[PATCH] Ce script doit etre execute depuis D:\\OVERLORD\\")
        sys.exit(1)

    # Backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"maestro_pre_v220_{ts}.py"
    shutil.copy2(MAESTRO_PATH, backup)
    print(f"[PATCH] Backup -> {backup}")

    src = MAESTRO_PATH.read_text(encoding="utf-8")

    try:
        ast.parse(src)
        print("[PATCH] AST source OK")
    except SyntaxError as e:
        print(f"[PATCH] ERREUR AST source : {e}")
        sys.exit(1)

    changed = False

    # ── 1. Imports QC ─────────────────────────────────────────────────────────
    if "CLIP_QC_OK" not in src:
        # Ancre : commentaire imports internes (tirets speciaux UTF-8 presents)
        anchor = _find(src, [
            "# \u2500\u2500 Imports internes",   # tirets box-drawing
            "# -- Imports internes",              # tirets ASCII fallback
        ])
        if anchor:
            pos = src.index(anchor)
            eol = src.index("\n", pos)
            src = src[:eol + 1] + IMPORTS_INJECT + src[eol + 1:]
            print("[PATCH] OK Imports QC injectes")
            changed = True
        else:
            # Fallback : apres "from datetime import datetime"
            anchor_fb = "from datetime import datetime"
            if anchor_fb in src:
                pos = src.index(anchor_fb) + len(anchor_fb)
                eol = src.index("\n", pos)
                src = src[:eol + 1] + IMPORTS_INJECT + src[eol + 1:]
                print("[PATCH] OK Imports QC injectes (fallback datetime)")
                changed = True
            else:
                print("[PATCH] WARN Imports QC : aucune ancre trouvee")
    else:
        print("[PATCH] SKIP Imports QC deja presents")

    # ── 2. Methode block_quality_control() ────────────────────────────────────
    if "block_quality_control" not in src:
        anchor = _find(src, [
            "    def block_postprod(",
            "    def block_postprod (",
        ])
        if anchor:
            src = src.replace(anchor, QC_METHOD + anchor, 1)
            print("[PATCH] OK block_quality_control() injecte avant block_postprod")
            changed = True
        else:
            anchor_fb = '\nif __name__ == "__main__"'
            if anchor_fb in src:
                src = src.replace(anchor_fb, "\n" + QC_METHOD + anchor_fb, 1)
                print("[PATCH] OK block_quality_control() injecte (fallback fin fichier)")
                changed = True
            else:
                print("[PATCH] WARN block_quality_control() : ancre non trouvee")
    else:
        print("[PATCH] SKIP block_quality_control() deja present")

    # ── 3. Flag CLI --no-qc ───────────────────────────────────────────────────
    if "--no-qc" not in src:
        anchor = _find(src, [
            'parser.add_argument("--bible"',
            'parser.add_argument("--media-type"',
            'parser.add_argument("--universe"',
            'parser.add_argument("--output"',
        ])
        if anchor:
            pos = src.index(anchor) + len(anchor)
            eol = src.index("\n", pos)
            src = src[:eol + 1] + CLI_FLAG + src[eol + 1:]
            print("[PATCH] OK Flag --no-qc injecte")
            changed = True
        else:
            print("[PATCH] WARN --no-qc : ancre argparse non trouvee")
    else:
        print("[PATCH] SKIP --no-qc deja present")

    # ── 4. self._no_qc ────────────────────────────────────────────────────────
    if "_no_qc" not in src:
        anchor = "args = parser.parse_args()"
        if anchor in src:
            pos = src.index(anchor) + len(anchor)
            eol = src.index("\n", pos)
            src = (src[:eol + 1]
                   + "    self._no_qc = getattr(args, 'no_qc', False)\n"
                   + src[eol + 1:])
            print("[PATCH] OK self._no_qc injecte")
            changed = True
        else:
            print("[PATCH] WARN self._no_qc : args = parser.parse_args() non trouve")
    else:
        print("[PATCH] SKIP self._no_qc deja present")

    # ── 5. Appel QC avant block_postprod ──────────────────────────────────────
    if "block_quality_control" in src and "block_quality_control()" not in src:
        anchor = _find(src, [
            "self.block_postprod()",
            "block_postprod()",
        ])
        if anchor:
            src = src.replace(anchor, QC_CALL + "        " + anchor, 1)
            print("[PATCH] OK Appel QC injecte avant block_postprod()")
            changed = True
        else:
            print("[PATCH] WARN Appel QC : ancre block_postprod() non trouvee")
            print("[PATCH]   Ajouter manuellement avant self.block_postprod() :")
            print("          self.block_quality_control(run_id=self._run_id)")
    elif "block_quality_control()" in src:
        print("[PATCH] SKIP Appel QC deja present")

    if not changed:
        print("[PATCH] Aucun changement applique -- fichier deja a jour ?")
        return

    # ── Validation AST post-patch ─────────────────────────────────────────────
    try:
        ast.parse(src)
        print("[PATCH] AST post-patch OK")
    except SyntaxError as e:
        print(f"[PATCH] ERREUR AST post-patch : {e}")
        print("[PATCH] Restauration backup automatique...")
        shutil.copy2(backup, MAESTRO_PATH)
        print(f"[PATCH] Backup restaure depuis {backup}")
        sys.exit(1)

    MAESTRO_PATH.write_text(src, encoding="utf-8")
    print(f"[PATCH] maestro.py V2.20 ecrit -> {MAESTRO_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  Ov3rLoRd -- Patch maestro.py -> V2.20")
    print("  Ov3rLoRd")
    print("=" * 60)
    patch_maestro()
    print("\n[PATCH] Termine.")
    print('  Test complet : python maestro.py --media-type anime --universe "evangelion battle asuka"')
    print('  Test rapide  : python maestro.py --no-qc --media-type anime --universe "evangelion battle asuka"')
