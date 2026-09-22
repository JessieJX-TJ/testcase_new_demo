import argparse
import json
import os
from typing import Dict, List

import faiss
import numpy as np
from neo4j import GraphDatabase

from config import NEO4J_CONFIG, RETRIEVAL_CONFIG, EMBEDDING_CONFIG
from embedding_client import get_encoder


DEFAULT_TYPED_LABELS = [
    "Precondition",
    "Action",
    "Expected",
    "TestCase",
]


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _fetch_distinct_names_by_label(driver, label: str) -> List[str]:
    cypher = f"""
    MATCH (n:`{label}`)
    WHERE n.name IS NOT NULL
    RETURN DISTINCT n.name AS name
    """
    with driver.session() as session:
        rows = session.run(cypher)
        names = [r["name"] for r in rows if r.get("name")]
    # Deduplicate + stable sort (keeps the index reproducible)
    return sorted(set(names))


def _build_faiss_index(embeddings: np.ndarray) -> faiss.Index:
    if embeddings.ndim != 2:
        raise ValueError(f"embeddings shape invalid: {embeddings.shape}")

    dim = int(embeddings.shape[1])
    index = faiss.IndexFlatL2(dim)

    arr = np.ascontiguousarray(embeddings, dtype=np.float32)
    index.add(arr)
    return index


def build_typed_indexes(
    index_dir: str,
    labels: List[str],
) -> None:
    print("=" * 80)
    print("Building typed category vector indexes")
    print("=" * 80)

    driver = GraphDatabase.driver(
        NEO4J_CONFIG["uri"], auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"])
    )

    try:
        _ensure_dir(index_dir)

        embedding_model_name = EMBEDDING_CONFIG["model_name"]
        encoder = get_encoder(embedding_model_name)
        index_meta: Dict[str, Dict] = {}

        for label in labels:
            print(f"\n📦 Processing type: {label}")
            names = _fetch_distinct_names_by_label(driver, label)
            print(f"   - Entity count: {len(names)}")

            if len(names) == 0:
                print("   ⚠️  No entities found, skipping")
                continue

            # Generate embeddings
            vec = encoder.encode(names, normalize_embeddings=True, convert_to_numpy=True)
            vec = np.ascontiguousarray(vec, dtype=np.float32)

            # Build FAISS index
            index = _build_faiss_index(vec)

            index_file = os.path.join(index_dir, f"{label}.faiss")
            text_file = os.path.join(index_dir, f"{label}.json")

            faiss.write_index(index, index_file)
            with open(text_file, "w", encoding="utf-8") as f:
                json.dump(names, f, ensure_ascii=False, indent=2)

            index_meta[label] = {
                "count": len(names),
                "index_file": index_file,
                "text_file": text_file,
                "embedding_model": embedding_model_name,
                "dim": int(index.d),
            }

            print(f"   ✅ Wrote index: {index_file}")
            print(f"   ✅ Wrote texts: {text_file}")

        meta_file = os.path.join(index_dir, "index_meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(index_meta, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Typed index build complete; wrote metadata: {meta_file}")
        print(f"✅ Built {len(index_meta)} category indexes")

    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="typed", choices=["typed"], help="only typed is supported")
    parser.add_argument(
        "--index-dir",
        default=RETRIEVAL_CONFIG["structured"]["index_dir"],
        help="index output directory",
    )
    parser.add_argument(
        "--labels",
        default=",".join(DEFAULT_TYPED_LABELS),
        help="comma-separated Neo4j labels to index",
    )

    args = parser.parse_args()

    labels = [x.strip() for x in (args.labels or "").split(",") if x.strip()]

    if args.mode == "typed":
        build_typed_indexes(
            index_dir=args.index_dir,
            labels=labels,
        )


if __name__ == "__main__":
    main()
