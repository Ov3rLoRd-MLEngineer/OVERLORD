"""
agents/infra/rag_indexer.py — Indexation semantique locale des sources RAG Ov3rLoRd

Decoupe en chunks les sources factuelles cataloguees dans DOCS/RAG_SOURCES.md
(CLAUDE.md, docs d'index, rapports d'audit/veille), calcule leurs embeddings
via sentence-transformers (modele leger, CPU uniquement -- ne touche jamais
aux GPU RTX 5080/5060 Ti, reservees respectivement aux runs ponctuels et au
service Ollama, cf. CLAUDE.md "Economie de session et de tokens") et persiste
le tout sur disque dans workspace/rag_index/.

Usage :
  py -3.12 agents/infra/rag_indexer.py            -> reconstruit l'index
  py -3.12 agents/infra/rag_indexer.py --status    -> affiche l'etat de l'index sans le reconstruire

Complement de DOCS/RAG_SOURCES.md : ce fichier documentait un catalogue de
chargement manuel ("pas encore une recherche automatique par pertinence") --
rag_indexer.py + rag_query.py fournissent ce mecanisme de recherche reel.
La liste SOURCES ci-dessous doit rester alignee avec le tableau de
DOCS/RAG_SOURCES.md si de nouveaux rapports y sont ajoutes (pas de lecture
automatique de ce tableau -- meme limite de maintenance manuelle assumee).
"""
import argparse
import hashlib
import io
import json
import logging
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', '').lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger("rag_indexer")

# Modele multilingue (le corpus est majoritairement en francais) -- teste face
# a all-MiniLM-L6-v2 (anglais) sur ce meme corpus : classement bien plus
# coherent des passages pertinents pour des questions en francais. Reste
# leger (~470 Mo, CPU seul, ~2s/requete).
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
# Prefixes requis par ce modele (voir sa fiche HF) : "passage: " a l'indexation,
# "query: " a la recherche -- sans quoi la qualite de similarite se degrade.
E5_PASSAGE_PREFIX = "passage: "
E5_QUERY_PREFIX = "query: "
INDEX_DIR = _REPO_ROOT / "workspace" / "rag_index"
EMBEDDINGS_FILE = INDEX_DIR / "embeddings.npy"
CHUNKS_FILE = INDEX_DIR / "chunks.jsonl"
MANIFEST_FILE = INDEX_DIR / "manifest.json"

CHUNK_MAX_CHARS = 900

# Sources factuelles -- alignees sur le tableau de DOCS/RAG_SOURCES.md
# (noyau toujours charge + rapports d'audit + rapports de veille DOCS/MD/).
SOURCES = [
    "CLAUDE.md",
    "DOCS/INDEX.md",
    "DOCS/LLM-Secour.md",
    "DOCS/RAG_SOURCES.md",
    "RAPPORT_AUDIT_PIPELINE_AOUT2026.md",
    "RAPPORT_IDEES_HISTORIQUE_V150_V227.md",
    "DOCS/MD/Audit de maturité technique 2026 — Pipeline anime IA.md",
    "DOCS/MD/Prompt engineering robuste anti-hallucination pour un pipeline SDXL ComfyUI de datasets synthétiques.md",
    "DOCS/MD/Regional Prompting.md",
    "DOCS/MD/Pipeline lineart -N&B - color after.md",
    "DOCS/MD/QC_ANATOMIQUE_AUDIT_LICENCES_20260729.md",
]


_BULLET_RE = __import__("re").compile(r"^\s*([-*]|\d+[.)])\s+")


def _split_units(text: str) -> list[str]:
    """Decoupe le texte en unites logiques : chaque item de liste ('- ', '* ',
    '1. ') demarre une nouvelle unite (au lieu d'etre noye dans le paragraphe
    qui l'entoure), les lignes vides separent les paragraphes normaux, et les
    titres '#' restent des marqueurs a part (prefixes par un espace unique
    reconnaissable par le caller)."""
    units: list[str] = []
    current: list[str] = []

    def flush():
        if current:
            body = "\n".join(current).rstrip()
            if body:
                units.append(body)
            current.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            units.append(line)  # marqueur de titre, reconnu via son '#' de tete
            continue
        if _BULLET_RE.match(stripped) and current:
            flush()
        current.append(line)
    flush()
    return units


