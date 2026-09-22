#!/usr/bin/env python3
"""
eval_online.py - Per-image quality evaluation using Qwen-VL-Plus.

Evaluates each image with structured triple-level feedback that can
be consumed by the LLM rewrite workflow in app.py.

Output format per image:
  - 5 quality scores (0-10)
  - issues[] with triple_indices, issue_type, description, suggested_correction
  - meta (image_id, doc_name, ocr_term_count, triple_count)

Usage:
    python eval_online.py --image lighting_spec_0001
    python eval_online.py --image lighting_spec_0001 --triples  # also show triples
"""

import argparse, base64, json, os, sys, time
from pathlib import Path

os.environ.setdefault("DASHSCOPE_API_KEY", "")

PROJECT_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH      = PROJECT_ROOT / "pdf_pipeline" / "data" / "manifests" / "image_manifest.json"
INTERMEDIATE_ROOT  = PROJECT_ROOT / "pdf_pipeline" / "data" / "intermediate"
OUTPUT_DIR         = PROJECT_ROOT / "eval_results" / "online"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def resolve_project_path(path_text: str) -> Path:
    text = str(path_text or "")
    if text.startswith("/home/dt/智己项目"):
        mapped = PROJECT_ROOT / text[len("/home/dt/智己项目"):].lstrip("/\\")
        if mapped.exists():
            return mapped
    normalized = text.replace("\\", "/")
    if "智己项目/" in normalized:
        mapped = PROJECT_ROOT / normalized.split("智己项目/", 1)[1]
        if mapped.exists():
            return mapped
    candidate = Path(text)
    if candidate.exists():
        return candidate
    return candidate


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_json(path: Path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def load_manifest():
    return load_json(MANIFEST_PATH, [])


def find_item_by_image_id(manifest, image_id):
    for item in manifest:
        if item.get("image_id") == image_id:
            return item
    return None


def get_intermediate_paths(doc_name, image_id):
    doc_dir = INTERMEDIATE_ROOT / doc_name / image_id
    return {
        "ocr_terms":   doc_dir / "ocr" / "terms.json",
        "ocr_full":    doc_dir / "ocr" / "full.json",
        "description": doc_dir / "description" / "result.json",
        "triples":     doc_dir / "triples" / "result.json",
    }


# ---------------------------------------------------------------------------
# Prompt builder — structured triple-level feedback
# ---------------------------------------------------------------------------
def build_eval_prompt(ocr_terms: list, description: dict, triples: list) -> str:
    ocr_sample = "\n".join(ocr_terms[:60]) if ocr_terms else "(no OCR terms)"

    desc_brief = {
        "table_type": description.get("table_type", ""),
        "topic": description.get("topic", ""),
        "engineering_interpretation": description.get("engineering_interpretation", ""),
    }
    desc_text = json.dumps(desc_brief, ensure_ascii=False, indent=2)

    # Numbered triples for reference
    numbered_triples = []
    for i, t in enumerate(triples):
        numbered_triples.append({
            "index": i,
            "head": t.get("head", ""),
            "relation": t.get("relation", ""),
            "tail": t.get("tail", ""),
        })
    triples_text = json.dumps(numbered_triples, ensure_ascii=False, indent=2)

    prompt = f"""You are a quality evaluator for an automotive specification knowledge-graph extraction pipeline.

This pipeline processes a table image from a Chinese automotive technical specification:
1. OCR extracts visible text terms
2. A vision model generates a structured description of the table
3. Triples (head, relation, tail) are extracted from the table content

Your task: evaluate the quality of step 3 (triple extraction) against the image, OCR terms, and table description.

=== OCR TERMS (sample of what the OCR detected) ===
{ocr_sample}

=== TABLE DESCRIPTION ===
{desc_text}

=== EXTRACTED TRIPLES (numbered, same order as in the pipeline output) ===
{triples_text}

=== EVALUATION INSTRUCTIONS ===

Reply ONLY with a valid JSON object. No markdown fences, no extra text.

Score the extraction on:
- ocr_completeness (0-10): Are the OCR terms accurate and complete?
- description_accuracy (0-10): Does the description match the image?
- triple_precision (0-10): Are the extracted triples factually correct?
- triple_recall (0-10): Are important relationships missing?
- overall_score (0-10): Weighted avg (OCR 0.2, Desc 0.2, Precision 0.3, Recall 0.3)

For EACH issue found, include a structured entry in the issues[] array with:
- triple_indices: array of 0-based triple indices affected
- issue_type: one of [wrong_entity, wrong_relation, missing_triple, extra_triple, spelling, incomplete, redundant]
- severity: one of [critical, major, minor]
- description: brief Chinese description of the problem

=== CORRECTIONS FORMAT ===

For EACH issue, also produce a "correction" object that tells the system exactly what to do.
Use <action> tags to indicate the operation type.

Available operations:
- <action>delete</action>   — remove this triple (needs: triple_indices)
- <action>modify</action>   — rewrite this triple (needs: triple_indices + corrected_head, corrected_relation, corrected_tail)
- <action>add</action>      — insert a new triple (needs: new_head, new_relation, new_tail, no triple_indices)

Each correction object format:
{{
  "triple_indices": [<int>],       // which existing triples to act on (empty [] for add)
  "action": "<delete|modify|add>",
  "reason": "<why this change>",
  "corrected_head": "<new value>",     // only for modify/add
  "corrected_relation": "<new value>", // only for modify/add
  "corrected_tail": "<new value>"      // only for modify/add
}}

For "add": triple_indices=[], action="add", corrected_head/relation/tail filled.
For "modify": triple_indices=[idx], action="modify", corrected_* filled.
For "delete": triple_indices=[idx], action="delete", corrected_* can be empty strings.

JSON FORMAT:
{{
  "ocr_completeness": <int 0-10>,
  "ocr_completeness_reason": "<brief>",
  "description_accuracy": <int 0-10>,
  "description_accuracy_reason": "<brief>",
  "triple_precision": <int 0-10>,
  "triple_precision_reason": "<brief>",
  "triple_recall": <int 0-10>,
  "triple_recall_reason": "<brief>",
  "overall_score": <int 0-10>,
  "issues": [
    {{
      "triple_indices": [<int>],
      "issue_type": "<type>",
      "severity": "<critical|major|minor>",
      "description": "<Chinese description>"
    }}
  ],
  "corrections": [
    {{
      "triple_indices": [<int>],
      "action": "<delete|modify|add>",
      "reason": "<why>",
      "corrected_head": "<value>",
      "corrected_relation": "<value>",
      "corrected_tail": "<value>"
    }}
  ]
}}

Output ONLY the JSON object."""
    return prompt


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------
def call_qwen_vl(image_b64: str, prompt_text: str) -> str:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ.get("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    response = client.chat.completions.create(
        model="qwen-vl-plus",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": prompt_text},
        ]}],
        max_tokens=4096, temperature=0.1,
    )
    return response.choices[0].message.content


