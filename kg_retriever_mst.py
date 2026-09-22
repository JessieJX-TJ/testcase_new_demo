"""
Knowledge graph retriever based on MST (approach 4: layered retrieval)

Retrieval pipeline:
1. Entity extraction: extract key entities from the query (typed retrieval)
2. Path subgraph: build connected skeleton with MST (≤3 hops)
3. Evidence subgraph: expand 1-hop neighbors for TestCase nodes
"""

import json
import numpy as np
import faiss
from neo4j import GraphDatabase
import os
from typing import List, Dict, Set, Tuple


class UnionFind:
    """Union-find (for Kruskal MST)."""
    
    def __init__(self, elements):
        self.parent = {e: e for e in elements}
        self.rank = {e: 0 for e in elements}
    
    def find(self, x):
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x, y):
        """Union by rank."""
        root_x, root_y = self.find(x), self.find(y)
        if root_x == root_y:
            return False
        
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1
        return True


class KnowledgeGraphRetrieverMST:
    """Knowledge graph retriever based on MST."""
    
    def __init__(self, uri, user, password, index_dir="cache/vector_index"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.index_dir = index_dir
        
        # Load typed indexes
        self.indexes = {}
        self.entity_texts = {}
        self._load_typed_indexes()
    
    def close(self):
        self.driver.close()
    
    def _load_typed_indexes(self):
        """Load typed vector indexes."""
        meta_file = os.path.join(self.index_dir, "index_meta.json")
        
        if not os.path.exists(meta_file):
            print(f"⚠️  Typed index metadata not found: {meta_file}")
            return
        
        with open(meta_file, 'r', encoding='utf-8') as f:
            index_info = json.load(f)
        
        print(f"📥 Loading typed indexes...")
        for entity_type, info in index_info.items():
            raw_index_path = info["index_file"].replace('\\', '/')
            raw_text_path = info["text_file"].replace('\\', '/')

            index_filename = os.path.basename(raw_index_path)
            text_filename = os.path.basename(raw_text_path)
            
            index_file = os.path.join(self.index_dir, index_filename)
            text_file = os.path.join(self.index_dir, text_filename)
            
            print(f"DEBUG: Loading {entity_type} -> {index_file}")
            
            if os.path.exists(index_file) and os.path.exists(text_file):
                try:
                    self.indexes[entity_type] = faiss.read_index(index_file)
                    with open(text_file, 'r', encoding='utf-8') as f:
                        self.entity_texts[entity_type] = json.load(f)
                    print(f"   ✅ {entity_type}: loaded")
                except Exception as e:
                    print(f"   ❌ {entity_type}: load error - {str(e)}")
            else:
                print(f"   ❌ {entity_type}: missing files - path check failed: {index_file}")
        
        print(f"✅ Initialization complete; active indexes: {len(self.indexes)}")
    def extract_key_entities(
        self, 
        query_text: str, 
        model,
        entity_types: List[str] = None,
        type_weights: Dict[str, float] = None,
        top_k_per_type: int = 3,
        threshold: float = 0.65
    ) -> List[Dict]:
        """
        Extract key entities from the query (layered retrieval).

        Args:
            query_text: User query
            model: Embedding model
            entity_types: Entity types to search (None = all)
            type_weights: Per-type weights {type: weight}
            top_k_per_type: Entities retrieved per type
            threshold: Similarity threshold

        Returns:
            List[Dict]: [{"name": str, "type": str, "score": float}, ...]
        """
        if not self.indexes:
            raise ValueError("Typed indexes not loaded; build indexes first")
        
        if entity_types is None:
            entity_types = list(self.indexes.keys())
        
        if type_weights is None:
            type_weights = {
                "TestCase": 1.5,
                "Precondition": 1.2,
                "Action": 1.0,
                "Expected": 0.8,
                "TestType": 0.5
            }
        
        print(f"\n🔍 Layered entity retrieval:")
        print(f"   Query: {query_text}")
        print(f"   Entity types: {entity_types}")

        def _l2_to_cosine_sim(d: float) -> float:
            # IndexFlatL2 returns squared L2 distance.
            # For normalized vectors: ||a-b||^2 = 2 - 2*cos(a,b) => cos = 1 - d/2
            return 1.0 - (float(d) / 2.0)
        
        query_vec = model.encode([query_text], normalize_embeddings=True, convert_to_numpy=True)
        query_array = np.ascontiguousarray(query_vec, dtype=np.float32)
        
        all_entities = []
        for entity_type in entity_types:
            if entity_type not in self.indexes:
                print(f"   ⚠️  Skipping unknown type: {entity_type}")
                continue
            
            index = self.indexes[entity_type]
            texts = self.entity_texts[entity_type]
            weight = type_weights.get(entity_type, 1.0)
            
            D, I = index.search(query_array, top_k_per_type)
            
            for idx, i in enumerate(I[0]):
                if i < len(texts):
                    raw_sim = _l2_to_cosine_sim(D[0][idx])
                    score = raw_sim * weight
                    all_entities.append({
                        "name": texts[i],
                        "type": entity_type,
                        "score": score,
                        "raw_score": raw_sim
                    })
            
            print(f"   - {entity_type}: retrieved {len(I[0])} entities")
        
        entity_dict = {}
        for e in all_entities:
            name = e["name"]
            if name not in entity_dict or e["score"] > entity_dict[name]["score"]:
                entity_dict[name] = e
        
        filtered = [e for e in entity_dict.values() if e["score"] >= threshold]
        
        key_entities = sorted(filtered, key=lambda x: x["score"], reverse=True)
        
        print(f"\n✅ Key entities extracted: {len(key_entities)}")
        for i, e in enumerate(key_entities[:5]):
            print(f"   {i+1}. [{e['type']}] {e['name']} (score={e['score']:.3f})")
        
        return key_entities
    
    def compute_shortest_paths(
        self, 
        key_entities: List[str], 
        max_hops: int = 3
    ) -> Dict[Tuple[str, str], Dict]:
        """
        Compute shortest paths between key entities.

        Args:
            key_entities: List of key entity names
            max_hops: Maximum hop count

        Returns:
            Dict: {(entity1, entity2): {"distance": int, "paths": [path_list]}}
        """
        print(f"\n🔗 Computing shortest paths (max_hops={max_hops})...")
        
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $entities AS entity1
                UNWIND $entities AS entity2
                WITH entity1, entity2
                WHERE entity1 < entity2
                MATCH (n1 {name: entity1}), (n2 {name: entity2})
                OPTIONAL MATCH path = shortestPath((n1)-[*..%d]-(n2))
                RETURN entity1, entity2, 
                       CASE WHEN path IS NULL THEN null ELSE length(path) END AS distance,
                       CASE WHEN path IS NULL THEN null ELSE [node in nodes(path) | node.name] END AS path_nodes,
                       CASE WHEN path IS NULL THEN null ELSE [rel in relationships(path) | type(rel)] END AS path_relations
            """ % max_hops, entities=key_entities)
            
            distances = {}
            for record in result:
                entity1 = record["entity1"]
                entity2 = record["entity2"]
                distance = record["distance"]
                
                if distance is not None:
                    distances[(entity1, entity2)] = {
                        "distance": distance,
                        "path_nodes": record["path_nodes"],
                        "path_relations": record["path_relations"]
                    }
        
        print(f"   ✅ Found {len(distances)} paths")
        return distances
    
    def build_mst(
        self, 
        key_entities: List[str], 
        distances: Dict[Tuple[str, str], Dict]
    ) -> List[Tuple[str, str, Dict]]:
        """
        Build minimum spanning tree with Kruskal's algorithm.

        Args:
            key_entities: List of key entity names
            distances: Pairwise distances

        Returns:
            List[Tuple]: [(entity1, entity2, path_info), ...]
        """
        print(f"\n🌳 Building MST...")
        
        uf = UnionFind(key_entities)
        
        edges = sorted(distances.items(), key=lambda x: x[1]["distance"])
        
        mst_edges = []
        for (u, v), info in edges:
            if uf.union(u, v):
                mst_edges.append((u, v, info))
        
        print(f"   ✅ MST has {len(mst_edges)} edges")
        
        return mst_edges
    
    def expand_all_shortest_paths(
        self, 
        mst_edges: List[Tuple[str, str, Dict]]
    ) -> Dict:
        """
        Expand all same-length shortest paths for each MST edge.

        Args:
            mst_edges: MST edge list

        Returns:
            Dict: {"nodes": set, "edges": set}
        """
        print(f"\n🔄 Expanding all shortest paths...")
        
        skeleton_subgraph = {
            "nodes": set(),
            "edges": set()
        }
        
        with self.driver.session() as session:
            for u, v, info in mst_edges:
                target_distance = info["distance"]
                
                result = session.run("""
                    MATCH (start {name: $start_name}), (end {name: $end_name})
                    MATCH path = allShortestPaths((start)-[*..%d]-(end))
                    WHERE length(path) = $target_distance
                    RETURN [node in nodes(path) | node.name] AS path_nodes,
                           [rel in relationships(path) | type(rel)] AS path_relations
                """ % (target_distance + 1), start_name=u, end_name=v, target_distance=target_distance)
                
                path_count = 0
                for record in result:
                    path_nodes = record["path_nodes"]
                    path_relations = record["path_relations"]
                    
                    skeleton_subgraph["nodes"].update(path_nodes)
                    
                    for i in range(len(path_nodes) - 1):
                        edge = (path_nodes[i], path_relations[i], path_nodes[i+1])
                        skeleton_subgraph["edges"].add(edge)
                    
                    path_count += 1
                
                print(f"   - {u} <-> {v}: {path_count} paths")
        
        print(f"   ✅ Skeleton subgraph: {len(skeleton_subgraph['nodes'])} nodes, {len(skeleton_subgraph['edges'])} edges")
        
        return skeleton_subgraph
    
    def expand_testcase_neighbors(
        self, 
        skeleton_subgraph: Dict,
        max_neighbors_per_testcase: int = 10
    ) -> Dict:
        """
        Expand 1-hop neighbors for TestCase nodes in the skeleton subgraph.

        Args:
            skeleton_subgraph: Skeleton subgraph
            max_neighbors_per_testcase: Max neighbors per TestCase

        Returns:
            Dict: Evidence subgraph
        """
        print(f"\n🌿 Expanding TestCase neighbors (max {max_neighbors_per_testcase} per TestCase)...")
        
        testcase_nodes = []
        with self.driver.session() as session:
            for node in skeleton_subgraph["nodes"]:
                result = session.run("""
                    MATCH (n {name: $name})
                    RETURN labels(n) AS labels
                """, name=node)
                
                record = result.single()
                if record and "TestCase" in record["labels"]:
                    testcase_nodes.append(node)
        
        print(f"   Found {len(testcase_nodes)} TestCase nodes")
        
        evidence_subgraph = {
            "nodes": skeleton_subgraph["nodes"].copy(),
            "edges": skeleton_subgraph["edges"].copy()
        }
        
        if testcase_nodes:
            with self.driver.session() as session:
                total_neighbor_count = 0
                for tc_node in testcase_nodes:
                    result = session.run("""
                        MATCH (tc:TestCase {name: $tc_name})-[r]-(neighbor)
                        WHERE neighbor.name IS NOT NULL
                        RETURN tc.name AS testcase,
                               type(r) AS relation,
                               neighbor.name AS neighbor_name,
                               labels(neighbor)[0] AS neighbor_type,
                               startNode(r).name = tc.name AS is_outgoing
                        ORDER BY
                            CASE type(r)
                                WHEN '前提条件' THEN 0
                                WHEN '执行动作' THEN 1
                                WHEN '预期行为' THEN 2
                                WHEN '测试用例类型' THEN 3
                                ELSE 9
                            END,
                            CASE labels(neighbor)[0]
                                WHEN 'Precondition' THEN 0
                                WHEN 'Action' THEN 1
                                WHEN 'Expected' THEN 2
                                WHEN 'TestType' THEN 3
                                ELSE 9
                            END,
                            neighbor.name,
                            type(r)
                        LIMIT $max_neighbors
                    """, tc_name=tc_node, max_neighbors=max_neighbors_per_testcase)
                    
                    tc_neighbor_count = 0
                    for record in result:
                        testcase = record["testcase"]
                        neighbor = record["neighbor_name"]
                        relation = record["relation"]
                        is_outgoing = record["is_outgoing"]
                        
                        evidence_subgraph["nodes"].add(neighbor)
                        
                        if is_outgoing:
                            edge = (testcase, relation, neighbor)
                        else:
                            edge = (neighbor, relation, testcase)
                        
                        evidence_subgraph["edges"].add(edge)
                        tc_neighbor_count += 1
                    
                    total_neighbor_count += tc_neighbor_count
                
                print(f"   ✅ Expanded {total_neighbor_count} neighbor nodes")
        
        print(f"   ✅ Evidence subgraph: {len(evidence_subgraph['nodes'])} nodes, {len(evidence_subgraph['edges'])} edges")
        
        return evidence_subgraph
    
    def retrieve_evidence_subgraph(
        self,
        query_text: str,
        model,
        entity_types: List[str] = None,
        type_weights: Dict[str, float] = None,
        top_k_per_type: int = 3,
        max_hops: int = 3,
        threshold: float = 0.65
    ) -> Dict:
        """
        Full evidence subgraph retrieval pipeline.

        Args:
            query_text: User query
            model: Embedding model
            entity_types: Entity types to search
            type_weights: Per-type weights
            top_k_per_type: Entities per type
            max_hops: Maximum hops
            threshold: Similarity threshold

        Returns:
            Dict: Evidence subgraph
        """
        print(f"\n{'='*80}")
        print(f"🎯 Evidence subgraph retrieval")
        print(f"{'='*80}")
        
        key_entities_info = self.extract_key_entities(
            query_text, model, entity_types, type_weights, top_k_per_type, threshold
        )
        key_entities = [e["name"] for e in key_entities_info]
        
        if len(key_entities) < 2:
            print(f"⚠️  Insufficient key entities ({len(key_entities)} < 2); cannot build subgraph")
            return {
                "nodes": set(key_entities),
                "edges": set(),
                "key_entities": key_entities_info,
                "metadata": {"error": "insufficient_entities"}
            }
        
        distances = self.compute_shortest_paths(key_entities, max_hops)
        
        if not distances:
            print(f"⚠️  No connected paths between key entities")
            return {
                "nodes": set(key_entities),
                "edges": set(),
                "key_entities": key_entities_info,
                "metadata": {"error": "no_paths"}
            }
        
        mst_edges = self.build_mst(key_entities, distances)
        
        skeleton_subgraph = self.expand_all_shortest_paths(mst_edges)
        
        evidence_subgraph = self.expand_testcase_neighbors(skeleton_subgraph)
        
        evidence_subgraph["key_entities"] = key_entities_info
        evidence_subgraph["metadata"] = {
            "query": query_text,
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
    
    def format_subgraph_for_llm(self, evidence_subgraph: Dict) -> str:
        """
        Format evidence subgraph as LLM-readable text.

        Args:
            evidence_subgraph: Evidence subgraph

        Returns:
            str: Formatted text
        """
        lines = []
        
        lines.append("## Key entities")
        for i, entity in enumerate(evidence_subgraph.get("key_entities", [])[:5]):
            lines.append(f"{i+1}. [{entity['type']}] {entity['name']} (relevance: {entity['score']:.2f})")
        
        lines.append("\n## Knowledge triples")
        for i, (head, relation, tail) in enumerate(evidence_subgraph["edges"]):
            lines.append(f"{i+1}. {head} --[{relation}]--> {tail}")
        
        return "\n".join(lines)
