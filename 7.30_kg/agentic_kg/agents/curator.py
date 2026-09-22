from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agentic_kg.models import AgentRunTrace, DocumentProfile
from agentic_kg.paths import PENDING_SKILLS_ROOT, sanitize_filename
from agentic_kg.tools.llm_client import suggest_skill_draft


class SkillCuratorAgent:
    name = "Skill Curator Agent"

    def create_pending_draft(self, profile: DocumentProfile, reason: str = "") -> tuple[str, AgentRunTrace]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = sanitize_filename(f"{profile.file_type}_{profile.source_name}_{timestamp}.SKILL.md")
        draft_path = PENDING_SKILLS_ROOT / base_name
        lines = [
            f"# 待审核技能草稿：{profile.source_name}",
            "",
            f"- 创建时间：{timestamp}",
            f"- 文件类型：{profile.file_type}",
            f"- 模板识别：{profile.template_kind}",
            f"- 业务域：{profile.domain or '未知'}",
            f"- 来源文件：{profile.source_path}",
            f"- 触发原因：{reason or '未命中正式技能'}",
            "",
            "## Sheet / Header 摘要",
            "",
            f"- Sheets：{', '.join(profile.sheets) if profile.sheets else '无'}",
            f"- Selected sheet：{profile.selected_sheet or '无'}",
            f"- Headers：{', '.join(profile.headers[:30]) if profile.headers else '无'}",
            "",
            "## 样例行",
            "",
        ]
        for row in profile.sample_rows[:5]:
            lines.append("- " + " | ".join(row[:12]))
        llm_note = ""
        try:
            llm_note = suggest_skill_draft(profile)
        except Exception as exc:
            llm_note = f"LLM 辅助建议未生成：{exc}"

        lines.extend(
            [
                "",
                "## 待人工确认",
                "",
                "- 字段映射是否正确",
                "- 哪些列应作为 head/relation/tail",
                "- 是否可以沉淀为正式技能",
                "",
                "## LLM 辅助建议",
                "",
                llm_note or "无",
            ]
        )
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        trace = AgentRunTrace(
            agent=self.name,
            status="success",
            input_summary=profile.summary(),
            output_summary=f"已生成待审核技能草稿: {draft_path}",
            details={"draft_path": str(draft_path)},
        )
        return str(draft_path), trace
