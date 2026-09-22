from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from prompts import build_triple_prompt
from utils.io_utils import ensure_dir, load_json, load_text, save_json, save_text
from utils.output_paths import get_legacy_stage_dir, get_stage_output_dir
from utils.model_utils import (
    call_with_retry,
    encode_image_base64,
    extract_multimodal_text,
    get_api_client,
    openai_chat_multimodal,
)
from utils.text_utils import extract_json_payload, normalize_term

STRUCTURE_TABLE_RELATIONS = ["输入来自", "输出到", "连接到", "控制对象", "包含子功能"]
SPLITTABLE_CONDITION_RELATIONS = {"前提条件", "触发条件", "抑制条件", "状态保持条件", "复位条件"}
ENUMERATION_PREFIX_PATTERN = re.compile(r"^满足以下(?:任意一|任一)?条件[:：]\s*")
ENUMERATION_ITEM_PATTERN = re.compile(r"\d+[.、]\s*")


def _get_relations_for_table_type(extraction_config: dict[str, Any], table_type: str) -> list[str]:
    configured_relations = list(extraction_config.get("allowed_relations", []))
    if table_type == "structure_table":
        return STRUCTURE_TABLE_RELATIONS
    return configured_relations


def _normalize_relation(relation: str) -> str:
    cleaned = relation.strip()
    lowered = cleaned.casefold()
    aliases = {
        "触发condition": "触发条件",
        "输入来自": "输入来自",
        "输出到": "输出到",
        "连接到": "连接到",
        "控制对象": "控制对象",
        "包含子功能": "包含子功能",
    }
    return aliases.get(lowered, cleaned)


def _split_enumerated_conditions(tail: str) -> list[str]:
    body = ENUMERATION_PREFIX_PATTERN.sub("", tail).strip()
    if not body:
        return []
    parts = re.split(r"(?=\d+[.、]\s*)", body)
    cleaned_parts: list[str] = []
    for part in parts:
        part = ENUMERATION_ITEM_PATTERN.sub("", part, count=1).strip(" ；;，,")
        normalized = normalize_term(part)
        if normalized:
            cleaned_parts.append(normalized)
    return cleaned_parts


def _split_conjunctive_conditions(tail: str) -> list[str]:
    normalized_tail = tail.replace("；", " && ").replace(";", " && ")
    parts = re.split(r"\s*(?:&&|并且|且)\s*", normalized_tail)
    cleaned_parts: list[str] = []
    for part in parts:
        normalized = normalize_term(part)
        if normalized:
            cleaned_parts.append(normalized)
    return cleaned_parts


def _expand_tail_fragments(relation: str, tail: str, table_type: str) -> list[str]:
    normalized_tail = normalize_term(tail)
    if table_type == "structure_table":
        return [normalized_tail] if normalized_tail else []
    if relation not in SPLITTABLE_CONDITION_RELATIONS:
        return [normalized_tail] if normalized_tail else []

    if ENUMERATION_PREFIX_PATTERN.search(normalized_tail) or re.search(r"\d+[.、]", normalized_tail):
        parts = _split_enumerated_conditions(normalized_tail)
        if len(parts) > 1:
            return parts

    if any(token in normalized_tail for token in ["&&", "并且", "且", ";", "；"]):
        parts = _split_conjunctive_conditions(normalized_tail)
        if len(parts) > 1:
            return parts

    return [normalized_tail] if normalized_tail else []


