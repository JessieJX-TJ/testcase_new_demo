DESCRIPTION_PROMPT = """你是一名资深整车电子电器系统需求工程师，熟悉外灯、车身控制、电动尾门等功能规范。\n\n请分析这张技术规范中的表格图片，并输出结构化理解结果。你的目标不是复述表格，而是帮助后续测试规则抽取。\n\n请重点识别以下内容：\n1. 这张表的工程主题是什么\n2. 表格属于哪一种类型：logic_table、signal_table、state_table、fault_table、parameter_table、structure_table、other\n3. 表格整体结构\n4. 行和列分别代表什么语义\n5. 识别关键工程对象：功能名、控制器/模块名、输入信号、输出信号、系统状态、模式名、故障状态、阈值/定时\n6. 用一句工程化的话总结这张表可用于什么测试验证\n\n要求：\n- 保留英文术语原拼写\n- 不要臆造表中没有出现的信号名\n- 若存在不确定内容，明确写入 uncertain_points\n- 严格输出 JSON，不要输出 Markdown\n\n输出格式：\n{\n  \"table_type\": \"\",\n  \"topic\": \"\",\n  \"row_semantics\": \"\",\n  \"column_semantics\": \"\",\n  \"has_merged_cells\": true,\n  \"header_levels\": 0,\n  \"core_entities\": [],\n  \"core_conditions\": [],\n  \"core_outputs\": [],\n  \"core_faults\": [],\n  \"core_timing_constraints\": [],\n  \"engineering_interpretation\": \"\",\n  \"uncertain_points\": []\n}\n"""


def build_triple_prompt(
    ocr_whitelist: list[str],
    table_description_json: str,
    allowed_relations: list[str],
    table_type: str,
) -> str:
    whitelist_str = "\n".join(f"- {term}" for term in ocr_whitelist) if ocr_whitelist else "- 无"
    relation_str = "、".join(allowed_relations)
    if table_type == "structure_table":
        table_type_guidance = """补充要求（structure_table）：
- 这类图片通常表达模块连接、输入输出方向、控制对象、包含关系
- 只能抽取图中明确可见的结构关系，不要把连线臆造为触发条件、状态变化、信号有效、开关 ON/OFF、时序约束
- 如果图中只有箭头和模块名，则优先抽取“输入来自”“输出到”“连接到”“控制对象”“包含子功能”
- 如果某个状态词、条件词、阈值词没有在图中明确出现，不得补全
"""
    else:
        table_type_guidance = """补充要求（非 structure_table）：
- 可以抽取逻辑条件、状态依赖、故障响应、时序约束等规则
- 但仍然不能臆造图片中未明确出现的条件或结论
"""
    return f"""你是一名车辆电子功能测试工程师，擅长从技术规范表格中提取可验证的系统规则。\n\n你的任务是：从当前表格中抽取适合构建测试知识图谱的候选三元组。\n\n一、抽取目标\n请优先抽取以下类型的工程规则：\n1. 功能触发条件\n2. 功能抑制条件\n3. 输入与输出映射关系\n4. 模式或状态依赖关系\n5. 优先级与互斥关系\n6. 故障响应与降级关系\n7. 时序、保持、复位相关约束\n\n二、三元组定义\n- head：结果、行为、状态或功能命题，必须写成可测试的完整语义命题\n- relation：必须从限定集合中选择\n- tail：触发条件、约束条件、依赖对象、输入、故障、模式或上下文，也必须写成完整语义命题\n\n三、关系集合\n只能从以下关系中选择：{relation_str}\n\n四、抽取原则\n1. 只抽取对功能验证有价值的规则\n2. 不要输出版面信息类三元组\n3. head 和 tail 必须是工程上能理解、能验证的命题\n4. 专业术语、模块名、信号名、状态名必须优先使用 OCR 白名单中的原始术语\n5. 如果表格是逻辑判定表，应优先输出 IF-THEN 风格规则\n6. 如果表格是信号表，应优先输出 输入、输出、依赖 关系\n7. 如果表格是故障表，应优先输出 故障响应、功能抑制、降级 关系\n8. 不要臆造表中未出现的功能、信号或条件\n9. 如果信息不完整，不要补全推测\n\n五、当前表类型\n{table_type}\n\n六、表类型专项约束\n{table_type_guidance}\n\n七、OCR术语白名单\n{whitelist_str}\n\n八、表格结构理解\n{table_description_json}\n\n九、输出要求\n严格输出 JSON 数组，不要解释：\n[\n  {{\n    \"head\": \"\",\n    \"relation\": \"\",\n    \"tail\": \"\",\n    \"triple_type\": \"\",\n    \"evidence_terms\": [],\n    \"confidence_note\": \"high|medium|low\"\n  }}\n]\n"""


def build_fusion_prompt(triples_json: str) -> str:
    return f"""你是一名车辆系统需求分析工程师，正在整理从多张技术规范表格中抽取得到的候选知识图谱三元组。\n\n请对这些三元组进行融合，目标是：\n1. 去除重复\n2. 合并语义等价表达\n3. 统一专业术语写法\n4. 标记潜在冲突\n5. 保留来源信息\n\n处理规则如下：\n一、实体规范化\n- 统一模块名、信号名、模式名、功能名的写法\n- 优先采用技术文档中更正式、更标准的英文拼写\n- 不要改变原有工程含义\n\n二、重复合并\n- 完全相同的三元组合并为一条\n- 语义相同但措辞略有不同的三元组合并为一条\n- 合并后 sources 去重合并\n\n三、宽泛与特例\n- 如果一条规则是另一条规则的泛化描述，而另一条更具体，优先保留更具体的规则\n- 若两者并不矛盾，可同时保留\n\n四、冲突标记\n- 如果同一功能或结果在相同语义范围下对应互相矛盾的条件或结论，请标记 conflict=true 并给出 conflict_note\n- 除非明显错误，否则不要直接删除冲突项\n\n五、输出要求\n- 严格输出 JSON 数组\n- 每条结果保留字段：head, relation, tail, sources, conflict, conflict_note\n\n输入三元组如下：\n{triples_json}\n"""
