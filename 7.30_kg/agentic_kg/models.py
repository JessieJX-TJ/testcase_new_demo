from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _compact(value: Any, max_len: int = 220) -> str:
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


@dataclass
class DocumentProfile:
    file_type: str
    source_path: str
    source_name: str
    template_kind: str = "unknown"
    domain: str = ""
    sheets: List[str] = field(default_factory=list)
    selected_sheet: Optional[str] = None
    headers: List[str] = field(default_factory=list)
    sample_rows: List[List[str]] = field(default_factory=list)
    row_count: int = 0
    image_count: int = 0
    candidate_skill_ids: List[str] = field(default_factory=list)
    risk_points: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        parts = [
            f"type={self.file_type}",
            f"template={self.template_kind}",
            f"domain={self.domain or '-'}",
        ]
        if self.selected_sheet:
            parts.append(f"sheet={self.selected_sheet}")
        if self.headers:
            parts.append(f"headers={len(self.headers)}")
        if self.image_count:
            parts.append(f"images={self.image_count}")
        return ", ".join(parts)


@dataclass
class TripleRecord:
    head: str
    relation: str
    tail: str
    source_type: str
    source_file: str
    sheet_name: str = ""
    row: Optional[int] = None
    domain: str = ""
    skill_id: str = ""
    confidence: float = 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def key(self) -> tuple[str, str, str]:
        return (self.head.strip(), self.relation.strip(), self.tail.strip())


@dataclass
class QualityReport:
    total_triples: int = 0
    empty_field_count: int = 0
    duplicate_count: int = 0
    low_confidence_count: int = 0
    field_mismatch_count: int = 0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentRunTrace:
    agent: str
    status: str
    input_summary: str = ""
    output_summary: str = ""
    elapsed_ms: int = 0
    error: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["input_summary"] = _compact(payload["input_summary"])
        payload["output_summary"] = _compact(payload["output_summary"])
        if payload["error"]:
            payload["error"] = _compact(payload["error"], 500)
        return payload


@dataclass
class SkillMatch:
    skill_id: str
    name: str
    confidence: float
    status: str = "enabled"
    reason: str = ""
    tool: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentTaskResult:
    profile: Optional[DocumentProfile] = None
    skill: Optional[SkillMatch] = None
    triples: List[TripleRecord] = field(default_factory=list)
    quality: QualityReport = field(default_factory=QualityReport)
    traces: List[AgentRunTrace] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    skill_draft_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile.to_dict() if self.profile else None,
            "skill": self.skill.to_dict() if self.skill else None,
            "triples": [item.to_dict() for item in self.triples],
            "quality": self.quality.to_dict(),
            "traces": [item.to_dict() for item in self.traces],
            "artifacts": self.artifacts,
            "skill_draft_path": self.skill_draft_path,
        }
