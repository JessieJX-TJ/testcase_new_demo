import pandas as pd
import re
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


# === 配置区域：输入输出路径建议外部传入，默认使用当前目录 ===
PROJECT_ROOT = Path(__file__).resolve().parent
FILE_PATH = str(PROJECT_ROOT / "input")
SHEET_NAME = 0  # Excel 中的 sheet 索引或名称
OUTPUT_JSON = str(PROJECT_ROOT / "outputs" / "triples_output.json")

# ==========================================

# ==========================================

DOMAIN_ORDER = [
    "3_3_3离车上锁功能对比.xlsx",
    "0801EF15 伴我回家控制.xlsx",
    "0801EF23 紧急制动灯控制.xlsx",
    "0801EF13 迎宾灯控制.xlsx",
]

GROUPED_DOMAIN_CONFIGS = {
    "伴我回家控制": {
        "section_header": "0801EF15 伴我回家控制",
        "sheet_index": 1,
        "header_aliases": {},
    },
    "迎宾灯控制": {
        "section_header": "0801EF13 迎宾灯控制",
        "sheet_index": 1,
        "header_aliases": {},
    },
    "紧急制动灯控制": {
        "section_header": "0801EF23 紧急制动灯控制",
        "sheet_index": 1,
        "header_aliases": {9: "结果信号"},
    },
}


def strip_trailing_punct(s: str) -> str:
    """去除字符串末尾的中英文标点及空白"""
    if not isinstance(s, str):
        return s
    return re.sub(r"[\s　]*[，。；、,.!?！？;：:]+$", "", s.strip())


def read_table(file_path: str, sheet_name=0) -> pd.DataFrame:
    """读取 Excel 文件并去除各单元格末尾标点"""
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    for col in df.columns:
        df[col] = df[col].astype(str).apply(strip_trailing_punct)
    return df


def clean_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("_x000D_", "\n")
    text = text.strip()
    if not text or text.lower() == "nan":
        return ""
    return strip_trailing_punct(text)


def split_numbered_items(text: str) -> List[str]:
    normalized = clean_cell(text)
    if not normalized:
        return []
    items: List[str] = []
    current = ""
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^\d+[\.、]", line):
            if current:
                items.append(strip_trailing_punct(current))
            current = re.sub(r"^\d+[\.、]\s*", "", line)
        elif current:
            current = f"{current} {line}".strip()
        else:
            current = line
    if current:
        items.append(strip_trailing_punct(current))
    if items:
        return items
    return [strip_trailing_punct(line.strip()) for line in normalized.splitlines() if line.strip()]


def infer_domain_from_name(file_name: str) -> str:
    if "离车上锁" in file_name:
        return "离车上锁功能测试"
    for domain_name in GROUPED_DOMAIN_CONFIGS:
        if domain_name in file_name:
            return domain_name
    raise ValueError(f"无法识别输入文件类型: {file_name}")


def iter_input_files(input_path: str) -> List[Path]:
    path = Path(input_path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"输入路径不存在: {input_path}")

    all_files = {item.name: item for item in path.iterdir() if item.suffix.lower() == ".xlsx"}
    ordered = [all_files[name] for name in DOMAIN_ORDER if name in all_files]
    if ordered:
        return ordered

    filtered = []
    for item in sorted(all_files.values(), key=lambda p: p.name):
        if "离车上锁功能对比v2" in item.name:
            continue
        filtered.append(item)
    return filtered


def normalize_grouped_header(value: Any, column_index: int, header_aliases: Dict[int, str]) -> str:
    if column_index in header_aliases:
        return header_aliases[column_index]
    text = clean_cell(value)
    if not text:
        return ""
    if "编号名称" in text:
        return "编号名称"
    if text.startswith("编号"):
        return "编号"
    if "标题" in text:
        return "标题"
    if text.startswith("P11L_M2"):
        return "P11L_M2"
    if text.startswith("S12L_M1") and "P基线" not in text and "SOP基线" not in text:
        return "S12L_M1"
    if text == "#":
        return "#"
    if "步骤描述" in text:
        return "步骤描述"
    if "步骤" in text:
        return "步骤"
    if "预期结果" in text:
        return "预期结果"
    if "SOP基线" in text:
        return "SOP基线"
    if "P基线" in text:
        return "P基线"
    if "备注" in text:
        return "备注"
    return strip_trailing_punct(text.split("\n", 1)[0])


def build_grouped_rows(file_path: Path, domain_name: str) -> List[Dict[str, Any]]:
    config = GROUPED_DOMAIN_CONFIGS[domain_name]
    xls = pd.ExcelFile(file_path)
    sheet_name = xls.sheet_names[config["sheet_index"]]
    raw_df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    header_row = raw_df.iloc[0].tolist()
    headers = [normalize_grouped_header(value, idx, config["header_aliases"]) for idx, value in enumerate(header_row)]

    groups: List[Dict[str, Any]] = []
    current_group: Dict[str, Any] | None = None

    for row_index in range(1, len(raw_df)):
        row_values = [clean_cell(value) for value in raw_df.iloc[row_index].tolist()]
        if not any(row_values):
            continue
        row_data = {headers[idx] if headers[idx] else f"col_{idx}": row_values[idx] for idx in range(len(row_values))}
        is_new_group = bool(row_data.get("编号") or row_data.get("编号名称") or row_data.get("标题"))
        if is_new_group:
            current_group = {
                "row": row_index + 1,
                "rows": [row_data],
            }
            groups.append(current_group)
        elif current_group is not None:
            current_group["rows"].append(row_data)

    return groups


