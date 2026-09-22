import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseSkill
from .sts_text import compact_text, normalize_mojibake, write_jsonl


class _SimpleTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._in_table = False
        self._in_cell = False
        self._table: List[List[str]] = []
        self._row: List[str] = []
        self._cell: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag == "table":
            self._in_table = True
            self._table = []
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in {"td", "th"}:
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._row.append(compact_text("".join(self._cell)))
            self._in_cell = False
        elif tag == "tr" and self._in_table:
            if any(self._row):
                self._table.append(self._row)
        elif tag == "table" and self._in_table:
            if self._table:
                self.tables.append(self._table)
            self._in_table = False

    def handle_data(self, data: str):
        if self._in_cell:
            self._cell.append(data)


class STSBuildRequirementKnowledgeSkill(BaseSkill):
    name = "sts.build_requirement_knowledge"
    description = "Build requirement units, signal index and coverage matrix from STS sections."
    input_schema = {"required": ["sections"], "optional": ["document_id", "mineru_artifacts"]}
    output_schema = {"format": "sts_knowledge"}

    FIELD_KEYS = {
        "preconditions": ("前提条件", "前置条件", "适用条件", "配置", "车辆状态", "整车模式"),
        "triggers": ("触发条件", "触发", "输入条件", "请求", "信号变化", "条件"),
        "actions": ("执行动作", "动作", "控制请求", "控制逻辑"),
        "expected_results": ("预期行为", "预期结果", "执行结果", "常显", "文字弹框提示", "报警音", "图标显示", "显示"),
        "hmi_display": ("HMI", "常显", "文字弹框提示", "图标显示", "仪表", "中控屏"),
        "status_feedback": ("状态反馈", "反馈", "响应", "Resp", "Response", "失败提醒", "提醒"),
        "test_environment": ("测试环境", "场景示例", "台架", "实车"),
        "remarks": ("备注", "说明", "项目", "适用项目"),
    }
    SIGNAL_KEYS = ("Signal Name", "信号名称", "信号名", "Service Name", "Interface Name", "Parameter", "发送方", "发送", "接收方", "接收", "通信方式", "通讯方式", "信号编码")
    FIELD_LABEL_VALUES = {"前提条件", "前置条件", "触发条件", "执行动作", "执行结果", "预期结果", "预期行为", "HMI显示", "文字弹框提示", "报警音", "图标显示", "常显", "状态反馈", "测试环境", "场景示例"}
    GENERIC_SIGNAL_NAMES = {"PowerLiftgateSystem", "PowerLiftgate", "PersonalizationData"}
    USEFUL_SECTION_RE = re.compile(r"功能逻辑|常显|TT|Warning|Chime|异常处理|控制|设置|状态|信号|接口|服务|提醒", re.I)
    LOW_VALUE_SECTION_RE = re.compile(r"变更历史|需求来源|配置限制|功能框图|性能要求|诊断要求|文档说明", re.I)

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sections = input_data.get("sections") or []
        document_id = input_data.get("document_id") or ""
        artifacts = input_data.get("mineru_artifacts") or {}

        units: List[Dict[str, Any]] = []
        signals: List[Dict[str, Any]] = []
        for section in sections:
            section = self._clean_section(section)
            tables = self._extract_tables(section.get("content", ""))
            has_signal_table = False
            for table_index, table in enumerate(tables, 1):
                if self._is_signal_table(table):
                    has_signal_table = True
                    signals.extend(self._parse_signal_table(document_id, section, table, table_index))
                if self.LOW_VALUE_SECTION_RE.search(section.get("title", "")):
                    continue
                units.extend(self._parse_requirement_table(document_id, section, table, table_index))
            if (not tables or not has_signal_table) and not any(unit.get("section_id") == section.get("section_id") for unit in units):
                text_unit = self._unit_from_text(document_id, section)
                if text_unit:
                    units.append(text_unit)

        units = self._dedupe_units(units)
        for unit in units:
            unit["related_signals"] = self._match_signals(unit, signals)
            unit["test_intents"] = self._infer_test_intents(unit)
            unit["source_quality"] = self._quality(unit)

        coverage_matrix = [{
            "unit_id": unit.get("unit_id"),
            "section_id": unit.get("section_id"),
            "function": unit.get("function"),
            "test_intents": unit.get("test_intents", []),
            "must_cover": unit.get("source_quality") != "low",
            "covered_by_cases": [],
        } for unit in units]

        knowledge = {
            "document_id": document_id,
            "requirement_units": units,
            "signals": signals,
            "coverage_matrix": coverage_matrix,
        }
        knowledge["knowledge_artifacts"] = self._save_artifacts(artifacts, knowledge)
        return {**knowledge, "skill": self.name}

    def _clean_section(self, section: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(section)
        for key in ("title", "content", "content_preview"):
            out[key] = normalize_mojibake(out.get(key, ""))
        return out

    def _extract_tables(self, markdown: str) -> List[List[List[str]]]:
        parser = _SimpleTableParser()
        parser.feed(markdown or "")
        if parser.tables:
            return parser.tables
        return self._extract_malformed_tables(markdown or "")

    def _extract_malformed_tables(self, markdown: str) -> List[List[List[str]]]:
        tables: List[List[List[str]]] = []
        for table_html in re.findall(r"<table[\s\S]*?(?:</table>|$)", markdown, flags=re.I):
            rows: List[List[str]] = []
            for row_html in re.findall(r"<tr[\s\S]*?(?:</tr>|$)", table_html, flags=re.I):
                cells = []
                for cell_html in re.findall(r"<t[dh][^>]*>([\s\S]*?)(?=<t[dh][^>]*>|</tr>|$)", row_html, flags=re.I):
                    cell_html = re.sub(r"/t[dh]>\s*$", "", cell_html, flags=re.I)
                    cells.append(compact_text(cell_html))
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    def _is_signal_table(self, table: List[List[str]]) -> bool:
        text = " ".join(cell for row in table[:3] for cell in row)
        return sum(1 for key in self.SIGNAL_KEYS if key.lower() in text.lower()) >= 2

    def _parse_signal_table(self, document_id: str, section: Dict[str, Any], table: List[List[str]], table_index: int) -> List[Dict[str, Any]]:
        if len(table) < 2:
            return []
        header = self._headers(table[0])
        signals = []
        for row_index, row in enumerate(table[1:], 1):
            values = self._row_to_dict(header, row)
            name = self._first_value(values, "Signal Name", "信号名称", "信号名", "Service Name", "Interface Name", "Parameter Name") or (row[0] if row else "")
            if not compact_text(name):
                continue
            signals.append({
                "signal_id": f"sig_{section.get('section_id', 'sec')}_{table_index}_{row_index}",
                "document_id": document_id,
                "section_id": section.get("section_id"),
                "section_title": section.get("title"),
                "name": compact_text(name),
                "sender": self._first_value(values, "发送方", "发送") or "",
                "receiver": self._first_value(values, "接收方", "接收") or "",
                "communication": self._first_value(values, "通信方式", "通讯方式") or "",
                "encoding": self._first_value(values, "信号编码", "Parameter", "Parameter name", "Parameter Name") or "",
                "raw": values,
            })
        return signals

    def _parse_requirement_table(self, document_id: str, section: Dict[str, Any], table: List[List[str]], table_index: int) -> List[Dict[str, Any]]:
        if len(table) < 2:
            return []
        vertical_unit = self._parse_vertical_requirement_table(document_id, section, table, table_index)
        if vertical_unit:
            return [vertical_unit]
        header = self._headers(table[0])
        data_rows = table[1:]
        normalized = self._normalize_multi_header(table)
        if normalized:
            header, data_rows = normalized
        table_text = " ".join(cell for row in table[:4] for cell in row)
        if not any(any(key.lower() in table_text.lower() for key in keys) for keys in self.FIELD_KEYS.values()):
            return []

        units = []
        last_values: Dict[str, str] = {}
        for row_index, row in enumerate(data_rows, 1):
            values = self._row_to_dict(header, row)
            if self._is_header_like_row(values):
                continue
            unit = self._base_unit(document_id, section, f"t{table_index}_r{row_index}")
            hits = 0
            for key, value in values.items():
                field = self._field_for_key(key)
                value = compact_text(value)
                if not value and field in last_values:
                    value = last_values[field]
                if field and value and value not in {"-", "NA", "N/A", "无"}:
                    unit[field] = self._append(unit.get(field, ""), value)
                    last_values[field] = value
                    hits += 1
            if hits >= 1 and self._unit_has_assertion(unit):
                unit["raw_row"] = values
                unit["source_type"] = "table_row"
                units.append(unit)
        return units

    def _normalize_multi_header(self, table: List[List[str]]) -> Optional[tuple[List[str], List[List[str]]]]:
        if len(table) < 3:
            return None
        first = [compact_text(cell) for cell in table[0]]
        second = [compact_text(cell) for cell in table[1]]
        if "执行结果" not in first or not any(self._field_for_key(cell) in {"expected_results", "hmi_display", "status_feedback"} for cell in second):
            return None
        result_index = first.index("执行结果")
        trailing_count = max(0, len(table[2]) - result_index - len(second))
        header = first[:result_index] + second
        if trailing_count:
            header.extend(first[-trailing_count:])
        while len(header) < len(table[2]):
            header.append(f"col_{len(header) + 1}")
        return header[:len(table[2])], table[2:]

    def _parse_vertical_requirement_table(self, document_id: str, section: Dict[str, Any], table: List[List[str]], table_index: int) -> Optional[Dict[str, Any]]:
        if len(table) < 3 or len(table[0]) < 2:
            return None
        first_header = compact_text(table[0][0])
        if first_header not in {"HMI界面", "项目", "需求项", "字段"}:
            return None
        unit = self._base_unit(document_id, section, f"t{table_index}_record")
        raw_rows: List[Dict[str, str]] = []
        hits = 0
        for row in table[1:]:
            if len(row) < 2:
                continue
            label = compact_text(row[0])
            value = compact_text("; ".join(cell for cell in row[1:] if compact_text(cell)))
            field = self._field_for_key(label)
            if not field or not value or value in {"-", "NA", "N/A", "无"}:
                continue
            unit[field] = self._append(unit.get(field, ""), value)
            raw_rows.append({"field": label, "value": value})
            hits += 1
        if hits >= 2 and self._unit_has_assertion(unit):
            unit["raw_rows"] = raw_rows
            unit["source_type"] = "table_record"
            return unit
        return None

    def _unit_from_text(self, document_id: str, section: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = compact_text(section.get("title", ""))
        content = compact_text(section.get("content", ""))
        if len(content) < 120:
            return None
        if self.LOW_VALUE_SECTION_RE.search(title):
            return None
        if not (section.get("is_candidate") or self.USEFUL_SECTION_RE.search(title) or self.USEFUL_SECTION_RE.search(content[:1200])):
            return None
        unit = self._base_unit(document_id, section, "text")
        unit["requirement_text"] = content[:2400]
        unit["expected_results"] = content[:1600]
        unit["source_type"] = "section_text"
        return unit

    def _base_unit(self, document_id: str, section: Dict[str, Any], suffix: str) -> Dict[str, Any]:
        section_id = str(section.get("section_id") or "sec").replace(" ", "_")
        title = compact_text(section.get("title", ""))
        return {
            "unit_id": f"ru_{section_id}_{suffix}",
            "document_id": document_id,
            "section_id": section.get("section_id"),
            "section_title": title,
            "page_start": section.get("page_start"),
            "page_end": section.get("page_end"),
            "function": re.sub(r"^\d+(?:\.\d+)*\s*", "", title) or section_id,
            "preconditions": "",
            "triggers": "",
            "actions": "",
            "expected_results": "",
            "hmi_display": "",
            "status_feedback": "",
            "test_environment": "",
            "remarks": "",
        }

    def _headers(self, row: List[str]) -> List[str]:
        headers = []
        for index, cell in enumerate(row):
            clean = compact_text(cell)
            headers.append(clean or f"col_{index + 1}")
        return headers

    def _row_to_dict(self, header: List[str], row: List[str]) -> Dict[str, str]:
        return {header[index] if index < len(header) else f"col_{index + 1}": compact_text(cell) for index, cell in enumerate(row)}

    def _first_value(self, values: Dict[str, str], *keys: str) -> str:
        for key in keys:
            value = values.get(key)
            if compact_text(value):
                return compact_text(value)
        return ""

    def _is_header_like_row(self, values: Dict[str, str]) -> bool:
        cells = [compact_text(value) for value in values.values() if compact_text(value)]
        return bool(cells) and all(cell in self.FIELD_LABEL_VALUES for cell in cells)

    def _field_for_key(self, key: str) -> Optional[str]:
        key = compact_text(key)
        for field, keys in self.FIELD_KEYS.items():
            if any(item.lower() in key.lower() for item in keys):
                return field
        return None

    def _append(self, old: str, new: str) -> str:
        old = compact_text(old)
        new = compact_text(new)
        if not old:
            return new
        if not new or new in old:
            return old
        return f"{old}; {new}"

    def _unit_has_assertion(self, unit: Dict[str, Any]) -> bool:
        return bool(unit.get("triggers") or unit.get("actions") or unit.get("expected_results") or unit.get("hmi_display") or unit.get("status_feedback"))

    def _dedupe_units(self, units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out = []
        for unit in units:
            key = tuple(compact_text(unit.get(field, "")) for field in ("section_id", "preconditions", "triggers", "expected_results", "hmi_display", "status_feedback"))
            if key in seen:
                continue
            seen.add(key)
            out.append(unit)
        return out

    def _match_signals(self, unit: Dict[str, Any], signals: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        text = json.dumps(unit, ensure_ascii=False)
        related = []
        for signal in signals:
            name = signal.get("name", "")
            encoding = signal.get("encoding", "")
            if name in self.GENERIC_SIGNAL_NAMES:
                continue
            if (name and name in text) or (encoding and len(encoding) >= 4 and encoding in text):
                related.append({
                    "name": name,
                    "signal_id": signal.get("signal_id", ""),
                    "encoding": signal.get("encoding", ""),
                    "communication": signal.get("communication", ""),
                })
        return related[:12]

    def _infer_test_intents(self, unit: Dict[str, Any]) -> List[str]:
        text = json.dumps(unit, ensure_ascii=False)
        intents = ["Positive function"]
        if unit.get("preconditions"):
            intents.append("Precondition not satisfied")
        if re.search(r"失败|异常|Fail|Invalid|not in|未|禁止|不可|拒绝", text, re.I):
            intents.append("Reject/failure path")
        if re.search(r">=|<=|>|<|边界|超时|timeout|retry|5km/h|10s|3s|6s", text, re.I):
            intents.append("Boundary/timeout")
        if unit.get("hmi_display"):
            intents.append("HMI display consistency")
        if unit.get("status_feedback"):
            intents.append("Status feedback")
        if unit.get("related_signals"):
            intents.append("Signal/service interface")
        if re.search(r"优先级|仲裁|占用|priority|occupy", text, re.I):
            intents.append("Service priority/arbitration")
        return list(dict.fromkeys(intents))

    def _quality(self, unit: Dict[str, Any]) -> str:
        if unit.get("source_type") == "table_record" and (unit.get("triggers") or unit.get("actions")):
            return "high"
        if unit.get("source_type") == "table_row" and (unit.get("triggers") or unit.get("expected_results")):
            return "high"
        if unit.get("source_type") == "section_text":
            return "medium"
        return "low"

    def _save_artifacts(self, artifacts: Dict[str, Any], knowledge: Dict[str, Any]) -> Dict[str, str]:
        artifact_dir_value = artifacts.get("artifact_dir")
        if not artifact_dir_value:
            return {}
        artifact_dir = Path(artifact_dir_value)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "requirement_units_path": str(artifact_dir / "requirement_units.json"),
            "requirement_units_jsonl_path": str(artifact_dir / "requirement_units.jsonl"),
            "signals_path": str(artifact_dir / "signals.json"),
            "coverage_matrix_path": str(artifact_dir / "coverage_matrix.json"),
            "sts_knowledge_path": str(artifact_dir / "sts_knowledge.json"),
        }
        (artifact_dir / "requirement_units.json").write_text(json.dumps(knowledge["requirement_units"], ensure_ascii=False, indent=2), encoding="utf-8")
        write_jsonl(artifact_dir / "requirement_units.jsonl", knowledge["requirement_units"])
        (artifact_dir / "signals.json").write_text(json.dumps(knowledge["signals"], ensure_ascii=False, indent=2), encoding="utf-8")
        (artifact_dir / "coverage_matrix.json").write_text(json.dumps(knowledge["coverage_matrix"], ensure_ascii=False, indent=2), encoding="utf-8")
        (artifact_dir / "sts_knowledge.json").write_text(json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8")
        return paths
