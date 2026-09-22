import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseSkill
from .sts_text import compact_text, normalize_mojibake, write_jsonl


class STSSplitSectionsSkill(BaseSkill):
    name = "sts.split_sections"
    description = "Split extracted STS markdown into traceable numbered sections."
    input_schema = {"required": ["pages"], "optional": ["document_id", "mineru_artifacts"]}
    output_schema = {"format": "sections"}

    SECTION_RE = re.compile(r"^\s*#{1,6}\s*((?:\d+\.)*\d+)\s+(.{1,180})\s*$")
    LOW_VALUE_RE = re.compile(r"变更历史|需求来源|配置限制|功能框图|性能要求|诊断要求|文档说明|目录", re.I)
    HIGH_VALUE_RE = re.compile(r"功能逻辑|常显|TT|Warning|Chime|异常处理|控制|设置|开关|状态|提醒|信号|接口|服务", re.I)

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pages = input_data.get("pages") or []
        document_id = input_data.get("document_id") or ""
        artifacts = input_data.get("mineru_artifacts") or {}
        sections = self._split(pages)
        self._save_artifacts(artifacts, sections)
        return {"document_id": document_id, "sections": sections, "skill": self.name}

    def _split(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = "\n".join(normalize_mojibake(page.get("text") or "") for page in pages)
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        def close_current() -> None:
            nonlocal current
            if not current:
                return
            current["content"] = self._clean_content(current.get("content", ""))
            if current["content"] or current["title"]:
                current["is_candidate"] = self._is_candidate(current)
                current["content_preview"] = compact_text(current["content"])[:260]
                sections.append(current)
            current = None

        for raw_line in text.splitlines():
            line = normalize_mojibake(raw_line).strip()
            if not line:
                if current:
                    current["content"] += "\n"
                continue
            match = self.SECTION_RE.match(line)
            if match:
                close_current()
                section_id = match.group(1).strip(".")
                title = compact_text(match.group(2).strip())
                current = {
                    "section_id": section_id,
                    "title": title,
                    "level": section_id.count(".") + 1,
                    "parent": ".".join(section_id.split(".")[:-1]) or None,
                    "page_start": self._infer_page(section_id, pages),
                    "page_end": self._infer_page(section_id, pages),
                    "content": "",
                }
                continue
            if current is None:
                current = {
                    "section_id": "intro",
                    "title": "Document introduction",
                    "level": 1,
                    "parent": None,
                    "page_start": 1,
                    "page_end": 1,
                    "content": "",
                }
            current["content"] += line + "\n"

        close_current()
        if not sections and text.strip():
            sections.append({
                "section_id": "full",
                "title": "Full document",
                "level": 1,
                "parent": None,
                "page_start": 1,
                "page_end": len(pages) or 1,
                "content": compact_text(text),
                "content_preview": compact_text(text)[:260],
                "is_candidate": True,
            })
        return self._merge_tiny_sections(sections)

    def _merge_tiny_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for section in sections:
            if merged and len(section.get("content", "")) < 40 and section.get("level", 1) > merged[-1].get("level", 1):
                merged[-1]["content"] += f"\n\n## {section['section_id']} {section['title']}\n{section.get('content', '')}"
                merged[-1]["content_preview"] = compact_text(merged[-1]["content"])[:260]
                merged[-1]["is_candidate"] = self._is_candidate(merged[-1])
            else:
                merged.append(section)
        return merged

    def _clean_content(self, value: str) -> str:
        text = normalize_mojibake(value or "")
        text = text.replace("\u3000", " ")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _is_candidate(self, section: Dict[str, Any]) -> bool:
        title = f"{section.get('section_id', '')} {section.get('title', '')}"
        content = section.get("content", "")
        if self.HIGH_VALUE_RE.search(title) or self.HIGH_VALUE_RE.search(content[:1200]):
            return True
        if self.LOW_VALUE_RE.search(title) and len(content) < 1800:
            return False
        return len(content) >= 240

    def _infer_page(self, section_id: str, pages: List[Dict[str, Any]]) -> Optional[int]:
        needle = section_id.split(".")[0]
        for page in pages:
            text = normalize_mojibake(page.get("text") or "")
            if re.search(rf"(^|\n)\s*#+\s*{re.escape(needle)}(?:\.|\s)", text):
                return page.get("page") or 1
        return None

    def _save_artifacts(self, artifacts: Dict[str, Any], sections: List[Dict[str, Any]]) -> None:
        artifact_dir = artifacts.get("artifact_dir")
        if not artifact_dir:
            return
        root = Path(artifact_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "sections.json").write_text(json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8")
        write_jsonl(root / "section_chunks.jsonl", sections)
