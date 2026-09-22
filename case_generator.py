#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test case generator module.
Groups cases by execution action and uses an LLM to generate reverse test cases.
"""

import json
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from llm_client import generate_testcase
import threading
import time


class CaseClassifier:
    """Test case classifier."""
    
    def __init__(self, json_file: str):
        self.json_file = json_file
        self.test_cases = []
        
    def load_cases(self) -> List[Dict]:
        """Load test cases from JSON."""
        print(f"Loading test cases: {self.json_file}")
        with open(self.json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            raw_cases = data.get('test_cases', [])
            
            # Assign a unique row number as the stable ID for each case
            self.test_cases = []
            for idx, case in enumerate(raw_cases):
                case['row_number'] = idx
                # Unique ID: prefer 编号; if duplicate, use 编号_row index
                original_id = case.get('original_data', {}).get('编号', '')
                if original_id and original_id != 'nan':
                    case['unique_id'] = f"{original_id}_{idx}"
                else:
                    case['unique_id'] = f"ROW_{idx}"
                self.test_cases.append(case)
                
        print(f"Loaded {len(self.test_cases)} test case(s)")
        return self.test_cases
    
    def classify_by_action(self) -> Dict[str, List[Dict]]:
        """Group cases by execution action (legacy API for compatibility)."""
        action_groups = {}
        
        for case in self.test_cases:
            original_data = case.get('original_data', {})
            action = original_data.get('执行动作', '未分类')
            
            # Normalize action text
            action = action.strip()
            if not action:
                action = '未分类'
            
            if action not in action_groups:
                action_groups[action] = []
            
            # Extract key fields; use unique_id as the stable identifier
            case_info = {
                'unique_id': case.get('unique_id', f"ROW_{case.get('row_number', 0)}"),  # unique ID
                '编号': original_data.get('编号', ''),  # original ID (may duplicate)
                '测试用例名称': original_data.get('测试用例名称', ''),
                '测试用例类型': original_data.get('测试用例类型', ''),
                '前提条件': case.get('前提条件_分割', []),
                '执行动作': action,
                '预期行为': original_data.get('预期行为', ''),
                'row_number': case.get('row_number', 0),
                '是否单一预期': self._is_single_expected(original_data.get('预期行为', ''))
            }
            
            action_groups[action].append(case_info)
        
        # Sort groups by case count
        sorted_groups = dict(sorted(
            action_groups.items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        ))
        
        return sorted_groups
    
    def classify_by_type_and_action(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Two-level grouping by test case type and execution action."""
        type_action_groups = {}
        
        for case in self.test_cases:
            original_data = case.get('original_data', {})
            case_type = original_data.get('测试用例类型', '未分类')
            action = original_data.get('执行动作', '未分类')
            
            # Normalize text
            case_type = case_type.strip() if case_type else '未分类'
            action = action.strip() if action else '未分类'
            
            if not case_type:
                case_type = '未分类'
            if not action:
                action = '未分类'
            
            # Initialize type bucket
            if case_type not in type_action_groups:
                type_action_groups[case_type] = {}
            
            # Initialize action bucket
            if action not in type_action_groups[case_type]:
                type_action_groups[case_type][action] = []
            
            # Extract key fields; use unique_id as the stable identifier
            case_info = {
                'unique_id': case.get('unique_id', f"ROW_{case.get('row_number', 0)}"),  # unique ID
                '编号': original_data.get('编号', ''),  # original ID (may duplicate)
                '测试用例名称': original_data.get('测试用例名称', ''),
                '测试用例类型': case_type,
                '前提条件': case.get('前提条件_分割', []),
                '执行动作': action,
                '预期行为': original_data.get('预期行为', ''),
                'row_number': case.get('row_number', 0),
                '是否单一预期': self._is_single_expected(original_data.get('预期行为', ''))
            }
            
            type_action_groups[case_type][action].append(case_info)
        
        # Sort by case count (type first, then action within type)
        sorted_groups = {}
        for case_type in sorted(type_action_groups.keys()):
            total_cases = sum(len(cases) for cases in type_action_groups[case_type].values())
            
            sorted_actions = dict(sorted(
                type_action_groups[case_type].items(),
                key=lambda x: len(x[1]),
                reverse=True
            ))
            
            sorted_groups[case_type] = {
                'actions': sorted_actions,
                'total_count': total_cases
            }
        
        sorted_groups = dict(sorted(
            sorted_groups.items(),
            key=lambda x: x[1]['total_count'],
            reverse=True
        ))
        
        return sorted_groups
    
    def _is_single_expected(self, expected: str) -> bool:
        """Return True if expected behavior is a single outcome (not a numbered list).

        Rules:
        - Contains numbered sub-items (e.g. 1. 2. 3. or 1) 2) 3)) → multiple outcomes (False)
        - No numbered sub-items → single outcome (True)
        """
        if not expected or expected.strip() == "":
            return False  # empty is not treated as single expected
        
        expected = expected.strip()
        
        # Only numbered sub-items indicate multiple expected outcomes
        import re
        # Match list numbering but avoid decimals (e.g. 11.5)
        numbered_patterns = [
            r'\d+\.\s',      # 1. 2. 3. (space required after dot)
            r'^\d+\.',       # line-start 1. 2. 3.
            r'\n\d+\.',      # after newline 1. 2. 3.
            r'\d+\)',        # 1) 2) 3)
            r'\d+、',        # 1、2、3、
            r'[①②③④⑤⑥⑦⑧⑨⑩]',  # circled digits
            r'[⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽]',  # parenthesized digits
        ]
        
        for pattern in numbered_patterns:
            if re.search(pattern, expected):
                return False  # numbered list → multiple outcomes
        
        return True


