# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# segnet_premask.py — Cœur batch commun des pré-masques *SegNet (Ov3rLoRd)
#
# Logique partagée par les batch_premask.py de footsegnet / handsegnet /
# facesegnet / bodysegnet, factorisée pour éviter la duplication 4x déjà vue
# sur les bugs logits/masks et UnicodeEncodeError (une copie par projet =
# quatre corrections à chaque bug).
#
# Chaîne par image et par catégorie :
#   1. Bbox : primary_box_fn (ex. DWPose via foot_box_for_image) si fourni,
#      sinon/en échec → fallback grounding VLM (agents.vlm_grounding, requête
#      neutre par catégorie). Provenance tracée : "dwpose" | "qwenvl_grounding".
#      La confiance auto-déclarée du VLM est ignorée (non discriminante).
#   2. Inférence SAM du projet (infer_fn) sur la zone, convention ML brute
#      (BLANC=objet), feather=0.
#   3. Post-traitement : nettoyage composantes connexes (opt-in --clean,
#      comportement historique) puis closing SYSTÉMATIQUE des trous internes
#      (scipy binary_fill_holes — jamais de cavité noire dans un objet plein,
#      même helper de principe que le flood fill d'annotate.py).
#   4. Sorties : masque dans dataset\premasks\ (<stem>.png en mono-classe,
#      <stem>__<cat>.png en multi-classes — mêmes noms que masks_raw\), image
#      QC 2 panneaux dans premasks\_qc\<nom>_compare.png (source+bbox | masque,
#      compatible check_masks_qwenvl.py --mode premask), provenance et IoU vs
#      masque manuel éventuel dans premasks\_provenance.csv, échecs dans
#      premasks\_failures.log.
#
# Jamais d'écriture dans masks_raw\ (annotation manuelle intouchable).

import csv
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

REPO_ROOT = Path(r"D:\OVERLORD")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.vlm_grounding import grounding_boxes  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
COMPARE_PANEL_HEIGHT = 512

PROVENANCE_FIELDS = ["timestamp", "image", "category", "box_source",
                     "x", "y", "w", "h", "status", "mask_pct",
                     "iou_manual", "sam_score", "elapsed_s"]


@dataclass
class PremaskCategory:
    """Une catégorie de pré-masque d'un projet SegNet.

    name             : None = projet mono-classe (masque <stem>.png, ex.
                       footsegnet) ; sinon suffixe multi-classes
                       (<stem>__<name>.png, ex. "hand", "eyes").
    grounding_object : requête de grounding VLM, neutre et sans couleur
                       (ex. "the character's hands").
    primary_box_fn   : source de bbox principale (ex. DWPose) — callable
                       (Path) -> (x, y, w, h) | None ; None = grounding direct.
    infer_kwargs     : kwargs additionnels pour infer_fn (ex. {"refine": True}
                       pour footsegnet, {"part": "hand"} pour les autres).
    keep_components  : nb de composantes connexes gardées par --clean.
    """
    name: str | None
    grounding_object: str
    primary_box_fn: Callable | None = None
    infer_kwargs: dict = field(default_factory=dict)
    keep_components: int = 2

    def out_name(self, stem: str) -> str:
        return f"{stem}.png" if self.name is None else f"{stem}__{self.name}.png"

    def label(self) -> str:
        return self.name or "mask"


# ── Post-traitement masque ───────────────────────────────────────────────────

def clean_mask(mask_bin: np.ndarray, keep: int = 2) -> np.ndarray:
    """Garde les `keep` plus grosses composantes connexes (bruit isolé retiré).
    Comportement historique de footsegnet\\batch_premask.py."""
    labeled, n = ndimage.label(mask_bin)
    if n <= keep:
        return mask_bin
    sizes = ndimage.sum(mask_bin, labeled, index=range(1, n + 1))
    keep_labels = set((np.argsort(sizes)[::-1][:keep] + 1).tolist())
    return np.isin(labeled, list(keep_labels)).astype(np.uint8)


def fill_mask_holes(mask_bin: np.ndarray) -> np.ndarray:
    """Closing des trous internes (noir enclavé dans du blanc) : un objet
    plein ne doit jamais contenir de cavité. binary_fill_holes ne touche que
    les zones entièrement encloses — les échancrures ouvertes sur le fond
    restent intactes."""
    return ndimage.binary_fill_holes(mask_bin).astype(np.uint8)


# ── QC visuel ────────────────────────────────────────────────────────────────

