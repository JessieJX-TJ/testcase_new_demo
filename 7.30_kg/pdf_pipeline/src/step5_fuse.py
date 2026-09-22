from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from prompts import build_fusion_prompt
from utils.io_utils import ensure_dir, save_json, save_text
from utils.model_utils import call_with_retry, extract_generation_text, get_api_client, openai_chat_text
from utils.output_paths import get_doc_final_dir, get_final_root
from utils.text_utils import extract_json_payload, normalize_term


def _deduplicate_exact(flat_triples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for triple in flat_triples:
        key = (
            normalize_term(str(triple.get("head", ""))),
            normalize_term(str(triple.get("relation", ""))),
            normalize_term(str(triple.get("tail", ""))),
        )
        if key not in grouped:
            grouped[key] = {
                "head": triple.get("head", ""),
                "relation": triple.get("relation", ""),
                "tail": triple.get("tail", ""),
                "sources": list(triple.get("sources", [])),
                "conflict": bool(triple.get("conflict", False)),
                "conflict_note": str(triple.get("conflict_note", "")),
            }
        else:
            grouped[key]["sources"] = sorted(set(grouped[key]["sources"] + list(triple.get("sources", []))))
    return list(grouped.values())


def _fuse_flat_triples(
    flat_triples: list[dict[str, Any]],
    output_root: Path,
    client: Any,
    fusion_config: dict[str, Any],
    final_output_path: Path,
) -> list[dict[str, Any]]:
    ensure_dir(output_root)

    exact_deduped = _deduplicate_exact(flat_triples)
    save_json(output_root / "exact_deduped.json", exact_deduped)

    if not exact_deduped:
        save_json(final_output_path, [])
        return []

    batch_size = int(fusion_config.get("batch_size", 60))
    batches = [exact_deduped[i : i + batch_size] for i in range(0, len(exact_deduped), batch_size)]
    fused_batches: list[dict[str, Any]] = []

    for batch_index, batch in enumerate(batches, start=1):
        batch_path = output_root / f"fusion_batch_{batch_index:03d}.json"
        raw_text_path = output_root / f"fusion_batch_{batch_index:03d}_raw.txt"
        if batch_path.exists():
            with batch_path.open("r", encoding="utf-8") as f:
                fused_batches.extend(json.load(f))
            continue

        triples_json = json.dumps(batch, ensure_ascii=False, indent=2)
        prompt = build_fusion_prompt(triples_json)

        def _call() -> Any:
            return openai_chat_text(
                client=client,
                model=fusion_config.get("model", "qwen-plus"),
                prompt_text=prompt,
            )

        response = call_with_retry(_call, max_retries=int(fusion_config.get("max_retries", 3)))
        raw_text = extract_generation_text(response)
        save_text(raw_text_path, raw_text)
        try:
            parsed = extract_json_payload(raw_text)
        except Exception:
            parsed = batch
        fused = parsed if isinstance(parsed, list) else batch
        save_json(batch_path, fused)
        fused_batches.extend(fused)

    final_triples = _deduplicate_exact(fused_batches)
    save_json(final_output_path, final_triples)
    return final_triples


def fuse_triples(
    all_triples: dict[str, list[dict[str, Any]]],
    manifest: list[dict[str, Any]],
    config: dict[str, Any],
    project_root: Path,
) -> list[dict[str, Any]]:
    output_root = project_root / config.get("output_root", "data") / "intermediate" / "fused"
    final_root = ensure_dir(get_final_root(project_root, config))
    client = get_api_client(config)
    fusion_config = config.get("fusion", {})

    manifest_by_image_id = {item["image_id"]: item for item in manifest}
    all_flat_triples: list[dict[str, Any]] = []
    flat_triples_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for image_id, triples in all_triples.items():
        item = manifest_by_image_id.get(image_id, {})
        doc_id = str(item.get("doc_id", "unknown"))
        doc_name = str(item.get("doc_name", doc_id or "unknown"))
        for triple in triples:
            payload = {
                "head": triple.get("head", ""),
                "relation": triple.get("relation", ""),
                "tail": triple.get("tail", ""),
                "sources": [image_id],
                "conflict": False,
                "conflict_note": "",
                "table_type": triple.get("source_table_type", "other"),
                "evidence_terms": triple.get("evidence_terms", []),
                "source_doc_id": doc_id,
                "source_doc_name": doc_name,
            }
            all_flat_triples.append(payload)
            flat_triples_by_doc[doc_id].append(payload)

    for doc_id, doc_flat_triples in flat_triples_by_doc.items():
        item = next((candidate for candidate in manifest if candidate["doc_id"] == doc_id), {"doc_id": doc_id, "doc_name": doc_id})
        doc_output_root = output_root / doc_id
        doc_final_path = get_doc_final_dir(project_root, config, item) / "knowledge_graph.json"
        _fuse_flat_triples(doc_flat_triples, doc_output_root, client, fusion_config, doc_final_path)

    aggregate_final_path = final_root / "knowledge_graph.json"
    return _fuse_flat_triples(all_flat_triples, output_root / "all_documents", client, fusion_config, aggregate_final_path)
