from typing import Any, Dict, Optional

from utils import rag_pipeline

from ..base import BaseSkill


class TestcaseGenerateFromRequirementSkill(BaseSkill):
    name = "testcase.generate_from_requirement"
    description = "Generate test cases from a natural-language requirement using the existing RAG pipeline."
    input_schema = {
        "required": ["user_input"],
        "optional": ["testcase_count", "model", "progress_callback"],
    }
    output_schema = {"format": "rag_generation_result"}

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        user_input = (input_data.get("user_input") or "").strip()
        if not user_input:
            raise ValueError("user_input is required")
        testcase_count = int(input_data.get("testcase_count") or 1)
        model = input_data.get("model") or "Qwen3-4B"
        progress_callback = input_data.get("progress_callback")

        testcase, context_text, triples, similar_cases, elapsed_time, complete_testcases, pdf_kg_evidence = rag_pipeline(
            user_input,
            testcase_count,
            model=model,
            progress_callback=progress_callback,
        )
        return {
            "testcase": testcase,
            "context": context_text,
            "triples": triples,
            "similar_cases": similar_cases,
            "elapsed_time": elapsed_time,
            "complete_testcases": complete_testcases,
            "pdf_kg_evidence": pdf_kg_evidence,
            "skill": self.name,
        }
