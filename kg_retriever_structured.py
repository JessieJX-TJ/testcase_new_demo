"""
Knowledge graph retriever based on structured extraction

Retrieval pipeline:
1. Use Qwen3-8B to extract structured fields from the user query (preconditions, actions, expected behavior)
2. Search the corresponding typed vector indexes
3. Search TestCase with the original query text
4. Same downstream flow as MST retriever (shortest paths, MST, path expansion, neighbor expansion)
"""

import json
import numpy as np
import faiss
from neo4j import GraphDatabase
import os
from typing import List, Dict, Set, Tuple, Optional
from llm_client import generate_testcase
from kg_retriever_mst import UnionFind, KnowledgeGraphRetrieverMST


class KnowledgeGraphRetrieverStructured(KnowledgeGraphRetrieverMST):
    """Structured-extraction knowledge graph retriever (extends MST retriever)."""
    
    def __init__(self, uri, user, password, index_dir="cache/vector_index"):
        """Initialize retriever."""
        super().__init__(uri, user, password, index_dir)
        self._structured_extract_cache = {}
        print(f"✅ Structured retriever initialized")
    
    def extract_structured_info(self, query_text: str) -> Dict[str, List[str]]:
        """
        Extract structured information from the query using Qwen3-8B.

        Args:
            query_text: User query text

        Returns:
            Dict: {
                "preconditions": ["...", ...],
                "actions": ["...", ...],
                "expected": ["...", ...]
            }
        """
        print(f"\n🔍 Structured information extraction:")
        print(f"   Query: {query_text}")
        
        if query_text in self._structured_extract_cache:
            return self._structured_extract_cache[query_text]

        prompt = f"""Extract structured information from the following test requirement.

Test requirement: {query_text}

Analyze and extract:
1. **Preconditions**: States, environment, or conditions that must hold before testing
   - e.g. vehicle state, power mode, door/window state, slope, etc.

2. **Actions**: Operations to perform
   - e.g. button press, setting change, voice command, etc.

3. **Expected**: Expected test outcome or system response
   - e.g. normal function, system prompt, state change, etc.

**Important**:
- If a category has no clear information, return an empty list []
- Extract all relevant information without over-speculating
- Keep each item concise and explicit

Output JSON only (no other text):
```json
{{
  "preconditions": ["条件1", "条件2"],
  "actions": ["动作1", "动作2"],
  "expected": ["预期1", "预期2"]
}}
```"""
        
        try:
            response, elapsed = generate_testcase(
                prompt=prompt,
                model="Qwen3-8B",
                max_tokens=1024
            )
            
            print(f"   ⏱️  Extraction time: {elapsed:.2f}s")
            
            response = response.strip()
            
            if response.startswith("```json"):
                response = response[7:]
            elif response.startswith("```"):
                response = response[3:]
            
            if response.endswith("```"):
                response = response[:-3]
            
            response = response.strip()
            
            extracted = json.loads(response)
            
            if not isinstance(extracted, dict):
                raise ValueError("Extraction result is not a dict")
            
            result = {
                "preconditions": extracted.get("preconditions", []),
                "actions": extracted.get("actions", []),
                "expected": extracted.get("expected", [])
            }
            
            for key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]] if result[key] else []
            
            print(f"\n   ✅ Extraction succeeded:")
            print(f"      - Preconditions: {len(result['preconditions'])}")
            for i, item in enumerate(result['preconditions'][:3], 1):
                print(f"        {i}. {item}")
            if len(result['preconditions']) > 3:
                print(f"        ... and {len(result['preconditions']) - 3} more")
            
            print(f"      - Actions: {len(result['actions'])}")
            for i, item in enumerate(result['actions'][:3], 1):
                print(f"        {i}. {item}")
            if len(result['actions']) > 3:
                print(f"        ... and {len(result['actions']) - 3} more")
            
            print(f"      - Expected behavior: {len(result['expected'])}")
            for i, item in enumerate(result['expected'][:3], 1):
                print(f"        {i}. {item}")
            if len(result['expected']) > 3:
                print(f"        ... and {len(result['expected']) - 3} more")

            self._structured_extract_cache[query_text] = result
            return result
            
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON parse failed: {e}")
            print(f"   Raw response: {response[:200]}...")
            result = {
                "preconditions": [],
                "actions": [],
                "expected": []
            }
            self._structured_extract_cache[query_text] = result
            return result
        except Exception as e:
            print(f"   ❌ Extraction failed: {e}")
            result = {
                "preconditions": [],
                "actions": [],
                "expected": []
            }
            self._structured_extract_cache[query_text] = result
            return result

        
    
    def extract_key_entities_structured(
        self, 
        query_text: str, 
        model,
        threshold: float = 0.7,
        top_k_per_item: int = 2
    ) -> List[Dict]:
        """
        Entity retrieval based on structured extraction.

        Args:
            query_text: User query
            model: Embedding model
            threshold: Similarity threshold (default 0.7)

        Returns:
            List[Dict]: [{\"name\": str, \"type\": str, \"score\": float}, ...]
        """
        if not self.indexes:
            raise ValueError("Typed indexes not loaded; build indexes first")
        
        print(f"\n{'='*80}")
        print(f"🔍 Structured entity retrieval")
        print(f"{'='*80}")
        
        extracted = self.extract_structured_info(query_text)
        
        print(f"\n📊 Typed vector search:")
        
        all_entities = []
        
        def _l2_to_cosine_sim(d: float) -> float:
            # IndexFlatL2 returns squared L2 distance.
            # For normalized vectors: ||a-b||^2 = 2 - 2*cos(a,b) => cos = 1 - d/2
            return 1.0 - (float(d) / 2.0)

        if extracted["preconditions"] and len(extracted["preconditions"]) > 0:
            print(f"\n   🔹 Searching preconditions ({len(extracted['preconditions'])} items, top-{top_k_per_item}):")
            for precond in extracted["preconditions"]:
                print(f"      - {precond}")
                if "Precondition" in self.indexes:
                    vec = model.encode([precond], normalize_embeddings=True, convert_to_numpy=True)
                    query_array = np.ascontiguousarray(vec, dtype=np.float32)
                    
                    index = self.indexes["Precondition"]
                    texts = self.entity_texts["Precondition"]
                    
                    D, I = index.search(query_array, top_k_per_item)
                    
                    for idx, i in enumerate(I[0]):
                        if i < len(texts):
                            score = _l2_to_cosine_sim(D[0][idx])
                            all_entities.append({
                                "name": texts[i],
                                "type": "Precondition",
                                "score": score,
                                "source_query": precond
                            })
        else:
            print(f"\n   ⏭️  Skipping precondition search (nothing extracted)")
        
        if extracted["actions"] and len(extracted["actions"]) > 0:
            print(f"\n   🔹 Searching actions ({len(extracted['actions'])} items, top-{top_k_per_item}):")
            for action in extracted["actions"]:
                print(f"      - {action}")
                if "Action" in self.indexes:
                    vec = model.encode([action], normalize_embeddings=True, convert_to_numpy=True)
                    query_array = np.ascontiguousarray(vec, dtype=np.float32)
                    
                    index = self.indexes["Action"]
                    texts = self.entity_texts["Action"]
                    
                    D, I = index.search(query_array, top_k_per_item)
                    
                    for idx, i in enumerate(I[0]):
                        if i < len(texts):
                            score = _l2_to_cosine_sim(D[0][idx])
                            all_entities.append({
                                "name": texts[i],
                                "type": "Action",
                                "score": score,
                                "source_query": action
                            })
        else:
            print(f"\n   ⏭️  Skipping action search (nothing extracted)")
        
        if extracted["expected"] and len(extracted["expected"]) > 0:
            print(f"\n   🔹 Searching expected behavior ({len(extracted['expected'])} items, top-{top_k_per_item}):")
            for expected in extracted["expected"]:
                print(f"      - {expected}")
                if "Expected" in self.indexes:
                    vec = model.encode([expected], normalize_embeddings=True, convert_to_numpy=True)
                    query_array = np.ascontiguousarray(vec, dtype=np.float32)
                    
                    index = self.indexes["Expected"]
                    texts = self.entity_texts["Expected"]
                    
                    D, I = index.search(query_array, top_k_per_item)
                    
                    for idx, i in enumerate(I[0]):
                        if i < len(texts):
                            score = _l2_to_cosine_sim(D[0][idx])
                            all_entities.append({
                                "name": texts[i],
                                "type": "Expected",
                                "score": score,
                                "source_query": expected
                            })
        else:
            print(f"\n   ⏭️  Skipping expected-behavior search (nothing extracted)")
        
        print(f"\n   🔹 Searching test cases (original query, top-1):")
        print(f"      - {query_text}")
        if "TestCase" in self.indexes:
            vec = model.encode([query_text], normalize_embeddings=True, convert_to_numpy=True)
            query_array = np.ascontiguousarray(vec, dtype=np.float32)
            
            index = self.indexes["TestCase"]
            texts = self.entity_texts["TestCase"]
            
            D, I = index.search(query_array, 1)
            
            for idx, i in enumerate(I[0]):
                if i < len(texts):
                    score = _l2_to_cosine_sim(D[0][idx])
                    all_entities.append({
                        "name": texts[i],
                        "type": "TestCase",
                        "score": score,
                        "source_query": query_text
                    })
        
        print(f"\n   📋 Result processing:")
        print(f"      - Raw results: {len(all_entities)} entities")
        
        entity_dict = {}
        for e in all_entities:
            name = e["name"]
            if name not in entity_dict or e["score"] > entity_dict[name]["score"]:
                entity_dict[name] = e
        
        print(f"      - After dedup: {len(entity_dict)} entities")
        
        filtered = []
        for e in entity_dict.values():
            if e["type"] == "TestCase":
                filtered.append(e)
            elif e["score"] >= threshold:
                filtered.append(e)
        print(f"      - After threshold (>={threshold}): {len(filtered)} entities")
        
        key_entities = sorted(filtered, key=lambda x: x["score"], reverse=True)
        
        print(f"\n✅ Key entities extracted: {len(key_entities)}")
        for i, e in enumerate(key_entities[:10], 1):
            print(f"   {i}. [{e['type']}] {e['name'][:60]}... (score={e['score']:.3f})")
        
        if len(key_entities) > 10:
            print(f"   ... and {len(key_entities) - 10} more entities")
        
        return key_entities
    
    def _build_skeleton_from_mst(self, mst_edges: List[Tuple[str, str, Dict]]) -> Dict:
        """
        Build skeleton subgraph directly from MST edges (no full shortest-path expansion).

        Args:
            mst_edges: MST edges [(u, v, info), ...]

        Returns:
            Dict: {"nodes": set, "edges": set}
        """
        print(f"\n🔗 Building skeleton from MST (direct paths, no expansion)...")
        
        skeleton_subgraph = {
            "nodes": set(),
            "edges": set()
        }
        
        for u, v, info in mst_edges:
            path_nodes = info["path_nodes"]
            path_relations = info["path_relations"]
            
            skeleton_subgraph["nodes"].update(path_nodes)
            
            for i in range(len(path_nodes) - 1):
                edge = (path_nodes[i], path_relations[i], path_nodes[i+1])
                skeleton_subgraph["edges"].add(edge)
            
            print(f"   - {u} <-> {v}: {len(path_nodes)} nodes")
        
        print(f"   ✅ Skeleton subgraph: {len(skeleton_subgraph['nodes'])} nodes, {len(skeleton_subgraph['edges'])} edges")
        
        return skeleton_subgraph
    
    def retrieve_evidence_subgraph(
        self,
        query_text: str,
        model,
        max_hops: int = 3,
        threshold: float = 0.7
    ) -> Dict:
        """
        Full evidence subgraph retrieval (structured mode).

        Args:
            query_text: User query
            model: Embedding model
            max_hops: Maximum hops
            threshold: Similarity threshold (default 0.7)

        Returns:
            Dict: Evidence subgraph
        """
        print(f"\n{'='*80}")
        print(f"🎯 Evidence subgraph retrieval (structured extraction)")
        print(f"{'='*80}")
        
        key_entities_info = self.extract_key_entities_structured(
            query_text=query_text,
            model=model,
            threshold=threshold,
            top_k_per_item=2
        )
        key_entities = [e["name"] for e in key_entities_info]
        
        if len(key_entities) < 2:
            print(f"⚠️  Insufficient structured entities ({len(key_entities)} < 2); falling back to layered retrieval...")
            try:
                fallback_info = super().extract_key_entities(
                    query_text=query_text,
                    model=model,
                    top_k_per_type=3,
                    threshold=max(0.55, threshold - 0.15)
                )
                key_entities_info = fallback_info
                key_entities = [e["name"] for e in key_entities_info]
                print(f"   ✅ Fallback retrieved {len(key_entities)} entities")
            except Exception as e:
                print(f"   ❌ Fallback retrieval failed: {e}")

        if len(key_entities) < 2:
            print(f"⚠️  Still insufficient key entities ({len(key_entities)} < 2); cannot build subgraph")
            return {
                "nodes": set(key_entities),
                "edges": set(),
                "key_entities": key_entities_info,
                "metadata": {
                    "error": "insufficient_entities",
                    "query": query_text
                }
            }
        
        distances = self.compute_shortest_paths(key_entities, max_hops)
        
        if not distances:
            print(f"⚠️  No connected paths between key entities")
            return {
                "nodes": set(key_entities),
                "edges": set(),
                "key_entities": key_entities_info,
                "metadata": {
                    "error": "no_paths",
                    "query": query_text
                }
            }
        
        mst_edges = self.build_mst(key_entities, distances)
        
        skeleton_subgraph = self._build_skeleton_from_mst(mst_edges)
        
        evidence_subgraph = self.expand_testcase_neighbors(
            skeleton_subgraph,
            max_neighbors_per_testcase=max_hops * 5
        )
        
        evidence_subgraph["key_entities"] = key_entities_info
        evidence_subgraph["metadata"] = {
            "query": query_text,
            "retrieval_mode": "structured_extraction",
            "key_entity_count": len(key_entities),
            "mst_edge_count": len(mst_edges),
            "total_nodes": len(evidence_subgraph["nodes"]),
            "total_edges": len(evidence_subgraph["edges"]),
            "max_hops": max_hops
        }
        
        print(f"\n{'='*80}")
        print(f"✅ Evidence subgraph complete")
        print(f"{'='*80}")
        
        return evidence_subgraph


