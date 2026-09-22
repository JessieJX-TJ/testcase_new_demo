from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from utils.io_utils import ensure_dir


_STAGE_TO_LEGACY_DIR = {
    "ocr": "ocr",
    "description": "descriptions",
    "triples": "raw_triples",
}


def sanitize_path_component(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized or "unnamed"


def get_intermediate_root(project_root: Path, config: dict[str, Any]) -> Path:
    return project_root / config.get("output_root", "data") / "intermediate"


def get_final_root(project_root: Path, config: dict[str, Any]) -> Path:
    return project_root / config.get("output_root", "data") / "final"


def get_doc_output_dir(project_root: Path, config: dict[str, Any], item: dict[str, Any]) -> Path:
    doc_name = str(item.get("doc_name") or item.get("doc_id") or "unnamed")
    return get_intermediate_root(project_root, config) / sanitize_path_component(doc_name)


def get_doc_final_dir(project_root: Path, config: dict[str, Any], item: dict[str, Any]) -> Path:
    doc_name = str(item.get("doc_name") or item.get("doc_id") or "unnamed")
    return ensure_dir(get_final_root(project_root, config) / sanitize_path_component(doc_name))


def get_image_output_dir(project_root: Path, config: dict[str, Any], item: dict[str, Any]) -> Path:
    return get_doc_output_dir(project_root, config, item) / str(item["image_id"])


def get_stage_output_dir(project_root: Path, config: dict[str, Any], item: dict[str, Any], stage: str) -> Path:
    return ensure_dir(get_image_output_dir(project_root, config, item) / stage)


def get_legacy_stage_dir(project_root: Path, config: dict[str, Any], item: dict[str, Any], stage: str) -> Path:
    legacy_dir = _STAGE_TO_LEGACY_DIR[stage]
    return project_root / config.get("output_root", "data") / "intermediate" / legacy_dir / str(item["doc_id"])
