from __future__ import annotations

import argparse
from pathlib import Path

from scan_inputs import build_manifest, load_config
from step2_ocr import run_ocr
from step3_desc import generate_descriptions
from step4_extract import extract_triples
from step5_fuse import fuse_triples
from utils.env_utils import load_local_env, require_env


def run_pipeline(config_path: Path) -> None:
    project_root = config_path.resolve().parents[1]
    load_local_env(project_root / ".env")
    require_env("DASHSCOPE_API_KEY")
    config = load_config(config_path)

    manifest = build_manifest(config, project_root)
    print(f"[SCAN] 已加载 {len(manifest)} 张图片")

    ocr_results = run_ocr(manifest, config, project_root)
    print(f"[OCR] 已完成 {len(ocr_results)} 张图片")

    descriptions = generate_descriptions(manifest, config, project_root)
    print(f"[DESC] 已完成 {len(descriptions)} 张图片")

    all_triples = extract_triples(manifest, config, project_root, ocr_results, descriptions)
    total_raw = sum(len(v) for v in all_triples.values())
    print(f"[TRIPLE] 已抽取 {total_raw} 条候选三元组")

    fused = fuse_triples(all_triples, manifest, config, project_root)
    print(f"[FUSE] 最终输出 {len(fused)} 条知识图谱三元组")
    print(f"[DONE] 输出文件: {project_root / config.get('output_root', 'data') / 'final' / 'knowledge_graph.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "config" / "pipeline_config.json"),
    )
    args = parser.parse_args()
    run_pipeline(Path(args.config))
