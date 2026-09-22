#!/usr/bin/env python3
"""离线测试：PDF 在线全链路（需要 API Key + PaddleOCR）
用法：
    python test_pdf_online.py --image lighting_spec_0001
    python test_pdf_online.py --image lighting_spec_0001 --skip-ocr  # 跳过 OCR（使用缓存）
"""
import json, sys, os, time, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pdf_pipeline" / "src"))

os.environ.setdefault("DASHSCOPE_API_KEY", "")

from step2_ocr import run_ocr
from step3_desc import generate_descriptions
from step4_extract import extract_triples
from step5_fuse import fuse_triples
from scan_inputs import load_config
from utils.env_utils import load_local_env


def main():
    parser = argparse.ArgumentParser(description="PDF 在线全链路测试（需要 API + PaddleOCR）")
    parser.add_argument("--image", required=True, help="image_id（如 lighting_spec_0001）")
    parser.add_argument("--skip-ocr", action="store_true", help="跳过 OCR 阶段")
    args = parser.parse_args()

    manifest_path = ROOT / "pdf_pipeline" / "data" / "manifests" / "image_manifest.json"
    config_path = ROOT / "pdf_pipeline" / "config" / "pipeline_config.json"
    project_root = ROOT / "pdf_pipeline"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = next((i for i in manifest if i["image_id"] == args.image), None)
    if not item:
        print(f"[ERROR] 未找到 image_id: {args.image}")
        ids = [i["image_id"] for i in manifest]
        print(f"可用: {ids[:5]}...")
        sys.exit(1)

    # 路径映射
    for fld in ["image_path", "source_dir"]:
        orig = item.get(fld, "")
        if orig.startswith("/home/dt/智己项目/"):
            item[fld] = str(ROOT / orig[len("/home/dt/智己项目/"):])

    config = load_config(config_path)
    single = [item]
    pid = item["image_id"]

    print(f"\n{'='*60}")
    print(f"  PDF 在线全链路测试")
    print(f"{'='*60}")
    print(f"  image_id:    {pid}")
    print(f"  doc_name:    {item['doc_name']}")
    print(f"  image_path:  {item.get('image_path', 'N/A')[:80]}...")
    print(f"  image_exists:{Path(item['image_path']).exists() if item.get('image_path') else False}")
    print(f"{'='*60}")

    if not Path(item.get("image_path", "")).exists():
        print("[WARN] 图片文件不存在，OCR/描述/抽取将失败。请确认智己PDF/output/ 已完整拷贝。")

    # Stage 1: OCR
    ocr_results = {}
    if args.skip_ocr:
        print("\n[SKIP] OCR 阶段（--skip-ocr）")
    else:
        print("\n[Stage 1/4] PaddleOCR 文字识别 ...")
        t0 = time.time()
        try:
            ocr_results = run_ocr(single, config, project_root)
            terms = ocr_results.get(pid, [])
            print(f"  [OK] OCR 完成 ({time.time()-t0:.1f}s): {len(terms)} 个术语")
        except Exception as e:
            print(f"  [FAIL] OCR 失败: {e}")

    # Stage 2: Description
    print("\n[Stage 2/4] Qwen-VL 表格结构描述 ...")
    t0 = time.time()
    try:
        descriptions = generate_descriptions(single, config, project_root)
        desc = descriptions.get(pid, {})
        print(f"  [OK] Description 完成 ({time.time()-t0:.1f}s)")
        print(f"  table_type: {desc.get('table_type','N/A')}")
        print(f"  topic:      {desc.get('topic','N/A')}")
    except Exception as e:
        print(f"  [FAIL] Description 失败: {e}")
        descriptions = {}

    # Stage 3: Triple Extraction
    print("\n[Stage 3/4] Qwen-VL 三元组抽取 (Skill: pdf.online_table_pipeline.v1) ...")
    t0 = time.time()
    try:
        all_triples = extract_triples(single, config, project_root, ocr_results, descriptions)
        raw_count = len(all_triples.get(pid, []))
        print(f"  [OK] 抽取完成 ({time.time()-t0:.1f}s): {raw_count} 条候选三元组")
        if raw_count > 0:
            print(f"  前 5 条:")
            for t in all_triples.get(pid, [])[:5]:
                print(f"    ({t.get('head','')}, {t.get('relation','')}, {t.get('tail','')})")
    except Exception as e:
        print(f"  [FAIL] 三元组抽取失败: {e}")
        all_triples = {}

    # Stage 4: Fusion
    print("\n[Stage 4/4] Qwen-Plus 语义融合 (Skill: fusion.semantic_dedup_conflict.v1) ...")
    t0 = time.time()
    try:
        fused = fuse_triples(all_triples, single, config, project_root)
        conflicts = sum(1 for t in fused if t.get("conflict"))
        print(f"  [OK] 融合完成 ({time.time()-t0:.1f}s): {len(fused)} 条融合后, {conflicts} 个冲突")
        if fused:
            print(f"  融合后前 5 条:")
            for t in fused[:5]:
                flag = "" if t.get("conflict") else ""
                print(f"    {flag}({t.get('head','')}, {t.get('relation','')}, {t.get('tail','')})")
    except Exception as e:
        print(f"  [FAIL] 融合失败: {e}")

    print(f"\n{'='*60}")
    print(f"  测试完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