class ReverseTestCaseGenerator:
    """Reverse test case generator (LLM-backed)."""
    
    def __init__(self, model_name: str = "qwen2.5-3b-finetune-data-continued"):
        self.model_name = model_name
        self.generation_tasks = {}  # active generation tasks
    
    def _is_single_expected(self, expected: str) -> bool:
        """Return True if expected behavior is a single outcome (not a numbered list).

        Rules:
        - Contains numbered sub-items (e.g. 1. 2. 3. or 1) 2) 3)) → multiple outcomes (False)
        - No numbered sub-items → single outcome (True)
        """
        if not expected or expected.strip() == "":
            return False  # empty is not treated as single expected
        
        expected = expected.strip()
        
        import re
        numbered_patterns = [
            r'\d+\.\s',
            r'^\d+\.',
            r'\n\d+\.',
            r'\d+\)',
            r'\d+、',
            r'[①②③④⑤⑥⑦⑧⑨⑩]',
            r'[⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽]',
        ]
        
        for pattern in numbered_patterns:
            if re.search(pattern, expected):
                return False
        
        return True
        
    def create_task(self, case_ids: List[str], test_cases: List[Dict], generation_mode: str = 'single') -> str:
        """Create an async generation task.

        Args:
            case_ids: Selected case unique_id values
            test_cases: Full case list
            generation_mode:
                - 'single': one reverse case per selected case
                - 'batch': synthesize multiple reverse/variant cases from selected cases
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        print(f"\n📦 Creating task: {task_id}")
        print(f"🎯 Generation mode: {generation_mode}")
        print(f"📋 Case IDs to process: {len(case_ids)}")
        print(f"📊 Total cases available: {len(test_cases)}")
        
        cases_to_process = [case for case in test_cases if case.get('unique_id') in case_ids]
        
        print(f"✅ Cases after filter: {len(cases_to_process)}")
        if cases_to_process:
            print(f"📝 First case: {cases_to_process[0].get('unique_id', 'Unknown')} - {cases_to_process[0].get('测试用例名称', 'Unknown')}")
            if len(cases_to_process) > 1:
                print(f"📝 Case list:")
                for idx, case in enumerate(cases_to_process[:5], 1):
                    print(f"   {idx}. {case.get('unique_id')} - {case.get('测试用例名称')}")
                if len(cases_to_process) > 5:
                    print(f"   ... and {len(cases_to_process) - 5} more case(s)")
        
        if generation_mode == 'batch':
            estimated_total = len(cases_to_process) * 2  # rough estimate 1–3 per input case
        else:
            estimated_total = len(cases_to_process)
        
        self.generation_tasks[task_id] = {
            'status': 'pending',
            'mode': generation_mode,
            'input_count': len(cases_to_process),
            'total': estimated_total,
            'completed': 0,
            'failed': 0,
            'results': [],
            'failed_cases': [],
            'cases_snapshot': cases_to_process,
            'start_time': datetime.now().isoformat()
        }
        
        thread = threading.Thread(
            target=self._process_cases_batch,
            args=(task_id, cases_to_process)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _process_cases_batch(self, task_id: str, cases: List[Dict]):
        """Background worker for batch generation.

        Batch mode:
        - Group selected cases by 执行动作
        - Synthesize new test cases per group
        - Useful for exploring scenarios under the same action
        """
        task = self.generation_tasks[task_id]
        task['status'] = 'processing'
        
        try:
            print(f"\n🔄 Batch synthesis mode")
            print(f"📊 Input cases: {len(cases)}")
            
            action_groups = {}
            for case in cases:
                action = case.get('执行动作', '未分类')
                if action not in action_groups:
                    action_groups[action] = []
                action_groups[action].append(case)
            
            print(f"📋 Action groups: {len(action_groups)}")
            print(f"💡 Each group targets 3–5 new cases; estimated total {len(action_groups) * 3}–{len(action_groups) * 5}")
            
            for action, group_cases in action_groups.items():
                print(f"\n🎯 Processing action: {action}")
                print(f"📝 Selected cases in group: {len(group_cases)}")
                print(f"📋 Case names: {[c.get('测试用例名称', 'Unknown') for c in group_cases]}")
                
                generated_cases = self._generate_batch_cases(group_cases, action)
                
                if generated_cases:
                    task['results'].extend(generated_cases)
                    task['completed'] += len(generated_cases)
                    print(f"✅ Generated {len(generated_cases)} case(s)")
                else:
                    task['failed'] += 1
                    task['failed_cases'].append({
                        '执行动作': action,
                        '原因': 'LLM returned empty result'
                    })
                
                task['percentage'] = round(task['completed'] / task['total'] * 100, 1)
            
            task['total'] = task['completed'] + task['failed']
            task['percentage'] = 100
            
        except Exception as e:
            print(f"❌ Batch generation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            task['failed'] += 1
        
        task['status'] = 'completed'
        task['end_time'] = datetime.now().isoformat()
        print(f"\n✅ Batch generation finished; {task['completed']} case(s) created")
    
    def _generate_batch_cases(self, cases: List[Dict], action: str) -> List[Dict]:
        """Synthesize reverse/variant cases from a group.

        Strategy:
        - Single expected: LLM reverse cases
        - Multiple expected: programmatic combinations (no LLM)
        """
        
        print(f"\n🧠 Starting synthesis...")
        
        single_expected_cases = []
        multiple_expected_cases = []
        
        for case in cases:
            is_single = self._is_single_expected(case.get('预期行为', ''))
            if is_single:
                single_expected_cases.append(case)
            else:
                multiple_expected_cases.append(case)
        
        print(f"📊 Single-expected cases: {len(single_expected_cases)}")
        print(f"📊 Multi-expected cases: {len(multiple_expected_cases)}")
        
        all_generated_cases = []
        
        if single_expected_cases:
            print(f"\n🤖 LLM reverse generation for {len(single_expected_cases)} single-expected case(s)...")
            llm_cases = self._generate_single_cases_with_llm(single_expected_cases, action)
            all_generated_cases.extend(llm_cases)
            print(f"✅ LLM produced {len(llm_cases)} case(s)")
        
        if multiple_expected_cases:
            print(f"\n🔢 Combination generation for {len(multiple_expected_cases)} multi-expected case(s)...")
            combo_cases = self._generate_multiple_cases_combinations(multiple_expected_cases, action)
            all_generated_cases.extend(combo_cases)
            print(f"✅ Combinations produced {len(combo_cases)} case(s)")
        
        return all_generated_cases
    
    def _generate_single_cases_with_llm(self, cases: List[Dict], action: str) -> List[Dict]:
        """Use LLM to generate reverse cases for single-expected inputs."""
        
        prompt = self._build_batch_prompt(cases, action)
        
        try:
            response = generate_testcase(
                prompt=prompt,
                model=self.model_name
            )
            
            if isinstance(response, tuple):
                print(f"⚠️  Response is a tuple; using first element (text)")
                response = response[0]
            elif not isinstance(response, str):
                print(f"⚠️  Warning: response is not str, got {type(response)}")
                response = str(response)
            
            print(f"✅ LLM response length: {len(response)} chars")
            print(f"📄 First 300 chars: {response[:300]}")
            
            result = self._parse_batch_response(response)
            
            if result and 'generated_cases' in result:
                generated_cases = []
                
                print(f"\n✅ Parsed {len(result['generated_cases'])} generated case(s)")
                
                for idx, gen_case in enumerate(result['generated_cases']):
                    print(f"\n📝 Raw generated case {idx+1}:")
                    print(f"   keys: {list(gen_case.keys())}")
                    
                    case_name = gen_case.get('案例名称') or gen_case.get('case_name', '')
                    preconditions = gen_case.get('前提条件') or gen_case.get('preconditions', [])
                    expected = gen_case.get('预期行为') or gen_case.get('expected_behavior', '')
                    related = gen_case.get('关联原始案例') or gen_case.get('related_original_cases', [])
                    
                    print(f"   case name: {case_name}")
                    print(f"   precondition count: {len(preconditions)}")
                    print(f"   expected behavior: {expected[:50] if expected else '(empty)'}")
                    print(f"   related source cases: {related}")
                    
                    case_info = {
                        '案例编号': f"GEN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx+1}",
                        '案例名称': case_name,
                        '测试用例类型': cases[0].get('测试用例类型', ''),
                        '前提条件': preconditions,
                        '执行动作': action,
                        '预期行为': expected,
                        '关联原始案例': related,
                        '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        '使用模型': self.model_name
                    }
                    
                    print(f"   ✅ Built case name: {case_info['案例名称']}")
                    print(f"   ✅ Built precondition count: {len(case_info['前提条件'])}")
                    
                    generated_cases.append(case_info)
                
                print(f"\n✅ Successfully built {len(generated_cases)} case(s)")
                return generated_cases
            else:
                print(f"❌ Parse result empty or invalid format")
                return []
                
        except Exception as e:
            print(f"❌ LLM generation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _generate_multiple_cases_combinations(self, cases: List[Dict], action: str) -> List[Dict]:
        """Generate combinations for multi-expected cases (three-phase pipeline).

        Phase 1: enumerate all combinations programmatically
        Phase 2: LLM filters invalid combinations
        Phase 3: build concrete cases for valid combinations
        """
        from itertools import combinations
        
        all_generated = []
        
        for case in cases:
            case_name = case.get('测试用例名称', 'Unnamed case')
            preconditions = case.get('前提条件', [])
            action_text = case.get('执行动作', '')
            expected_behavior = case.get('预期行为', '')
            
            print(f"\n📝 Multi-expected case: {case_name}")
            
            action_items = self._parse_multiple_expected_items(action_text)
            expected_items = self._parse_multiple_expected_items(expected_behavior)
            
            if not action_items:
                print(f"⚠️  No numbered list in execution action; using full action text")
                action_items = [action_text]
            
            if not expected_items or len(expected_items) <= 1:
                print(f"⚠️  Expected behavior has ≤1 item or could not parse; skipping")
                continue
            
            n_items = min(len(action_items), len(expected_items))
            if len(action_items) != len(expected_items):
                print(f"⚠️  Execution action ({len(action_items)} items) vs expected behavior ({len(expected_items)} items); using min={n_items}")
            
            print(f"📊 Parsed {n_items} action–expected pair(s)")
            for i in range(n_items):
                print(f"   {i+1}. action: {action_items[i][:30]}... | expected: {expected_items[i][:30]}...")
            
            print(f"\n🔢 Phase 1: enumerate all combinations...")
            all_possible_combinations = []
            
            for k in range(1, n_items):
                for combo in combinations(range(n_items), k):
                    all_possible_combinations.append(combo)
            
            print(f"📊 {len(all_possible_combinations)} possible combination(s)")
            
            print(f"\n🤖 Phase 2: LLM filter invalid combinations...")
            valid_combinations = self._filter_combinations_with_llm(
                case=case,
                action_items=action_items,
                expected_items=expected_items,
                all_combinations=all_possible_combinations
            )
            
            if not valid_combinations:
                print(f"⚠️  No valid combinations after LLM filter; fallback to prefix-only sequences")
                valid_combinations = [tuple(range(0, k)) for k in range(1, n_items)]
            
            print(f"✅ {len(valid_combinations)} valid combination(s) after filter")
            
            print(f"\n🔍 Phase 2.5: deduplicate valid combinations...")
            valid_combinations = self._deduplicate_combinations_with_llm(
                valid_combinations=valid_combinations,
                action_items=action_items,
                expected_items=expected_items
            )
            print(f"✅ {len(valid_combinations)} unique combination(s) after dedup")
            
            print(f"\n🎨 Phase 3: build concrete test cases...")
            generated_count = 0
            for combo in valid_combinations:
                selected_actions = [action_items[i] for i in combo]
                selected_expected = [expected_items[i] for i in combo]
                
                combo_case = self._build_combination_case(
                    original_case=case,
                    selected_actions=selected_actions,
                    selected_expected=selected_expected,
                    combo_indices=combo,
                    total_items=n_items
                )
                
                all_generated.append(combo_case)
                generated_count += 1
            
            print(f"✅ Generated {generated_count} combination case(s) for '{case_name}'")
        
        return all_generated
    
    def _filter_combinations_with_llm(self, case: Dict, action_items: List[str], 
                                     expected_items: List[str], all_combinations: List[tuple]) -> List[tuple]:
        """Use LLM to drop logically invalid action combinations.

        Args:
            case: Source case
            action_items: Parsed 执行动作 items
            expected_items: Parsed 预期行为 items
            all_combinations: All index tuples to evaluate

        Returns:
            Valid combination tuples
        """
        case_name = case.get('测试用例名称', 'Unnamed')
        preconditions = case.get('前提条件', [])
        
        combinations_text = ""
        for idx, combo in enumerate(all_combinations, 1):
            actions = [f"{i+1}. {action_items[i]}" for i in combo]
            combinations_text += f"\nCombo {idx}: items {','.join([str(i+1) for i in combo])}\n"
            combinations_text += "  执行动作:\n    " + "\n    ".join(actions) + "\n"
        
        preconditions_text = '\n    '.join([f"- {cond}" for cond in preconditions])
        
        prompt = f"""You are a test-case analysis expert. Review the execution-action combinations below and decide which are logically valid.

