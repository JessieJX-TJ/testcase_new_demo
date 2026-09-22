# 离车上锁测试用例 Excel 抽取 Skill

- `skill_id`: `excel.lock_test_case.v1`
- 输入：`.xlsx`，sheet 为 `Test Cases`
- 必备列：`Test Case Type`、`Test Case Name`、`Test Case Logic`、`Preconditions`、`Precondition signals`、`Precondition values`、`Actions`、`Action signals`、`Action values`、`Expectations`、`Expectation signals`、`Expectation values`
- 抽取工具：复用 `excel文件处理/Visualize/extractor.py` 中的 `build_lock_output_lines`
- 输出：统一 `TripleRecord[]`

