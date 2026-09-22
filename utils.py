from kg_retriever_structured import KnowledgeGraphRetrieverStructured
from testcase_formatter import TestCaseFormatter, format_testcases_as_context, format_testcases_as_pae_chains
from prompt_builder import build_testcase_prompt, format_context
from llm_client import generate_testcase
from embedding_client import get_encoder, EmbeddingClient
from config import NEO4J_CONFIG, RETRIEVAL_CONFIG, SIMILAR_CASES_CONFIG, EMBEDDING_CONFIG
from pdf_kg_retriever import format_pdf_kg_evidence, retrieve_pdf_kg_evidence
import textwrap
import re
import json
import faiss
import numpy as np

# Lazy embedding init so the Flask UI can start without DASHSCOPE_API_KEY.
_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = get_encoder(EMBEDDING_CONFIG["model_name"])
    return _encoder


def wrap_text(text, width=20):
    """
    Wrap text for display so long content does not break the layout.
    """
    return '\n'.join(textwrap.wrap(text, width=width))


def process_triple(triple):
    """
    Clean special formats in triples: strip redundant prefixes and truncate long values.
    """
    for key in ['head', 'relation', 'tail']:
        triple[key] = re.sub(r'(SysVol|VehLckngSta|BLEComfortLock EnableSetting|PassiveEntryFunction|DigKeylnCar|DoorHandSwiSts|UnlockWindow|KeyInsideCar)\s*[:：]\s*', '', triple[key])
        if len(triple[key]) > 40:
            triple[key] = triple[key][:37] + "..."
    return triple


