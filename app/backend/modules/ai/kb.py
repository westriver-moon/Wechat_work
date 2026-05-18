import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from modules.shared.paths import BACKEND_ROOT, DATA_ROOT
from modules.shared.text_utils import lexical_score, normalize_text

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

try:
    import faiss
except Exception:
    faiss = None

# Files stored alongside backend
BASE_DIR = BACKEND_ROOT
INDEX_PATH = BASE_DIR / "kb_index.faiss"
META_PATH = BASE_DIR / "kb_meta.json"
TEXTS_PATH = BASE_DIR / "kb_texts.json"
STATE_PATH = BASE_DIR / "kb_state.json"

# Small model for embeddings; change as needed
EMB_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE = max(240, int(os.getenv("KB_CHUNK_SIZE", "560")))
CHUNK_OVERLAP = max(40, min(CHUNK_SIZE // 2, int(os.getenv("KB_CHUNK_OVERLAP", "140"))))
LEXICAL_MIN_SCORE = max(0.0, float(os.getenv("KB_LEXICAL_MIN_SCORE", "0.05")))

QUERY_EXPANSIONS = {
    "选课": ["教务", "培养方案", "补退选", "教学日历"],
    "课程": ["教务", "培养方案", "补退选", "教学日历"],
    "转专业": ["学籍", "教务", "接收计划", "遴选办法"],
    "转系": ["转专业", "学籍", "接收计划", "遴选办法"],
    "宿舍": ["住宿", "入住", "宿管", "辅导员"],
    "校园网": ["网络", "认证", "账号", "信息化"],
    "网络": ["校园网", "认证", "账号", "信息化"],
    "图书馆": ["借阅", "馆藏", "数据库", "座位预约"],
    "奖学金": ["资助", "奖助", "申请", "评审"],
    "助学金": ["资助", "奖助", "申请", "评审"],
    "报到": ["迎新", "入学", "材料", "流程"],
    "军训": ["国防教育", "训练", "安排"],
    "医保": ["医疗", "健康", "报销", "门诊", "校医院"],
    "报销": ["医保", "校医院", "票据", "转诊"],
    "车辆": ["入校", "车证", "通行", "停车"],
    "家长车": ["车辆", "入校", "迎新", "停车"],
}


def _split_with_overlap(text: str, chunk_size: int, overlap: int) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    step = max(1, chunk_size - overlap)
    chunks = []
    for start in range(0, len(text), step):
        part = text[start : start + chunk_size].strip()
        if len(part) < 24:
            continue
        chunks.append(part)
        if start + chunk_size >= len(text):
            break
    return chunks


def _iter_markdown_blocks(raw: str) -> List[str]:
    blocks: List[str] = []
    heading_stack: List[str] = []
    paragraph: List[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        title = " / ".join(heading_stack[-2:]).strip()
        body = " ".join(paragraph).strip()
        paragraph.clear()
        if not body:
            return
        if title:
            blocks.append(f"{title}\n{body}")
        else:
            blocks.append(body)

    for line in (raw or "").replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(title)
            continue

        paragraph.append(stripped)

    flush_paragraph()
    return blocks


def _expand_query(query: str) -> str:
    query = (query or "").strip()
    if not query:
        return ""

    expanded_terms: List[str] = [query]
    normalized = normalize_text(query)
    for key, aliases in QUERY_EXPANSIONS.items():
        if key in query or key in normalized:
            expanded_terms.extend(aliases)

    dedup = []
    seen = set()
    for term in expanded_terms:
        token = term.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        dedup.append(token)
    return " ".join(dedup)


def _load_texts_from_data(data_dir: Path) -> List[Dict]:
    texts = []
    for p in sorted((data_dir).glob("*.md")):
        raw = p.read_text(encoding="utf-8")
        blocks = _iter_markdown_blocks(raw)
        chunk_id = 0
        for block in blocks:
            for chunk in _split_with_overlap(block, CHUNK_SIZE, CHUNK_OVERLAP):
                texts.append({"source": p.name, "chunk_id": chunk_id, "text": chunk})
                chunk_id += 1

        # Empty markdown files or parsing failures should still degrade gracefully.
        if not blocks:
            for chunk in _split_with_overlap(raw, CHUNK_SIZE, CHUNK_OVERLAP):
                texts.append({"source": p.name, "chunk_id": chunk_id, "text": chunk})
                chunk_id += 1
    return texts


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
    data_dir = data_dir or DATA_ROOT
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
_MODEL_LOCK = threading.Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
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
    expanded_query = _expand_query(query)
    scored = []
    for idx, text in enumerate(texts):
        score = lexical_score(expanded_query, text)
        source = str((metas[idx] if idx < len(metas) else {}).get("source") or "")
        if source and source.replace("_", "") in expanded_query:
            score = min(1.0, score + 0.05)
        scored.append((score, idx))
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, idx in scored:
        if len(results) >= k:
            break
        if score < LEXICAL_MIN_SCORE and results:
            break
        meta = metas[idx] if idx < len(metas) else {}
        results.append(
            {
                "score": float(score),
                "source": meta.get("source") or "unknown.md",
                "chunk_id": int(meta.get("chunk_id", 0)),
                "text": texts[idx],
            }
        )

    # Ensure at least one candidate is returned for downstream fallback synthesis.
    if not results and scored:
        score, idx = scored[0]
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
        # In query path, avoid hidden writes and fall back to in-memory lexical retrieval.
        texts = _load_texts_from_data(DATA_ROOT)
        if not texts:
            return []
        metas = [{"source": t["source"], "chunk_id": t["chunk_id"]} for t in texts]
        values = [t["text"] for t in texts]
        return _query_lexical(query, metas, values, k)

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
