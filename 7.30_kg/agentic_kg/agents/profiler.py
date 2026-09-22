from __future__ import annotations

from pathlib import Path

from agentic_kg.models import AgentRunTrace, DocumentProfile
from agentic_kg.tools.excel_tool import profile_excel
from agentic_kg.tools.pdf_tool import profile_pdf_manifest


class DocumentProfilerAgent:
    name = "Document Profiler Agent"

    def profile_excel(self, path: str | Path) -> tuple[DocumentProfile, AgentRunTrace]:
        profile = profile_excel(path)
        trace = AgentRunTrace(
            agent=self.name,
            status="success",
            input_summary=str(path),
            output_summary=profile.summary(),
            details={"risk_points": profile.risk_points, "sheets": profile.sheets},
        )
        return profile, trace

    def profile_pdf(self) -> tuple[DocumentProfile, AgentRunTrace]:
        profile = profile_pdf_manifest()
        trace = AgentRunTrace(
            agent=self.name,
            status="success",
            input_summary=profile.source_path,
            output_summary=profile.summary(),
            details=profile.metadata,
        )
        return profile, trace
