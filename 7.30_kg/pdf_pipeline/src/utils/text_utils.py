from __future__ import annotations

import json
import re
from typing import Any


CODE_BLOCK_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def clean_model_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = CODE_BLOCK_PATTERN.sub("", cleaned).strip()
    return cleaned


def extract_json_payload(text: str) -> Any:
    cleaned = clean_model_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_list = cleaned.find("[")
        end_list = cleaned.rfind("]")
        if start_list != -1 and end_list != -1 and end_list > start_list:
            return json.loads(cleaned[start_list : end_list + 1])
        start_obj = cleaned.find("{")
        end_obj = cleaned.rfind("}")
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            return json.loads(cleaned[start_obj : end_obj + 1])
        raise


def normalize_space(value: str) -> str:
    value = value.replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_term(value: str) -> str:
    value = normalize_space(value)
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("：", ":")
    value = value.replace("，", ",")
    return value.strip(" ,;；。")


def looks_like_valid_term(value: str, min_len: int, max_len: int) -> bool:
    value = normalize_term(value)
    if not value:
        return False
    if len(value) < min_len or len(value) > max_len:
        return False
    if re.fullmatch(r"[-–_=+./\\|:;,0-9]+", value):
        return False
    return True
