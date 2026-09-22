from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.io_utils import ensure_dir, save_json


VALID_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_manifest(config: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    runtime = config.get("runtime", {})
    limit_per_doc = int(runtime.get("limit_per_doc", 0) or 0)
    manifest: list[dict[str, Any]] = []
    for doc in config.get("input_documents", []):
        doc_id = doc["doc_id"]
        doc_name = doc["doc_name"]
        image_dir = Path(doc["image_dir"])
        if not image_dir.exists():
            continue
        images = sorted([p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in VALID_SUFFIXES])
        if limit_per_doc > 0:
            images = images[:limit_per_doc]
        for index, image_path in enumerate(images, start=1):
            image_id = f"{doc_id}_{index:04d}"
            manifest.append(
                {
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "image_id": image_id,
                    "image_path": str(image_path),
                    "file_name": image_path.name,
                    "source_dir": str(image_dir),
                }
            )
    output_root = project_root / config.get("output_root", "data") / "manifests"
    ensure_dir(output_root)
    save_json(output_root / "image_manifest.json", manifest)
    return manifest