【Original test case】
案例名称: {case_name}
前提条件:
    {preconditions_text}

【Full 执行动作 list】
{self._format_action_list(action_items)}

【Full 预期行为 list】
{self._format_action_list(expected_items)}

【All candidate combinations】
{combinations_text}

【Task】
For each combination, judge logical validity. Consider:
1. **Dependencies**: Does a later action require the outcome of an earlier one?
   - Example: "Press exterior switch during closing" requires a prior action that started closing
   - Example: "Press again after hover" requires a prior action that produced hover state

2. **State prerequisites**: Does the action text assume a prior state?
   - Phrases like "during ...", "after ...", "again", "continue" usually imply prior steps

3. **Causal chain**: If some steps are skipped, do the remaining steps still form a coherent flow?

【Criteria】
- ✅ Valid: steps are coherent; no missing prerequisites
- ❌ Invalid: missing dependency or impossible assumed state

【Output format】
{{
  "valid_combinations": [
    {{"combo_index": 1, "is_valid": true, "reason": "brief rationale"}},
    {{"combo_index": 2, "is_valid": false, "reason": "why invalid"}}
  ],
  "summary": "overall analysis"
}}

【Example — domain actions remain in Chinese】
Original actions:
1. 按压尾门内开关
2. 在关闭过程中按下外开关
3. 车辆悬停后，再次按压尾门开关