def append_grouped_triple(lines: List[str], row_no: int, head: str, relation: str, tail: str) -> None:
    head = clean_cell(head)
    relation = clean_cell(relation)
    tail = clean_cell(tail)
    if not head or not relation or not tail:
        return
    lines.append(json.dumps({"row": row_no, "head": head, "relation": relation, "tail": tail}, ensure_ascii=False))


def build_grouped_output_lines(file_path: Path, domain_name: str) -> List[str]:
    config = GROUPED_DOMAIN_CONFIGS[domain_name]
    groups = build_grouped_rows(file_path, domain_name)
    lines = [f"#{config['section_header']}"]

    for group_idx, group in enumerate(groups, start=1):
        row_no = group["row"]
        first_row = group["rows"][0]
        code = first_row.get("编号", "")
        function_name = first_row.get("编号名称", "")
        title = first_row.get("标题", "")

        lines.append(f"// 第 {row_no} 行测试用例（原第 {group_idx} 组）")
        append_grouped_triple(lines, row_no, code, "编号名称", function_name)
        append_grouped_triple(lines, row_no, function_name, "包含测试用例", title)
        append_grouped_triple(lines, row_no, title, "P11L_M2", first_row.get("P11L_M2", ""))
        append_grouped_triple(lines, row_no, title, "S12L_M1", first_row.get("S12L_M1", ""))

        for row_data in group["rows"]:
            step_no = row_data.get("#", "")
            step_items = split_numbered_items(row_data.get("步骤", ""))
            expected_items = split_numbered_items(row_data.get("预期结果", ""))
            step_detail = row_data.get("步骤描述", "")
            result_signal = row_data.get("结果信号", "")

            relation = "前提条件" if step_no == "1" else "操作动作"
            for item in step_items:
                append_grouped_triple(lines, row_no, title, relation, item)

            if step_detail:
                detail_relation = "前提条件描述" if step_no == "1" else "步骤描述"
                append_grouped_triple(lines, row_no, title, detail_relation, step_detail)

            for item in expected_items:
                append_grouped_triple(lines, row_no, title, "预期结果", item)

            if result_signal:
                append_grouped_triple(lines, row_no, title, "结果信号", result_signal)

        append_grouped_triple(lines, row_no, title, "P基线", first_row.get("P基线", ""))
        append_grouped_triple(lines, row_no, title, "SOP基线", first_row.get("SOP基线", ""))
        append_grouped_triple(lines, row_no, title, "备注", first_row.get("备注", ""))

    return lines


def parse_test_case_string(input_str: str) -> Dict[str, List[str]]:
    """解析测试用例文本块为字段映射"""
    def extract_list(block: str) -> list:
        items = re.findall(r"\[\d+\][^[]*", str(block))
        return [re.sub(r"[，。；、,.!?！？;：:、]+$", "", item.split(']', 1)[-1].strip()) for item in items if item.strip()]

    parsed = {}
    for key in ['Test Case Type', 'Test Case Name', 'Test Case Logic']:
        m = re.search(fr"{key}:\s*(.+)", input_str)
        parsed[key] = strip_trailing_punct(m.group(1)) if m else ''

    blocks = [
        ('Preconditions', 'Precondition signals'),
        ('Precondition signals', 'Precondition values'),
        ('Precondition values', 'Actions'),
        ('Actions', 'Action signals'),
        ('Action signals', 'Action values'),
        ('Action values', 'Expectations'),
        ('Expectations', 'Expectation signals'),
        ('Expectation signals', 'Expectation values'),
        ('Expectation values', None)
    ]
    for start, end in blocks:
        pattern = re.escape(start) + r":\s*(.*?)" + (re.escape(end) if end else r"$")
        m = re.search(pattern, input_str, re.S)
        block_text = m.group(1) if m else ''
        parsed[start] = extract_list(block_text)

    return parsed


def extract_value(raw_val: str) -> str:
    raw_val = strip_trailing_punct(raw_val)
    m = re.search(r"\(([^)]+)\)", raw_val)
    return strip_trailing_punct(m.group(1)) if m else raw_val


