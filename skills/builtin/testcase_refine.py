from typing import Any, Dict, Optional

from llm_client import generate_testcase

from ..base import BaseSkill


class TestcaseRefineSkill(BaseSkill):
    name = "testcase.refine"
    description = "Refine a generated test case based on reviewer issues and an optional instruction."
    input_schema = {"required": ["current_testcase"], "optional": ["instruction", "eval_issues", "model"]}
    output_schema = {"format": "refined_testcase"}

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current_testcase = (input_data.get("current_testcase") or "").strip()
        if not current_testcase:
            raise ValueError("current_testcase is required")
        instruction = (input_data.get("instruction") or "Improve the test case according to the review feedback.").strip()
        eval_issues = input_data.get("eval_issues") or []
        issues_text = "\n".join(f"- {item}" for item in eval_issues)
        model = input_data.get("model") or "Qwen3-4B"

        prompt = f"""You are an automotive test expert. Refine the following test case.
Keep the same test objective and preserve the structure: test item, preconditions, execution steps, expected behavior.
Return only the improved test case.

Current test case:
{current_testcase}

Review feedback:
{issues_text}

Instruction:
{instruction}
"""
        testcase, elapsed_time = generate_testcase(prompt, model=model)
        return {"testcase": testcase, "elapsed_time": elapsed_time, "skill": self.name}
