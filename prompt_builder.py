def format_context(triples):
    context = "Related feature information from the knowledge graph:\n"
    for t in triples:
        context += f"- {t['head']} {t['relation']} {t['tail']}\n"
    return context

def format_similar_cases(similar_cases):
    """
    Format similar test cases for prompt reference.
    Emphasizes that these cases are the primary basis for generating new ones.
    """
    if not similar_cases:
        return ""
    
    cases_text = "\n\n=== 📚 Retrieved similar test cases (generation reference) ===\n"
    cases_text += "The following cases are the most similar from the test case library. Study their structure, format, and content:\n"
    
    for i, case in enumerate(similar_cases, 1):
        cases_text += f"\n【Reference case {i}】{case.get('caseName', 'Unnamed case')}\n"
        cases_text += f"Similarity score: {case.get('similarity_score', 0):.3f}\n"
        
        if 'logic' in case:
            cases_text += f"✓ Test logic: {case['logic']}\n"
        if 'user_input' in case:
            cases_text += f"✓ Original requirement: {case['user_input']}\n"
        
        if i < len(similar_cases):
            cases_text += "-" * 60 + "\n"
    
    cases_text += "\n💡 Important: Use the structure and format of the cases above when generating new test cases.\n"
    
    return cases_text

def build_testcase_prompt(user_input, context, similar_cases=None, testcase_count=1):
    print(context)
    
    similar_cases_text = format_similar_cases(similar_cases) if similar_cases else ""
    
    evidence_notice = """
Evidence usage requirements:
1. Neo4j test-case knowledge graph evidence is mainly for learning PAE structure, step wording, and expected-behavior organization from existing cases.
2. PDF specification knowledge graph evidence acts as generation constraints to align signal names, state values, preconditions, action triggers, and expected results.
3. If evidence is insufficient, produce conservative, executable, verifiable test cases; do not invent proprietary signals not supported by the user requirement or evidence.
"""

    has_similar_cases = similar_cases and len(similar_cases) > 0
    
    count_text = "one" if testcase_count == 1 else f"{testcase_count}"
    if testcase_count == 1:
        multiple_notice = "\n\n⚠️ Important: Generate exactly 1 complete test case as specified."
    else:
        multiple_notice = f"\n\n⚠️ Important: Generate exactly {testcase_count} distinct test cases, separated by \"---\". Each case should have a different focus or scenario. You must produce {testcase_count} cases—no more, no less."
    
    if has_similar_cases:
        prompt = f"""
You are a professional vehicle test engineer. Your task is to generate {count_text} new test case(s) that meet the user requirement, **based on the retrieved similar test cases**.

⭐ Core requirement: Study the similar cases below carefully; they are the primary basis for new test cases.
{similar_cases_text}

	=== 🔍 Supplementary reference and constraints: knowledge graph ===
	{context}
	{evidence_notice}

	=== 💬 New user requirement ===
	\"{user_input}\"

=== 📝 Generation guide ===
Generate test cases in the following standard format:

测试项：[测试项名称]
前提条件：
1. [前提条件1]
2. [前提条件2]
...
执行动作：
[具体的执行动作]

预期行为：
[具体的预期行为]


⚠️ Format requirements (strict):
1. **前提条件**: At least one precondition, using a numbered list
2. **执行动作**: Concrete operation steps
3. **预期行为**: Clear expected results
4. **All three sections required**: 前提条件, 执行动作, and 预期行为 must be present and non-empty
5. **Output test case body only**: Do not output analysis, chain-of-thought, explanations, or conversational phrases such as "OK, I will now..."

✅ Generation tips:
1. **Primary reference**: Analyze structure, logic, and wording of the similar cases above
2. **Consistent format**: Match the format of the reference cases
	3. **Accurate content**: Combine Neo4j case evidence and PDF specification evidence for correct steps and expectations
4. **Clear logic**: Preconditions must be explicit; steps must be executable; results must be verifiable
5. **Moderate innovation**: Adjust and refine based on the new requirement while following the references
6. **Self-check**: Verify the output includes 前提条件, 执行动作, and 预期行为
{multiple_notice}

Now generate {count_text} new test case(s) strictly as specified:
"""
    else:
        prompt = f"""
You are a professional vehicle test engineer. Generate {count_text} standardized test case(s) from the user requirement and knowledge graph.

	=== 🔍 Knowledge graph and generation constraints ===
	{context}
	{evidence_notice}

=== 💬 User requirement ===
\"{user_input}\"

=== 📝 Generation guide ===
Generate test cases in the following standard format:

测试项：[测试项名称]
前提条件：
1. [前提条件1]
2. [前提条件2]
...
执行动作：
[具体的执行动作]

预期行为：
[具体的预期行为]


⚠️ Format requirements (strict):
1. **前提条件**: At least one precondition, using a numbered list
2. **执行动作**: Describe the operation in one complete sentence
3. **预期行为**: Describe the expected result in one complete sentence
4. **All three sections required**: 前提条件, 执行动作, and 预期行为 must be present and non-empty
5. **Output test case body only**: Do not output analysis, chain-of-thought, explanations, or conversational phrases such as "OK, I will now..."

✅ Generation tips:
1. Preconditions should be clear; include at least one
2. 执行动作 should be detailed and executable in one sentence
3. 预期行为 should be verifiable in one sentence
4. Ensure the case includes 前提条件, 执行动作, and 预期行为
{multiple_notice}

Now generate {count_text} test case(s) strictly as specified:
"""
    
    return prompt
