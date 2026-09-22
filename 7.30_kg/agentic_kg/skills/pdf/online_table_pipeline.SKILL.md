# PDF 表格在线多阶段抽取 Skill

- `skill_id`: `pdf.online_table_pipeline.v1`
- 输入：`image_manifest.json` 中的一张图片记录
- 阶段：
  1. `run_ocr`：PaddleOCR 提取 OCR full records 和 whitelist terms
  2. `generate_descriptions`：Qwen-VL 生成表格结构描述
  3. `extract_triples`：Qwen-VL 基于图片、OCR 白名单和表格描述抽取候选三元组
  4. `fuse_triples`：Qwen-Plus 做去冗余、术语统一和冲突标记
- 输出：统一 `TripleRecord[]`、阶段日志、`fusion_report`
- 进化策略：若 OCR 失败或模型输出无法解析，记录为运行记忆并进入后续技能优化候选。

