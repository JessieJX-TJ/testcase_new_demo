from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from utils.io_utils import ensure_dir, load_json, load_text, save_json, save_text
from utils.output_paths import get_legacy_stage_dir, get_stage_output_dir
from utils.text_utils import looks_like_valid_term, normalize_term


def _append_term(
    whitelist_terms: list[str],
    seen_terms: set[str],
    text: str,
    score: float,
    conf_threshold: float,
    min_term_length: int,
    max_term_length: int,
    max_whitelist_terms: int,
) -> None:
    if score < conf_threshold:
        return
    if len(whitelist_terms) >= max_whitelist_terms:
        return
    if not looks_like_valid_term(text, min_term_length, max_term_length):
        return
    normalized_key = text.casefold()
    if normalized_key in seen_terms:
        return
    seen_terms.add(normalized_key)
    whitelist_terms.append(text)


def _extract_records_from_result(result: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not result:
        return records

    def _to_jsonable_bbox(bbox: Any) -> Any:
        if hasattr(bbox, "tolist"):
            return bbox.tolist()
        return bbox

    def _append_from_mapping(payload: Any) -> bool:
        if not hasattr(payload, "get"):
            return False
        texts = payload.get("rec_texts")
        scores = payload.get("rec_scores")
        if scores is None or (hasattr(scores, "__len__") and len(scores) == 0):
            scores = []
        boxes = payload.get("rec_polys")
        if boxes is None or (hasattr(boxes, "__len__") and len(boxes) == 0):
            boxes = payload.get("dt_polys")
        if boxes is None or (hasattr(boxes, "__len__") and len(boxes) == 0):
            boxes = payload.get("rec_boxes")
        if boxes is None:
            boxes = []
        if not isinstance(texts, list):
            return False
        for line_index, text in enumerate(texts):
            score = scores[line_index] if line_index < len(scores) else 0.0
            bbox = boxes[line_index] if line_index < len(boxes) else None
            records.append(
                {
                    "text": normalize_term(str(text)),
                    "score": float(score),
                    "bbox": _to_jsonable_bbox(bbox),
                    "line_index": line_index,
                }
            )
        return True

    if _append_from_mapping(result):
        return records
    if isinstance(result, list) and result and _append_from_mapping(result[0]):
        return records

    if isinstance(result, list) and result and isinstance(result[0], list):
        for line_index, line in enumerate(result[0]):
            if not isinstance(line, (list, tuple)) or len(line) != 2:
                continue
            bbox, payload = line
            if not isinstance(payload, (list, tuple)) or len(payload) != 2:
                continue
            text, score = payload
            records.append(
                {
                    "text": normalize_term(str(text)),
                    "score": float(score),
                    "bbox": _to_jsonable_bbox(bbox),
                    "line_index": line_index,
                }
            )
        return records

    iterable = result if isinstance(result, list) else [result]
    for line_index, item in enumerate(iterable):
        if not hasattr(item, "get"):
            continue
        text = item.get("text") or item.get("rec_text") or item.get("transcription") or ""
        score = item.get("score") or item.get("rec_score") or item.get("prob") or 0.0
        bbox = item.get("bbox") or item.get("box") or item.get("points")
        records.append(
            {
                "text": normalize_term(str(text)),
                "score": float(score),
                "bbox": _to_jsonable_bbox(bbox),
                "line_index": line_index,
            }
        )
    return records


def _create_ocr_engine(PaddleOCR: Any, ocr_config: dict[str, Any]) -> Any:
    lang = ocr_config.get("lang", "ch")
    modern_kwargs = {
        "lang": lang,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": bool(ocr_config.get("use_angle_cls", True)),
        "device": str(ocr_config.get("device", "cpu") or "cpu"),
        "enable_mkldnn": False,
    }
    legacy_kwargs = {
        "lang": lang,
        "use_angle_cls": bool(ocr_config.get("use_angle_cls", True)),
        "use_gpu": False,
        "show_log": False,
        "enable_mkldnn": False,
    }
    try:
        return PaddleOCR(**modern_kwargs)
    except Exception as modern_error:
        try:
            return PaddleOCR(**legacy_kwargs)
        except Exception as legacy_error:
            raise RuntimeError(
                f"PaddleOCR init failed. modern={modern_error}; legacy={legacy_error}"
            ) from legacy_error


def _run_ocr_engine(ocr: Any, image_path: Path) -> Any:
    if hasattr(ocr, "predict"):
        return ocr.predict(str(image_path))
    return ocr.ocr(str(image_path))


def run_ocr(manifest: list[dict[str, Any]], config: dict[str, Any], project_root: Path) -> dict[str, list[str]]:
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")

    from paddleocr import PaddleOCR
    import paddle

    ocr_config = config.get("ocr", {})
    ensure_dir(project_root / config.get("output_root", "data") / "intermediate")

    device_pref = str(ocr_config.get("device", "")).lower()
    use_gpu_flag = bool(ocr_config.get("use_gpu", False)) or device_pref == "gpu"
    try:
        if use_gpu_flag and paddle.is_compiled_with_cuda():
            paddle.set_device("gpu")
            print("[OCR] Using GPU device")
        else:
            paddle.set_device("cpu")
            if use_gpu_flag and not paddle.is_compiled_with_cuda():
                print("[OCR] GPU requested but CUDA is unavailable; fallback to CPU")
            else:
                print("[OCR] Using CPU device")
    except Exception as _:
        pass

    # Create PaddleOCR with parameters that work for both 2.x and 3.x.
    ocr = _create_ocr_engine(PaddleOCR, ocr_config)

    conf_threshold = float(ocr_config.get("conf_threshold", 0.8))
    min_term_length = int(ocr_config.get("min_term_length", 1))
    max_term_length = int(ocr_config.get("max_term_length", 80))
    max_whitelist_terms = int(ocr_config.get("max_whitelist_terms", 300))
    result_map: dict[str, list[str]] = {}

    for item in manifest:
        image_id = item["image_id"]
        image_path = Path(item["image_path"])
        item_dir = get_stage_output_dir(project_root, config, item, "ocr")
        full_json_path = item_dir / "full.json"
        whitelist_json_path = item_dir / "terms.json"
        whitelist_txt_path = item_dir / "ocr.txt"
        legacy_dir = get_legacy_stage_dir(project_root, config, item, "ocr")
        legacy_full_json_path = legacy_dir / f"{image_id}_ocr_full.json"
        legacy_whitelist_json_path = legacy_dir / f"{image_id}_ocr_terms.json"
        legacy_whitelist_txt_path = legacy_dir / f"{image_id}_ocr.txt"

        if whitelist_json_path.exists():
            terms_payload = load_json(whitelist_json_path, default={})
            result_map[image_id] = terms_payload.get("whitelist_terms", [])
            continue
        if full_json_path.exists() or whitelist_txt_path.exists():
            full_records = load_json(full_json_path, default=[])
            whitelist_text = load_text(whitelist_txt_path, default="")
            whitelist_terms = [normalize_term(line) for line in whitelist_text.splitlines() if normalize_term(line)]
            terms_payload = {
                "doc_id": item["doc_id"],
                "image_id": image_id,
                "image_path": str(image_path),
                "whitelist_terms": whitelist_terms,
                "term_count": len(whitelist_terms),
            }
            save_json(full_json_path, full_records)
            save_json(whitelist_json_path, terms_payload)
            if whitelist_terms:
                save_text(whitelist_txt_path, "\n".join(whitelist_terms))
            result_map[image_id] = whitelist_terms
            continue
        if legacy_whitelist_json_path.exists():
            terms_payload = load_json(legacy_whitelist_json_path, default={})
            full_records = load_json(legacy_full_json_path, default=[])
            whitelist_text = load_text(legacy_whitelist_txt_path, default="\n".join(terms_payload.get("whitelist_terms", [])))
            save_json(full_json_path, full_records)
            save_json(whitelist_json_path, terms_payload)
            save_text(whitelist_txt_path, whitelist_text)
            result_map[image_id] = terms_payload.get("whitelist_terms", [])
            continue

        result = _run_ocr_engine(ocr, image_path)
        full_records: list[dict[str, Any]] = []
        whitelist_terms: list[str] = []
        seen_terms: set[str] = set()

        extracted_records = _extract_records_from_result(result)
        for record in extracted_records:
            full_records.append(
                {
                    "text": record["text"],
                    "score": round(float(record["score"]), 4),
                    "bbox": record["bbox"],
                    "line_index": record["line_index"],
                }
            )
            _append_term(
                whitelist_terms=whitelist_terms,
                seen_terms=seen_terms,
                text=record["text"],
                score=float(record["score"]),
                conf_threshold=conf_threshold,
                min_term_length=min_term_length,
                max_term_length=max_term_length,
                max_whitelist_terms=max_whitelist_terms,
            )

        terms_payload = {
            "doc_id": item["doc_id"],
            "image_id": image_id,
            "image_path": str(image_path),
            "whitelist_terms": whitelist_terms,
            "term_count": len(whitelist_terms),
        }
        save_json(full_json_path, full_records)
        save_json(whitelist_json_path, terms_payload)
        save_text(whitelist_txt_path, "\n".join(whitelist_terms))
        result_map[image_id] = whitelist_terms

    return result_map
