# 三元组语义融合与冲突识别 Skill

- `skill_id`: `fusion.semantic_dedup_conflict.v1`
- 输入：候选三元组集合
- 核心能力：
  - 精确重复合并
  - 语义等价合并
  - 统一专业术语
  - 标记潜在冲突并保留来源
- 当前实现：复用 `pdf_kg_pipeline/src/step5_fuse.py`
- 输出：`head/relation/tail/sources/conflict/conflict_note`