Analysis:
- Combo [1]: ✅ Valid — basic inner-switch press only
- Combo [1,2]: ✅ Valid — interrupt during close; step 2 depends on "closing" from step 1
- Combo [2]: ❌ Invalid — step 2 needs "closing" state without step 1
- Combo [2,3]: ❌ Invalid — steps 2 and 3 depend on step 1
- Combo [1,3]: ❌ Invalid — step 3 needs hover state missing from skipped step 2

Output JSON only; no extra prose."""
        
        try:
            response = generate_testcase(
                prompt=prompt,
                model=self.model_name
            )
            
            if isinstance(response, tuple):
                response = response[0]
            elif not isinstance(response, str):
                response = str(response)
            
            print(f"📄 LLM response length: {len(response)} chars")
            
            result = self._parse_batch_response(response)
            
            if result and 'valid_combinations' in result:
                valid_combos = []
                
                for item in result['valid_combinations']:
                    combo_idx = item.get('combo_index', 0) - 1
                    is_valid = item.get('is_valid', False)
                    reason = item.get('reason', '')
                    
                    if is_valid and 0 <= combo_idx < len(all_combinations):
                        valid_combos.append(all_combinations[combo_idx])
                        print(f"  ✅ Combo {combo_idx+1} valid: {reason}")
                    else:
                        print(f"  ❌ Combo {combo_idx+1} invalid: {reason}")
                
                summary = result.get('summary', '')
                if summary:
                    print(f"\n💡 Summary: {summary}")
                
                return valid_combos
            else:
                print("❌ LLM response format invalid; could not parse")
                return []
                
        except Exception as e:
            print(f"❌ LLM filter failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _deduplicate_combinations_with_llm(self, valid_combinations: List[tuple],
                                           action_items: List[str],
                                           expected_items: List[str]) -> List[tuple]:
        """Deduplicate valid action/expected combinations deterministically.

        The caller previously expected an LLM-backed method here. Keeping the
        method local avoids a runtime AttributeError and gives a stable default:
        combinations with the same selected actions and expected behaviors are
        considered duplicates.
        """
        unique = []
        seen = set()

        for combo in valid_combinations or []:
            action_key = tuple(action_items[i].strip() for i in combo if i < len(action_items))
            expected_key = tuple(expected_items[i].strip() for i in combo if i < len(expected_items))
            key = (action_key, expected_key)
            if key in seen:
                continue
            seen.add(key)
            unique.append(combo)

        return unique

    def _format_action_list(self, items: List[str]) -> str:
        """Format a numbered list for prompts."""
        return '\n'.join([f"{i+1}. {item}" for i, item in enumerate(items)])
    
    def _parse_multiple_expected_items(self, expected_behavior: str) -> List[str]:
        """Split multi-item 预期行为 / 执行动作 text into numbered segments.

        Supported formats:
        - 1. xxx 2. xxx 3. xxx
        - 1) xxx 2) xxx 3) xxx
        - ① xxx ② xxx ③ xxx
        """
        import re
        
        patterns = [
            r'(?:^|\n)\s*(?:\d+[.、)]|[①②③④⑤⑥⑦⑧⑨⑩])\s*([^\n]+)',
        ]
        
        for pattern in patterns:
            items = re.findall(pattern, expected_behavior, re.MULTILINE)
            if items:
                return [item.strip() for item in items]
        
        return []
    
    def _build_combination_case(self, original_case: Dict, selected_actions: List[str], 
                                selected_expected: List[str], combo_indices: tuple, total_items: int) -> Dict:
        """Build one combination-derived case.

        Args:
            original_case: Source case
            selected_actions: Chosen 执行动作 items
            selected_expected: Chosen 预期行为 items
            combo_indices: Selected indices (for naming)
            total_items: Original item count
        """
        indices_str = '+'.join([str(i+1) for i in combo_indices])
        k = len(selected_actions)
        original_name = original_case.get('测试用例名称', 'Unnamed')
        
        case_name = f"{original_name}-combo{k}items(items {indices_str})"
        
        if len(selected_actions) == 1:
            action_text = selected_actions[0]
            expected_text = selected_expected[0]
        else:
            action_text = '\n'.join([f"{i+1}. {item}" for i, item in enumerate(selected_actions)])
            expected_text = '\n'.join([f"{i+1}. {item}" for i, item in enumerate(selected_expected)])
        
        combo_case = {
            '案例编号': f"COMBO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(combo_indices)}of{total_items}",
            '案例名称': case_name,
            '测试用例类型': original_case.get('测试用例类型', ''),
            '前提条件': original_case.get('前提条件', []).copy(),
            '执行动作': action_text,
            '预期行为': expected_text,
            '关联原始案例': [original_case.get('测试用例名称', '')],
            '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '生成方式': f'combination({k}/{total_items})'
        }
        
        return combo_case
    
    def _build_batch_prompt(self, cases: List[Dict], action: str) -> str:
        """Build batch synthesis prompt for single-expected reverse case generation."""
        
        cases_text = ""
        case_names = []
        single_expected_cases = []
        
        for idx, case in enumerate(cases, 1):
            case_name = case.get('测试用例名称', f"Case {idx}")
            case_names.append(case_name)
            
            preconditions = '\n    '.join([f"- {cond}" for cond in case['前提条件']])
            expected_text = case['预期行为']
            
            cases_text += f"""
