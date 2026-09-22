from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from agentic_kg.models import AgentRunTrace, DocumentProfile, QualityReport, TripleRecord


class QualityReviewerAgent:
    name = "Quality Reviewer Agent"

    def review(self, triples: Iterable[TripleRecord], profile: DocumentProfile | None = None) -> tuple[QualityReport, AgentRunTrace]:
        items = list(triples)
        keys = [item.key() for item in items]
        duplicates = sum(count - 1 for count in Counter(keys).values() if count > 1)
        empty = sum(1 for item in items if not item.head.strip() or not item.relation.strip() or not item.tail.strip())
        low_conf = sum(1 for item in items if item.confidence < 0.5)
        issues: List[str] = []
        suggestions: List[str] = []
        field_mismatch = 0

        if empty:
            issues.append(f"存在 {empty} 条 head/relation/tail 空值记录。")
            suggestions.append("建议回到源表定位空字段，或在技能中增加空值过滤。")
        if duplicates:
            issues.append(f"存在 {duplicates} 条重复三元组。")
            suggestions.append("建议融合前按 head/relation/tail 去重。")
        if low_conf:
            issues.append(f"存在 {low_conf} 条低置信度三元组。")
            suggestions.append("建议人工复核低置信度记录。")
        if profile:
            for risk in profile.risk_points:
                if "数量可能不一致" in risk:
                    field_mismatch += 1
                issues.append(risk)
            if profile.template_kind == "unknown":
                suggestions.append("建议审核 pending Skill 草稿，确认字段映射后再启用。")
            if profile.file_type == "pdf" and not items:
                suggestions.append("当前图片没有缓存三元组，可在原 PDF 工作台运行在线抽取。")

        score = 1.0
        if items:
            score -= min(0.35, empty / max(len(items), 1))
            score -= min(0.25, duplicates / max(len(items), 1))
            score -= min(0.2, low_conf / max(len(items), 1))
            score -= min(0.2, field_mismatch * 0.05)
        elif profile and profile.template_kind != "unknown":
            score = 0.4
        else:
            score = 0.2
        score = max(0.0, round(score, 3))

        report = QualityReport(
            total_triples=len(items),
            empty_field_count=empty,
            duplicate_count=duplicates,
            low_confidence_count=low_conf,
            field_mismatch_count=field_mismatch,
            issues=issues,
            suggestions=suggestions,
            score=score,
        )
        trace = AgentRunTrace(
            agent=self.name,
            status="success" if score >= 0.7 else "warning",
            input_summary=f"{len(items)} triples",
            output_summary=f"score={score}, issues={len(issues)}",
            details=report.to_dict(),
        )
        return report, trace
