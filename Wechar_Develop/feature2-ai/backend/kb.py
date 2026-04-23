import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import requests

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

try:
    import faiss
except Exception:
    faiss = None

# Files stored alongside backend
BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "kb_index.faiss"
META_PATH = BASE_DIR / "kb_meta.json"
TEXTS_PATH = BASE_DIR / "kb_texts.json"
STATE_PATH = BASE_DIR / "kb_state.json"

# Small model for embeddings; change as needed
EMB_MODEL_NAME = "all-MiniLM-L6-v2"


def _load_texts_from_data(data_dir: Path) -> List[Dict]:
    texts = []
    for p in sorted((data_dir).glob("*.md")):
        raw = p.read_text(encoding="utf-8")
        # simple fixed-size chunking; production should use tokenizer-aware chunking
        chunk_size = 800
        for i in range(0, len(raw), chunk_size):
            chunk = raw[i : i + chunk_size].strip()
            if not chunk:
                continue
            texts.append({"source": p.name, "chunk_id": i // chunk_size, "text": chunk})
    return texts


def _normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    for p in "，。！？；：、,.!?;:()（）[]【】{}\n\t\r\"'“”‘’":
        text = text.replace(p, " ")
    return " ".join(text.split())


def _char_ngrams(text: str, n: int = 2) -> set:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _lexical_score(query: str, content: str) -> float:
    q = _normalize_text(query)
    t = _normalize_text(content)
    if not q or not t:
        return 0.0

    q2 = _char_ngrams(q, 2)
    t2 = _char_ngrams(t, 2)
    q1 = set(q)
    t1 = set(t)

    overlap2 = len(q2 & t2) / max(1, len(q2))
    overlap1 = len(q1 & t1) / max(1, len(q1))
    contain_bonus = 0.2 if q in t else 0.0

    return float(min(1.0, 0.55 * overlap2 + 0.35 * overlap1 + contain_bonus))


def _save_meta_and_texts(texts: List[Dict]):
    metas = [{"source": t["source"], "chunk_id": t["chunk_id"]} for t in texts]
    text_values = [t["text"] for t in texts]
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False)
    with open(TEXTS_PATH, "w", encoding="utf-8") as f:
        json.dump(text_values, f, ensure_ascii=False)


def _save_state(state: Dict):
    merged = {
        "ready": bool(state.get("ready")),
        "backend": state.get("backend", "none"),
        "doc_count": int(state.get("doc_count", 0)),
        "updated_at": int(time.time()),
        "error": state.get("error", ""),
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)


def _load_state() -> Dict:
    if not STATE_PATH.exists():
        return {"ready": False, "backend": "none", "doc_count": 0, "error": ""}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "ready": bool(data.get("ready")),
            "backend": data.get("backend", "none"),
            "doc_count": int(data.get("doc_count", 0)),
            "updated_at": int(data.get("updated_at", 0)),
            "error": data.get("error", ""),
        }
    except Exception:
        return {"ready": False, "backend": "none", "doc_count": 0, "error": "state_parse_error"}