Case {idx}:
  Name: {case_name}
  前提条件:
    {preconditions}
  预期行为: {expected_text}

"""
            single_expected_cases.append({
                'index': idx,
                'name': case_name,
                'preconditions': case['前提条件'],
                'expected': case['预期行为']
            })
        
        case_names_str = "、".join([f'"{name}"' for name in case_names])
        
        reverse_guidance = ""
        if single_expected_cases:
            reverse_guidance = "\n【Reverse generation for single-expected positive cases】\n"
            for sc in single_expected_cases:
                reverse_guidance += f"\nFor case {sc['index']} ({sc['name']}):\n"
                reverse_guidance += "  Strategy: negate each precondition in turn to produce reverse test cases\n"
                for i, cond in enumerate(sc['preconditions'], 1):
                    reverse_guidance += f"    - Precondition {i}: {cond}\n"
                reverse_guidance += f"  预期行为: {sc['expected']}\n"
                reverse_guidance += "  → After negation: function does not run or fails as expected\n"
        
        prompt = f"""You are a vehicle test-case expert with deep knowledge of vehicle modules and behavior.

【Task】
Analyze the {len(cases)} test cases below that share the same 执行动作. From their 前提条件 and 预期行为, produce 3–5 new **reverse** test cases.

【Case types】
- **Positive**: all preconditions satisfied; feature behaves normally
- **Reverse**: at least one precondition fails; feature must not succeed as in the positive case

