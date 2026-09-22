#!/usr/bin/env python3
"""离线测试：PDF 缓存三元组读取（零 API 调用，直接读 MinerU 处理后的缓存）
用法：
    python test_pdf_cache.py                          # 列出所有可用图片
    python test_pdf_cache.py --image lighting_spec_0001  # 读取指定图片的三元组
    python test_pdf_cache.py --all                      # 读取所有图片并汇总
"""
import json, sys, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

MANIFEST_PATH = ROOT / "pdf_pipeline" / "data" / "manifests" / "image_manifest.json"
PDF_DATA = ROOT / "pdf_pipeline" / "data" / "intermediate"


def load_manifest():
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] manifest 不存在: {MANIFEST_PATH}")
        return []
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_image_bundle(item: dict) -> dict:
    """读取单张图片的 OCR / Description / Triples 缓存。"""
    doc_dir = PDF_DATA / item["doc_name"] / item["image_id"]
    bundle = {"item": item, "doc_dir": str(doc_dir), "stages": {}}

    for stage, path in [
        ("OCR_terms", doc_dir / "ocr" / "terms.json"),
        ("OCR_full", doc_dir / "ocr" / "full.json"),
        ("Description", doc_dir / "description" / "result.json"),
        ("Triples", doc_dir / "triples" / "result.json"),
    ]:
        if path.exists():
            bundle["stages"][stage] = json.loads(path.read_text(encoding="utf-8"))
            if stage == "Triples":
                bundle["stages"][stage + "_count"] = len(bundle["stages"][stage])
        else:
            bundle["stages"][stage] = None
            bundle["stages"][stage + "_count"] = 0
    return bundle


def show_bundle(bundle: dict):
    item = bundle["item"]
    s = bundle["stages"]
    print(f"\n  {'='*56}")
    print(f"  图片: {item['image_id']} | {item['file_name']}")
    print(f"  文档: {item['doc_name']}")
    print(f"  路径: {item.get('resolved_image_path', item.get('image_path', 'N/A'))}")
    print(f"  {'='*56}")
    print(f"  [OCR]      术语白名单: {s.get('OCR_terms_count', 0)} 个")
    print(f"  [OCR]      完整记录:   {len(s.get('OCR_full') or {})} 条")
    print(f"  [DESC]     表格类型:   {(s.get('Description') or {}).get('table_type', 'N/A')}")
    print(f"  [DESC]     主题:       {(s.get('Description') or {}).get('topic', 'N/A')}")
    print(f"  [TRIPLE]   三元组数:   {s.get('Triples_count', 0)} 条")

    triples = s.get("Triples") or []
    if triples:
        print(f"\n  前 5 条三元组:")
        for t in triples[:5]:
            print(f"    ({t.get('head','')}, {t.get('relation','')}, {t.get('tail','')})")

    # Fusion check
    fused_dir = PDF_DATA / "fused" / item.get("doc_id", "")
    fusion_file = fused_dir / "knowledge_graph.json"
    if fusion_file.exists():
        fused = json.loads(fusion_file.read_text(encoding="utf-8"))
        matching = [t for t in fused if t.get("source_image_id") == item["image_id"]]
        conflict = sum(1 for t in matching if t.get("conflict"))
        print(f"  [FUSION]   融合后:     {len(matching)} 条 (冲突: {conflict})")
    else:
        print(f"  [FUSION]   未运行融合")


def main():
    parser = argparse.ArgumentParser(description="PDF 缓存三元组离线读取测试")
    parser.add_argument("--image", help="指定 image_id（如 lighting_spec_0001）")
    parser.add_argument("--all", action="store_true", help="读取所有图片并汇总")
    args = parser.parse_args()

    manifest = load_manifest()
    if not manifest:
        return

    doc_names = sorted(set(item["doc_name"] for item in manifest))

    if args.image:
        item = next((i for i in manifest if i["image_id"] == args.image), None)
        if not item:
            print(f"[ERROR] 未找到图片: {args.image}")
            print(f"可用 image_id:")
            for i in manifest:
                print(f"  - {i['image_id']} ({i['doc_name']})")
            return
        show_bundle(load_image_bundle(item))

    elif args.all:
        print(f"\n{'='*60}")
        print(f"  PDF 缓存批量读取测试")
        print(f"{'='*60}")
        print(f"  文档数: {len(doc_names)}")
        print(f"  图片数: {len(manifest)}")
        total_triples = 0
        total_fused = 0
        for item in manifest:
            bundle = load_image_bundle(item)
            c = bundle["stages"].get("Triples_count", 0)
            total_triples += c
            tag = "[OK]" if c > 0 else "[!] "
            print(f"  {tag} {item['image_id']:30s} | {item['doc_name'][:20]:20s} | {c:4d} triples")
            fused_dir = PDF_DATA / "fused" / item.get("doc_id", "")
            fusion_file = fused_dir / "knowledge_graph.json"
            if fusion_file.exists():
                fused = json.loads(fusion_file.read_text(encoding="utf-8"))
                total_fused += len([t for t in fused if t.get("source_image_id") == item["image_id"]])
        print(f"{'='*60}")
        print(f"  候选三元组总计: {total_triples} 条")
        print(f"  融合后三元组总计: {total_fused} 条")
        print()

    else:
        print(f"\n{'='*60}")
        print(f"  PDF 图片清单")
        print(f"{'='*60}")
        for item in manifest:
            doc_dir = PDF_DATA / item["doc_name"] / item["image_id"]
            has_triple = (doc_dir / "triples" / "result.json").exists()
            tag = "[OK]" if has_triple else "[!] "
            print(f"  {tag} {item['image_id']:30s} | {item['doc_name'][:25]:25s} | {item['file_name']}")
        print(f"{'='*60}")
        print(f"\n  运行模式:")
        print(f"    python test_pdf_cache.py --all          # 批量统计")
        print(f"    python test_pdf_cache.py --image {manifest[0]['image_id']}  # 查看详情")
        print()


if __name__ == "__main__":
    main()
