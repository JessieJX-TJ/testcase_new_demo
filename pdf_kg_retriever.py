import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_KG_ROOT = PROJECT_ROOT / "7.30_kg" / "pdf_pipeline" / "data" / "final"


def _pdf_kg_root() -> Path:
    return Path(os.getenv("PDF_KG_FINAL_ROOT", str(DEFAULT_PDF_KG_ROOT))).expanduser()


def _safe_text(value) -> str:
    return str(value or "").strip()


def _char_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> set:
    compact = re.sub(r"\s+", "", text)
    grams = set()
    for n in range(min_n, max_n + 1):
        if len(compact) >= n:
            grams.update(compact[i:i + n] for i in range(len(compact) - n + 1))
    return grams


def _tokens(text: str) -> set:
    text = _safe_text(text).lower()
    tokens = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text))
    tokens.update(_char_ngrams(text))
    return {token for token in tokens if token}


def _iter_pdf_kg_files(root: Path) -> Iterable[Tuple[str, Path]]:
    if not root.exists():
        return []
    files = []
    for path in sorted(root.rglob("knowledge_graph.json")):
        # The root-level file is an aggregate. Use per-document files to avoid
        # duplicating evidence and to keep the document source explicit.
        if path.parent == root:
            continue
        files.append((path.parent.name, path))
    return files


@lru_cache(maxsize=4)
def _load_pdf_kg_records(root_text: str) -> Tuple[Dict, ...]:
    root = Path(root_text)
    records = []
    for doc_name, path in _iter_pdf_kg_files(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"⚠️ Failed to read PDF KG file: {path} ({exc})")
            continue
        if not isinstance(data, list):
            continue
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            head = _safe_text(item.get("head"))
            relation = _safe_text(item.get("relation"))
            tail = _safe_text(item.get("tail"))
            if not (head or relation or tail):
                continue
            sources = item.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            text = " ".join([doc_name, head, relation, tail, " ".join(map(str, sources))])
            records.append({
                "doc_name": doc_name,
                "head": head,
                "relation": relation,
                "tail": tail,
                "sources": [str(source) for source in sources],
                "conflict": bool(item.get("conflict", False)),
                "conflict_note": _safe_text(item.get("conflict_note")),
                "_text": text,
                "_tokens": tuple(sorted(_tokens(text))),
                "_idx": idx,
            })
    return tuple(records)


def _score_record(query: str, query_tokens: set, record: Dict) -> float:
    record_text = record["_text"].lower()
    record_tokens = set(record.get("_tokens") or [])
    if not record_tokens:
        return 0.0

    overlap = query_tokens & record_tokens
    if not overlap:
        return 0.0

    score = 0.0
    score += len(overlap)
    score += sum(min(len(token), 8) / 8 for token in overlap)

    normalized_query = re.sub(r"\s+", "", query.lower())
    for field in ("head", "relation", "tail", "doc_name"):
        value = _safe_text(record.get(field)).lower()
        compact_value = re.sub(r"\s+", "", value)
        if value and value in query.lower():
            score += 3.0
        if compact_value and compact_value in normalized_query:
            score += 3.0
        if normalized_query and normalized_query in compact_value:
            score += 4.0

    if record.get("conflict"):
        score *= 0.85
    return score


def retrieve_pdf_kg_evidence(
    query: str,
    top_k: int = 20,
    per_doc_limit: int = 6,
    min_score: float = 75.0,
) -> List[Dict]:
    """Retrieve relevant triples from PDF-extracted KG JSON files.

    The lexical scorer produces query-local raw scores, so the public ``score``
    is normalized to 0-100 before applying the strict ``score > min_score``
    filter.
    """
    query = _safe_text(query)
    if not query:
        return []

    root = _pdf_kg_root()
    records = _load_pdf_kg_records(str(root))
    query_tokens = _tokens(query)
    if not records or not query_tokens:
        return []

    scored = []
    for record in records:
        score = _score_record(query, query_tokens, record)
        if score > 0:
            public_record = {k: v for k, v in record.items() if not k.startswith("_")}
            public_record["raw_score"] = round(float(score), 4)
            scored.append(public_record)

    if not scored:
        return []

    max_raw_score = max(float(item["raw_score"]) for item in scored) or 1.0
    for item in scored:
        item["score"] = round((float(item["raw_score"]) / max_raw_score) * 100, 2)

    scored = [item for item in scored if item["score"] > min_score]
    scored.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    doc_counts = {}
    seen = set()
    for item in scored:
        key = (item["doc_name"], item["head"], item["relation"], item["tail"])
        if key in seen:
            continue
        if doc_counts.get(item["doc_name"], 0) >= per_doc_limit:
            continue
        seen.add(key)
        selected.append(item)
        doc_counts[item["doc_name"]] = doc_counts.get(item["doc_name"], 0) + 1
        if len(selected) >= top_k:
            break
    return selected


def format_pdf_kg_evidence(evidence: List[Dict], max_items: int = 20) -> str:
    if not evidence:
        return "No matching PDF specification triples were retrieved."

    lines = [
        "=== PDF specification knowledge-graph evidence (retrieved from JSON triples extracted from 4 SSTS/PDF documents) ===",
        "Treat the following evidence as supplementary constraints: keep signals, states, preconditions, actions, and expected results consistent with the specification; do not invent signal names or state values unsupported by the evidence.",
    ]
    for idx, item in enumerate(evidence[:max_items], 1):
        sources = ", ".join(item.get("sources") or [])
        source_text = f" | source: {sources}" if sources else ""
        conflict_text = " | conflict: true" if item.get("conflict") else ""
        lines.append(
            f"{idx}. [{item.get('doc_name', '-')}] "
            f"({item.get('head', '')}, {item.get('relation', '')}, {item.get('tail', '')})"
            f"{source_text}{conflict_text}"
        )
    return "\n".join(lines)
