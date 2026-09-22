from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prompts import DESCRIPTION_PROMPT
from utils.io_utils import ensure_dir, load_json, load_text, save_json, save_text
from utils.output_paths import get_legacy_stage_dir, get_stage_output_dir
from utils.model_utils import (
    call_with_retry,
    encode_image_base64,
    extract_multimodal_text,
    get_api_client,
    openai_chat_multimodal,
)
from utils.text_utils import extract_json_payload


def generate_descriptions(manifest: list[dict[str, Any]], config: dict[str, Any], project_root: Path) -> dict[str, dict[str, Any]]:
    desc_config = config.get("description", {})
    ensure_dir(project_root / config.get("output_root", "data") / "intermediate")
    descriptions: dict[str, dict[str, Any]] = {}
    client = get_api_client(config)

    for item in manifest:
        image_id = item["image_id"]
        image_path = Path(item["image_path"])
        item_dir = get_stage_output_dir(project_root, config, item, "description")
        raw_text_path = item_dir / "raw.txt"
        json_path = item_dir / "result.json"
        legacy_dir = get_legacy_stage_dir(project_root, config, item, "description")
        legacy_raw_text_path = legacy_dir / f"{image_id}_desc_raw.txt"
        legacy_json_path = legacy_dir / f"{image_id}_desc.json"

        if json_path.exists():
            descriptions[image_id] = load_json(json_path, default={})
            continue

        if raw_text_path.exists():
            raw_text = load_text(raw_text_path, default="")
            try:
                parsed = extract_json_payload(raw_text)
            except Exception:
                parsed = {
                    "table_type": "other",
                    "topic": "",
                    "row_semantics": "",
                    "column_semantics": "",
                    "has_merged_cells": False,
                    "header_levels": 0,
                    "core_entities": [],
                    "core_conditions": [],
                    "core_outputs": [],
                    "core_faults": [],
                    "core_timing_constraints": [],
                    "engineering_interpretation": raw_text.strip(),
                    "uncertain_points": ["模型输出未能解析为标准JSON，已从raw.txt断点恢复"],
                }
            save_json(json_path, parsed)
            descriptions[image_id] = parsed
            continue

        if legacy_json_path.exists():
            parsed = load_json(legacy_json_path, default={})
            raw_text = load_text(legacy_raw_text_path, default=json.dumps(parsed, ensure_ascii=False, indent=2))
            save_text(raw_text_path, raw_text)
            save_json(json_path, parsed)
            descriptions[image_id] = parsed
            continue

        image_b64 = encode_image_base64(image_path)

        def _call() -> Any:
            return openai_chat_multimodal(
                client=client,
                model=desc_config.get("model", "qwen-vl-plus"),
                image_b64=image_b64,
                prompt_text=DESCRIPTION_PROMPT,
            )

        response = call_with_retry(_call, max_retries=int(desc_config.get("max_retries", 3)))
        raw_text = extract_multimodal_text(response)
        save_text(raw_text_path, raw_text)
        try:
            parsed = extract_json_payload(raw_text)
        except Exception:
            parsed = {
                "table_type": "other",
                "topic": "",
                "row_semantics": "",
                "column_semantics": "",
                "has_merged_cells": False,
                "header_levels": 0,
                "core_entities": [],
                "core_conditions": [],
                "core_outputs": [],
                "core_faults": [],
                "core_timing_constraints": [],
                "engineering_interpretation": raw_text.strip(),
                "uncertain_points": ["模型输出未能解析为标准JSON，已降级保存原始文本"],
            }
        save_json(json_path, parsed)
        descriptions[image_id] = parsed

    return descriptions
