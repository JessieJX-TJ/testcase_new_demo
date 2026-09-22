import json
import os
import re
from typing import Any, Dict, List, Optional

from llm_client import generate_testcase
from utils import retrieve_rag_evidence

from ..base import BaseSkill
from .sts_text import compact_text, normalize_mojibake


class STSGenerateCasesFromSectionsSkill(BaseSkill):
    name = "sts.generate_cases_from_sections"
    description = "Generate traceable test cases from STS requirement units or topic clusters."
    input_schema = {
        "required": [],
        "optional": ["document_id", "sections", "requirement_units", "topic_clusters", "signals", "model", "max_units", "max_sections"],
    }
    output_schema = {"format": "pending_testcases"}

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        document_id = input_data.get("document_id") or ""
        model = input_data.get("model") or os.getenv("STS_GENERATION_MODEL", "qwen-plus")
        signals = input_data.get("signals") or []
        max_units = self._to_int(input_data.get("max_units") or os.getenv("STS_MAX_UNITS_PER_GENERATION")) or 30
        clusters = input_data.get("topic_clusters") or []
        units = input_data.get("requirement_units") or []
        sections = input_data.get("sections") or []
        use_rag = input_data.get("use_rag", True)
        testcase_count = self._to_int(input_data.get("testcase_count")) or self._to_int(os.getenv("STS_CASES_PER_REQUIREMENT")) or 2

        if clusters:
            cases = self._generate_from_clusters(document_id, clusters, signals, model, max_units, use_rag, testcase_count)
        elif units:
            cases = self._generate_unit_batches(document_id, units[:max_units], signals, model, None, use_rag, testcase_count)
        else:
            max_sections = self._to_int(input_data.get("max_sections")) or 8
            cases = self._generate_from_sections(document_id, sections[:max_sections], model, use_rag, testcase_count)
        return {"document_id": document_id, "generated_cases": cases, "skill": self.name}

    def _generate_from_clusters(self, document_id: str, clusters: List[Dict[str, Any]], signals: List[Dict[str, Any]], model: str, max_units: int, use_rag: bool, testcase_count: int) -> List[Dict[str, Any]]:
        generated: List[Dict[str, Any]] = []
        budget = max_units
        for cluster in clusters:
            units = cluster.get("requirement_units") or []
            high_units = [self._clean_unit(unit) for unit in units if unit.get("source_quality") in {"high", "medium"} and self._is_usable_unit(unit)]
            if high_units:
                per_cluster = max(1, min(6, budget))
                selected = high_units[:per_cluster]
                generated.extend(self._generate_unit_batches(document_id, selected, signals, model, cluster, use_rag, testcase_count))
                budget -= len(selected)
                if budget <= 0:
                    break
            else:
                generated.append(self._generate_cluster_fallback(document_id, cluster, model, use_rag, testcase_count))
        return generated

    def _generate_unit_batches(self, document_id: str, units: List[Dict[str, Any]], signals: List[Dict[str, Any]], model: str, cluster: Optional[Dict[str, Any]], use_rag: bool, testcase_count: int) -> List[Dict[str, Any]]:
        generated = []
        for unit in units:
            unit = self._clean_unit(unit)
            prompt = self._build_unit_prompt(unit, signals, cluster)
            llm_error = ""
            rag_error = ""
            rag_context = ""
            rag_triples: List[Dict[str, Any]] = []
            similar_cases: List[Dict[str, Any]] = []
            complete_testcases: List[Dict[str, Any]] = []
            try:
                if use_rag:
                    rag_context, rag_triples, similar_cases, complete_testcases = retrieve_rag_evidence(self._unit_query_text(unit, cluster))
                    testcase, elapsed_time = generate_testcase(
                        self._build_unit_rag_prompt(unit, cluster, rag_context, similar_cases, complete_testcases, testcase_count),
                        model=model,
                        max_tokens=4096,
                    )
                else:
                    testcase, elapsed_time = generate_testcase(prompt, model=model, max_tokens=4096)
            except Exception as exc:
                rag_error = str(exc) if use_rag else ""
                try:
                    testcase, elapsed_time = generate_testcase(prompt, model=model, max_tokens=4096)
                except Exception as fallback_exc:
                    testcase = self._fallback_unit_case(unit, cluster)
                    elapsed_time = 0
                    llm_error = str(fallback_exc)
            generated.append({
                "document_id": document_id,
                "cluster_id": (cluster or {}).get("cluster_id"),
                "topic": (cluster or {}).get("topic"),
                "unit_id": unit.get("unit_id"),
                "section_id": unit.get("section_id"),
                "section_title": unit.get("section_title"),
                "function": unit.get("function"),
                "page_start": unit.get("page_start"),
                "page_end": unit.get("page_end"),
                "test_intents": unit.get("test_intents") or [],
                "related_signals": unit.get("related_signals") or [],
                "requirement_text": self._unit_text(unit)[:3200],
                "testcase": self._clean_generated_testcase(testcase),
                "status": "pending_review",
                "elapsed_time": elapsed_time,
                "skill": self.name,
                "model": model,
                "generation_granularity": "requirement_unit",
                "source_quality": unit.get("source_quality", "medium"),
                "llm_error": llm_error,
                "rag_error": rag_error,
                "rag_query": self._unit_query_text(unit, cluster),
                "rag_context": rag_context,
                "rag_triples": rag_triples,
                "similar_cases": similar_cases,
                "retrieved_testcases": complete_testcases,
            })
        return generated

    def _generate_cluster_fallback(self, document_id: str, cluster: Dict[str, Any], model: str, use_rag: bool, testcase_count: int) -> Dict[str, Any]:
        prompt = self._build_cluster_prompt(cluster)
        llm_error = ""
        rag_error = ""
        rag_context = ""
        rag_triples: List[Dict[str, Any]] = []
        similar_cases: List[Dict[str, Any]] = []
        complete_testcases: List[Dict[str, Any]] = []
        try:
            if use_rag:
                rag_context, rag_triples, similar_cases, complete_testcases = retrieve_rag_evidence(self._cluster_query_text(cluster))
                testcase, elapsed_time = generate_testcase(
                    self._build_cluster_rag_prompt(cluster, rag_context, similar_cases, complete_testcases, testcase_count),
                    model=model,
                    max_tokens=4096,
                )
            else:
                testcase, elapsed_time = generate_testcase(prompt, model=model, max_tokens=4096)
        except Exception as exc:
            rag_error = str(exc) if use_rag else ""
            try:
                testcase, elapsed_time = generate_testcase(prompt, model=model, max_tokens=4096)
            except Exception as fallback_exc:
                testcase = self._fallback_cluster_case(cluster)
                elapsed_time = 0
                llm_error = str(fallback_exc)
        return {
            "document_id": document_id,
            "cluster_id": cluster.get("cluster_id"),
            "topic": cluster.get("topic"),
            "section_ids": [section.get("section_id") for section in cluster.get("sections") or []],
            "section_title": cluster.get("topic"),
            "page_start": cluster.get("page_start"),
            "page_end": cluster.get("page_end"),
            "requirement_text": self._cluster_text(cluster)[:3200],
            "testcase": self._clean_generated_testcase(testcase),
            "status": "pending_review",
            "elapsed_time": elapsed_time,
            "skill": self.name,
            "model": model,
            "generation_granularity": "topic_fallback",
            "source_quality": cluster.get("source_quality", "low"),
            "llm_error": llm_error,
            "rag_error": rag_error,
            "rag_query": self._cluster_query_text(cluster),
            "rag_context": rag_context,
            "rag_triples": rag_triples,
            "similar_cases": similar_cases,
            "retrieved_testcases": complete_testcases,
        }

    def _generate_from_sections(self, document_id: str, sections: List[Dict[str, Any]], model: str, use_rag: bool, testcase_count: int) -> List[Dict[str, Any]]:
        generated = []
        for section in sections:
            section = {key: normalize_mojibake(value) if isinstance(value, str) else value for key, value in section.items()}
            prompt = self._build_section_prompt(section)
            llm_error = ""
            rag_error = ""
            rag_context = ""
            rag_triples: List[Dict[str, Any]] = []
            similar_cases: List[Dict[str, Any]] = []
            complete_testcases: List[Dict[str, Any]] = []
            try:
                if use_rag:
                    rag_context, rag_triples, similar_cases, complete_testcases = retrieve_rag_evidence(self._section_query_text(section))
                    testcase, elapsed_time = generate_testcase(
                        self._build_section_rag_prompt(section, rag_context, similar_cases, complete_testcases, testcase_count),
                        model=model,
                        max_tokens=4096,
                    )
                else:
                    testcase, elapsed_time = generate_testcase(prompt, model=model, max_tokens=4096)
            except Exception as exc:
                rag_error = str(exc) if use_rag else ""
                try:
                    testcase, elapsed_time = generate_testcase(prompt, model=model, max_tokens=4096)
                except Exception as fallback_exc:
                    testcase = self._fallback_section_case(section)
                    elapsed_time = 0
                    llm_error = str(fallback_exc)
            generated.append({
                "document_id": document_id,
                "section_id": section.get("section_id"),
                "section_title": section.get("title"),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
                "requirement_text": compact_text(section.get("content", ""))[:2200],
                "testcase": self._clean_generated_testcase(testcase),
                "status": "pending_review",
                "elapsed_time": elapsed_time,
                "skill": self.name,
                "model": model,
                "generation_granularity": "section_fallback",
                "source_quality": "medium",
                "llm_error": llm_error,
                "rag_error": rag_error,
                "rag_query": self._section_query_text(section),
                "rag_context": rag_context,
                "rag_triples": rag_triples,
                "similar_cases": similar_cases,
                "retrieved_testcases": complete_testcases,
            })
        return generated

    def _build_unit_prompt(self, unit: Dict[str, Any], signals: List[Dict[str, Any]], cluster: Optional[Dict[str, Any]]) -> str:
        evidence = json.dumps(self._compact_unit(unit), ensure_ascii=False, indent=2)
        related_signals = self._related_signal_text(unit.get("related_signals") or [], signals)
        topic = (cluster or {}).get("topic") or "Unclustered topic"
        keywords = ", ".join((cluster or {}).get("keywords") or [])
        return f"""You are an automotive STS requirement test-design expert. Accuracy first: generate test cases only from the given evidence; do not invent features, signals, states, or timing not present in the input.

Requirements:
1. Each case must trace to requirement unit ID, section, topic, and coverage intent.
2. Prioritize: positive function, reject/failure paths, boundary/timeout, status feedback, HMI display, signal/service interfaces.
3. When a field is missing in the evidence, write "Not specified"; do not guess.
4. Each case must be executable, observable, and judgeable.
5. Write in English using the fixed structure below; output 2 to 4 cases; separate multiple cases with a line of three dashes.

Fixed structure:
Requirement unit ID:
Section:
Topic:
Coverage intent:
Test case name:
Preconditions:
Execution steps:
Expected behavior:
Related signals/interfaces:
Pass/fail criteria:

Topic: {topic}
Keywords: {keywords}

Requirement evidence:
{evidence}

Signal evidence:
{related_signals}
"""

    def _build_cluster_prompt(self, cluster: Dict[str, Any]) -> str:
        return f"""You are an automotive STS test engineer. You only have a topic cluster summary, not full structured requirement units. Generate test cases conservatively using only sections, functions, and signals present in the input.
Each case must include: test case name, related sections, preconditions, execution steps, expected behavior, pass/fail criteria. Use "Not specified" for missing fields.

Topic: {cluster.get('topic')}
Pages: {cluster.get('page_start')} - {cluster.get('page_end')}
Keywords: {', '.join(cluster.get('keywords') or [])}
Coverage intents: {', '.join(cluster.get('test_intents') or [])}
Section basis:
{self._cluster_text(cluster)}
"""

    def _build_section_prompt(self, section: Dict[str, Any]) -> str:
        return f"""You are an automotive STS test engineer. Generate test cases from the section text only; do not invent information absent from the text. Use "Not specified" for missing fields.
Section: {section.get('section_id')} {section.get('title')}
Pages: {section.get('page_start')} - {section.get('page_end')}
Content:
{compact_text(section.get('content', ''))[:5000]}
"""

    def _build_unit_rag_prompt(
        self,
        unit: Dict[str, Any],
        cluster: Optional[Dict[str, Any]],
        rag_context: str,
        similar_cases: List[Dict[str, Any]],
        retrieved_testcases: List[Dict[str, Any]],
        testcase_count: int,
    ) -> str:
        return self._build_sts_rag_prompt(
            source_title=f"{unit.get('section_id') or ''} {unit.get('section_title') or ''}".strip(),
            topic=(cluster or {}).get("topic") or "Unclustered topic",
            sts_evidence=json.dumps(self._compact_unit(unit), ensure_ascii=False, indent=2),
            rag_context=rag_context,
            similar_cases=similar_cases,
            retrieved_testcases=retrieved_testcases,
            testcase_count=testcase_count,
        )

    def _build_cluster_rag_prompt(
        self,
        cluster: Dict[str, Any],
        rag_context: str,
        similar_cases: List[Dict[str, Any]],
        retrieved_testcases: List[Dict[str, Any]],
        testcase_count: int,
    ) -> str:
        return self._build_sts_rag_prompt(
            source_title=cluster.get("cluster_id") or "STS topic",
            topic=cluster.get("topic") or "Untitled topic",
            sts_evidence=self._cluster_text(cluster),
            rag_context=rag_context,
            similar_cases=similar_cases,
            retrieved_testcases=retrieved_testcases,
            testcase_count=testcase_count,
        )

    def _build_section_rag_prompt(
        self,
        section: Dict[str, Any],
        rag_context: str,
        similar_cases: List[Dict[str, Any]],
        retrieved_testcases: List[Dict[str, Any]],
        testcase_count: int,
    ) -> str:
        return self._build_sts_rag_prompt(
            source_title=f"{section.get('section_id') or ''} {section.get('title') or ''}".strip(),
            topic="STS section requirement",
            sts_evidence=compact_text(section.get("content") or section.get("content_preview") or "")[:5000],
            rag_context=rag_context,
            similar_cases=similar_cases,
            retrieved_testcases=retrieved_testcases,
            testcase_count=testcase_count,
        )

    def _build_sts_rag_prompt(
        self,
        source_title: str,
        topic: str,
        sts_evidence: str,
        rag_context: str,
        similar_cases: List[Dict[str, Any]],
        retrieved_testcases: List[Dict[str, Any]],
        testcase_count: int,
    ) -> str:
        return f"""You are an automotive STS test-design expert. Using STS topic/requirement evidence and retrieved knowledge-graph test cases as references, generate {testcase_count} new test cases.

Strict constraints:
1. STS evidence is the requirement source. Knowledge-graph cases are only for structure, phrasing of preconditions/actions/expected results, and executability—do not copy unrelated features into new cases.
2. Each case must include: test item, preconditions, execution steps, expected behavior, related section/requirement unit, and reference basis.
3. Preconditions, execution steps, and expected behavior must not be empty. Use "Not specified" when information is missing; do not invent signals, states, or thresholds absent from STS evidence.
4. Granularity must align with knowledge-graph cases:
    - Preconditions should be an executable scenario state set (vehicle mode, door locks, power mode, tailgate state, grade, speed, gear, charging state, etc.)—keep only conditions relevant to the STS topic and non-conflicting.
    - Execution steps must be one business action or stimulus a tester, HIL, or simulator can perform (e.g., press the remote tailgate switch; inject PLGFailReminder=0x04 on the bench and request tailgate close)—not isolated signal toggles alone.
    - Expected behavior must cover STS-required prompts/chimes/HMI/status feedback and remain observable and judgeable.
5. When STS evidence only lists signal conditions, place them under preconditions or execution-step stimulus details and add environment/scenario detail at the same granularity as reference cases.
6. Produce {testcase_count} cases with distinct test focus; separate cases with ---.
7. Output only test-case body text—no analysis, chain-of-thought, explanations, Markdown headings, or chat.

Output format (every case):
Test item:
Related section/requirement unit:
Reference basis:
Preconditions:
1.
Execution steps:
Expected behavior:

=== STS topic ===
{topic}

=== STS source ===
{source_title}

=== STS requirement evidence ===
{sts_evidence}

=== Full test cases from knowledge graph (reference only) ===
{self._format_retrieved_testcases_for_prompt(retrieved_testcases) or rag_context or 'No full test cases retrieved.'}

=== Similar test cases from vector search (reference only) ===
{self._format_similar_cases_for_prompt(similar_cases)}
"""

    def _format_retrieved_testcases_for_prompt(self, testcases: List[Dict[str, Any]]) -> str:
        rows = []
        for index, testcase in enumerate(testcases[:5], 1):
            preconditions = "; ".join(testcase.get("preconditions") or []) or "Not specified"
            actions = "; ".join(testcase.get("actions") or []) or "Not specified"
            expected = "; ".join(testcase.get("expected_behaviors") or []) or "Not specified"
            rows.append(
                f"[KG case {index}] {testcase.get('case_name') or 'Untitled'}\n"
                f"Preconditions: {preconditions}\n"
                f"Execution steps: {actions}\n"
                f"Expected behavior: {expected}"
            )
        return "\n\n".join(rows)

    def _format_similar_cases_for_prompt(self, similar_cases: List[Dict[str, Any]]) -> str:
        if not similar_cases:
            return "No similar test cases retrieved."
        rows = []
        for index, case in enumerate(similar_cases[:3], 1):
            rows.append(
                f"[Similar case {index}] {case.get('caseName') or 'Untitled'}\n"
                f"Similarity: {case.get('similarity_score', 0):.3f}\n"
                f"Test logic: {case.get('logic') or 'Not specified'}\n"
                f"Original requirement: {case.get('user_input') or 'Not specified'}"
            )
        return "\n\n".join(rows)

    def _compact_unit(self, unit: Dict[str, Any]) -> Dict[str, Any]:
        keep = (
            "unit_id", "section_id", "section_title", "page_start", "page_end", "function",
            "preconditions", "triggers", "actions", "expected_results", "hmi_display",
            "status_feedback", "test_environment", "remarks", "related_signals", "test_intents", "source_quality",
        )
        return {key: unit.get(key) for key in keep if unit.get(key) not in (None, "", [])}

    def _related_signal_text(self, related: List[Any], signals: List[Dict[str, Any]]) -> str:
        if not related:
            return "No explicit related signals extracted."
        names = []
        for item in related:
            if isinstance(item, dict):
                names.append(str(item.get("name", "")))
            else:
                names.append(str(item))
        matched = []
        for signal in signals:
            payload = json.dumps(signal, ensure_ascii=False)
            if any(name and name in payload for name in names):
                matched.append(signal)
        return json.dumps(matched[:12] or related[:12], ensure_ascii=False, indent=2)

    def _unit_text(self, unit: Dict[str, Any]) -> str:
        labels = [
            ("unit_id", "Requirement unit"), ("section_title", "Section"), ("function", "Function"),
            ("preconditions", "Preconditions"), ("triggers", "Trigger conditions"), ("actions", "Execution steps"),
            ("expected_results", "Expected results"), ("hmi_display", "HMI display"),
            ("status_feedback", "Status feedback"), ("test_environment", "Test environment"), ("remarks", "Remarks"),
        ]
        return "\n".join(f"{label}: {unit.get(key)}" for key, label in labels if unit.get(key))

    def _clean_generated_testcase(self, text: str) -> str:
        cleaned = normalize_mojibake(text or "")
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.I).strip()
        markers = [
            r"(?:^|\n)\s*(?:测试项|Test item)\s*[：:]",
            r"(?:^|\n)\s*(?:测试用例名称|Test case name)\s*[：:]",
            r"(?:^|\n)\s*(?:需求单元ID|Requirement unit ID)\s*[：:]",
        ]
        starts = []
        for marker in markers:
            starts.extend(match.start() for match in re.finditer(marker, cleaned))
        if starts:
            cleaned = cleaned[max(starts):].strip()
        cleaned = re.sub(r"^#+\s*(?:测试用例|Test case)[^\n]*\n+", "", cleaned, flags=re.I).strip()
        return compact_text(cleaned)

    def _unit_query_text(self, unit: Dict[str, Any], cluster: Optional[Dict[str, Any]]) -> str:
        parts = [
            f"STS topic: {(cluster or {}).get('topic') or 'Unclustered topic'}",
            f"Section: {unit.get('section_id') or ''} {unit.get('section_title') or ''}",
            f"Function: {unit.get('function') or ''}",
            f"Preconditions: {unit.get('preconditions') or ''}",
            f"Trigger conditions: {unit.get('triggers') or ''}",
            f"Execution steps: {unit.get('actions') or ''}",
            f"Expected results: {unit.get('expected_results') or unit.get('hmi_display') or unit.get('status_feedback') or ''}",
            f"Related signals: {self._format_related_signal_names(unit.get('related_signals') or [])}",
            f"Coverage intents: {', '.join(unit.get('test_intents') or [])}",
        ]
        return compact_text("\n".join(part for part in parts if part.strip()))

    def _cluster_query_text(self, cluster: Dict[str, Any]) -> str:
        return compact_text("\n".join([
            f"STS topic: {cluster.get('topic') or ''}",
            f"Keywords: {', '.join(cluster.get('keywords') or [])}",
            f"Coverage intents: {', '.join(cluster.get('test_intents') or [])}",
            f"Topic summary: {cluster.get('summary') or ''}",
            f"Related sections: {self._cluster_text(cluster)}",
        ]))

    def _section_query_text(self, section: Dict[str, Any]) -> str:
        return compact_text("\n".join([
            f"STS section: {section.get('section_id') or ''} {section.get('title') or ''}",
            f"Pages: {section.get('page_start') or '-'} - {section.get('page_end') or '-'}",
            f"Section content: {section.get('content') or section.get('content_preview') or ''}",
        ]))[:5000]

    def _fallback_unit_case(self, unit: Dict[str, Any], cluster: Optional[Dict[str, Any]]) -> str:
        expected = unit.get("expected_results") or unit.get("hmi_display") or unit.get("status_feedback") or "Not specified"
        return "\n".join([
            f"Requirement unit ID: {unit.get('unit_id') or 'Not specified'}",
            f"Section: {unit.get('section_id') or 'Not specified'} {unit.get('section_title') or ''}".strip(),
            f"Topic: {(cluster or {}).get('topic') or 'Unclustered topic'}",
            f"Coverage intents: {', '.join(unit.get('test_intents') or []) or 'Not specified'}",
            f"Test case name: Verify {unit.get('function') or unit.get('section_title') or 'STS requirement'}",
            f"Preconditions: {unit.get('preconditions') or 'Not specified'}",
            f"Execution steps: {unit.get('triggers') or unit.get('actions') or 'Not specified'}",
            f"Expected behavior: {expected}",
            f"Related signals/interfaces: {self._format_related_signal_names(unit.get('related_signals') or [])}",
            "Pass/fail criteria: Actual results must match expected behavior; confirm against original STS where fields are not specified.",
        ])

    def _format_related_signal_names(self, related: List[Any]) -> str:
        names = []
        for item in related[:8]:
            if isinstance(item, dict):
                names.append(str(item.get("name") or item.get("signal_id") or "").strip())
            else:
                names.append(str(item).strip())
        names = [name for name in names if name]
        return ", ".join(dict.fromkeys(names)) or "Not specified"

    def _fallback_cluster_case(self, cluster: Dict[str, Any]) -> str:
        sections = cluster.get("sections") or []
        first_section = sections[0] if sections else {}
        return "\n".join([
            "Requirement unit ID: Not specified",
            f"Section: {first_section.get('section_id') or 'Not specified'} {first_section.get('title') or ''}".strip(),
            f"Topic: {cluster.get('topic') or 'Untitled topic'}",
            f"Coverage intents: {', '.join(cluster.get('test_intents') or []) or 'Not specified'}",
            f"Test case name: Verify {cluster.get('topic') or 'STS topic'}",
            "Preconditions: Not specified",
            f"Execution steps: Perform related operations per section content: {first_section.get('content_preview') or cluster.get('summary') or 'Not specified'}",
            "Expected behavior: Actual behavior must satisfy the related section description.",
            f"Related signals/interfaces: {', '.join(cluster.get('keywords') or []) or 'Not specified'}",
            "Pass/fail criteria: Actual results must match the STS section description; confirm against the original STS document where fields are missing.",
        ])

    def _fallback_section_case(self, section: Dict[str, Any]) -> str:
        return "\n".join([
            "Requirement unit ID: Not specified",
            f"Section: {section.get('section_id') or 'Not specified'} {section.get('title') or ''}".strip(),
            "Topic: STS section requirement",
            "Coverage intents: Not specified",
            f"Test case name: Verify {section.get('title') or 'STS section'}",
            "Preconditions: Not specified",
            f"Execution steps: Perform related operations per section content: {compact_text(section.get('content') or section.get('content_preview') or '')[:500] or 'Not specified'}",
            "Expected behavior: Actual behavior must satisfy the STS section description.",
            "Related signals/interfaces: Not specified",
            "Pass/fail criteria: Actual results must match the STS section description; confirm against the original STS document where fields are missing.",
        ])

    def _cluster_text(self, cluster: Dict[str, Any]) -> str:
        chunks = []
        for section in cluster.get("sections") or []:
            chunks.append(
                f"[{section.get('section_id')}] {section.get('title')}\n"
                f"Pages: {section.get('page_start')} - {section.get('page_end')}\n"
                f"{section.get('content_preview', '')}"
            )
        return "\n\n".join(chunks)

    def _clean_unit(self, unit: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(unit)
        for key, value in list(out.items()):
            if isinstance(value, str):
                out[key] = compact_text(normalize_mojibake(value))
        return out

    def _is_usable_unit(self, unit: Dict[str, Any]) -> bool:
        label_values = {"前提条件", "前置条件", "触发条件", "执行动作", "执行结果", "预期结果", "HMI显示", "文字弹框提示", "报警音", "图标显示", "常显"}
        evidence_fields = ("preconditions", "triggers", "actions", "expected_results", "hmi_display", "status_feedback")
        values = [compact_text(unit.get(field, "")) for field in evidence_fields]
        values = [value for value in values if value]
        if not values:
            return False
        if values and all(value in label_values for value in values):
            return False
        title = compact_text(unit.get("section_title", ""))
        if re.search(r"变更历史|需求来源|配置限制|功能框图|性能要求|诊断要求|文档说明|目录", title, re.I):
            return False
        return True

    def _to_int(self, value: Any) -> Optional[int]:
        if value in (None, "", False):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
