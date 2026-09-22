from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentic_kg.agents.curator import SkillCuratorAgent
from agentic_kg.agents.profiler import DocumentProfilerAgent
from agentic_kg.agents.reviewer import QualityReviewerAgent
from agentic_kg.agents.router import SkillRouterAgent
from agentic_kg.models import AgentRunTrace, AgentTaskResult, DocumentProfile, TripleRecord
from agentic_kg.paths import MEMORY_ROOT, append_jsonl, ensure_runtime_dirs
from agentic_kg.tools.excel_tool import extract_excel_triples
from agentic_kg.tools.incremental_tool import run_incremental_analysis
from agentic_kg.tools.pdf_tool import get_pdf_doc_map, load_pdf_cached_bundle, triples_from_pdf_bundle
from agentic_kg.tools.pdf_tool import run_pdf_online_pipeline, triples_from_fused_pdf


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class AgenticKGOrchestrator:
    def __init__(self) -> None:
        ensure_runtime_dirs()
        self.profiler = DocumentProfilerAgent()
        self.router = SkillRouterAgent()
        self.reviewer = QualityReviewerAgent()
        self.curator = SkillCuratorAgent()

    def _record_run(self, task_type: str, result: AgentTaskResult) -> None:
        append_jsonl(
            MEMORY_ROOT / "extraction_runs.jsonl",
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "task_type": task_type,
                "result": result.to_dict(),
            },
        )

    def run_excel(self, excel_path: str | Path) -> AgentTaskResult:
        traces: List[AgentRunTrace] = []
        result = AgentTaskResult(traces=traces)

        start = time.perf_counter()
        profile, trace = self.profiler.profile_excel(excel_path)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.profile = profile

        start = time.perf_counter()
        skill, trace = self.router.route(profile)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.skill = skill

        triples: List[TripleRecord] = []
        if skill.status == "enabled" and profile.template_kind != "unknown":
            start = time.perf_counter()
            try:
                triples = extract_excel_triples(excel_path, profile, skill.skill_id)
                traces.append(
                    AgentRunTrace(
                        agent="Excel Extraction Agent",
                        status="success",
                        input_summary=f"{Path(excel_path).name}, skill={skill.skill_id}",
                        output_summary=f"抽取 {len(triples)} 条三元组",
                        elapsed_ms=_elapsed_ms(start),
                    )
                )
            except Exception as exc:
                traces.append(
                    AgentRunTrace(
                        agent="Excel Extraction Agent",
                        status="error",
                        input_summary=f"{Path(excel_path).name}, skill={skill.skill_id}",
                        output_summary="抽取失败",
                        elapsed_ms=_elapsed_ms(start),
                        error=str(exc),
                    )
                )
        else:
            start = time.perf_counter()
            draft_path, trace = self.curator.create_pending_draft(profile, reason=skill.reason)
            trace.elapsed_ms = _elapsed_ms(start)
            traces.append(trace)
            result.skill_draft_path = draft_path

        result.triples = triples
        start = time.perf_counter()
        quality, trace = self.reviewer.review(triples, profile)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.quality = quality
        self._record_run("excel", result)
        return result

    def run_pdf_cached(
        self,
        doc_name: Optional[str] = None,
        image_id: Optional[str] = None,
        mode: str = "cache",
    ) -> AgentTaskResult:
        traces: List[AgentRunTrace] = []
        result = AgentTaskResult(traces=traces)

        start = time.perf_counter()
        profile, trace = self.profiler.profile_pdf()
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.profile = profile

        start = time.perf_counter()
        skill, trace = self.router.route(profile)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.skill = skill

        doc_map = get_pdf_doc_map()
        selected_doc_name = doc_name or (next(iter(doc_map.keys())) if doc_map else "")
        items = doc_map.get(selected_doc_name, [])
        selected_item: Optional[Dict[str, Any]] = None
        if image_id:
            selected_item = next((item for item in items if item.get("image_id") == image_id), None)
        if selected_item is None and items:
            selected_item = items[0]

        triples: List[TripleRecord] = []
        bundle: Dict[str, Any] = {}
        start = time.perf_counter()
        if selected_item is None:
            traces.append(
                AgentRunTrace(
                    agent="PDF Extraction Agent",
                    status="warning",
                    input_summary=f"doc={selected_doc_name}, image={image_id or '-'}",
                    output_summary="未找到可读取的 manifest item",
                    elapsed_ms=_elapsed_ms(start),
                )
            )
        elif mode == "online":
            online_skill_id = "pdf.online_table_pipeline.v1"
            try:
                bundle = run_pdf_online_pipeline(
                    selected_item,
                    run_label=f"{selected_item.get('image_id', 'image')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                )
                triples = triples_from_fused_pdf(bundle, online_skill_id)
                if result.skill:
                    result.skill.skill_id = online_skill_id
                    result.skill.name = "PDF 表格在线多阶段抽取"
                    result.skill.tool = "pdf.run_online_pipeline"
                    result.skill.reason = "用户选择在线流水线：OCR -> Description -> Triple Extraction -> Fusion。"
                traces.append(
                    AgentRunTrace(
                        agent="PDF Pipeline Agent",
                        status="success",
                        input_summary=f"{selected_item.get('doc_name')} / {selected_item.get('image_id')}",
                        output_summary=f"在线完成 OCR/描述/抽取/融合，融合后三元组 {len(triples)} 条",
                        elapsed_ms=_elapsed_ms(start),
                        details={
                            "stage_logs": bundle.get("stage_logs", []),
                            "fusion_report": bundle.get("fusion_report", {}),
                        },
                    )
                )
                traces.append(
                    AgentRunTrace(
                        agent="Fusion & Conflict Agent",
                        status="success",
                        input_summary=f"raw={bundle.get('fusion_report', {}).get('raw_count', 0)}",
                        output_summary=(
                            f"fused={bundle.get('fusion_report', {}).get('fused_count', 0)}, "
                            f"conflicts={bundle.get('fusion_report', {}).get('conflict_count', 0)}"
                        ),
                        details=bundle.get("fusion_report", {}),
                    )
                )
            except Exception as exc:
                traces.append(
                    AgentRunTrace(
                        agent="PDF Pipeline Agent",
                        status="error",
                        input_summary=f"{selected_item.get('doc_name')} / {selected_item.get('image_id')}",
                        output_summary="在线流水线失败",
                        elapsed_ms=_elapsed_ms(start),
                        error=str(exc),
                    )
                )
                bundle = load_pdf_cached_bundle(selected_item)
                triples = triples_from_pdf_bundle(bundle, skill.skill_id)
                traces.append(
                    AgentRunTrace(
                        agent="PDF Cache Fallback Agent",
                        status="warning",
                        input_summary="online failed, fallback to cache",
                        output_summary=f"读取缓存三元组 {len(triples)} 条",
                        details={"fallback_reason": str(exc)},
                    )
                )
        else:
            bundle = load_pdf_cached_bundle(selected_item)
            triples = triples_from_pdf_bundle(bundle, skill.skill_id)
            traces.append(
                AgentRunTrace(
                    agent="PDF Extraction Agent",
                    status="success" if bundle.get("has_cached_triples") else "warning",
                    input_summary=f"{selected_item.get('doc_name')} / {selected_item.get('image_id')}",
                    output_summary=f"读取缓存三元组 {len(triples)} 条",
                    elapsed_ms=_elapsed_ms(start),
                    details={
                        "has_cached_triples": bundle.get("has_cached_triples"),
                        "image_exists": selected_item.get("image_exists"),
                    },
                )
            )

        result.triples = triples
        result.artifacts = {
            "doc_names": list(doc_map.keys()),
            "selected_doc_name": selected_doc_name,
            "selected_image_id": selected_item.get("image_id") if selected_item else "",
            "bundle": bundle,
        }
        start = time.perf_counter()
        quality, trace = self.reviewer.review(triples, profile)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.quality = quality
        self._record_run("pdf", result)
        return result

    def run_incremental(
        self,
        baseline_excel: str | Path,
        candidate_excel: str | Path,
        domain: str,
        domain_dir: str | Path,
        overwrite_current: bool = True,
    ) -> AgentTaskResult:
        traces: List[AgentRunTrace] = []
        result = AgentTaskResult(traces=traces)
        profile = DocumentProfile(
            file_type="incremental",
            source_path=str(candidate_excel),
            source_name=Path(candidate_excel).name,
            template_kind="lock_incremental",
            domain=domain,
            candidate_skill_ids=["incremental.case_scoped_diff.v1"],
            metadata={"baseline_excel": str(baseline_excel), "domain_dir": str(domain_dir)},
        )
        result.profile = profile

        start = time.perf_counter()
        skill, trace = self.router.route(profile)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.skill = skill

        start = time.perf_counter()
        try:
            payload = run_incremental_analysis(
                baseline_excel=baseline_excel,
                candidate_excel=candidate_excel,
                domain=domain,
                domain_dir=domain_dir,
                overwrite_current=overwrite_current,
            )
            traces.append(
                AgentRunTrace(
                    agent="Incremental Update Agent",
                    status="success",
                    input_summary=f"baseline={Path(baseline_excel).name}, candidate={Path(candidate_excel).name}",
                    output_summary=str(payload.get("summary", {})),
                    elapsed_ms=_elapsed_ms(start),
                    details={"logs": payload.get("logs", [])[-8:]},
                )
            )
        except Exception as exc:
            payload = {"summary": {}, "pending_add": [], "pending_remove": [], "pending_changed": [], "logs": []}
            traces.append(
                AgentRunTrace(
                    agent="Incremental Update Agent",
                    status="error",
                    input_summary=f"baseline={baseline_excel}, candidate={candidate_excel}",
                    output_summary="增量分析失败",
                    elapsed_ms=_elapsed_ms(start),
                    error=str(exc),
                )
            )

        triples: List[TripleRecord] = []
        for record in payload.get("pending_add", []):
            if record.get("record_type") != "triple":
                continue
            triples.append(
                TripleRecord(
                    head=str(record.get("head", "")),
                    relation=str(record.get("relation", "")),
                    tail=str(record.get("tail", "")),
                    source_type="incremental",
                    source_file=str(record.get("source_file", "")),
                    row=record.get("row"),
                    domain=str(record.get("domain", domain)),
                    skill_id=skill.skill_id if skill else "incremental.case_scoped_diff.v1",
                    confidence=1.0,
                    evidence={
                        "change_type": record.get("change_type"),
                        "case_key": record.get("case_key"),
                        "case_name": record.get("case_name"),
                    },
                )
            )

        result.triples = triples
        result.artifacts = payload
        start = time.perf_counter()
        quality, trace = self.reviewer.review(triples, profile)
        trace.elapsed_ms = _elapsed_ms(start)
        traces.append(trace)
        result.quality = quality
        self._record_run("incremental", result)
        return result
