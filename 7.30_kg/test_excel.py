#!/usr/bin/env python3
"""离线测试：Excel 三元组抽取
用法：
    python test_excel.py                          # 批量抽取所有 Excel
    python test_excel.py --file input/3_3_3离车上锁功能对比.xlsx  # 抽取单个文件
    python test_excel.py --file input/0801EF15 伴我回家控制.xlsx   # 抽取分组模板
"""
import sys, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from extractor import (
    infer_domain_from_name,
    build_lock_output_lines,
    build_grouped_output_lines,
    iter_input_files,
)


def run_single(file_path: Path) -> dict:
    domain = infer_domain_from_name(file_path.name)
    if domain == "离车上锁功能测试":
        lines = build_lock_output_lines(file_path)
    else:
        lines = build_grouped_output_lines(file_path, domain)

    triples = []
    for line in lines:
        line = line.strip()
        if line.startswith("#") or line.startswith("//") or not line:
            continue
        import json
        try:
            triples.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    return {
        "file": file_path.name,
        "domain": domain,
        "template": "lock_test_case" if domain == "离车上锁功能测试" else "grouped_test_case",
        "triple_count": len(triples),
        "triples": triples,
    }


def main():
    parser = argparse.ArgumentParser(description="Excel 三元组抽取离线测试")
    parser.add_argument("--file", help="指定单个 Excel 文件（可选，默认批量抽取）")
    args = parser.parse_args()

    if args.file:
        file_path = ROOT / args.file
        if not file_path.exists():
            print(f"[ERROR] 文件不存在: {file_path}")
            sys.exit(1)
        result = run_single(file_path)
        print(f"\n{'='*60}")
        print(f"  Excel 三元组抽取测试")
        print(f"{'='*60}")
        print(f"  文件:     {result['file']}")
        print(f"  业务域:   {result['domain']}")
        print(f"  模板:     {result['template']} (Skill: excel.{result['template']}.v1)")
        print(f"  三元组数: {result['triple_count']} 条")
        print(f"{'='*60}")
        if result['triples']:
            print(f"\n  前 10 条三元组:")
            for t in result['triples'][:10]:
                print(f"    ({t['head']}, {t['relation']}, {t['tail']})")
            if result['triple_count'] > 10:
                print(f"    ... (省略 {result['triple_count'] - 10} 条)")
        print()
    else:
        print(f"\n{'='*60}")
        print(f"  Excel 三元组批量抽取测试")
        print(f"{'='*60}")
        input_dir = ROOT / "input"
        total = 0
        for file_path in sorted(input_dir.glob("*.xlsx"), key=lambda p: p.name):
            try:
                result = run_single(file_path)
                tag = "[OK]" if result['triple_count'] > 0 else "[WARN]"
                print(f"  {tag} {result['file']:45s} domain={result['domain']:15s} template={result['template']:20s} triples={result['triple_count']}")
                total += result['triple_count']
            except Exception as exc:
                print(f"  [FAIL] {file_path.name}: {exc}")
        print(f"{'='*60}")
        print(f"  总计: {total} 条三元组")
        print()


if __name__ == "__main__":
    main()