def _chunk_markdown(text: str, source: str) -> list[dict]:
    """Decoupe un texte markdown en chunks ~CHUNK_MAX_CHARS en empaquetant des
    unites logiques (titres/items de liste/paragraphes, voir _split_units) --
    un item de liste court n'est jamais noye dans un chunk fourre-tout de 10+
    puces sans rapport, ce qui degradait la precision de la recherche
    semantique (puces ADR courtes vs. paragraphes de rapport plus longs).
    Garde le dernier titre vu comme contexte (`heading`) de chaque chunk."""
    units = _split_units(text)
    chunks = []
    current_heading = ""
    buf_units: list[str] = []
    buf_len = 0

    def flush():
        nonlocal buf_units, buf_len
        if not buf_units:
            return
        body = "\n".join(buf_units).strip()
        if body:
            chunks.append({"source": source, "heading": current_heading, "text": body})
        buf_units = []
        buf_len = 0

    for unit in units:
        if unit.startswith("#"):
            flush()
            current_heading = unit.lstrip("#").strip()
            continue
        unit_len = len(unit)
        if buf_units and buf_len + unit_len > CHUNK_MAX_CHARS:
            flush()
        buf_units.append(unit)
        buf_len += unit_len + 1
        if unit_len > CHUNK_MAX_CHARS:
            flush()
    flush()
    return chunks


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def build_index(sources: list[str] | None = None) -> dict:
    """Reconstruit l'index complet et le persiste dans INDEX_DIR. Retourne le manifest."""
    from sentence_transformers import SentenceTransformer
    import numpy as np

    sources = sources or SOURCES
    all_chunks: list[dict] = []
    source_hashes: dict[str, str] = {}
    skipped: list[str] = []

    for rel_path in sources:
        path = _REPO_ROOT / rel_path
        if not path.exists():
            skipped.append(rel_path)
            log.warning("[RAG_INDEXER] source introuvable, ignoree : %s", rel_path)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        source_hashes[rel_path] = _file_hash(path)
        file_chunks = _chunk_markdown(text, rel_path)
        all_chunks.extend(file_chunks)
        log.info("[RAG_INDEXER] %s -> %d chunk(s)", rel_path, len(file_chunks))

    if not all_chunks:
        raise RuntimeError("Aucune source RAG trouvee -- index non reconstruit (verifier SOURCES / chemins repo).")

    log.info("[RAG_INDEXER] chargement du modele %s (CPU)...", EMBEDDING_MODEL)
    t0 = time.time()
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    log.info("[RAG_INDEXER] modele charge en %.1fs", time.time() - t0)

    texts = [E5_PASSAGE_PREFIX + c["text"] for c in all_chunks]
    t0 = time.time()
    embeddings = model.encode(
        texts, batch_size=32, show_progress_bar=False,
        convert_to_numpy=True, normalize_embeddings=True,
    ).astype("float32")
    log.info("[RAG_INDEXER] %d chunks embeddes en %.1fs", len(texts), time.time() - t0)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_FILE, embeddings)
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        for i, c in enumerate(all_chunks):
            f.write(json.dumps({"id": i, **c}, ensure_ascii=False) + "\n")

    manifest = {
        "model": EMBEDDING_MODEL,
        "embedding_dim": int(embeddings.shape[1]),
        "num_chunks": len(all_chunks),
        "sources": source_hashes,
        "skipped_sources": skipped,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "device": "cpu",
    }
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    log.info("[RAG_INDEXER] index persiste dans %s (%d chunks, dim %d)",
              INDEX_DIR, manifest["num_chunks"], manifest["embedding_dim"])
    return manifest


def index_status() -> dict:
    """Etat de l'index sur disque sans rien reconstruire."""
    if not MANIFEST_FILE.exists():
        return {"exists": False}
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    manifest["exists"] = True
    manifest["embeddings_file_present"] = EMBEDDINGS_FILE.exists()
    manifest["chunks_file_present"] = CHUNKS_FILE.exists()
    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Affiche l'etat de l'index sans le reconstruire")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(index_status(), ensure_ascii=False, indent=2))
    else:
        build_index()