def _build_compare(source: Image.Image, boxes: list[tuple[int, int, int, int]],
                   box_source: str, mask: Image.Image,
                   label: str) -> Image.Image:
    """Source + bbox(es) (ROUGE=dwpose, VERT=qwenvl_grounding — même code
    couleur que le test de grounding) | masque, à hauteur fixe."""
    source = source.convert("RGB")
    color = (255, 0, 0) if box_source == "dwpose" else (0, 255, 0)
    draw = ImageDraw.Draw(source)
    for x, y, w, h in boxes:
        draw.rectangle([x, y, x + w, y + h], outline=color, width=4)

    panels = [(source, f"SOURCE + BOX ({box_source})"),
              (mask, f"PREMASK {label}")]
    rendered = []
    for img, text in panels:
        pw = round(img.width * COMPARE_PANEL_HEIGHT / img.height)
        panel = img.convert("RGB").resize((pw, COMPARE_PANEL_HEIGHT),
                                          Image.LANCZOS)
        d = ImageDraw.Draw(panel)
        d.rectangle([0, 0, panel.width - 1, 18], fill=(0, 0, 0))
        d.text((4, 4), text, fill=(255, 255, 0))
        rendered.append(panel)

    sep = 4
    total_w = sum(p.width for p in rendered) + sep * (len(rendered) - 1)
    canvas = Image.new("RGB", (total_w, COMPARE_PANEL_HEIGHT), (128, 128, 128))
    px = 0
    for p in rendered:
        canvas.paste(p, (px, 0))
        px += p.width + sep
    return canvas


# ── Helpers sélection / rapport ──────────────────────────────────────────────

def _matches_only(stem: str, only: set[str], only_nums: set[int]) -> bool:
    suffix = stem.rsplit("_", 1)[-1]
    return (stem in only or suffix in only
            or (suffix.isdigit() and int(suffix) in only_nums))


def _failure_names(failure_log: Path) -> set[str]:
    """Noms d'images journalisés en échec (lignes '  POSE/INFER/BOX <nom>')."""
    names: set[str] = set()
    if not failure_log.exists():
        return names
    for line in failure_log.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ("POSE", "INFER", "BOX"):
            names.add(parts[1])
    return names