def _sanitize_triples(
    parsed: Any,
    allowed_relations: list[str],
    image_id: str,
    item: dict[str, Any],
    table_type: str,
) -> list[dict[str, Any]]:
    triples: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    if not isinstance(parsed, list):
        return triples
    for triple in parsed:
        if not isinstance(triple, dict):
            continue
        head = normalize_term(str(triple.get("head", "")).strip())
        relation = _normalize_relation(str(triple.get("relation", "")).strip())
        tail = str(triple.get("tail", "")).strip()
        if not head or not relation or not tail:
            continue
        if relation not in allowed_relations:
            continue
        expanded_tails = _expand_tail_fragments(relation, tail, table_type)
        for expanded_tail in expanded_tails:
            key = (head, relation, expanded_tail)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            triples.append(
                {
                    "head": head,
                    "relation": relation,
                    "tail": expanded_tail,
                    "triple_type": str(triple.get("triple_type", "candidate_rule")).strip() or "candidate_rule",
                    "evidence_terms": triple.get("evidence_terms", []),
                    "confidence_note": str(triple.get("confidence_note", "medium")).strip() or "medium",
                    "source_image_id": image_id,
                    "source_doc_id": item["doc_id"],
                    "source_table_type": table_type,
                }
            )
    return triples


def extract_triples(
    manifest: list[dict[str, Any]],
    config: dict[str, Any],
    project_root: Path,
    ocr_results: dict[str, list[str]],
    descriptions: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    extraction_config = config.get("triple_extraction", {})
    ensure_dir(project_root / config.get("output_root", "data") / "intermediate")
    all_triples: dict[str, list[dict[str, Any]]] = {}
    client = get_api_client(config)

    for item in manifest:
        image_id = item["image_id"]
        image_path = Path(item["image_path"])
        description_payload = descriptions.get(image_id, {})
        table_type = str(description_payload.get("table_type", "other")).strip() or "other"
        allowed_relations = _get_relations_for_table_type(extraction_config, table_type)
        item_dir = get_stage_output_dir(project_root, config, item, "triples")
        raw_text_path = item_dir / "raw.txt"
        json_path = item_dir / "result.json"
        legacy_dir = get_legacy_stage_dir(project_root, config, item, "triples")
        legacy_raw_text_path = legacy_dir / f"{image_id}_triples_raw.txt"
        legacy_json_path = legacy_dir / f"{image_id}_triples.json"

        if json_path.exists():
            cached = load_json(json_path, default=[])
            triples = _sanitize_triples(cached, allowed_relations, image_id, item, table_type)
            if triples != cached:
                save_json(json_path, triples)
            all_triples[image_id] = triples
            continue

        if raw_text_path.exists():
            raw_text = load_text(raw_text_path, default="")
            try:
                parsed = extract_json_payload(raw_text)
            except Exception:
                parsed = []
            triples = _sanitize_triples(parsed, allowed_relations, image_id, item, table_type)
            save_json(json_path, triples)
            all_triples[image_id] = triples
            continue

        if legacy_json_path.exists():
            parsed_legacy = load_json(legacy_json_path, default=[])
            raw_text = load_text(legacy_raw_text_path, default=json.dumps(parsed_legacy, ensure_ascii=False, indent=2))
            triples = _sanitize_triples(parsed_legacy, allowed_relations, image_id, item, table_type)
            save_text(raw_text_path, raw_text)
            save_json(json_path, triples)
            all_triples[image_id] = triples
            continue

        whitelist = ocr_results.get(image_id, [])
        description_text = json.dumps(description_payload, ensure_ascii=False, indent=2)
        prompt = build_triple_prompt(
            ocr_whitelist=whitelist,
            table_description_json=description_text,
            allowed_relations=allowed_relations,
            table_type=table_type,
        )

        image_b64 = encode_image_base64(image_path)

        def _call() -> Any:
            return openai_chat_multimodal(
                client=client,
                model=extraction_config.get("model", "qwen-vl-plus"),
                image_b64=image_b64,
                prompt_text=prompt,
            )

        response = call_with_retry(_call, max_retries=int(extraction_config.get("max_retries", 3)))
        raw_text = extract_multimodal_text(response)
        save_text(raw_text_path, raw_text)
        try:
            parsed = extract_json_payload(raw_text)
        except Exception:
            parsed = []
        triples = _sanitize_triples(parsed, allowed_relations, image_id, item, table_type)
        save_json(json_path, triples)
        all_triples[image_id] = triples

    return all_triples
