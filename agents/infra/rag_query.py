"""
agents/infra/rag_query.py — Recherche semantique sur l'index RAG Ov3rLoRd

Interroge l'index construit par agents/infra/rag_indexer.py (embeddings
sentence-transformers, CPU) et retourne les N passages les plus pertinents
pour une question donnee.

Usage CLI :
  py -3.12 agents/infra/rag_query.py "quel sampler par defaut ?"
  py -3.12 agents/infra/rag_query.py "quel sampler par defaut ?" --top-k 3 --json

Usage Aider (`/read-only`) : les chemins retournes par --json (champ "source")
peuvent etre passes directement a `/read-only <chemin>` pour charger le
fichier source complet dans la session, une fois le passage pertinent repere.

Usage programmatique (voir agents/creative/llm_router.py) :
  from agents.infra.rag_query import retrieve, format_context
  passages = retrieve("ma question", top_k=3)
  context_block = format_context(passages)

Recherche hybride (semantique + BM25 lexical), fusionnees par rang (RRF) :
sur ce corpus (rapports techniques + ADR courtes truffees d'identifiants
rares -- `dpmpp_2m`, `taesdxl`...), la seule similarite cosinus d'un modele
leger souffre d'un effet de "hub" -- des passages longs et generiques
remontent avant la puce precise qui contient litteralement le terme
cherche. Un score BM25 (correspondance exacte de tokens) corrige ce biais
sans perdre la capacite de la recherche semantique a matcher des
reformulations qui ne partagent aucun mot-cle.
"""
import argparse
import io
import json
import logging
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.infra.rag_indexer import (
    EMBEDDING_MODEL, EMBEDDINGS_FILE, CHUNKS_FILE, MANIFEST_FILE, E5_QUERY_PREFIX,
)

log = logging.getLogger("rag_query")

# Caches module-level : eviter de recharger le modele (~10s), l'index et le
# BM25 a chaque appel quand rag_query est importe par un process long (ex.
# le routeur LLM appele en boucle sur une session).
_model = None
_embeddings = None
_chunks = None
_bm25 = None

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class RagIndexMissing(RuntimeError):
    """Leve quand l'index n'existe pas encore sur disque -- lancer
    `py -3.12 agents/infra/rag_indexer.py` pour le construire."""


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _load_index():
    global _embeddings, _chunks, _bm25
    if _embeddings is not None:
        return
    if not (EMBEDDINGS_FILE.exists() and CHUNKS_FILE.exists() and MANIFEST_FILE.exists()):
        raise RagIndexMissing(
            f"Index RAG absent dans {EMBEDDINGS_FILE.parent} -- "
            "lancer 'py -3.12 agents/infra/rag_indexer.py' d'abord."
        )
    import numpy as np
    from rank_bm25 import BM25Okapi
    _embeddings = np.load(EMBEDDINGS_FILE)
    _chunks = []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                _chunks.append(json.loads(line))
    _bm25 = BM25Okapi([_tokenize(c["text"]) for c in _chunks])


def _load_model():
    global _model
    if _model is not None:
        return _model
    from sentence_transformers import SentenceTransformer
    try:
        # modele deja telecharge/cache lors du premier `rag_indexer.py` --
        # evite un aller-retour reseau (HEAD huggingface.co) a chaque appel
        # depuis un process qui redemarre souvent (ex. llm_router.py en CLI).
        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu", local_files_only=True)
    except Exception:
        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _model


_RRF_K = 60  # constante standard de la Reciprocal Rank Fusion (Cormack et al. 2009)


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Retourne les `top_k` chunks les plus pertinents pour `query`, en
    fusionnant par rang (RRF) le classement semantique (cosinus sur les
    embeddings E5) et le classement lexical (BM25 sur les tokens bruts) --
    voir la note de module sur l'effet de hub. Chaque resultat :
    {source, heading, text, score, semantic_score, bm25_score}.

    Leve RagIndexMissing si l'index n'a pas encore ete construit -- a la
    charge de l'appelant de decider s'il doit degrader (voir llm_router.py
    qui capture cette exception pour ne jamais bloquer un appel LLM)."""
    import numpy as np

    _load_index()
    model = _load_model()
    query_vec = model.encode([E5_QUERY_PREFIX + query], convert_to_numpy=True,
                              normalize_embeddings=True).astype("float32")[0]

    # embeddings deja normalises a l'indexation -> produit scalaire = similarite cosinus.
    semantic_scores = _embeddings @ query_vec
    bm25_scores = np.asarray(_bm25.get_scores(_tokenize(query)))

    semantic_ranks = np.empty(len(semantic_scores), dtype=int)
    semantic_ranks[np.argsort(-semantic_scores)] = np.arange(len(semantic_scores))
    bm25_ranks = np.empty(len(bm25_scores), dtype=int)
    bm25_ranks[np.argsort(-bm25_scores)] = np.arange(len(bm25_scores))

    rrf_scores = 1.0 / (_RRF_K + semantic_ranks) + 1.0 / (_RRF_K + bm25_ranks)

    top_k = max(1, min(top_k, len(rrf_scores)))
    top_idx = np.argpartition(-rrf_scores, top_k - 1)[:top_k]
    top_idx = top_idx[np.argsort(-rrf_scores[top_idx])]

    results = []
    for idx in top_idx:
        idx = int(idx)
        chunk = _chunks[idx]
        results.append({
            "source": chunk["source"],
            "heading": chunk.get("heading", ""),
            "text": chunk["text"],
            "score": float(rrf_scores[idx]),
            "semantic_score": float(semantic_scores[idx]),
            "bm25_score": float(bm25_scores[idx]),
        })
    return results


def format_context(passages: list[dict], max_chars_per_passage: int = 600) -> str:
    """Formate une liste de passages (sortie de retrieve()) en bloc de contexte
    textuel compact, pret a etre injecte dans un system prompt LLM."""
    if not passages:
        return ""
    blocks = []
    for p in passages:
        text = p["text"].strip()
        if len(text) > max_chars_per_passage:
            text = text[:max_chars_per_passage].rsplit(" ", 1)[0] + "..."
        heading = f" ({p['heading']})" if p.get("heading") else ""
        blocks.append(f"[{p['source']}{heading}]\n{text}")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Question en langage naturel")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute au lieu du format lisible")
    args = parser.parse_args()

    try:
        passages = retrieve(args.query, top_k=args.top_k)
    except RagIndexMissing as e:
        print(f"[rag_query] {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(passages, ensure_ascii=False, indent=2))
    else:
        for i, p in enumerate(passages, 1):
            heading = f" — {p['heading']}" if p.get("heading") else ""
            print(f"--- [{i}] score={p['score']:.3f} {p['source']}{heading} ---")
            print(p["text"])
            print()
