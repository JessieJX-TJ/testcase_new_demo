"""
Test-case formatting module.
Reconstruct complete test cases from knowledge-graph triples.
"""
from typing import List, Dict, Set, Tuple, Optional
from neo4j import GraphDatabase


class TestCaseFormatter:
    """Extract and format complete test cases from the knowledge graph"""
    
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def extract_testcases_from_subgraph(self, evidence_subgraph: Dict) -> List[Dict]:
        """
        Extract complete test cases from an evidence subgraph.
        
        Args:
            evidence_subgraph: Evidence subgraph containing nodes and edges
            
        Returns:
            List[Dict]: List of complete test cases
        """
        nodes = evidence_subgraph.get("nodes", set())
        edges = evidence_subgraph.get("edges", set())
        
        # Find all TestCase nodes
        testcase_nodes = self._find_testcase_nodes(nodes)
        
        if not testcase_nodes:
            print("⚠️  No TestCase nodes found in subgraph")
            return []
        
        print(f"📋 Found {len(testcase_nodes)} TestCase nodes")
        
        # Build a complete test case for each TestCase
        complete_testcases = []
        for testcase_name in testcase_nodes:
            testcase = self._build_complete_testcase(testcase_name, edges)
            if testcase:
                complete_testcases.append(testcase)
        
        print(f"✅ Successfully built {len(complete_testcases)} complete test cases")
        return complete_testcases
    
    def _find_testcase_nodes(self, nodes: Set[str]) -> List[str]:
        """Find TestCase-typed nodes from a node set"""
        testcase_nodes = []
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n:TestCase)
                WHERE n.name IN $nodes
                RETURN n.name AS name
            """, nodes=list(nodes))
            
            for record in result:
                testcase_nodes.append(record["name"])
        
        return testcase_nodes
    
    def _build_complete_testcase(self, testcase_name: str, edges: Set[Tuple]) -> Dict:
        """
        Build a complete test case starting from a TestCase node.
        
        Args:
            testcase_name: TestCase node name
            edges: All edges in the subgraph
            
        Returns:
            Dict: Complete test-case structure
        """
        # Extract information related to this TestCase from the edge set
        preconditions = []
        actions = []
        expected_behaviors = []
        test_type = None
        
        for head, relation, tail in edges:
            # Outgoing edges of TestCase
            if head == testcase_name:
                # Use Chinese relation types (Neo4j schema names — do not rename)
                if relation == "前提条件" or relation == "has_precondition":
                    preconditions.append(tail)
                elif relation == "执行动作" or relation == "has_action":
                    actions.append(tail)
                elif relation == "预期行为" or relation == "has_expected":
                    expected_behaviors.append(tail)
                elif relation == "测试用例类型" or relation == "belongs_to":
                    test_type = tail
            
            # Incoming edges of TestCase (if any)
            elif tail == testcase_name:
                # Incoming edges may also carry preconditions, etc.
                if relation == "前提条件" or relation == "has_precondition":
                    preconditions.append(head)
                elif relation == "执行动作" or relation == "has_action":
                    actions.append(head)
                elif relation == "预期行为" or relation == "has_expected":
                    expected_behaviors.append(head)
        
        # If no related info was found, query Neo4j directly
        if not (preconditions or actions or expected_behaviors):
            return self._query_testcase_from_neo4j(testcase_name)
        
        # Build test-case structure
        testcase = {
            "case_name": testcase_name,
            "test_type": test_type,
            "preconditions": preconditions,
            "actions": actions,
            "expected_behaviors": expected_behaviors
        }
        
        return testcase
    
    def _query_testcase_from_neo4j(self, testcase_name: str) -> Dict:
        """
        Query complete test-case information directly from Neo4j.
        
        Args:
            testcase_name: TestCase node name
            
        Returns:
            Dict: Complete test-case structure
        """
        with self.driver.session() as session:
            # Use Chinese relation types (Neo4j schema names — do not rename)
            result = session.run("""
                MATCH (tc:TestCase {name: $testcase_name})
                OPTIONAL MATCH (tc)-[:`前提条件`]->(pre)
                OPTIONAL MATCH (tc)-[:`执行动作`]->(act)
                OPTIONAL MATCH (tc)-[:`预期行为`]->(exp)
                OPTIONAL MATCH (tc)-[:`测试用例类型`]->(type)
                RETURN tc.name AS case_name,
                       labels(type)[0] AS test_type,
                       collect(DISTINCT pre.name) AS preconditions,
                       collect(DISTINCT act.name) AS actions,
                       collect(DISTINCT exp.name) AS expected_behaviors
            """, testcase_name=testcase_name)
            
            record = result.single()
            if not record:
                return {
                    "case_name": testcase_name,
                    "test_type": None,
                    "preconditions": [],
                    "actions": [],
                    "expected_behaviors": []
                }
            
            preconditions = [p for p in record["preconditions"] if p]
            actions = [a for a in record["actions"] if a]
            expected_behaviors = [e for e in record["expected_behaviors"] if e]
            
            return {
                "case_name": record["case_name"],
                "test_type": record["test_type"],
                "preconditions": preconditions,
                "actions": actions,
                "expected_behaviors": expected_behaviors
            }


def format_testcases_as_context(testcases: List[Dict]) -> str:
    """
    Format a list of test cases as context text.
    
    Args:
        testcases: List of test cases
        
    Returns:
        str: Formatted context text
    """
    if not testcases:
        return "No related test-case information was retrieved.\n"
    
    context = "Related test cases retrieved from the knowledge graph:\n\n"
    
    for i, testcase in enumerate(testcases, 1):
        context += f"[Test Case {i}] {testcase['case_name']}\n"
        
        if testcase.get('test_type'):
            context += f"Test type: {testcase['test_type']}\n"
        
        if testcase.get('preconditions'):
            context += f"Preconditions:\n"
            for pre in testcase['preconditions']:
                context += f"  - {pre}\n"
        
        if testcase.get('actions'):
            context += f"Actions:\n"
            for act in testcase['actions']:
                context += f"  - {act}\n"
        
        if testcase.get('expected_behaviors'):
            context += f"Expected behaviors:\n"
            for exp in testcase['expected_behaviors']:
                context += f"  - {exp}\n"
        
        context += "\n" + "-" * 60 + "\n\n"
    
    return context


def format_testcases_as_pae_chains(testcases: List[Dict]) -> str:
    """
    Format test cases as explicit PAE (Precondition-Action-Expectation) logic chains.
    
    Format: Precondition - Action - Expectation
    When there are multiple preconditions, wrap them in 【】 and separate with 、
    
    Args:
        testcases: List of test cases
        
    Returns:
        str: Formatted PAE logic-chain text
    """
    if not testcases:
        return "No related test-case information was retrieved.\n"
    
    context = "Related test cases retrieved from the knowledge graph (PAE logic-chain format):\n\n"
    
    for i, testcase in enumerate(testcases, 1):
        context += f"[Test Case {i}] {testcase['case_name']}\n"
        
        if testcase.get('test_type'):
            context += f"Test type: {testcase['test_type']}\n\n"
        
        # Build PAE logic chain
        context += "Logic chain:\n"
        
        # Preconditions
        preconditions = testcase.get('preconditions', [])
        if preconditions:
            if len(preconditions) == 1:
                context += f"  Precondition: {preconditions[0]}\n"
            else:
                # Multiple preconditions wrapped in 【】 and separated by 、
                precond_str = "、".join(preconditions)
                context += f"  Precondition: 【{precond_str}】\n"
        else:
            context += f"  Precondition: none\n"
        
        # Actions
        actions = testcase.get('actions', [])
        if actions:
            context += f"  ↓\n"
            for j, act in enumerate(actions, 1):
                context += f"  Action {j}: {act}\n"
        else:
            context += f"  ↓\n"
            context += f"  Action: none\n"
        
        # Expectations
        expected_behaviors = testcase.get('expected_behaviors', [])
        if expected_behaviors:
            context += f"  ↓\n"
            for k, exp in enumerate(expected_behaviors, 1):
                context += f"  Expectation {k}: {exp}\n"
        else:
            context += f"  ↓\n"
            context += f"  Expectation: none\n"
        
        context += "\n" + "-" * 60 + "\n\n"
    
    return context