【Shared 执行动作】
{action}

【Source cases】
{cases_text}
{reverse_guidance}

【Generation rules】
1. **Reverse cases**:
   - Negate preconditions one at a time (or in meaningful combinations)
   - Negation examples: on→off, valid→invalid, normal→abnormal, connected→disconnected
   - Reverse 预期行为: feature does not execute or fails in an expected way

2. **Logic**:
   - Preconditions determine 预期行为
   - Same 前提条件 + same 执行动作 ⇒ same 预期行为
   - Different 预期行为 must come from different 前提条件
   - Do not emit cases with identical 前提条件 but conflicting 预期行为

3. **De-duplication**:
   - Avoid scenarios already covered by the source list
   - Prefer missing edge cases

4. **Quality**:
   - Clear 案例名称
   - Specific 前提条件
   - Verifiable 预期行为
   - Each new case should have a distinct precondition set

【Output — strict JSON】
{{
  "generated_cases": [
    {{
      "案例名称": "concise scenario name",
      "前提条件": ["precondition 1", "precondition 2"],
      "预期行为": "clear expected outcome",
      "关联原始案例": ["related source case name"]
    }}
  ]
}}

【Important】
1. **JSON only** — no other text
2. 关联原始案例 must use case **names** from: {case_names_str}
3. Produce 3–5 high-value non-duplicate reverse cases
4. 前提条件 must be a JSON array of strings
5. Skip duplicates of existing cases

