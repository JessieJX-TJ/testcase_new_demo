from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from agentic_kg.models import DocumentProfile, TripleRecord
# VISUAL_EXTRACTOR_PATH 已更新指向 pipelines/excel/extractor.py
from agentic_kg.paths import VISUAL_EXTRACTOR_PATH, import_module_from_path


LOCK_COLUMNS = [
    "Test Case Type",
    "Test Case Name",
    "Test Case Logic",
    "Preconditions",
    "Precondition signals",
    "Precondition values",
    "Actions",
    "Action signals",
    "Action values",
    "Expectations",
    "Expectation signals",
    "Expectation values",
]


_EXTRACTOR = None


def load_visual_extractor() -> Any:
    global _EXTRACTOR
    if _EXTRACTOR is None:
        _EXTRACTOR = import_module_from_path("agentic_visual_extractor", VISUAL_EXTRACTOR_PATH)
    return _EXTRACTOR


def _cell_to_text(value: Any, max_len: int = 120) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("_x000D_", "\n")
    text = " / ".join(part.strip() for part in text.splitlines() if part.strip())
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _sample_sheet(path: Path, sheet_name: str) -> List[List[str]]:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=5)
    rows: List[List[str]] = []
    for _, row in raw.iterrows():
        rows.append([_cell_to_text(value) for value in row.tolist()])
    return rows


def _safe_headers(path: Path, sheet_name: str) -> List[str]:
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, nrows=0)
        return [str(col).strip() for col in df.columns]
    except Exception:
        return []


def _infer_grouped_domain(path: Path, sheets: List[str]) -> str:
    name = path.name
    for candidate in ["伴我回家控制", "迎宾灯控制", "紧急制动灯控制"]:
        if candidate in name or any(candidate in sheet for sheet in sheets):
            return candidate
    return ""


def profile_excel(path: str | Path) -> DocumentProfile:
    excel_path = Path(path)
    xls = pd.ExcelFile(excel_path)
    sheets = list(xls.sheet_names)
    risk_points: List[str] = []
    template_kind = "unknown"
    selected_sheet = sheets[0] if sheets else None
    headers: List[str] = []
    domain = ""
    candidate_skill_ids: List[str] = []

    for sheet in sheets:
        sheet_headers = _safe_headers(excel_path, sheet)
        if sheet_headers == LOCK_COLUMNS:
            template_kind = "lock_test_case"
            selected_sheet = sheet
            headers = sheet_headers
            domain = "离车上锁功能测试"
            candidate_skill_ids = ["excel.lock_test_case.v1"]
            break

    if template_kind == "unknown" and len(sheets) >= 2:
        extractor = load_visual_extractor()
        raw = pd.read_excel(excel_path, sheet_name=sheets[1], header=None, nrows=1)
        header_row = raw.iloc[0].tolist() if not raw.empty else []
        normalized = [
            extractor.normalize_grouped_header(value, idx, {})
            for idx, value in enumerate(header_row)
        ]
        required = {"编号", "编号名称", "标题", "#", "步骤", "预期结果"}
        if required.issubset(set(normalized)):
            template_kind = "grouped_test_case"
            selected_sheet = sheets[1]
            headers = normalized
            domain = _infer_grouped_domain(excel_path, sheets)
            candidate_skill_ids = ["excel.grouped_test_case.v1"]

    if template_kind == "unknown":
        selected_sheet = sheets[0] if sheets else None
        headers = _safe_headers(excel_path, selected_sheet) if selected_sheet else []
        candidate_skill_ids = ["excel.unknown_template.draft"]
        risk_points.append("未命中内置 Excel 模板，需要生成待审核技能草稿。")

    if template_kind == "lock_test_case":
        try:
            df = pd.read_excel(excel_path, sheet_name=selected_sheet)
            for index, row in df.iterrows():
                actions = str(row.get("Actions", ""))
                action_signals = str(row.get("Action signals", ""))
                action_values = str(row.get("Action values", ""))
                counts = [actions.count("["), action_signals.count("["), action_values.count("[")]
                if len(set(counts)) > 1:
                    risk_points.append(f"第 {index + 2} 行 Actions/Action signals/Action values 数量可能不一致: {counts}")
                    break
        except Exception as exc:
            risk_points.append(f"无法检查动作字段数量: {exc}")

    sample_rows = _sample_sheet(excel_path, selected_sheet) if selected_sheet else []
    row_count = int(pd.read_excel(excel_path, sheet_name=selected_sheet, header=None).shape[0]) if selected_sheet else 0
    return DocumentProfile(
        file_type="excel",
        source_path=str(excel_path),
        source_name=excel_path.name,
        template_kind=template_kind,
        domain=domain,
        sheets=sheets,
        selected_sheet=selected_sheet,
        headers=headers,
        sample_rows=sample_rows,
        row_count=row_count,
        candidate_skill_ids=candidate_skill_ids,
        risk_points=risk_points,
        metadata={"required_lock_columns": LOCK_COLUMNS},
    )


def _parse_output_lines(lines: List[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or text.startswith("//"):
            continue
        try:
            records.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return records


def extract_excel_triples(path: str | Path, profile: DocumentProfile, skill_id: str) -> List[TripleRecord]:
    excel_path = Path(path)
    extractor = load_visual_extractor()

    if profile.template_kind == "lock_test_case":
        raw_records = _parse_output_lines(extractor.build_lock_output_lines(excel_path))
    elif profile.template_kind == "grouped_test_case":
        if not profile.domain:
            raise ValueError("分组 Excel 模板缺少可识别业务域。")
        raw_records = _parse_output_lines(extractor.build_grouped_output_lines(excel_path, profile.domain))
    else:
        raw_records = []

    triples: List[TripleRecord] = []
    for record in raw_records:
        triples.append(
            TripleRecord(
                head=str(record.get("head", "")),
                relation=str(record.get("relation", "")),
                tail=str(record.get("tail", "")),
                source_type="excel",
                source_file=excel_path.name,
                sheet_name=profile.selected_sheet or "",
                row=int(record["row"]) if str(record.get("row", "")).isdigit() else record.get("row"),
                domain=profile.domain,
                skill_id=skill_id,
                confidence=1.0,
                evidence={
                    "template_kind": profile.template_kind,
                    "source_path": str(excel_path),
                },
            )
        )
    return triples
