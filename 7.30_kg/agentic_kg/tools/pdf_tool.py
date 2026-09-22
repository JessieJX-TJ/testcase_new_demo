from __future__ import annotations

import copy
import importlib
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agentic_kg.models import DocumentProfile, TripleRecord
from agentic_kg.paths import (
    PDF_CONFIG_PATH,
    PDF_MANIFEST_PATH,
    PDF_ROOT,
    add_pdf_src_to_path,
    load_json,
    resolve_project_path,
    load_local_env,
)


def _sanitize_path_component(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized or "unnamed"


def load_pdf_config() -> Dict[str, Any]:
    return load_json(PDF_CONFIG_PATH, default={}) or {}


def load_pdf_manifest() -> List[Dict[str, Any]]:
    manifest = load_json(PDF_MANIFEST_PATH, default=[]) or []
    fixed: List[Dict[str, Any]] = []
    for item in manifest:
        payload = dict(item)
        image_path = resolve_project_path(str(payload.get("image_path", "")))
        source_dir = resolve_project_path(str(payload.get("source_dir", "")))
        payload["resolved_image_path"] = str(image_path)
        payload["resolved_source_dir"] = str(source_dir)
        payload["image_exists"] = image_path.exists()
        fixed.append(payload)
    return fixed


def profile_pdf_manifest() -> DocumentProfile:
    config = load_pdf_config()
    manifest = load_pdf_manifest()
    doc_counter: Dict[str, int] = defaultdict(int)
    missing_count = 0
    for item in manifest:
        doc_counter[str(item.get("doc_name") or item.get("doc_id") or "unknown")] += 1
        if not item.get("image_exists"):
            missing_count += 1
    risk_points: List[str] = []
    if missing_count:
        risk_points.append(f"{missing_count} 张 manifest 图片当前路径不存在，已尝试旧路径映射。")
    if not manifest:
        risk_points.append("未找到 PDF manifest，请先运行或生成 pdf_kg_pipeline 的 image_manifest.json。")
    return DocumentProfile(
        file_type="pdf",
        source_path=str(PDF_MANIFEST_PATH),
        source_name="image_manifest.json",
        template_kind="pdf_manifest",
        domain=config.get("project_name", "pdf_kg_pipeline"),
        image_count=len(manifest),
        candidate_skill_ids=["pdf.cached_table_triples.v1"],
        risk_points=risk_points,
        metadata={
            "documents": dict(doc_counter),
            "config_path": str(PDF_CONFIG_PATH),
        },
    )


def check_pdf_online_readiness() -> Dict[str, Any]:
    load_local_env(PDF_ROOT / ".env")
    api_key_present = bool(__import__("os").environ.get("DASHSCOPE_API_KEY", "").strip())
    paddle_error = ""
    paddleocr_error = ""
    paddle_version = ""
    try:
        paddle_module = importlib.import_module("paddle")
        paddle_version = str(getattr(paddle_module, "__version__", "installed"))
        paddle_ready = True
    except Exception as exc:
        paddle_ready = False
        paddle_error = str(exc)
    try:
        importlib.import_module("paddleocr")
        paddleocr_ready = True
    except Exception as exc:
        paddleocr_ready = False
        paddleocr_error = str(exc)
    manifest = load_pdf_manifest()
    image_ready = any(item.get("image_exists") for item in manifest)
    blockers: List[str] = []
    if not api_key_present:
        blockers.append("缺少 DASHSCOPE_API_KEY，无法调用 Qwen-VL/Qwen-Plus。")
    if not paddleocr_ready or not paddle_ready:
        blockers.append("缺少 PaddleOCR/PaddlePaddle，无法执行实时 OCR。")
    if not image_ready:
        blockers.append("manifest 中没有可访问的本地图片。")
    return {
        "api_key_present": api_key_present,
        "paddleocr_ready": paddleocr_ready,
        "paddle_ready": paddle_ready,
        "paddle_version": paddle_version,
        "paddle_error": paddle_error,
        "paddleocr_error": paddleocr_error,
        "manifest_count": len(manifest),
        "local_image_count": sum(1 for item in manifest if item.get("image_exists")),
        "ready": not blockers,
        "blockers": blockers,
        "recommendation": (
            "建议使用 Python 3.10/3.11 独立 OCR 环境安装 paddleocr/paddlepaddle，"
            "Agent 前端继续通过子进程或服务调用 OCR。"
            if any("PaddleOCR" in item for item in blockers)
            else "在线 PDF 流水线具备运行条件。"
        ),
    }


def get_pdf_doc_map() -> Dict[str, List[Dict[str, Any]]]:
    doc_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in load_pdf_manifest():
        doc_name = str(item.get("doc_name") or item.get("doc_id") or "unknown")
        doc_map[doc_name].append(item)
    return dict(doc_map)


def _stage_paths(item: Dict[str, Any]) -> Dict[str, Path]:
    config = load_pdf_config()
    doc_name = str(item.get("doc_name") or item.get("doc_id") or "unknown")
    output_root = PDF_ROOT / config.get("output_root", "data") / "intermediate"
    image_dir = output_root / _sanitize_path_component(doc_name) / str(item["image_id"])
    return {
        "ocr_terms": image_dir / "ocr" / "terms.json",
        "ocr_full": image_dir / "ocr" / "full.json",
        "description": image_dir / "description" / "result.json",
        "description_raw": image_dir / "description" / "raw.txt",
        "triples": image_dir / "triples" / "result.json",
        "triples_raw": image_dir / "triples" / "raw.txt",
    }


def load_pdf_cached_bundle(item: Dict[str, Any]) -> Dict[str, Any]:
    paths = _stage_paths(item)
    bundle = {
        "item": item,
        "paths": {key: str(value) for key, value in paths.items()},
        "ocr_terms": load_json(paths["ocr_terms"], default={}),
        "ocr_full": load_json(paths["ocr_full"], default=[]),
        "description": load_json(paths["description"], default={}),
        "triples": load_json(paths["triples"], default=[]),
        "has_cached_triples": paths["triples"].exists(),
        "resolved_image_path": item.get("resolved_image_path") or str(resolve_project_path(str(item.get("image_path", "")))),
    }
    return bundle


def triples_from_pdf_bundle(bundle: Dict[str, Any], skill_id: str) -> List[TripleRecord]:
    item = bundle["item"]
    triples: List[TripleRecord] = []
    for record in bundle.get("triples") or []:
        triples.append(
            TripleRecord(
                head=str(record.get("head", "")),
                relation=str(record.get("relation", "")),
                tail=str(record.get("tail", "")),
                source_type="pdf",
                source_file=str(item.get("file_name", "")),
                sheet_name=str(record.get("source_table_type", "")),
                row=None,
                domain=str(item.get("doc_name", "")),
                skill_id=skill_id,
                confidence=0.8 if str(record.get("confidence_note", "medium")).lower() == "medium" else 1.0,
                evidence={
                    "image_id": item.get("image_id"),
                    "doc_id": item.get("doc_id"),
                    "image_path": bundle.get("resolved_image_path"),
                    "evidence_terms": record.get("evidence_terms", []),
                    "confidence_note": record.get("confidence_note", ""),
                },
            )
        )
    return triples


def _import_pdf_runtime() -> Dict[str, Any]:
    add_pdf_src_to_path()
    from scan_inputs import load_config
    from step2_ocr import run_ocr
    from step3_desc import generate_descriptions
    from step4_extract import extract_triples
    from step5_fuse import fuse_triples
    from utils.env_utils import load_local_env, require_env

    return {
        "load_config": load_config,
        "run_ocr": run_ocr,
        "generate_descriptions": generate_descriptions,
        "extract_triples": extract_triples,
        "fuse_triples": fuse_triples,
        "load_local_env": load_local_env,
        "require_env": require_env,
    }


def build_single_item_runtime_config(run_label: str | None = None) -> Dict[str, Any]:
    config = load_pdf_config()
    runtime_config = copy.deepcopy(config)
    label = run_label or time.strftime("%Y%m%d_%H%M%S")
    runtime_config["output_root"] = f"data/agentic_runs/{label}"
    runtime_config.setdefault("runtime", {})
    runtime_config["runtime"]["skip_existing"] = False
    runtime_config["runtime"]["limit_per_doc"] = 0
    return runtime_config


def run_pdf_online_pipeline(item: Dict[str, Any], run_label: str | None = None) -> Dict[str, Any]:
    """Run OCR, description, triple extraction and fusion for one PDF image.

    A dedicated output_root is used for each run so the existing pdf_kg_pipeline
    caches are not deleted or overwritten.
    """
    runtime = _import_pdf_runtime()
    runtime["load_local_env"](PDF_ROOT / ".env")
    runtime["require_env"]("DASHSCOPE_API_KEY")
    config = build_single_item_runtime_config(run_label)
    resolved_image = resolve_project_path(str(item.get("image_path", "")))
    if not resolved_image.exists():
        raise FileNotFoundError(f"PDF 图片不存在: {resolved_image}")
    single_item = dict(item)
    single_item["image_path"] = str(resolved_image)
    single_item["source_dir"] = str(resolved_image.parent)
    single_manifest = [single_item]

    stage_logs: List[str] = []
    ocr_results = runtime["run_ocr"](single_manifest, config, PDF_ROOT)
    stage_logs.append(f"[OCR] terms={len(ocr_results.get(single_item['image_id'], []))}")
    descriptions = runtime["generate_descriptions"](single_manifest, config, PDF_ROOT)
    desc_payload = descriptions.get(single_item["image_id"], {})
    stage_logs.append(f"[DESC] table_type={desc_payload.get('table_type', 'other')}")
    all_triples = runtime["extract_triples"](single_manifest, config, PDF_ROOT, ocr_results, descriptions)
    raw_count = len(all_triples.get(single_item["image_id"], []))
    stage_logs.append(f"[TRIPLE] raw={raw_count}")
    fused = runtime["fuse_triples"](all_triples, single_manifest, config, PDF_ROOT)
    stage_logs.append(f"[FUSE] fused={len(fused)}")

    bundle = load_pdf_cached_bundle_for_config(single_item, config)
    bundle["online_run"] = True
    bundle["run_output_root"] = str(PDF_ROOT / config.get("output_root", "data"))
    bundle["stage_logs"] = stage_logs
    bundle["fused_triples"] = fused
    bundle["fusion_report"] = analyze_fusion(all_triples.get(single_item["image_id"], []), fused)
    return bundle


def load_pdf_cached_bundle_for_config(item: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    doc_name = str(item.get("doc_name") or item.get("doc_id") or "unknown")
    output_root = PDF_ROOT / config.get("output_root", "data") / "intermediate"
    image_dir = output_root / _sanitize_path_component(doc_name) / str(item["image_id"])
    paths = {
        "ocr_terms": image_dir / "ocr" / "terms.json",
        "ocr_full": image_dir / "ocr" / "full.json",
        "description": image_dir / "description" / "result.json",
        "description_raw": image_dir / "description" / "raw.txt",
        "triples": image_dir / "triples" / "result.json",
        "triples_raw": image_dir / "triples" / "raw.txt",
    }
    return {
        "item": item,
        "paths": {key: str(value) for key, value in paths.items()},
        "ocr_terms": load_json(paths["ocr_terms"], default={}),
        "ocr_full": load_json(paths["ocr_full"], default=[]),
        "description": load_json(paths["description"], default={}),
        "triples": load_json(paths["triples"], default=[]),
        "has_cached_triples": paths["triples"].exists(),
        "resolved_image_path": str(resolve_project_path(str(item.get("image_path", "")))),
    }


def analyze_fusion(raw_triples: List[Dict[str, Any]], fused_triples: List[Dict[str, Any]]) -> Dict[str, Any]:
    seen: Dict[tuple[str, str, str], int] = defaultdict(int)
    for triple in raw_triples:
        key = (
            str(triple.get("head", "")).strip(),
            str(triple.get("relation", "")).strip(),
            str(triple.get("tail", "")).strip(),
        )
        seen[key] += 1
    duplicate_exact = sum(count - 1 for count in seen.values() if count > 1)
    conflicts = [item for item in fused_triples if item.get("conflict")]
    return {
        "raw_count": len(raw_triples),
        "fused_count": len(fused_triples),
        "duplicate_exact_removed": duplicate_exact,
        "semantic_reduction": max(0, len(raw_triples) - len(fused_triples)),
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:20],
    }


def triples_from_fused_pdf(bundle: Dict[str, Any], skill_id: str) -> List[TripleRecord]:
    item = bundle["item"]
    triples: List[TripleRecord] = []
    for record in bundle.get("fused_triples") or []:
        triples.append(
            TripleRecord(
                head=str(record.get("head", "")),
                relation=str(record.get("relation", "")),
                tail=str(record.get("tail", "")),
                source_type="pdf",
                source_file=str(item.get("file_name", "")),
                sheet_name="fused",
                row=None,
                domain=str(item.get("doc_name", "")),
                skill_id=skill_id,
                confidence=0.95 if not record.get("conflict") else 0.55,
                evidence={
                    "sources": record.get("sources", []),
                    "conflict": record.get("conflict", False),
                    "conflict_note": record.get("conflict_note", ""),
                    "run_output_root": bundle.get("run_output_root", ""),
                },
            )
        )
    return triples