def build_index(data_dir: Path = None, index_path: Path = None):
    data_dir = data_dir or (BASE_DIR.parent / "data")
    index_path = index_path or INDEX_PATH

    texts = _load_texts_from_data(data_dir)
    if not texts:
        raise RuntimeError("no documents found to index")

    _save_meta_and_texts(texts)

    force_lexical = os.getenv("KB_FORCE_LEXICAL", "1").strip().lower() in {"1", "true", "yes", "on"}
    if force_lexical:
        state = {
            "ready": True,
            "backend": "lexical",
            "doc_count": len(texts),
            "error": "KB_FORCE_LEXICAL enabled",
        }
        _save_state(state)
        if index_path.exists():
            index_path.unlink()
        return state

    if SentenceTransformer is None or faiss is None:
        state = {
            "ready": True,
            "backend": "lexical",
            "doc_count": len(texts),
            "error": "sentence-transformers/faiss unavailable, fallback to lexical index",
        }
        _save_state(state)
        if index_path.exists():
            index_path.unlink()
        return state

    try:
        # Avoid hanging forever when model registry is unreachable.
        model_probe_timeout = int(os.getenv("KB_MODEL_PROBE_TIMEOUT", "12"))
        probe_url = f"https://huggingface.co/sentence-transformers/{EMB_MODEL_NAME}/resolve/main/modules.json"
        probe = requests.head(probe_url, timeout=model_probe_timeout)
        if probe.status_code >= 400:
            raise RuntimeError(f"huggingface_probe_status_{probe.status_code}")

        model = SentenceTransformer(EMB_MODEL_NAME)
        sentences = [t["text"] for t in texts]
        embs = model.encode(sentences, convert_to_numpy=True, show_progress_bar=True)

        # normalize for cosine similarity with IndexFlatIP
        faiss.normalize_L2(embs)
        dim = embs.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embs)

        faiss.write_index(index, str(index_path))
        state = {
            "ready": True,
            "backend": "faiss",
            "doc_count": len(texts),
            "error": "",
        }
        _save_state(state)
        return state
    except Exception as exc:
        # Build degraded but usable lexical index so retrieval still works.
        if index_path.exists():
            index_path.unlink()
        state = {
            "ready": True,
            "backend": "lexical",
            "doc_count": len(texts),
            "error": f"faiss_build_failed: {str(exc)[:240]}",
        }
        _save_state(state)
        return state


def load_index(index_path: Path = None):
    index_path = index_path or INDEX_PATH
    if not META_PATH.exists() or not TEXTS_PATH.exists():
        return None

    with open(META_PATH, "r", encoding="utf-8") as f:
        metas = json.load(f)
    with open(TEXTS_PATH, "r", encoding="utf-8") as f:
        texts = json.load(f)

    if index_path.exists() and faiss is not None:
        try:
            index = faiss.read_index(str(index_path))
            return {"backend": "faiss", "index": index, "metas": metas, "texts": texts}
        except Exception:
            pass

    return {"backend": "lexical", "index": None, "metas": metas, "texts": texts}


_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers unavailable")
        _MODEL = SentenceTransformer(EMB_MODEL_NAME)
    return _MODEL


def index_status() -> Dict:
    loaded = load_index()
    state = _load_state()
    if not loaded:
        return {
            "ready": False,
            "backend": "none",
            "doc_count": 0,
            "error": state.get("error", ""),
        }
    return {
        "ready": True,
        "backend": loaded["backend"],
        "doc_count": len(loaded["texts"]),
        "error": state.get("error", ""),
    }


def _query_lexical(query: str, metas: List[Dict], texts: List[str], k: int) -> List[Dict]:
    scored = []
    for idx, text in enumerate(texts):
        score = _lexical_score(query, text)
        if score <= 0:
            continue
        scored.append((score, idx))
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, idx in scored[:k]:
        meta = metas[idx] if idx < len(metas) else {}
        results.append(
            {
                "score": float(score),
                "source": meta.get("source") or "unknown.md",
                "chunk_id": int(meta.get("chunk_id", 0)),
                "text": texts[idx],
            }
        )
    return results


def query_index(query: str, k: int = 3, index_path: Path = None):
    loaded = load_index(index_path=index_path)
    if not loaded:
        return []

    backend = loaded["backend"]
    metas = loaded["metas"]
    texts = loaded["texts"]

    if backend != "faiss":
        return _query_lexical(query, metas, texts, k)

    try:
        model = _get_model()
        q_emb = model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(q_emb)
        D, I = loaded["index"].search(q_emb, k)
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            meta = metas[idx] if idx < len(metas) else {}
            results.append(
                {
                    "score": float(score),
                    "source": meta.get("source") or "unknown.md",
                    "chunk_id": int(meta.get("chunk_id", 0)),
                    "text": texts[idx],
                }
            )
        if results:
            return results
    except Exception:
        # FAISS path failed at query time; fallback to lexical retrieval.
        pass

    return _query_lexical(query, metas, texts, k)