if __name__ == "__main__":
    """Test structured retriever."""
    import sys
    import io
    
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    from embedding_client import EmbeddingClient
    from config import NEO4J_CONFIG
    
    NEO4J_URI = NEO4J_CONFIG["uri"]
    NEO4J_USER = NEO4J_CONFIG["user"]
    NEO4J_PASSWORD = NEO4J_CONFIG["password"]
    
    print("="*80)
    print("Initializing structured retriever")
    print("="*80)
    
    retriever = KnowledgeGraphRetrieverStructured(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        index_dir="cache/vector_index"
    )
    
    print("\nInitializing embedding model...")
    model = EmbeddingClient("qwen3-8b-embedding")
    
    test_query = "请生成一个测试用例，验证左后语音唤醒关闭尾门在车速60时的功能"
    
    print(f"\n\n{'='*80}")
    print(f"Test query: {test_query}")
    print(f"{'='*80}")
    
    try:
        evidence_subgraph = retriever.retrieve_evidence_subgraph(
            query_text=test_query,
            model=model,
            max_hops=3,
            threshold=0.7
        )
        
        print("\n" + "="*80)
        print("📊 Retrieval results")
        print("="*80)
        
        formatted_text = retriever.format_subgraph_for_llm(evidence_subgraph)
        print(formatted_text)
        
        metadata = evidence_subgraph.get("metadata", {})
        print(f"\n📈 Statistics:")
        print(f"   - Retrieval mode: {metadata.get('retrieval_mode', 'unknown')}")
        print(f"   - Key entity count: {metadata.get('key_entity_count', 0)}")
        print(f"   - MST edge count: {metadata.get('mst_edge_count', 0)}")
        print(f"   - Total nodes: {metadata.get('total_nodes', 0)}")
        print(f"   - Total edges: {metadata.get('total_edges', 0)}")
        
    except Exception as e:
        print(f"\n❌ Retrieval failed: {str(e)}")
        import traceback
        traceback.print_exc()
    
    retriever.close()
    print("\n✅ Test complete")