def encode_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def parse_eval_response(raw_response: str) -> dict:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    start, end = cleaned.find("{"), cleaned.rfind("}") + 1
    if start >= 0 and end > start:
        cleaned = cleaned[start:end]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_response": raw_response, "parse_error": True}


# ---------------------------------------------------------------------------
# Main evaluation function (imported by app.py)
# ---------------------------------------------------------------------------
def evaluate_single(image_id: str, manifest: list = None) -> dict:
    if manifest is None:
        manifest = load_manifest()
    item = find_item_by_image_id(manifest, image_id)
    if item is None:
        return {"image_id": image_id, "error": "Image not found in manifest"}

    doc_name = item.get("doc_name", "")
    image_path = resolve_project_path(item.get("resolved_image_path") or item.get("image_path", ""))
    paths = get_intermediate_paths(doc_name, image_id)

    ocr_data = load_json(paths["ocr_terms"], {})
    ocr_terms = ocr_data.get("whitelist_terms", []) if isinstance(ocr_data, dict) else []
    description = load_json(paths["description"], {})
    triples = load_json(paths["triples"], [])

    print(f"  Image: {image_id} | Doc: {doc_name} | OCR: {len(ocr_terms)} | Triples: {len(triples)}")

    if not image_path.exists():
        return {"image_id": image_id, "doc_name": doc_name, "error": "Image file not found",
                "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    image_b64 = encode_image_base64(str(image_path))
    prompt = build_eval_prompt(ocr_terms, description, triples)

    try:
        raw = call_qwen_vl(image_b64, prompt)
        result = parse_eval_response(raw)
        result["image_id"] = image_id
        result["doc_name"] = doc_name
        result["evaluated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result["ocr_term_count"] = len(ocr_terms)
        result["triple_count"] = len(triples)
        # Attach the actual triples (for rewrite workflow)
        result["_triples"] = triples
        result["_ocr_terms"] = ocr_terms[:60]
        result["_description"] = {"table_type": description.get("table_type",""),
                                  "topic": description.get("topic",""),
                                  "engineering_interpretation": description.get("engineering_interpretation","")}
        return result
    except Exception as e:
        return {"image_id": image_id, "doc_name": doc_name, "error": str(e),
                "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Online quality evaluation via Qwen-VL-Plus")
    parser.add_argument("--image", required=True, help="Image ID to evaluate")
    parser.add_argument("--triples", action="store_true", help="Also print triples")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = evaluate_single(args.image)

    if result.get("error"):
        print(f"[ERROR] {result['error']}")
        return

    print(f"\nOverall: {result.get('overall_score','?')}/10")
    print(f"  OCR completeness:    {result.get('ocr_completeness','?')}/10")
    print(f"  Description accuracy: {result.get('description_accuracy','?')}/10")
    print(f"  Triple precision:    {result.get('triple_precision','?')}/10")
    print(f"  Triple recall:       {result.get('triple_recall','?')}/10")

    issues = result.get("issues", [])
    if issues:
        print(f"\nIssues found: {len(issues)}")
        for i, iss in enumerate(issues):
            print(f"  [{iss.get('severity','?').upper()}] {iss.get('issue_type','?')}")
            print(f"    triples: {iss.get('triple_indices',[])}")
            print(f"    {iss.get('description','')}")
            print(f"    -> {iss.get('suggested_correction','')}")

    if args.triples:
        print(f"\nTriples:")
        for t in result.get("_triples", []):
            print(f"  ({t.get('head','')}, {t.get('relation','')}, {t.get('tail','')})")

    out = OUTPUT_DIR / f"{args.image}_eval.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
