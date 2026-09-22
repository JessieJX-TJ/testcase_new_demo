# 分组式车身控制测试用例 Excel 抽取 Skill

- `skill_id`: `excel.grouped_test_case.v1`
- 输入：`.xlsx`，业务数据在第二个 sheet
- 表头特点：第 1 行包含 `编号`、`编号名称`、`标题`、`#`、`步骤`、`预期结果`
- 分组规则：出现 `编号/编号名称/标题` 开启新组，空编号行延续上一测试用例
- 抽取工具：复用 `excel文件处理/Visualize/extractor.py` 中的 `build_grouped_output_lines`
- 输出：统一 `TripleRecord[]`

