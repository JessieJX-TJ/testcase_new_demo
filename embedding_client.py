"""Embedding model client - supports local models and remote APIs"""

import numpy as np
from typing import List, Union
import os

from dotenv_loader import load_dotenv

load_dotenv(override=True)


# Default embedding model
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")


class EmbeddingClient:
    """Unified embedding model client"""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        """
        Initialize the embedding model client.

        Args:
            model_name: Logical model id; all calls go through Alibaba Cloud Bailian DashScope.
                        Supported: text-embedding-v4 / Qwen3-Embedding-8B
        """
        self.model_name = model_name
        self.client = None
        self.api_key = None
        self._dashscope_model_id = None

        if self.model_name in ("text-embedding-v4", "Qwen3-Embedding-8B"):
            self._init_dashscope_api()
        else:
            raise ValueError(
                f"Unsupported embedding model: {model_name}; supported: text-embedding-v4 / Qwen3-Embedding-8B"
            )

    def _init_dashscope_api(self):
        """Initialize Alibaba Cloud Bailian DashScope OpenAI-compatible Embedding API"""
        from openai import OpenAI
        import httpx

        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing environment variable DASHSCOPE_API_KEY. Set DASHSCOPE_API_KEY in the system/terminal before running."
            )

        # Resolve the actual DashScope model ID to call
        if self.model_name == "text-embedding-v4":
            self._dashscope_model_id = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")
        else:
            # Qwen3-Embedding-8B or others: prefer env var, fall back to text-embedding-v4
            self._dashscope_model_id = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")

        print(f"📡 Initializing Alibaba Cloud Bailian Embedding: {self.model_name} → API model: {self._dashscope_model_id}")
        http_client = httpx.Client(timeout=120.0)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            http_client=http_client,
        )
        self.api_key = api_key
        print("✅ API client initialized")

    def _init_siliconflow_api(self):
        """Initialize SiliconFlow OpenAI-compatible Embedding API"""
        from openai import OpenAI
        import httpx
        import random

        keys = os.getenv("SILICONFLOW_API_KEYS")
        api_keys = [k.strip() for k in (keys or "").split(",") if k.strip()]
        if not api_keys:
            raise ValueError(
                "Missing environment variable SILICONFLOW_API_KEYS (comma-separated). Set SILICONFLOW_API_KEYS before running."
            )

        api_key = random.choice(api_keys)
        http_client = httpx.Client(timeout=120.0)
        model_id = os.getenv("SILICONFLOW_EMBEDDING_MODEL", _SILICONFLOW_DEFAULT_MODEL_ID)

        print(f"📡 Initializing SiliconFlow Embedding: {model_id}")
        self.client = OpenAI(
            api_key=api_key,
            base_url=_SILICONFLOW_BASE_URL,
            http_client=http_client,
        )
        self.api_key = api_key
        self._siliconflow_embedding_model_id = model_id
        print("✅ API client initialized")

    def encode(
        self,
        texts: Union[str, List[str]],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        batch_size: int = 10,
    ) -> np.ndarray:
        """
        Encode text into vectors.

        Args:
            texts: A single text or a list of texts
            normalize_embeddings: Whether to L2-normalize vectors
            convert_to_numpy: Whether to return a numpy array
            batch_size: Batch size (remote API only)

        Returns:
            numpy array of shape (n_texts, embedding_dim)
        """
        if isinstance(texts, str):
            texts = [texts]

        if self.model_name in ("text-embedding-v4", "Qwen3-Embedding-8B"):
            return self._encode_dashscope(
                texts=texts,
                normalize_embeddings=normalize_embeddings,
                convert_to_numpy=convert_to_numpy,
                batch_size=batch_size,
            )

        raise ValueError(f"Unsupported model: {self.model_name}")

    def _encode_dashscope(
        self,
        texts: List[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        batch_size: int = 10,
    ) -> np.ndarray:
        """Generate vectors via the DashScope OpenAI-compatible API"""
        if not self.client:
            raise RuntimeError("DashScope client is not initialized")

        # DashScope Embedding API has a batch size limit (<= 10)
        batch_size = min(int(batch_size), 10)

        all_vecs: List[List[float]] = []
        total = len(texts)
        batches = (total + batch_size - 1) // batch_size

        for bi in range(batches):
            chunk = texts[bi * batch_size:(bi + 1) * batch_size]
            resp = self.client.embeddings.create(
                model=self._dashscope_model_id,
                input=chunk,
            )

            for item in resp.data:
                all_vecs.append(item.embedding)

            print(f"✅ DashScope batch {bi + 1}/{batches} encoded successfully ({len(chunk)} texts)")

        emb = np.array(all_vecs, dtype=np.float32)

        if normalize_embeddings:
            norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12
            emb = emb / norms

        if convert_to_numpy:
            return emb
        return emb

    def _encode_siliconflow(
        self,
        texts: List[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        batch_size: int = 64,
    ) -> np.ndarray:
        """Generate vectors via the SiliconFlow OpenAI-compatible API"""
        if not self.client:
            raise RuntimeError("SiliconFlow client is not initialized")

        batch_size = max(1, int(batch_size))
        all_vecs: List[List[float]] = []
        total = len(texts)
        batches = (total + batch_size - 1) // batch_size

        model_id = getattr(self, "_siliconflow_embedding_model_id", _SILICONFLOW_DEFAULT_MODEL_ID)

        for bi in range(batches):
            chunk = texts[bi * batch_size:(bi + 1) * batch_size]
            resp = self.client.embeddings.create(
                model=model_id,
                input=chunk,
            )
            for item in resp.data:
                all_vecs.append(item.embedding)

            print(f"✅ SiliconFlow batch {bi + 1}/{batches} encoded successfully ({len(chunk)} texts)")

        emb = np.array(all_vecs, dtype=np.float32)

        if normalize_embeddings:
            norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12
            emb = emb / norms

        if convert_to_numpy:
            return emb
        return emb

    def get_dimension(self) -> int:
        """Return the embedding vector dimension"""
        return int(os.getenv("EMBEDDING_DIM", "1024"))


# ==================== Global singleton ====================

_global_encoder = None


def get_encoder(model_name: str = DEFAULT_EMBEDDING_MODEL) -> EmbeddingClient:
    """
    Get the global embedding encoder (singleton).

    Args:
        model_name: Model name

    Returns:
        EmbeddingClient instance
    """
    global _global_encoder

    if _global_encoder is None or _global_encoder.model_name != model_name:
        print(f"🔄 Initializing embedding model: {model_name}")
        _global_encoder = EmbeddingClient(model_name)

    return _global_encoder


# ==================== Convenience helpers ====================

def encode_text(
    texts: Union[str, List[str]],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    normalize: bool = True,
) -> np.ndarray:
    """
    Convenience helper: encode text into vectors.

    Args:
        texts: A single text or a list of texts
        model_name: Model name
        normalize: Whether to normalize

    Returns:
        numpy array
    """
    encoder = get_encoder(model_name)
    return encoder.encode(texts, normalize_embeddings=normalize)


if __name__ == "__main__":
    print("Please call EmbeddingClient via entity_Vector_Index.py in the project workflow.")