def retrieve_similar_testcases(query_text, top_k=None):
    """
    Retrieve similar test cases.
    - Load test-case data and vector index
    - Find the most similar test cases for the query text
    - Return a list of similar test cases
    """
    if top_k is None:
        top_k = SIMILAR_CASES_CONFIG["top_k"]
    
    try:
        # Load test-case data
        with open(SIMILAR_CASES_CONFIG["data_file"], 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
        
        # Load vector index
        index = faiss.read_index(SIMILAR_CASES_CONFIG["index_file"])
        
        # Vectorize query (same method as rebuild_simple.py)
        query_vec = _get_encoder().encode([query_text], normalize_embeddings=True, convert_to_numpy=True)
        
        # Convert to Python list then back to numpy (compatibility)
        query_list = query_vec.tolist()
        query_array = np.array(query_list, dtype=np.float32)
        
        # Search most similar test cases
        D, I = index.search(query_array, top_k)

        def _l2_to_cosine_sim(d: float) -> float:
            # IndexFlatL2 returns squared L2 distance.
            # If vectors are normalized: ||a-b||^2 = 2 - 2*cos(a,b) => cos = 1 - d/2
            return 1.0 - (float(d) / 2.0)
        
        # Collect similar test cases
        similar_cases = []
        for idx, score in zip(I[0], D[0]):
            if idx < len(test_cases):
                case = test_cases[idx].copy()
                case['similarity_score'] = _l2_to_cosine_sim(score)
                similar_cases.append(case)
        
        print(f"🔍 Retrieved {len(similar_cases)} similar test cases")
        return similar_cases
    except Exception as e:
        print(f"⚠️ Test-case retrieval failed: {e}")
        return []


def _filter_testcases_by_relevance(testcases, evidence_subgraph, threshold=0.5, top_k=5):
    """
    Rank retrieved complete test cases by relevance, then filter by threshold and top-k:
    - Prefer FAISS direct hits with similarity >= threshold
    - Use graph-neighbor expansions (no direct score) as supplements
    - Keep at most top_k cases
    """
    if not testcases:
        return testcases

    key_entities_info = evidence_subgraph.get("key_entities", [])
    tc_scores = {
        e["name"]: e["score"]
        for e in key_entities_info
        if e.get("type") == "TestCase"
    }

    scored = [(tc_scores.get(tc.get("case_name", ""), 0.0), tc) for tc in testcases]
    scored.sort(key=lambda x: x[0], reverse=True)

    above = [(s, tc) for s, tc in scored if s >= threshold]
    below = [(s, tc) for s, tc in scored if s < threshold]
    combined = above + below
    result = [tc for _, tc in combined[:top_k]]

    print(f"📋 Test-case filter: {len(testcases)} → {len(result)}"
          f" (threshold≥{threshold}: {len(above)}, supplemental: {max(0, len(result)-len(above))}, top_k={top_k})")
    return result


def _has_complete_pae(testcase):
    return bool(
        testcase.get('preconditions')
        and testcase.get('actions')
        and testcase.get('expected_behaviors')
    )


def retrieve_rag_evidence(question, progress_callback=None):
    """
    Retrieve RAG evidence:
    - Use structured extraction (preconditions, actions, expected behaviors)
    - Retrieve evidence subgraph (MST + TestCase neighbor expansion)
    - Reconstruct complete test cases from TestCase nodes
    - Retrieve similar test cases
    - Build structured context
    """
    retriever = None
    formatter = None
    try:
        def emit(message):
            if callable(progress_callback):
                progress_callback(message)

        emit("Retrieving PDF specification KG JSON evidence (keep only score>75)...")
        print("🔍 Retrieving PDF specification KG JSON evidence (keep only score>75)...")
        pdf_evidence = retrieve_pdf_kg_evidence(question, top_k=20, per_doc_limit=6, min_score=75)
        pdf_context_text = format_pdf_kg_evidence(pdf_evidence)
        pdf_triples = [
            {
                "head": item.get("head", ""),
                "relation": item.get("relation", ""),
                "tail": item.get("tail", ""),
                "source": "PDF_KG",
                "doc_name": item.get("doc_name", ""),
                "sources": item.get("sources", []),
                "score": item.get("score", 0),
            }
            for item in pdf_evidence
        ]
        emit(f"PDF specification evidence retrieval done: {len(pdf_triples)} triples (score>75)")
        print(f"✓ PDF specification evidence retrieved {len(pdf_triples)} triples (score>75)")
        if callable(progress_callback):
            progress_callback({"type": "pdf_evidence", "data": pdf_evidence})

        emit("Initializing structured knowledge-graph retriever...")
        print("🔄 Initializing structured knowledge-graph retriever...")
        retriever = KnowledgeGraphRetrieverStructured(
            uri=NEO4J_CONFIG["uri"],
            user=NEO4J_CONFIG["user"],
            password=NEO4J_CONFIG["password"],
            index_dir=RETRIEVAL_CONFIG["structured"]["index_dir"]
        )
        
        # Initialize test-case formatter
        formatter = TestCaseFormatter(
            uri=NEO4J_CONFIG["uri"],
            user=NEO4J_CONFIG["user"],
            password=NEO4J_CONFIG["password"]
        )
        
        # Initialize embedding model
        embedding_model = EmbeddingClient(EMBEDDING_CONFIG["model_name"])

        # Retrieve evidence subgraph
        emit("Retrieving evidence subgraph...")
        print("🔍 Retrieving evidence subgraph...")
        evidence_subgraph = retriever.retrieve_evidence_subgraph(
            query_text=question,
            model=embedding_model,
            max_hops=RETRIEVAL_CONFIG["structured"]["max_hops"],
            threshold=RETRIEVAL_CONFIG["structured"]["threshold"]
        )
        
        # Extract complete test cases from the evidence subgraph
        emit("Extracting complete test cases from evidence subgraph...")
        print("📋 Extracting complete test cases from subgraph...")
        complete_testcases = formatter.extract_testcases_from_subgraph(evidence_subgraph)

        # Threshold + Top-5 filter: rank by similarity; prefer score >= threshold; keep at most 5
        _cfg = RETRIEVAL_CONFIG["structured"]
        complete_testcases = _filter_testcases_by_relevance(
            complete_testcases,
            evidence_subgraph,
            threshold=_cfg["threshold"],
            top_k=_cfg.get("max_context_testcases", 5)
        )
        before_complete_filter = len(complete_testcases)
        complete_testcases = [tc for tc in complete_testcases if _has_complete_pae(tc)]
        emit(f"After context filter, kept {len(complete_testcases)} complete PAE cases")
        if before_complete_filter != len(complete_testcases):
            print(f"📋 Completeness filter: {before_complete_filter} → {len(complete_testcases)} (must include precondition, action, and expected)")

        # Convert subgraph to triple format (for frontend display)
        triples = []
        for head, relation, tail in evidence_subgraph.get("edges", set()):
            triples.append({
                "head": head,
                "relation": relation,
                "tail": tail
        })
        emit(f"Neo4j retrieval done: {len(triples)} triples, {len(complete_testcases)} complete test cases")
        print(f"✓ Neo4j retrieved {len(triples)} triples, {len(complete_testcases)} complete test cases")

        # Retrieve similar test cases
        emit("Retrieving similar test cases...")
        print("🔍 Retrieving similar test cases...")
        similar_cases = retrieve_similar_testcases(question, top_k=3)
        emit(f"Similar-case retrieval done: {len(similar_cases)}")
        print(f"✓ Retrieved {len(similar_cases)} similar cases")

        # Build RAG context (PAE logic-chain format)
        emit("Organizing RAG retrieval context...")
        print("📝 Building RAG context...")
        neo4j_context_text = format_testcases_as_pae_chains(complete_testcases)
        context_text = (
            "=== Neo4j test-case knowledge-graph evidence (complete PAE cases reconstructed from Excel triples) ===\n"
            f"{neo4j_context_text or 'No complete PAE cases were retrieved.'}\n\n"
            f"{pdf_context_text}"
        )
        return context_text, triples + pdf_triples, similar_cases, complete_testcases, pdf_evidence

    except Exception as e:
        if callable(progress_callback):
            progress_callback(f"Pipeline error: {type(e).__name__}: {str(e)}")
        print(f"❌ Structured RAG pipeline error: {type(e).__name__}: {str(e)}")
        raise
    finally:
        if retriever:
            retriever.close()
        if formatter:
            formatter.close()


def rag_pipeline_structured(question, testcase_count=1, model="Qwen3-8B", progress_callback=None):
    """
    Structured-retrieval RAG pipeline:
    - Retrieve knowledge-graph evidence and similar test cases
    - Build the prompt
    - Call the LLM to generate test cases

    Args:
        question: User test requirement
        testcase_count: Number of test cases to generate (default 1)
        model: Model identifier to use
    """
    try:
        def emit(message):
            if callable(progress_callback):
                progress_callback(message)

        context_text, triples, similar_cases, complete_testcases, pdf_evidence = retrieve_rag_evidence(question, progress_callback=progress_callback)
        prompt = build_testcase_prompt(question, context_text, similar_cases, testcase_count)
        emit(f"Prompt built (length: {len(prompt)} chars)")
        print(f"   - Prompt built, length: {len(prompt)} chars")
        
        emit(f"Calling model {model} to generate test cases...")
        print(f"🤖 Calling LLM to generate test cases (model: {model}, count: {testcase_count})...")
        testcase, elapsed_time = generate_testcase(prompt, model=model)
        emit(f"Generation done (elapsed: {elapsed_time:.2f}s)")
        print(f"✓ Test-case generation done (elapsed: {elapsed_time:.2f}s)")

        return testcase, context_text, triples, similar_cases, elapsed_time, complete_testcases, pdf_evidence

    except Exception as e:
        if callable(progress_callback):
            progress_callback(f"Pipeline error: {type(e).__name__}: {str(e)}")
        print(f"❌ Structured RAG pipeline error: {type(e).__name__}: {str(e)}")
        raise


def rag_pipeline(question, testcase_count=1, model="Qwen3-4B", use_structured=True, progress_callback=None):
    """
    Core RAG pipeline:
    - Retrieve related knowledge-graph triples from user input
    - Retrieve similar test cases
    - Build structured context
    - Build the prompt
    - Call the LLM to generate test cases
    - Return case text, triple list, and similar test cases
    
    Args:
        question: User test requirement
        testcase_count: Number of test cases to generate (default 1)
        model: Model identifier to use
        use_structured: Whether to use structured retrieval (default True)
    """
    # Structured retrieval only
    return rag_pipeline_structured(question, testcase_count, model, progress_callback=progress_callback)
