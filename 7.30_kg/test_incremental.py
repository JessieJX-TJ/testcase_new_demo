#!/usr/bin/env python3
"""离线测试：增量更新
用法：
    python test_incremental.py                                     # 运行完整 demo
    python test_incremental.py --init                              # 仅初始化基线
    python test_incremental.py --generate                          # 仅生成 pending
    python test_incremental.py --apply                             # 应用 pending 到 current
    python test_incremental.py --show                              # 查看当前 pending 状态
"""
import sys, os, argparse, json
from pathlib import Path
from io import StringIO
import contextlib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from incremental import (
    initialize_current_baseline,
    process_candidate_excel,
    apply_domain_pending,
    load_jsonl,
    DEFAULT_DOMAIN,
    DEFAULT_DOMAIN_DIR,
    DEFAULT_BASELINE_EXCEL,
    DEFAULT_CANDIDATE_EXCEL,
)


def capture_stdout(func, *args, **kwargs):
    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        func(*args, **kwargs)
    return [line for line in buffer.getvalue().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="增量更新离线测试")
    parser.add_argument("--init", action="store_true", help="初始化基线")
    parser.add_argument("--generate", action="store_true", help="生成 pending")
    parser.add_argument("--apply", action="store_true", help="应用 pending")
    parser.add_argument("--show", action="store_true", help="查看 pending 状态")
    args = parser.parse_args()

    baseline = str(ROOT / "input" / "3_3_3离车上锁功能对比.xlsx")
    candidate = str(ROOT / "input" / "3_3_3离车上锁功能对比v2.xlsx")
    domain_dir = str(ROOT / "domains" / "BCM_LOCK_离车上锁功能测试")

    run_all = not any([args.init, args.generate, args.apply, args.show])

    print(f"\n{'='*60}")
    print(f"  增量更新测试")
    print(f"{'='*60}")
    print(f"  基线文件: {Path(baseline).name}")
    print(f"  候选文件: {Path(candidate).name}")
    print(f"  领域目录: {domain_dir}")
    print(f"  关联 Skill: incremental.case_scoped_diff.v1")
    print(f"{'='*60}")

    if args.init or run_all:
        print("\n[Step 1/3] 初始化基线 (initialize_current_baseline) ...")
        logs = capture_stdout(initialize_current_baseline, baseline, DEFAULT_DOMAIN, domain_dir, True)
        for line in logs:
            print(f"  {line}")

    if args.generate or run_all:
        print("\n[Step 2/3] 生成增量 pending (process_candidate_excel) ...")
        logs = capture_stdout(process_candidate_excel, candidate, DEFAULT_DOMAIN, domain_dir)
        for line in logs:
            print(f"  {line}")

    if args.apply or run_all:
        print("\n[Step 3/3] 应用 pending 到 current (apply_domain_pending) ...")
        logs = capture_stdout(apply_domain_pending, domain_dir)
        for line in logs:
            print(f"  {line}")

    if args.show or run_all:
        print(f"\n{'='*60}")
        print(f"  Pending 状态")
        print(f"{'='*60}")
        domain_path = Path(domain_dir)
        for fname, label in [
            ("pending_add_triples.jsonl", "待增加"),
            ("pending_remove_triples.jsonl", "待删除"),
            ("pending_changed_triples.jsonl", "待更新"),
            ("current_triples.jsonl", "当前三元组"),
        ]:
            path = domain_path / fname
            if path.exists():
                records = load_jsonl(str(path))
                print(f"  {label}: {len(records)} 条")

    print(f"\n{'='*60}")
    print(f"  测试完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