def generate_lock_triples(tc: Dict[str, List[str]]) -> List[Tuple[str, str, str]]:
    ttype = tc.get("Test Case Type", '')
    tname = tc.get("Test Case Name", '')
    tlogic = tc.get("Test Case Logic", '')
    preconds = tc.get('Preconditions', [])
    psigs = tc.get('Precondition signals', [])
    pvals = tc.get('Precondition values', [])
    acts = tc.get('Actions', [])
    asigs = tc.get('Action signals', [])
    avals = tc.get('Action values', [])
    exps = tc.get('Expectations', [])
    esigs = tc.get('Expectation signals', [])
    evals = tc.get('Expectation values', [])

    triples = []
    triples.append((f"{ttype}测试用例", "属于类型", "离车上锁功能测试"))
    triples.append((tname, "是", f"{ttype}测试用例"))
    triples.append((tname, "验证逻辑", tlogic))

    for cond in preconds:
        triples.append((tname, "需要前提条件", cond))
    for cond, sig in zip(preconds, psigs):
        triples.append((cond, "对应信号", sig))
    for sig, val in zip(psigs, pvals):
        triples.append((sig, "预期值", extract_value(val)))

    composite = '，'.join(f"{sig}：{extract_value(val)}" for sig, val in zip(psigs, pvals))
    triples.append((tname, "需要复合条件", composite))

    for act, sig, val in zip(acts, asigs, avals):
        triples.append((composite, "执行动作", act))
        triples.append((act, "关联信号", sig))
        triples.append((sig, "动作值", extract_value(val)))

    for exp, sig, val in zip(exps, esigs, evals):
        triples.append((tname, "预期行为", exp))
        triples.append((exp, "对应信号", sig))
        triples.append((sig, "预期值", extract_value(val)))

    return triples


def generate_triples(tc: Dict[str, List[str]]) -> List[Tuple[str, str, str]]:
    return generate_lock_triples(tc)


def build_lock_output_lines(file_path: Path) -> List[str]:
    df = read_table(str(file_path), sheet_name=SHEET_NAME)
    lines: List[str] = []
    for idx, row in df.iterrows():
        record = '\n'.join(f"{col}: {row[col]}" for col in df.columns)
        tc = parse_test_case_string(record)
        triples = generate_lock_triples(tc)
        lines.extend(
            json.dumps({"row": idx + 1, "head": h, "relation": r, "tail": t}, ensure_ascii=False)
            for h, r, t in triples
        )
    return lines


def format_and_print_triples(idx: int, tc: Dict[str, List[str]], triples: List[Tuple[str, str, str]]):
    """按照规范格式打印三元组"""
    ttype = tc.get("Test Case Type", '')
    tname = tc.get("Test Case Name", '')
    tlogic = tc.get("Test Case Logic", '')
    preconds = tc.get('Preconditions', [])
    psigs = tc.get('Precondition signals', [])
    pvals = tc.get('Precondition values', [])
    acts = tc.get('Actions', [])
    asigs = tc.get('Action signals', [])
    avals = tc.get('Action values', [])
    exps = tc.get('Expectations', [])
    esigs = tc.get('Expectation signals', [])
    evals = tc.get('Expectation values', [])

    print(f"\n--- 第 {idx + 1} 行提取的三元组 ---\n")

    print("🎯 测试用例定义：")
    print(f"({ttype}测试用例, 属于类型, 离车上锁功能测试)")
    print(f"({tname}, 是, {ttype}测试用例)")
    print(f"({tname}, 验证逻辑, {tlogic})\n")

    print("📝 前提条件：")
    print("  ➤ 条件实体定义")
    for cond in preconds:
        print(f"({tname}, 需要前提条件, {cond})")
    print("  ➤ 条件与信号映射")
    for cond, sig in zip(preconds, psigs):
        print(f"({cond}, 对应信号, {sig})")
    print("  ➤ 信号与取值约束")
    for sig, val in zip(psigs, pvals):
        print(f"({sig}, 预期值, {extract_value(val)})\n")

    print("⚡️ 动作与结果：")
    print("  ➤ 动作定义")
    composite = '，'.join(f"{sig}：{extract_value(val)}" for sig, val in zip(psigs, pvals))
    print(f"({tname}, 需要复合条件, {composite})")
    for act, sig, val in zip(acts, asigs, avals):
        print(f"({composite}, 执行动作, {act})")
        print(f"({act}, 关联信号, {sig})")
        print(f"({sig}, 动作值, {extract_value(val)})")
    print("  ➤ 预期结果")
    for exp, sig, val in zip(exps, esigs, evals):
        print(f"({tname}, 预期行为, {exp})")
        print(f"({exp}, 对应信号, {sig})")
        print(f"({sig}, 预期值, {extract_value(val)})")


def main():
    output_lines: List[str] = []
    for file_path in iter_input_files(FILE_PATH):
        domain_name = infer_domain_from_name(file_path.name)
        if domain_name == "离车上锁功能测试":
            output_lines.extend(build_lock_output_lines(file_path))
        else:
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            output_lines.extend(build_grouped_output_lines(file_path, domain_name))

    output_path = Path(OUTPUT_JSON)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(output_lines) + '\n', encoding='utf-8')
    print(f"已保存至: {output_path}")


if __name__ == '__main__':
    main()
