import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_client import generate_testcase

from .base import BaseSkill


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CUSTOM_SKILLS_DIR = PROJECT_ROOT / "skills" / "custom"


class PromptTemplateSkill(BaseSkill):
    """Engineer-authored prompt skill loaded from skill.json/yaml + prompt.md."""

    def __init__(self, meta: Dict[str, Any], prompt_template: str, source_dir: Path):
        self.name = meta["name"]
        self.description = meta.get("description", "")
        self.input_schema = meta.get("input", {})
        self.output_schema = meta.get("output", {})
        self.model = meta.get("model", "Qwen3-4B")
        self.enabled = bool(meta.get("enabled", True))
        self.prompt_template = prompt_template
        self.source_dir = str(source_dir)
        self.source = meta.get("source", "local")
        self.origin_url = meta.get("origin_url", "")

    def _render_prompt(self, input_data: Dict[str, Any]) -> str:
        prompt = self.prompt_template
        for key, value in input_data.items():
            prompt = prompt.replace("{{ " + key + " }}", str(value))
            prompt = prompt.replace("{{" + key + "}}", str(value))
        return prompt

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prompt = self._render_prompt(input_data)
        content, elapsed_time = generate_testcase(prompt, model=input_data.get("model", self.model))
        return {"content": content, "elapsed_time": elapsed_time, "skill": self.name}

    def metadata(self) -> Dict[str, Any]:
        data = super().metadata()
        data.update({
            "model": self.model,
            "source_dir": self.source_dir,
            "source": self.source,
            "origin_url": self.origin_url,
        })
        return data


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        if not skill.name:
            raise ValueError("Skill name is required")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list(self) -> List[Dict[str, Any]]:
        return sorted((skill.metadata() for skill in self._skills.values()), key=lambda x: x["name"])

    def run(self, name: str, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        skill = self.get(name)
        if not skill:
            raise KeyError(f"Skill not found: {name}")
        if not skill.enabled:
            raise ValueError(f"Skill is disabled: {name}")
        return skill.run(input_data or {}, context=context)

    def load_builtin(self) -> None:
        from .builtin.sts_cluster import STSClusterTopicsSkill
        from .builtin.sts_generate import STSGenerateCasesFromSectionsSkill
        from .builtin.sts_ocr import STSExtractTextFromPDFSkill
        from .builtin.sts_split import STSSplitSectionsSkill
        from .builtin.sts_structure import STSBuildRequirementKnowledgeSkill
        from .builtin.testcase_evaluate import TestcaseEvaluateSkill
        from .builtin.testcase_generate import TestcaseGenerateFromRequirementSkill
        from .builtin.testcase_refine import TestcaseRefineSkill

        for skill in [
            TestcaseGenerateFromRequirementSkill(),
            TestcaseEvaluateSkill(),
            TestcaseRefineSkill(),
            STSExtractTextFromPDFSkill(),
            STSSplitSectionsSkill(),
            STSBuildRequirementKnowledgeSkill(),
            STSClusterTopicsSkill(),
            STSGenerateCasesFromSectionsSkill(),
        ]:
            self.register(skill)

    def load_custom(self, custom_dir: Path = CUSTOM_SKILLS_DIR) -> None:
        custom_dir.mkdir(parents=True, exist_ok=True)
        for skill_dir in [p for p in custom_dir.iterdir() if p.is_dir()]:
            try:
                skill = self._load_prompt_skill(skill_dir)
                if skill:
                    self.register(skill)
            except Exception as exc:
                print(f"Failed to load custom skill {skill_dir}: {type(exc).__name__}: {exc}")

    def reload(self) -> None:
        self._skills = {}
        self.load_builtin()
        self.load_custom()

    def create_prompt_skill(
        self,
        name: str,
        description: str,
        prompt: str,
        model: str = "Qwen3-4B",
        source: str = "local",
        origin_url: str = "",
    ) -> Dict[str, Any]:
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name.strip())
        if not safe_name:
            raise ValueError("Skill name is required")
        if not prompt.strip():
            raise ValueError("Prompt is required")
        skill_dir = CUSTOM_SKILLS_DIR / safe_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "name": safe_name,
            "version": "1.0.0",
            "description": description,
            "type": "prompt",
            "model": model,
            "enabled": True,
            "source": source,
            "origin_url": origin_url,
            "input": {"required": []},
            "output": {"format": "text"},
        }
        (skill_dir / "skill.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (skill_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        self.reload()
        skill = self.get(safe_name)
        if not skill:
            raise RuntimeError(f"Failed to load created skill: {safe_name}")
        return skill.metadata()

    def search_online(self, query: str = "") -> List[Dict[str, Any]]:
        """Search external skill indexes or a direct remote skill URL.

        Configure SKILL_MARKETPLACE_INDEX_URL or SKILL_MARKETPLACE_INDEX_URLS
        with comma-separated JSON URLs. The search input can also be a direct
        JSON, Markdown, or SKILL.md URL.
        """
        query = (query or "").strip()
        skills: List[Dict[str, Any]] = []

        if self._is_url(query):
            skills.extend(self._skills_from_remote_url(query))

        for index_url in self._marketplace_index_urls():
            try:
                skills.extend(self._skills_from_remote_url(index_url))
            except Exception as exc:
                print(f"Failed to load online skill index {index_url}: {type(exc).__name__}: {exc}")

        if not skills:
            skills = self._template_marketplace_skills()

        q = "" if self._is_url(query) else query.lower()
        normalized = [self._normalize_online_skill(item) for item in skills]
        if not q:
            return normalized
        return [
            item for item in normalized
            if q in item.get("name", "").lower() or q in item.get("description", "").lower()
        ]

    def import_online_skill(self, item: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._normalize_online_skill(item)
        prompt = skill.get("prompt", "").strip()
        prompt_url = skill.get("prompt_url") or skill.get("raw_url")
        skill_url = skill.get("skill_url")
        if not prompt and prompt_url:
            prompt = self._fetch_text(prompt_url)
        if not prompt and skill_url:
            prompt = self._prompt_from_remote_url(skill_url)
        if not prompt:
            raise ValueError("Online skill does not include a reusable prompt")
        return self.create_prompt_skill(
            name=skill.get("name", ""),
            description=skill.get("description", ""),
            prompt=prompt,
            model=skill.get("model", "Qwen3-4B"),
            source=skill.get("source", "online"),
            origin_url=skill.get("url") or skill.get("prompt_url") or skill.get("skill_url") or "",
        )

    def _marketplace_index_urls(self) -> List[str]:
        raw = os.getenv("SKILL_MARKETPLACE_INDEX_URLS") or os.getenv("SKILL_MARKETPLACE_INDEX_URL", "")
        return [url.strip() for url in raw.split(",") if url.strip()]

    def _template_marketplace_skills(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "market.sts_requirement_to_cases",
                "description": "Convert an STS requirement excerpt into structured test cases.",
                "type": "prompt",
                "source": "Built-in reusable template",
                "prompt": "You are an automotive test engineer.\nGenerate structured test cases from the following STS requirement excerpt:\n{{ requirement }}\n\nOutput fields: test item, preconditions, execution steps, expected results, pass/fail criteria.\nReturn only test cases, no explanation.",
            },
            {
                "name": "market.testcase_boundary_cases",
                "description": "Generate boundary, invalid-input, and recovery-scenario test cases from a requirement.",
                "type": "prompt",
                "source": "Built-in reusable template",
                "prompt": "You are an automotive functional testing expert.\nAdd boundary values, invalid inputs, state transitions, and recovery scenarios for:\n{{ requirement }}\n\nEach case must include: test objective, preconditions, steps, expected results, risk notes.",
            },
            {
                "name": "market.testcase_quality_review",
                "description": "Assess whether test cases are executable, observable, and judgeable; suggest fixes.",
                "type": "prompt",
                "source": "Built-in reusable template",
                "prompt": "You are an automotive test review expert.\nEvaluate completeness, executability, observability, and pass/fail criteria for:\n{{ testcase }}\n\nOutput: overall rating, main issues, revision suggestions, recommended score.",
            },
        ]

    def _skills_from_remote_url(self, url: str) -> List[Dict[str, Any]]:
        content = self._fetch_text(url)
        if self._looks_like_json(url, content):
            data = json.loads(content)
            if isinstance(data, dict) and isinstance(data.get("skills"), list):
                return data["skills"]
            if isinstance(data, dict):
                return [data]
            if isinstance(data, list):
                return data
            return []
        skill = self._skill_from_markdown_content(url, content)
        skill.update({
            "type": "prompt",
            "source": urllib.parse.urlparse(url).netloc or "remote-url",
            "url": url,
        })
        return [skill]

    def _prompt_from_remote_url(self, url: str) -> str:
        skills = self._skills_from_remote_url(url)
        if not skills:
            return ""
        return self._normalize_online_skill(skills[0]).get("prompt", "")

    def _skill_from_markdown_content(self, url: str, content: str) -> Dict[str, Any]:
        meta: Dict[str, str] = {}
        body = content
        match = re.match(r"\s*---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)", content)
        if match:
            for raw_line in match.group(1).splitlines():
                if ":" not in raw_line:
                    continue
                key, value = raw_line.split(":", 1)
                meta[key.strip()] = value.strip().strip("'\"")
            body = match.group(2).strip()
        return {
            "name": meta.get("name") or self._name_from_url(url),
            "description": meta.get("description") or "Prompt skill discovered from a remote Markdown/SKILL.md URL.",
            "prompt": body.strip(),
            "model": meta.get("model", "Qwen3-4B"),
        }

    def _normalize_online_skill(self, item: Dict[str, Any]) -> Dict[str, Any]:
        name = str(item.get("name") or item.get("id") or self._name_from_url(item.get("url", ""))).strip()
        prompt = str(item.get("prompt") or item.get("template") or item.get("instructions") or "")
        prompt_url = str(item.get("prompt_url") or item.get("raw_url") or "")
        skill_url = str(item.get("skill_url") or item.get("definition_url") or "")
        url = str(item.get("url") or item.get("html_url") or "")
        return {
            "name": name,
            "description": str(item.get("description") or ""),
            "type": str(item.get("type") or "prompt"),
            "source": str(item.get("source") or (urllib.parse.urlparse(url).netloc if url else "online")),
            "model": str(item.get("model") or "Qwen3-4B"),
            "url": url,
            "prompt_url": prompt_url,
            "skill_url": skill_url,
            "prompt": prompt,
            "importable": bool(prompt or prompt_url or skill_url),
        }

    def _fetch_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "TestCase-Agent-Skills/1.0"})
        with urllib.request.urlopen(request, timeout=10) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")

    def _is_url(self, value: str) -> bool:
        return value.lower().startswith(("http://", "https://"))

    def _looks_like_json(self, url: str, content: str) -> bool:
        return url.lower().split("?", 1)[0].endswith(".json") or content.lstrip().startswith(("{", "["))

    def _name_from_url(self, url: str) -> str:
        if not url:
            return "market.remote_prompt_skill"
        parsed = urllib.parse.urlparse(url)
        path_name = Path(parsed.path).stem or parsed.netloc or "remote_prompt_skill"
        safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", path_name).strip("_")
        return f"market.{safe or 'remote_prompt_skill'}"

    def _load_prompt_skill(self, skill_dir: Path) -> Optional[PromptTemplateSkill]:
        meta_file = skill_dir / "skill.json"
        yaml_file = skill_dir / "skill.yaml"
        prompt_file = skill_dir / "prompt.md"
        if not prompt_file.exists():
            return None
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        elif yaml_file.exists():
            meta = self._read_simple_yaml(yaml_file)
        else:
            return None
        if meta.get("type", "prompt") != "prompt":
            raise ValueError("Only prompt custom skills are supported by the safe loader")
        return PromptTemplateSkill(meta, prompt_file.read_text(encoding="utf-8"), skill_dir)

    def _read_simple_yaml(self, path: Path) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip().strip("'\"")
            if value.lower() in ("true", "false"):
                data[key.strip()] = value.lower() == "true"
            else:
                data[key.strip()] = value
        return data


skill_registry = SkillRegistry()
skill_registry.reload()
