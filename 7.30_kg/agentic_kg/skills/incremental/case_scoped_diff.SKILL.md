# 案例作用域增量更新 Skill

- `skill_id`: `incremental.case_scoped_diff.v1`
- 输入：baseline Excel、candidate Excel、domain、domain_dir
- 处理方式：复用 `excel文件处理/增量更新/extract.py`
- 输出：`pending_add_triples.jsonl`、`pending_remove_triples.jsonl`、`pending_changed_triples.jsonl` 的汇总与明细