def _migrate_provenance_header(csv_path: Path) -> None:
    """
    Réécrit _provenance.csv avec l'en-tête PROVENANCE_FIELDS courant si un
    ancien schéma est détecté (ex. colonne `sam_score` ajoutée après coup) —
    sinon un DictWriter avec un fieldnames plus large que l'en-tête existant
    désaligne silencieusement toutes les lignes déjà écrites (l'en-tête n'est
    écrit qu'une fois, à la création du fichier).

    Lit en mode positionnel (pas DictReader) : une ligne dont le nombre de
    valeurs correspond à un en-tête plus ancien (moins de colonnes) est
    mappée sur cet ancien en-tête, colonnes manquantes -> "". Gère aussi le
    cas d'un fichier déjà mixte (ancien + nouveau schéma) sans corrompre les
    lignes déjà au nouveau format.
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    old_header, raw_rows = rows[0], rows[1:]
    if old_header == PROVENANCE_FIELDS:
        return

    migrated = []
    for raw in raw_rows:
        if len(raw) == len(PROVENANCE_FIELDS):
            header = PROVENANCE_FIELDS
        elif len(raw) == len(old_header):
            header = old_header
        else:
            continue   # ligne illisible (tronquée) — ignorée plutôt que plantée
        as_dict = dict(zip(header, raw))
        migrated.append({k: as_dict.get(k, "") for k in PROVENANCE_FIELDS})

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=PROVENANCE_FIELDS)
        writer.writeheader()
        writer.writerows(migrated)


def _append_provenance(csv_path: Path, rows: list[dict]) -> None:
    new_file = not csv_path.exists()
    if not new_file:
        _migrate_provenance_header(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=PROVENANCE_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def load_sam_scores(premasks_dir: Path) -> dict[str, float]:
    """
    Lit _provenance.csv et retourne {stem_image: score_sam} pour la ligne "OK"
    la plus récente de chaque image (le CSV est en append — plusieurs runs
    successifs peuvent avoir généré des lignes pour la même image ; on garde
    la dernière rencontrée, donc la plus récente puisque les lignes sont
    ajoutées dans l'ordre chronologique).

    Utilisé par annotate.py --by-confidence pour ouvrir les images en premier
    dans l'ordre où SAM était le moins sûr de lui (logique d'active learning).
    """
    csv_path = premasks_dir / "_provenance.csv"
    scores: dict[str, float] = {}
    if not csv_path.exists():
        return scores
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "OK":
                continue
            raw = row.get("sam_score", "")
            if not raw:
                continue
            stem = Path(row["image"]).stem
            try:
                scores[stem] = float(raw)
            except ValueError:
                continue
    return scores


def _iou(a: np.ndarray, b: np.ndarray) -> float | None:
    union = np.logical_or(a, b).sum()
    if union == 0:
        return None
    return float(np.logical_and(a, b).sum() / union)


def _enclosing_box(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    """Boîte englobante de plusieurs zones (x, y, w, h) — pour la colonne
    bbox unique du CSV de provenance quand le grounding est multi-instance."""
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return (x1, y1, x2 - x1, y2 - y1)


def _infer_union(infer_fn: Callable, img_path: Path, out_path: Path,
                 boxes: list[tuple[int, int, int, int]], threshold: float,
                 infer_kwargs: dict) -> tuple[bool, float | None]:
    """
    Inférence SAM par bbox puis UNION des masques dans out_path (une passe
    par instance au lieu d'une passe sur une bbox englobante géante — mode
    multi-instance). Retourne (False, None) si aucune passe n'a abouti.

    Le score retourné est le score de confiance natif de SAM (scores[0] du
    predictor, déjà calculé à chaque prédiction — cf. infer.py) : le MINIMUM
    des scores par instance en mode multi-instance (le maillon le plus faible
    détermine la confiance globale du masque final).
    """
    if len(boxes) == 1:
        result = infer_fn(frame_path=str(img_path), zone=boxes[0],
                          output_path=str(out_path), threshold=threshold,
                          pipeline_convention=False, feather_px=0,
                          return_score=True, **infer_kwargs)
        if result is None:
            return False, None
        _, sam_score = result
        return True, sam_score

    union: np.ndarray | None = None
    scores: list[float] = []
    for k, box in enumerate(boxes):
        part_path = out_path.with_suffix(f".part{k}.png")
        result = infer_fn(frame_path=str(img_path), zone=box,
                          output_path=str(part_path), threshold=threshold,
                          pipeline_convention=False, feather_px=0,
                          return_score=True, **infer_kwargs)
        if result is None:
            continue
        _, part_score = result
        scores.append(part_score)
        part = (np.array(Image.open(part_path).convert("L")) > 127).astype(np.uint8)
        union = part if union is None else np.maximum(union, part)
        part_path.unlink(missing_ok=True)
    if union is None:
        return False, None
    Image.fromarray(union * 255, mode="L").save(out_path)
    return True, min(scores) if scores else None


# ── Boucle principale ────────────────────────────────────────────────────────

def run_batch(project: str, dataset_root: Path, infer_fn: Callable,
              categories: list[PremaskCategory], *,
              limit: int | None = None, only: str | None = None,
              clean: bool = False, skip_existing: bool = False,
              force: bool = False, from_failures: bool = False,
              threshold: float = 0.5, grounding_margin: int = 20,
              no_fallback: bool = False) -> list[dict]:
    """
    Génère les pré-masques du projet. Voir l'en-tête du module pour la chaîne.

    Sélection des images : celles de dataset_root\\raw\\ sans masque manuel
    dans masks_raw\\ pour la catégorie (— `force` traite aussi les annotées,
    utile en validation : on n'écrit que dans premasks\\). `from_failures`
    restreint aux images des _failures.log précédents ; `only` filtre par
    stems/indices ; `skip_existing` saute les pré-masques déjà générés.
    """
    raw_dir = dataset_root / "raw"
    masks_raw_dir = dataset_root / "masks_raw"
    premasks_dir = dataset_root / "premasks"
    qc_dir = premasks_dir / "_qc"
    failure_log = premasks_dir / "_failures.log"
    provenance_csv = premasks_dir / "_provenance.csv"

    tag = f"[{project}_premask]"

    images = [p for p in sorted(raw_dir.iterdir())
              if p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("_")]

    if from_failures:
        failed = _failure_names(failure_log)
        images = [p for p in images if p.name in failed]
        print(f"{tag} --from-failures : {len(images)} image(s) reprises de "
              f"{failure_log.name}")
    if only:
        only_set = {tok.strip() for tok in only.split(",") if tok.strip()}
        only_nums = {int(t) for t in only_set if t.isdigit()}
        images = [p for p in images if _matches_only(p.stem, only_set, only_nums)]

    # (image, catégorie) restant à traiter
    todo: list[tuple[Path, PremaskCategory]] = []
    for img_path in images:
        for cat in categories:
            out_name = cat.out_name(img_path.stem)
            if (masks_raw_dir / out_name).exists() and not force:
                continue
            if skip_existing and (premasks_dir / out_name).exists():
                continue
            todo.append((img_path, cat))
    if limit:
        todo = todo[:limit]

    premasks_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    n_cats = len(categories)
    print(f"{tag} {len(todo)} pré-masque(s) à générer "
          f"({n_cats} catégorie(s), fallback grounding "
          f"{'désactivé' if no_fallback else 'actif'})")

    ok = 0
    counts_source = {"dwpose": 0, "qwenvl_grounding": 0,
                     "qwenvl_grounding_multi": 0}
    box_failed: list[str] = []
    infer_failed: list[str] = []
    rows: list[dict] = []
    ious: list[float] = []
    sam_scores: list[float] = []
    t_start = time.time()

    for i, (img_path, cat) in enumerate(todo, 1):
        label = cat.label()
        out_name = cat.out_name(img_path.stem)
        out_path = premasks_dir / out_name
        t0 = time.time()

        # 1. Bbox(es) : source principale puis fallback grounding
        #    multi-instance (une bbox PAR occurrence — deux pieds écartés,
        #    deux mains — au lieu d'une boîte englobante géante)
        boxes: list[tuple[int, int, int, int]] = []
        box_source = ""
        if cat.primary_box_fn is not None:
            primary = cat.primary_box_fn(img_path)
            if primary is not None:
                boxes = [primary]
                box_source = "dwpose"
        if not boxes and not no_fallback:
            found = grounding_boxes(img_path, cat.grounding_object,
                                    margin_px=grounding_margin)
            if found:
                boxes = found
                box_source = ("qwenvl_grounding" if len(found) == 1
                              else f"qwenvl_grounding_multi({len(found)})")
        if not boxes:
            print(f"{tag} ({i}/{len(todo)}) {img_path.name} [{label}] : "
                  f"aucune bbox (pose ET grounding) — ignoré")
            box_failed.append(out_name)
            rows.append({"timestamp": datetime.now().isoformat(timespec="seconds"),
                         "image": img_path.name, "category": label,
                         "box_source": "", "x": "", "y": "", "w": "", "h": "",
                         "status": "BOX_FAILED", "mask_pct": "",
                         "iou_manual": "", "sam_score": "",
                         "elapsed_s": round(time.time() - t0, 1)})
            continue
        box = _enclosing_box(boxes)   # bbox unique du CSV/print

        # 2. Inférence SAM du projet (convention ML brute, masque net) —
        #    une passe par bbox, union des masques si multi-instance
        infer_ok, sam_score = _infer_union(infer_fn, img_path, out_path, boxes,
                                           threshold, cat.infer_kwargs)
        if not infer_ok:
            print(f"{tag} ({i}/{len(todo)}) {img_path.name} [{label}] : "
                  f"inférence échouée — ignoré")
            infer_failed.append(out_name)
            rows.append({"timestamp": datetime.now().isoformat(timespec="seconds"),
                         "image": img_path.name, "category": label,
                         "box_source": box_source, "x": box[0], "y": box[1],
                         "w": box[2], "h": box[3], "status": "INFER_FAILED",
                         "mask_pct": "", "iou_manual": "", "sam_score": "",
                         "elapsed_s": round(time.time() - t0, 1)})
            continue

        # 3. Post-traitement : clean opt-in, closing des trous systématique
        mask_bin = (np.array(Image.open(out_path).convert("L")) > 127).astype(np.uint8)
        if clean:
            mask_bin = clean_mask(mask_bin, keep=cat.keep_components)
        mask_bin = fill_mask_holes(mask_bin)
        Image.fromarray(mask_bin * 255, mode="L").save(out_path)
        mask_pct = float(mask_bin.mean() * 100)

        # IoU vs masque manuel s'il existe (mode validation --force)
        iou_val: float | None = None
        manual_path = masks_raw_dir / out_name
        if manual_path.exists():
            manual_bin = (np.array(Image.open(manual_path).convert("L")) > 127)
            if manual_bin.shape == mask_bin.shape:
                iou_val = _iou(mask_bin.astype(bool), manual_bin)
                if iou_val is not None:
                    ious.append(iou_val)

        # 4. QC visuel 2 panneaux
        with Image.open(img_path) as source:
            compare = _build_compare(source, boxes, box_source,
                                     Image.fromarray(mask_bin * 255, mode="L"),
                                     label)
        compare.save(qc_dir / f"{Path(out_name).stem}_compare.png")

        ok += 1
        counts_source[box_source.split("(")[0]] += 1
        elapsed = time.time() - t0
        iou_txt = f" IoU={iou_val:.2f}" if iou_val is not None else ""
        score_txt = f" SAM={sam_score:.3f}" if sam_score is not None else ""
        if sam_score is not None:
            sam_scores.append(sam_score)
        print(f"{tag} ({i}/{len(todo)}) {out_name} [{box_source}] "
              f"{mask_pct:.1f}%{iou_txt}{score_txt} ({elapsed:.1f}s)")
        rows.append({"timestamp": datetime.now().isoformat(timespec="seconds"),
                     "image": img_path.name, "category": label,
                     "box_source": box_source, "x": box[0], "y": box[1],
                     "w": box[2], "h": box[3], "status": "OK",
                     "mask_pct": round(mask_pct, 2),
                     "iou_manual": round(iou_val, 3) if iou_val is not None else "",
                     "sam_score": round(sam_score, 3) if sam_score is not None else "",
                     "elapsed_s": round(elapsed, 1)})

    # 5. Rapports
    if rows:
        _append_provenance(provenance_csv, rows)

    total_failed = len(box_failed) + len(infer_failed)
    elapsed_total = time.time() - t_start
    print(f"\n{tag} Terminé : {ok} pré-masque(s) "
          f"(dwpose={counts_source['dwpose']}, "
          f"qwenvl_grounding={counts_source['qwenvl_grounding']}, "
          f"multi={counts_source['qwenvl_grounding_multi']}), "
          f"{total_failed} échec(s), {elapsed_total:.1f}s")
    if ious:
        print(f"{tag} IoU vs masques manuels : moyenne {np.mean(ious):.3f}, "
              f"médiane {np.median(ious):.3f}, min {min(ious):.3f} "
              f"sur {len(ious)} masque(s)")
    if sam_scores:
        print(f"{tag} Score SAM natif : moyenne {np.mean(sam_scores):.3f}, "
              f"médiane {np.median(sam_scores):.3f}, min {min(sam_scores):.3f} "
              f"sur {len(sam_scores)} masque(s) — cf. annotate.py --by-confidence")
    print(f"{tag} Provenance : {provenance_csv}")
    print(f"{tag} QC : {qc_dir}")

    if box_failed or infer_failed:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{ts}] batch_premask -- {ok} OK, "
                 f"{len(box_failed)} échec(s) bbox, {len(infer_failed)} échec(s) inférence"]
        lines += [f"  BOX    {n}" for n in box_failed]
        lines += [f"  INFER  {n}" for n in infer_failed]
        with open(failure_log, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"{tag} Échecs journalisés -> {failure_log}")

    return rows


def make_cli_parser(project: str, default_object_desc: str):
    """Parser argparse commun aux 4 wrappers batch_premask.py."""
    import argparse
    parser = argparse.ArgumentParser(
        description=f"{project} — génération batch de pré-masques "
                    f"(bbox pose/grounding VLM, {default_object_desc})"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Limiter aux N premiers pré-masques (test rapide)")
    parser.add_argument("--only", default=None,
                        help="Ne traiter que ces images : indices ou stems "
                             "séparés par des virgules, ex: '00113,00115'")
    parser.add_argument("--clean", action="store_true",
                        help="Garde les plus grosses composantes connexes, retire le bruit isolé")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--skip-existing", action="store_true",
                        help="Sauter les pré-masques déjà présents dans premasks\\")
    parser.add_argument("--force", action="store_true",
                        help="Traiter aussi les images déjà annotées dans masks_raw\\ "
                             "(validation : IoU vs masque manuel ; n'écrit que dans premasks\\)")
    parser.add_argument("--from-failures", action="store_true",
                        help="Ne traiter que les images des _failures.log précédents")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Désactiver le fallback grounding VLM (comportement historique)")
    parser.add_argument("--grounding-margin", type=int, default=20,
                        help="Marge en px autour de la bbox grounding (défaut: 20)")
    return parser
