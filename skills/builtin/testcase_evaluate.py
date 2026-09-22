import json
import re
from typing import Any, Dict, Optional

from llm_client import generate_testcase

from ..base import BaseSkill


class TestcaseEvaluateSkill(BaseSkill):
    name = "testcase.evaluate"
    description = "Evaluate test-case quality and return score plus issue list."
    input_schema = {"required": ["testcase"], "optional": ["model"]}
    output_schema = {"format": "score_issues"}

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = (input_data.get("testcase") or "").strip()
        if not text:
            raise ValueError("testcase is required")
        model = input_data.get("model") or "Qwen3-1.7B-Critic"

        try:
            prompt = f"""You are an automotive test-case reviewer. Evaluate the generated test case.
Return only one JSON object with these fields:
- is_reasonable: boolean
- score: integer from 0 to 100
- confidence: number from 0 to 1
- issues: string array
- suggestions: string array

Generated test case:
{text}
"""
            critic_resp, _ = generate_testcase(prompt, model=model)
            candidate = (critic_resp or "").strip()
            match = re.search(r"\{[\s\S]*\}", candidate)
            if match:
                candidate = match.group(0)
            result = json.loads(candidate)
            is_reasonable = bool(result.get("is_reasonable"))
            score = max(0, min(100, int(result.get("score", 0))))
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
            issues = [str(x) for x in (result.get("issues") or []) if str(x).strip()]
            suggestions = [str(x) for x in (result.get("suggestions") or []) if str(x).strip()]
            merged = issues
            if confidence > 0:
                merged.append(f"Overall judgment: {'reasonable' if is_reasonable else 'not reasonable'}; confidence {confidence:.2f}")
            merged.extend(f"Suggestion: {s}" for s in suggestions)
            return {"score": score, "issues": merged, "raw": result, "skill": self.name}
        except Exception:
            score, issues = self._heuristic_evaluate(text)
            return {"score": score, "issues": issues, "raw": None, "skill": self.name}

    def _heuristic_evaluate(self, text: str):
        fields = ["test item", "preconditions", "execution steps", "expected behavior"]
        aliases = {
            "test item": ["测试项", "测试项目", "Test item", "test item"],
            "preconditions": ["前提条件", "前置条件", "Preconditions", "preconditions"],
            "execution steps": ["执行动作", "操作步骤", "Execution steps", "execution steps"],
            "expected behavior": ["预期行为", "预期结果", "Expected behavior", "expected behavior"],
        }
        issues = []
        score = 100
        for field in fields:
            if not any(alias in text for alias in aliases[field]):
                issues.append(f"Missing field: {field}")
                score -= 20
        if len(text) < 120:
            issues.append("Content is short; add executable steps and verifiable expected behavior.")
            score -= 10
        return max(0, min(100, score)), issues
