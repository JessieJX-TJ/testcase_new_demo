from __future__ import annotations

from agentic_kg.models import AgentRunTrace, DocumentProfile, SkillMatch
from agentic_kg.paths import SKILL_REGISTRY_PATH, load_json


class SkillRouterAgent:
    name = "Skill Router Agent"

    def __init__(self) -> None:
        self.registry = load_json(SKILL_REGISTRY_PATH, default=[]) or []

    def route(self, profile: DocumentProfile) -> tuple[SkillMatch, AgentRunTrace]:
        enabled = [item for item in self.registry if item.get("status", "enabled") == "enabled"]
        for skill in enabled:
            if skill.get("file_type") == profile.file_type and skill.get("template_kind") == profile.template_kind:
                match = SkillMatch(
                    skill_id=str(skill["skill_id"]),
                    name=str(skill.get("name", skill["skill_id"])),
                    confidence=0.98,
                    status=str(skill.get("status", "enabled")),
                    reason=f"模板类型 {profile.template_kind} 与技能注册表匹配。",
                    tool=str(skill.get("tool", "")),
                )
                return match, AgentRunTrace(
                    agent=self.name,
                    status="success",
                    input_summary=profile.summary(),
                    output_summary=f"命中 {match.skill_id}",
                    details=match.to_dict(),
                )

        draft_id = profile.candidate_skill_ids[0] if profile.candidate_skill_ids else f"{profile.file_type}.unknown_template.draft"
        match = SkillMatch(
            skill_id=draft_id,
            name="待审核新模板技能",
            confidence=0.35,
            status="pending_review",
            reason="未命中正式技能，将进入技能草稿流程。",
            tool="skill_curator.create_draft",
        )
        return match, AgentRunTrace(
            agent=self.name,
            status="warning",
            input_summary=profile.summary(),
            output_summary=f"未命中正式技能，建议草稿 {draft_id}",
            details=match.to_dict(),
        )
