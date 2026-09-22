"""
RAG system configuration.
"""

import os

from dotenv_loader import load_dotenv

load_dotenv(override=True)

# Neo4j configuration
NEO4J_CONFIG = {
    "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    "user": os.getenv("NEO4J_USER", "neo4j"),
    "password": os.getenv("NEO4J_PASSWORD", ""),
}


def _validate_neo4j_config() -> None:
    uri = NEO4J_CONFIG.get("uri")
    user = NEO4J_CONFIG.get("user")
    password = NEO4J_CONFIG.get("password")

    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("NEO4J_URI is not configured or is not a string")
    if not isinstance(user, str) or not user.strip():
        raise ValueError("NEO4J_USER is not configured or is not a string")
    if password is None:
        raise ValueError("NEO4J_PASSWORD is not configured (is None)")
    if not isinstance(password, str):
        raise ValueError("NEO4J_PASSWORD is not a string")


_validate_neo4j_config()

# Retrieval configuration
RETRIEVAL_CONFIG = {
    # Use structured retrieval by default
    "use_structured": True,
    
    # Structured retrieval parameters
    "structured": {
        "index_dir": "cache/vector_index_(text-embedding-v4)",
        "max_hops": 3,
        "threshold": 0.7,
        "max_neighbors_per_testcase": 15,
        "max_context_testcases": 5
    },
    
    # Original retrieval parameters
    "original": {
        "entity_top_k": 5,
        "relationship_top_k": 20
    }
}

# Similar-case retrieval configuration
SIMILAR_CASES_CONFIG = {
    "top_k": 3,
    "data_file": "data/generated_test_cases.json",
    "index_file": "embeddings/test_case_embeddings/index.faiss"
}

# Embedding model configuration
EMBEDDING_CONFIG = {
    "model_name": os.getenv("EMBEDDING_MODEL_NAME", "Qwen3-Embedding-8B")
}
