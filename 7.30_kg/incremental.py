import argparse
import hashlib
import importlib.util
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Set, Tuple


CURRENT_DIR = Path(__file__).resolve().parent  # pipelines/excel/
EXCEL_ROOT = CURRENT_DIR
VISUAL_EXTRACTOR_PATH = EXCEL_ROOT / "extractor.py"
DOMAINS_ROOT = EXCEL_ROOT / "domains"
DEFAULT_DOMAIN = "离车上锁功能测试"
DEFAULT_DOMAIN_DIR = DOMAINS_ROOT / "BCM_LOCK_离车上锁功能测试"
DEFAULT_BASELINE_EXCEL = EXCEL_ROOT / "input" / "3_3_3离车上锁功能对比.xlsx"
DEFAULT_CANDIDATE_EXCEL = EXCEL_ROOT / "input" / "3_3_3离车上锁功能对比v2.xlsx"
DEFAULT_STRATEGY = "regex_case"


_VISUAL_EXTRACTOR = None


def load_visual_extractor():
    """动态加载现有的 extractor.py，复用离车上锁三元组抽取逻辑。"""
    global _VISUAL_EXTRACTOR
    if _VISUAL_EXTRACTOR is not None:
        return _VISUAL_EXTRACTOR

    if not VISUAL_EXTRACTOR_PATH.exists():
        raise FileNotFoundError(f"未找到可复用的抽取脚本: {VISUAL_EXTRACTOR_PATH}")

    spec = importlib.util.spec_from_file_location(
        "incremental_visual_extractor",
        str(VISUAL_EXTRACTOR_PATH),
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载抽取脚本: {VISUAL_EXTRACTOR_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _VISUAL_EXTRACTOR = module
    return module


def compute_sha1(text: str) -> str:
    """对任意字符串计算 SHA1 哈希，返回 40 位小写十六进制字符串。"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def compute_case_key(case_id: str, case_name: str, occurrence_index: int = 1) -> str:
    """通过 case_anchor + occurrence_index 生成案例唯一标识。"""
    anchor = f"{case_id}||{case_name}||{occurrence_index}"
    return compute_sha1(anchor)


def compute_fact_hash(head: str, relation: str, tail: str) -> str:
    """通过三元组内容生成事实唯一指纹。"""
    content = f"{head}|{relation}|{tail}"
    return compute_sha1(content)


def compute_source_doc_key(normalized_source_file: str) -> str:
    """通过标准化文件名生成文档来源标识。"""
    return compute_sha1(normalized_source_file)


def normalize_filename(filename: str) -> str:
    """去除文件名末尾版本号后缀，统一识别同一份业务文档。"""
    name, ext = os.path.splitext(filename)
    name_clean = re.sub(r"[\s_]?[vV]\d+$", "", name)
    return name_clean + ext


def ensure_excel_exists(excel_path: str) -> Path:
    """校验 Excel 路径存在且是文件。"""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {excel_path}")
    if not path.is_file():
        raise FileNotFoundError(f"给定路径不是文件: {excel_path}")
    return path


def build_case_anchor(case_id: str, case_name: str) -> str:
    """构造案例锚点字符串。"""
    return f"{case_id}||{case_name}"


def build_case_scoped_key(case_key: str, fact_hash: str) -> str:
    """构造案例作用域下的事实键，避免 fact_hash 跨案例重复时误关联。"""
    return f"{case_key}::{fact_hash}"


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """读取 JSONL 文件，忽略空行。"""
    file_path = Path(path)
    if not file_path.exists():
        return []

    records: List[Dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                records.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 文件格式错误: {file_path} 第 {line_no} 行: {exc}") from exc
    return records


def write_jsonl(records: List[Dict[str, Any]], path: str):
    """将记录列表写入 JSONL 文件，每行一条 JSON。"""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def extract_triples_from_excel(excel_path: str, domain: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """从测试用例 Excel 中抽取候选三元组与案例索引。"""
    path = ensure_excel_exists(excel_path)
    extractor = load_visual_extractor()

    source_file = path.name
    normalized_source_file = normalize_filename(source_file)
    source_doc_key = compute_source_doc_key(normalized_source_file)

    try:
        df = extractor.read_table(str(path), sheet_name=0)
    except Exception as exc:
        raise ValueError(f"Excel 读取失败，请检查格式是否符合离车上锁测试用例模板: {excel_path}") from exc

    triples: List[Dict[str, Any]] = []
    case_index: List[Dict[str, Any]] = []
    case_anchor_counter: DefaultDict[str, int] = defaultdict(int)

    for idx, row in df.iterrows():
        record = "\n".join(f"{col}: {row[col]}" for col in df.columns)
        tc = extractor.parse_test_case_string(record)

        raw_case_type = str(tc.get("Test Case Type", "")).strip()
        case_name = str(tc.get("Test Case Name", "")).strip()
        if not raw_case_type and not case_name:
            continue
        if not raw_case_type or not case_name:
            raise ValueError(f"第 {idx + 1} 行测试用例缺少必要字段：Test Case Type 或 Test Case Name")

        case_id = f"{raw_case_type}测试用例"
        case_anchor = build_case_anchor(case_id, case_name)
        case_anchor_counter[case_anchor] += 1
        occurrence_index = case_anchor_counter[case_anchor]
        case_key = compute_case_key(case_id, case_name, occurrence_index)

        raw_triples = extractor.generate_lock_triples(tc)
        seen_fact_hashes: Set[str] = set()
        case_triples: List[Dict[str, Any]] = []

        for head, relation, tail in raw_triples:
            head_text = str(head)
            relation_text = str(relation)
            tail_text = str(tail)
            fact_hash = compute_fact_hash(head_text, relation_text, tail_text)
            if fact_hash in seen_fact_hashes:
                continue
            seen_fact_hashes.add(fact_hash)
            triple_record = {
                "doc_version": "candidate",
                "source_file": source_file,
                "source_doc_key": source_doc_key,
                "normalized_source_file": normalized_source_file,
                "strategy": DEFAULT_STRATEGY,
                "domain": domain,
                "row": idx + 1,
                "case_key": case_key,
                "case_id": case_id,
                "case_name": case_name,
                "case_anchor": case_anchor,
                "head": head_text,
                "relation": relation_text,
                "tail": tail_text,
                "fact_hash": fact_hash,
            }
            case_triples.append(triple_record)
            triples.append(triple_record)

        case_index.append({
            "doc_version": "candidate",
            "source_file": source_file,
            "source_doc_key": source_doc_key,
            "normalized_source_file": normalized_source_file,
            "strategy": DEFAULT_STRATEGY,
            "domain": domain,
            "row": idx + 1,
            "case_key": case_key,
            "case_id": case_id,
            "case_name": case_name,
            "case_anchor": case_anchor,
            "triple_count": len(case_triples),
            "fact_count": len(case_triples),
            "fact_hashes": sorted(seen_fact_hashes),
        })

    return triples, case_index


def load_current_case_index(domain_dir: str) -> Dict[str, Dict[str, Any]]:
    """加载当前案例索引，返回以 case_key 为键的字典。"""
    path = os.path.join(domain_dir, "current_case_index.jsonl")
    result: Dict[str, Dict[str, Any]] = {}
    for record in load_jsonl(path):
        result[record["case_key"]] = record
    return result


def load_current_triples(domain_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """加载当前三元组基线，返回以 fact_hash 为键的记录列表。"""
    path = os.path.join(domain_dir, "current_triples.jsonl")
    result: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in load_jsonl(path):
        result[record["fact_hash"]].append(record)
    return dict(result)


def flatten_triple_map(triple_map: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """将按 fact_hash 聚合的三元组字典展开为记录列表。"""
    records: List[Dict[str, Any]] = []
    for items in triple_map.values():
        records.extend(items)
    return records


def group_triples_by_case(triples: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按 case_key 聚合三元组，并保留原始顺序。"""
    grouped: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for triple in triples:
        grouped[triple["case_key"]].append(triple)
    return dict(grouped)


def build_case_scoped_record_map(triples: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """构造按 case_key + fact_hash 精确索引的记录字典。"""
    record_map: Dict[str, Dict[str, Any]] = {}
    for triple in triples:
        scoped_key = build_case_scoped_key(triple["case_key"], triple["fact_hash"])
        record_map[scoped_key] = triple
    return record_map


def sort_fact_hash_list(values: Iterable[str]) -> List[str]:
    """对 fact_hash 列表做稳定排序，保证幂等输出。"""
    return sorted(set(values))


def build_changed_pair(candidate_case: Dict[str, Any], old_triple: Dict[str, Any], new_triple: Dict[str, Any]) -> Dict[str, Any]:
    """构造逻辑变更对记录。"""
    return {
        "record_type": "changed_pair",
        "change_type": "logic_change",
        "domain": candidate_case["domain"],
        "source_file": candidate_case["source_file"],
        "source_doc_key": candidate_case["source_doc_key"],
        "normalized_source_file": candidate_case["normalized_source_file"],
        "strategy": candidate_case["strategy"],
        "row": candidate_case["row"],
        "case_key": candidate_case["case_key"],
        "case_id": candidate_case["case_id"],
        "case_name": candidate_case["case_name"],
        "case_anchor": candidate_case["case_anchor"],
        "old_triple": {
            "head": old_triple["head"],
            "relation": old_triple["relation"],
            "tail": old_triple["tail"],
            "fact_hash": old_triple["fact_hash"],
        },
        "new_triple": {
            "head": new_triple["head"],
            "relation": new_triple["relation"],
            "tail": new_triple["tail"],
            "fact_hash": new_triple["fact_hash"],
        },
    }


def match_changed_triples(
    removed_items: List[Dict[str, Any]],
    added_items: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    matched_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    used_new_indexes: Set[int] = set()

    for old_triple in removed_items:
        candidate_indexes: List[int] = []
        for index, new_triple in enumerate(added_items):
            if index in used_new_indexes:
                continue
            same_head = old_triple["head"] == new_triple["head"]
            same_tail = old_triple["tail"] == new_triple["tail"]
            if not (same_head or same_tail):
                continue
            if old_triple["fact_hash"] == new_triple["fact_hash"]:
                continue
            candidate_indexes.append(index)

        if not candidate_indexes:
            continue

        selected_index = min(
            candidate_indexes,
            key=lambda index: (
                0 if old_triple["head"] == added_items[index]["head"] else 1,
                0 if old_triple["tail"] == added_items[index]["tail"] else 1,
                added_items[index]["head"],
                added_items[index]["tail"],
                added_items[index]["fact_hash"],
            ),
        )
        used_new_indexes.add(selected_index)
        matched_pairs.append((old_triple, added_items[selected_index]))

    return matched_pairs


def case_match_score(candidate_case: Dict[str, Any], current_case: Dict[str, Any]) -> Tuple[int, float, int, int, int]:
    candidate_hashes = set(candidate_case["fact_hashes"])
    current_hashes = set(current_case["fact_hashes"])
    overlap = len(candidate_hashes & current_hashes)
    union = len(candidate_hashes | current_hashes)
    similarity = overlap / union if union else 1.0
    row_distance = -abs(candidate_case["row"] - current_case["row"])
    fact_distance = -abs(candidate_case["fact_count"] - current_case["fact_count"])
    return overlap, similarity, row_distance, fact_distance, -current_case["row"]


def match_candidate_cases_to_current(
    candidate_case_index: List[Dict[str, Any]],
    current_case_index: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Set[str]]:
    candidate_by_anchor: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    current_by_anchor: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in candidate_case_index:
        candidate_by_anchor[record["case_anchor"]].append(record)
    for record in current_case_index.values():
        current_by_anchor[record["case_anchor"]].append(record)

    matched_cases: Dict[str, Dict[str, Any]] = {}
    matched_current_keys: Set[str] = set()

    for case_anchor, candidate_cases in candidate_by_anchor.items():
        current_cases = current_by_anchor.get(case_anchor, [])
        if not current_cases:
            continue
        if len(candidate_cases) == 1 and len(current_cases) == 1:
            matched_cases[candidate_cases[0]["case_key"]] = current_cases[0]
            matched_current_keys.add(current_cases[0]["case_key"])
            continue

        remaining_candidate_cases = list(candidate_cases)
        remaining_current_cases = list(current_cases)
        while remaining_candidate_cases and remaining_current_cases:
            best_pair: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
            best_score: Optional[Tuple[int, float, int, int, int]] = None
            for candidate_case in remaining_candidate_cases:
                for current_case in remaining_current_cases:
                    score = case_match_score(candidate_case, current_case)
                    if score[0] <= 0:
                        continue
                    if best_score is None or score > best_score:
                        best_pair = (candidate_case, current_case)
                        best_score = score

            if not best_pair:
                break

            candidate_case, current_case = best_pair
            matched_cases[candidate_case["case_key"]] = current_case
            matched_current_keys.add(current_case["case_key"])
            remaining_candidate_cases.remove(candidate_case)
            remaining_current_cases.remove(current_case)

    return matched_cases, matched_current_keys


def compute_incremental_diff(
    candidate_triples: List[Dict[str, Any]],
    candidate_case_index: List[Dict[str, Any]],
    current_case_index: Dict[str, Dict[str, Any]],
    current_triples: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """计算候选版本相对于当前基线的新增、删除和逻辑变更。"""
    pending_add: List[Dict[str, Any]] = []
    pending_remove: List[Dict[str, Any]] = []
    pending_changed: List[Dict[str, Any]] = []

    current_case_keys = set(current_case_index.keys())

    candidate_case_triples = group_triples_by_case(candidate_triples)
    current_records = flatten_triple_map(current_triples)
    current_case_triples = group_triples_by_case(current_records)
    current_case_scoped_map = build_case_scoped_record_map(current_records)
    matched_case_map, matched_current_keys = match_candidate_cases_to_current(candidate_case_index, current_case_index)

    for candidate_case in candidate_case_index:
        candidate_case_key = candidate_case["case_key"]
        matched_current_case = matched_case_map.get(candidate_case_key)
        case_key = matched_current_case["case_key"] if matched_current_case else candidate_case_key
        effective_candidate_case = {**candidate_case, "case_key": case_key}
        incoming_hashes = set(candidate_case["fact_hashes"])
        incoming_hash_list = sort_fact_hash_list(incoming_hashes)
        case_candidate_triples = [
            {**triple, "case_key": case_key}
            for triple in candidate_case_triples.get(candidate_case_key, [])
        ]

        if matched_current_case is None:
            pending_add.append({
                "record_type": "case_marker",
                "change_type": "new_case_add",
                "domain": effective_candidate_case["domain"],
                "source_file": effective_candidate_case["source_file"],
                "source_doc_key": effective_candidate_case["source_doc_key"],
                "normalized_source_file": effective_candidate_case["normalized_source_file"],
                "strategy": effective_candidate_case["strategy"],
                "row": effective_candidate_case["row"],
                "case_key": case_key,
                "case_id": effective_candidate_case["case_id"],
                "case_name": effective_candidate_case["case_name"],
                "case_anchor": effective_candidate_case["case_anchor"],
                "previous_case_fact_hashes": [],
                "incoming_case_fact_hashes": incoming_hash_list,
            })
            for triple in case_candidate_triples:
                pending_add.append({
                    "record_type": "triple",
                    "change_type": "new_case_add",
                    **triple,
                })
            continue

        current_case = matched_current_case
        previous_hashes = set(current_case["fact_hashes"])
        previous_hash_list = sort_fact_hash_list(previous_hashes)

        if incoming_hashes == previous_hashes:
            continue

        removed_hashes = previous_hashes - incoming_hashes
        added_hashes = incoming_hashes - previous_hashes

        removed_triples = []
        for triple in current_case_triples.get(case_key, []):
            if triple["fact_hash"] in removed_hashes:
                scoped_key = build_case_scoped_key(case_key, triple["fact_hash"])
                if scoped_key in current_case_scoped_map:
                    removed_triples.append(current_case_scoped_map[scoped_key])

        added_triples = [
            triple for triple in case_candidate_triples
            if triple["fact_hash"] in added_hashes
        ]

        removed_by_relation: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        for triple in removed_triples:
            removed_by_relation[triple["relation"]].append(triple)

        added_by_relation: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        for triple in added_triples:
            added_by_relation[triple["relation"]].append(triple)

        for relation in sorted(set(removed_by_relation.keys()) & set(added_by_relation.keys())):
            old_items = removed_by_relation[relation]
            new_items = added_by_relation[relation]
            for old_triple, new_triple in match_changed_triples(old_items, new_items):
                pending_changed.append(build_changed_pair(effective_candidate_case, old_triple, new_triple))

        for triple in removed_triples:
            pending_remove.append({
                "record_type": "triple",
                "change_type": "changed_case_remove",
                **triple,
                "previous_case_fact_hashes": previous_hash_list,
                "incoming_case_fact_hashes": incoming_hash_list,
            })

        for triple in added_triples:
            pending_add.append({
                "record_type": "triple",
                "change_type": "changed_case_add",
                **triple,
            })

    for case_key in current_case_keys - matched_current_keys:
        current_case = current_case_index[case_key]
        previous_hashes = set(current_case["fact_hashes"])
        previous_hash_list = sort_fact_hash_list(previous_hashes)
        for triple in current_case_triples.get(case_key, []):
            if triple["fact_hash"] not in previous_hashes:
                continue
            pending_remove.append({
                "record_type": "triple",
                "change_type": "deleted_case_remove",
                **triple,
                "previous_case_fact_hashes": previous_hash_list,
                "incoming_case_fact_hashes": [],
            })

    return pending_add, pending_remove, pending_changed


def write_pending_files(
    domain_dir: str,
    pending_add: List[Dict[str, Any]],
    pending_remove: List[Dict[str, Any]],
    pending_changed: List[Dict[str, Any]],
):
    """将三类增量结果写入对应的 pending 文件。"""
    write_jsonl(pending_add, os.path.join(domain_dir, "pending_add_triples.jsonl"))
    write_jsonl(pending_remove, os.path.join(domain_dir, "pending_remove_triples.jsonl"))
    write_jsonl(pending_changed, os.path.join(domain_dir, "pending_changed_triples.jsonl"))


def convert_candidate_to_current(record: Dict[str, Any]) -> Dict[str, Any]:
    """将候选记录转换为 current 基线记录。"""
    current_record = dict(record)
    current_record["doc_version"] = "current"
    current_record.pop("record_type", None)
    current_record.pop("change_type", None)
    current_record.pop("previous_case_fact_hashes", None)
    current_record.pop("incoming_case_fact_hashes", None)
    return current_record


def deduplicate_current_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 case_key + fact_hash 去重，保留首次出现的记录。"""
    unique_records: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for record in records:
        scoped_key = build_case_scoped_key(record["case_key"], record["fact_hash"])
        if scoped_key in seen:
            continue
        seen.add(scoped_key)
        unique_records.append(record)
    return unique_records


def rebuild_case_index_from_current_records(current_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据最新 current_triples 重新聚合 current_case_index。"""
    grouped = group_triples_by_case(current_records)
    case_index: List[Dict[str, Any]] = []
    for case_key, triples in grouped.items():
        first = triples[0]
        fact_hashes = sort_fact_hash_list([triple["fact_hash"] for triple in triples])
        case_index.append({
            "doc_version": "current",
            "source_file": first["source_file"],
            "source_doc_key": first["source_doc_key"],
            "normalized_source_file": first["normalized_source_file"],
            "strategy": first["strategy"],
            "domain": first["domain"],
            "row": first["row"],
            "case_key": case_key,
            "case_id": first["case_id"],
            "case_name": first["case_name"],
            "case_anchor": first["case_anchor"],
            "triple_count": len(triples),
            "fact_count": len(fact_hashes),
            "fact_hashes": fact_hashes,
        })
    case_index.sort(key=lambda item: (item["row"], item["case_name"], item["case_key"]))
    return case_index


def initialize_current_baseline(excel_path: str, domain: str, domain_dir: str, overwrite: bool = False):
    """从一份原始 Excel 初始化 current 基线。"""
    domain_path = Path(domain_dir)
    domain_path.mkdir(parents=True, exist_ok=True)

    current_triples_path = domain_path / "current_triples.jsonl"
    current_case_index_path = domain_path / "current_case_index.jsonl"
    if not overwrite and current_triples_path.exists() and current_case_index_path.exists():
        print(f"[{domain}] 当前基线已存在，跳过初始化")
        return

    candidate_triples, candidate_case_index = extract_triples_from_excel(excel_path, domain)
    current_triples = [convert_candidate_to_current(record) for record in candidate_triples]
    current_case_index = [convert_candidate_to_current(record) for record in candidate_case_index]

    write_jsonl(current_triples, str(current_triples_path))
    write_jsonl(current_case_index, str(current_case_index_path))

    for pending_name in [
        "pending_add_triples.jsonl",
        "pending_remove_triples.jsonl",
        "pending_changed_triples.jsonl",
    ]:
        write_jsonl([], str(domain_path / pending_name))

    print(f"[{domain}] 已初始化 current 基线")
    print(f"  current_triples: {current_triples_path}")
    print(f"  current_case_index: {current_case_index_path}")


def build_latest_case_metadata_map(
    pending_add: List[Dict[str, Any]],
    pending_changed: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """从 pending 文件中提取每个案例的最新元数据，用于 apply 后统一 case_index 元信息。"""
    latest_meta: Dict[str, Dict[str, Any]] = {}

    for record in pending_add:
        if record.get("record_type") not in {"case_marker", "triple"}:
            continue
        latest_meta[record["case_key"]] = {
            "source_file": record["source_file"],
            "source_doc_key": record["source_doc_key"],
            "normalized_source_file": record["normalized_source_file"],
            "strategy": record["strategy"],
            "domain": record["domain"],
            "row": record["row"],
            "case_id": record["case_id"],
            "case_name": record["case_name"],
            "case_anchor": record["case_anchor"],
        }

    for record in pending_changed:
        latest_meta[record["case_key"]] = {
            "source_file": record["source_file"],
            "source_doc_key": record["source_doc_key"],
            "normalized_source_file": record["normalized_source_file"],
            "strategy": record["strategy"],
            "domain": record["domain"],
            "row": record["row"],
            "case_id": record["case_id"],
            "case_name": record["case_name"],
            "case_anchor": record["case_anchor"],
        }

    return latest_meta


def apply_domain_pending(domain_dir: str):
    """将人工审阅完成后的 pending 增量应用到正式 current 基线。"""
    domain_path = Path(domain_dir)
    domain_path.mkdir(parents=True, exist_ok=True)

    current_triples_path = domain_path / "current_triples.jsonl"
    current_case_index_path = domain_path / "current_case_index.jsonl"
    pending_add_path = domain_path / "pending_add_triples.jsonl"
    pending_remove_path = domain_path / "pending_remove_triples.jsonl"
    pending_changed_path = domain_path / "pending_changed_triples.jsonl"

    current_records = load_jsonl(str(current_triples_path))
    pending_add = load_jsonl(str(pending_add_path))
    pending_remove = load_jsonl(str(pending_remove_path))
    pending_changed = load_jsonl(str(pending_changed_path))

    removal_keys: Set[str] = set()
    for record in pending_remove:
        removal_keys.add(build_case_scoped_key(record["case_key"], record["fact_hash"]))
    for record in pending_changed:
        removal_keys.add(build_case_scoped_key(record["case_key"], record["old_triple"]["fact_hash"]))

    survivors: List[Dict[str, Any]] = []
    for record in current_records:
        scoped_key = build_case_scoped_key(record["case_key"], record["fact_hash"])
        if scoped_key in removal_keys:
            continue
        survivors.append(convert_candidate_to_current(record))

    addition_map: Dict[str, Dict[str, Any]] = {}
    for record in pending_add:
        if record.get("record_type") != "triple":
            continue
        current_record = convert_candidate_to_current(record)
        addition_map[build_case_scoped_key(current_record["case_key"], current_record["fact_hash"])] = current_record

    for record in pending_changed:
        current_record = {
            "doc_version": "current",
            "source_file": record["source_file"],
            "source_doc_key": record["source_doc_key"],
            "normalized_source_file": record["normalized_source_file"],
            "strategy": record["strategy"],
            "domain": record["domain"],
            "row": record["row"],
            "case_key": record["case_key"],
            "case_id": record["case_id"],
            "case_name": record["case_name"],
            "case_anchor": record["case_anchor"],
            "head": record["new_triple"]["head"],
            "relation": record["new_triple"]["relation"],
            "tail": record["new_triple"]["tail"],
            "fact_hash": record["new_triple"]["fact_hash"],
        }
        addition_map[build_case_scoped_key(current_record["case_key"], current_record["fact_hash"])] = current_record

    latest_meta = build_latest_case_metadata_map(pending_add, pending_changed)
    merged_records = survivors + list(addition_map.values())
    merged_records = deduplicate_current_records(merged_records)

    for record in merged_records:
        meta = latest_meta.get(record["case_key"])
        if meta is None:
            continue
        record["doc_version"] = "current"
        record["source_file"] = meta["source_file"]
        record["source_doc_key"] = meta["source_doc_key"]
        record["normalized_source_file"] = meta["normalized_source_file"]
        record["strategy"] = meta["strategy"]
        record["domain"] = meta["domain"]
        record["row"] = meta["row"]
        record["case_id"] = meta["case_id"]
        record["case_name"] = meta["case_name"]
        record["case_anchor"] = meta["case_anchor"]

    merged_records.sort(key=lambda item: (item["row"], item["case_name"], item["head"], item["relation"], item["tail"]))
    rebuilt_case_index = rebuild_case_index_from_current_records(merged_records)

    write_jsonl(merged_records, str(current_triples_path))
    write_jsonl(rebuilt_case_index, str(current_case_index_path))
    write_jsonl([], str(pending_add_path))
    write_jsonl([], str(pending_remove_path))
    write_jsonl([], str(pending_changed_path))

    print(f"[{domain_path.name}] 已应用 pending 增量")
    print(f"  current_triples 记录数: {len(merged_records)}")
    print(f"  current_case_index 案例数: {len(rebuilt_case_index)}")


def process_candidate_excel(excel_path: str, domain: str, domain_dir: str):
    """处理一份候选 Excel，生成该业务域的增量结果。"""
    os.makedirs(domain_dir, exist_ok=True)

    candidate_triples, candidate_case_index = extract_triples_from_excel(excel_path, domain)
    current_case_index = load_current_case_index(domain_dir)
    current_triples = load_current_triples(domain_dir)

    pending_add, pending_remove, pending_changed = compute_incremental_diff(
        candidate_triples,
        candidate_case_index,
        current_case_index,
        current_triples,
    )

    write_pending_files(domain_dir, pending_add, pending_remove, pending_changed)

    new_case_count = sum(1 for record in pending_add if record.get("record_type") == "case_marker")
    add_triple_count = sum(1 for record in pending_add if record.get("record_type") == "triple")
    print(f"[{domain}] 增量分析完成")
    print(f"  待新增案例数: {new_case_count}")
    print(f"  待新增三元组数: {add_triple_count}")
    print(f"  待删除记录数: {len(pending_remove)}")
    print(f"  逻辑变更对数: {len(pending_changed)}")


def run_default_demo():
    """按当前任务要求，初始化原始基线并对 v2 文件执行增量分析。"""
    initialize_current_baseline(
        excel_path=str(DEFAULT_BASELINE_EXCEL),
        domain=DEFAULT_DOMAIN,
        domain_dir=str(DEFAULT_DOMAIN_DIR),
        overwrite=True,
    )
    process_candidate_excel(
        excel_path=str(DEFAULT_CANDIDATE_EXCEL),
        domain=DEFAULT_DOMAIN,
        domain_dir=str(DEFAULT_DOMAIN_DIR),
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="汽车测试用例知识图谱增量更新系统")
    parser.add_argument("--excel", help="候选 Excel 文件路径")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="业务域名称")
    parser.add_argument("--domain-dir", default=str(DEFAULT_DOMAIN_DIR), help="业务域目录路径")
    parser.add_argument("--init-current-excel", help="用于初始化 current 基线的原始 Excel 文件路径")
    parser.add_argument("--overwrite-current", action="store_true", help="初始化 current 时覆盖已有基线")
    parser.add_argument("--apply", action="store_true", help="将 pending 增量应用到 current 基线")
    parser.add_argument("--demo", action="store_true", help="运行当前任务的默认演示流程")
    return parser


def main():
    """命令行主入口。"""
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.demo:
        run_default_demo()
        return

    if args.apply:
        apply_domain_pending(args.domain_dir)
        return

    if args.init_current_excel:
        initialize_current_baseline(
            excel_path=args.init_current_excel,
            domain=args.domain,
            domain_dir=args.domain_dir,
            overwrite=args.overwrite_current,
        )

    if args.excel:
        process_candidate_excel(
            excel_path=args.excel,
            domain=args.domain,
            domain_dir=args.domain_dir,
        )
        return

    if args.init_current_excel:
        return

    parser.print_help()


if __name__ == "__main__":
    main()