【Bad example — same 前提条件, different 预期行为】
❌ Wrong:
Case A:
  前提条件: ["生理PON", "车载设备2加电打开"]
  执行动作: 订阅灯信息节点灯光
  预期行为: 灯光闪烁

Case B:
  前提条件: ["生理PON", "车载设备2加电打开"]  ← identical
  执行动作: 订阅灯信息节点灯光
  预期行为: 灯光恒亮  ← conflicting expected behavior

【Good example — different 前提条件 drives different 预期行为】
✅ Correct:
Case A:
  前提条件: ["生理PON", "车载设备2加电打开"]
  执行动作: 订阅灯信息节点灯光
  预期行为: 灯光闪烁

Case B (reverse):
  前提条件: ["生理POFF", "车载设备2加电打开"]  ← negated precondition
  执行动作: 订阅灯信息节点灯光
  预期行为: 灯光不亮

===== Begin generation =====
Output JSON only, from "{{" to "}}", with no surrounding text."""
        
        return prompt
    
    def _parse_batch_response(self, response: str) -> Optional[Dict]:
        """Parse LLM batch response and extract JSON robustly."""
        try:
            if not isinstance(response, str):
                print(f"⚠️  Bad response type: {type(response)}; coercing to str")
                response = str(response)
            
            print(f"📄 Total LLM response length: {len(response)} chars")
            
            print(f"\n🔍 Strategy 1: find JSON containing 'generated_cases'...")
            generated_cases_patterns = [
                r'"generated_cases"\s*:\s*\[',
                r"'generated_cases'\s*:\s*\[",
                r'生成案例\s*:\s*\[',
            ]
            
            for pattern in generated_cases_patterns:
                if re.search(pattern, response):
                    print(f"✅ Matched generated_cases pattern")
                    match = re.search(pattern, response)
                    if match:
                        start_pos = response.rfind('{', 0, match.start())
                        if start_pos != -1:
                            json_str = self._extract_json_from_position(response, start_pos)
                            if json_str:
                                try:
                                    result = json.loads(json_str)
                                    if 'generated_cases' in result:
                                        print(f"✅ Extracted JSON with generated_cases")
                                        print(f"📊 Case count: {len(result['generated_cases'])}")
                                        return result
                                except json.JSONDecodeError:
                                    print(f"⚠️  Pattern matched but JSON parse failed; trying next method")
                                    pass
            
            print(f"\n🔍 Strategy 2: scan JSON from end of response...")
            last_brace = response.rfind('{')
            if last_brace != -1:
                json_str = self._extract_json_from_position(response, last_brace)
                if json_str:
                    try:
                        result = json.loads(json_str)
                        if 'generated_cases' in result:
                            print(f"✅ Extracted JSON from tail")
                            print(f"📊 Case count: {len(result['generated_cases'])}")
                            return result
                        else:
                            print(f"⚠️  Parsed JSON lacks 'generated_cases' key")
                    except json.JSONDecodeError as e:
                        print(f"⚠️  Tail JSON parse failed: {str(e)[:100]}")
            
            print(f"\n🔍 Strategy 3: regex scan for JSON objects...")
            json_pattern = r'\{[^{}]*"(?:generated_cases|案例)[\s\S]*?\}'
            json_matches = list(re.finditer(json_pattern, response, re.IGNORECASE))
            
            if json_matches:
                print(f"✅ Found {len(json_matches)} candidate JSON object(s)")
                
                for json_match in reversed(json_matches):
                    json_str = json_match.group(0)
                    try:
                        result = json.loads(json_str)
                        if 'generated_cases' in result and isinstance(result['generated_cases'], list):
                            print(f"✅ Valid JSON extracted")
                            print(f"📊 Case count: {len(result['generated_cases'])}")
                            if len(result['generated_cases']) > 0:
                                first_case = result['generated_cases'][0]
                                print(f"📝 First case sample: {json.dumps(first_case, ensure_ascii=False)[:100]}")
                            return result
                    except json.JSONDecodeError:
                        continue
            
            print(f"\n🔍 Strategy 4: greedy brace match...")
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)
                print(f"⚠️  Greedy match (may be imperfect): {json_str[:100]}...")
                try:
                    result = json.loads(json_str)
                    print(f"✅ JSON parsed")
                    print(f"📋 Top-level keys: {list(result.keys())}")
                    return result
                except json.JSONDecodeError:
                    pass
            
            print(f"❌ All JSON extraction strategies failed")
            print(f"First 500 chars:\n{response[:500]}")
            print(f"Last 500 chars:\n{response[-500:]}")
            return None
            
        except Exception as e:
            print(f"❌ Parse error: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_json_from_position(self, text: str, start_pos: int) -> Optional[str]:
        """Extract a balanced JSON object starting at start_pos."""
        if start_pos < 0 or start_pos >= len(text) or text[start_pos] != '{':
            return None
        
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start_pos, len(text)):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"':
                in_string = not in_string
                continue
            
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return text[start_pos:i+1]
        
        return None
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Return task status dict."""
        return self.generation_tasks.get(task_id)
    
    def get_task_results(self, task_id: str) -> Optional[Dict]:
        """Return task results and statistics."""
        task = self.generation_tasks.get(task_id)
        if not task:
            return None
        
        return {
            'reverse_cases': task['results'],
            'statistics': {
                '成功数': task['completed'],
                '失败数': task['failed'],
                '总数': task['total'],
                '成功率': f"{round(task['completed'] / task['total'] * 100, 1)}%" if task['total'] > 0 else "0%"
            },
            'failed_cases': task['failed_cases']
        }


# Manual test entrypoint
if __name__ == "__main__":
    classifier = CaseClassifier('data/测试案例.json')
    classifier.load_cases()
    action_groups = classifier.classify_by_action()
    
    print(f"\nGrouped into {len(action_groups)} execution action(s)")
    print("\nTop 10 actions by case count:")
    for i, (action, cases) in enumerate(list(action_groups.items())[:10]):
        print(f"{i+1}. {action}: {len(cases)} case(s)")
