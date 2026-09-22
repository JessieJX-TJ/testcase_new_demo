# model_mode_config.py
import os


MODEL_MODE = os.getenv("MODEL_MODE", "service")
ENABLE_MODEL_CACHE = True  # Set to False if GPU VRAM is below 32GB

# Base paths
BASE_MODELS = "models"
SFT_MODELS = "sft-model"

# Local direct-load model paths (direct mode)
LOCAL_MODEL_PATHS = {
    # 1. Case generation: fine-tuned 4B (LoRA)
    "Qwen3-4B": {
        "path": f"{SFT_MODELS}/qwen3-4b-sft-gen",
        "type": "lora",
        "base_model": f"{BASE_MODELS}/Qwen3-4B",
    },

    # 2. Evaluator: distilled/fine-tuned 1.7B (LoRA)
    "Qwen3-1.7B": {
        "path": f"{SFT_MODELS}/qwen3-1.7b-sft-critic",
        "type": "lora",
        "base_model": f"{BASE_MODELS}/Qwen3-1.7B",
    },

    # Legacy name compatibility
    "Qwen3-1.7B-Critic": {
        "path": f"{SFT_MODELS}/qwen3-1.7b-sft-critic",
        "type": "lora",
        "base_model": f"{BASE_MODELS}/Qwen3-1.7B",
    },
}

# Local service-mode configuration (service mode)
# Ports are injected via .env; Docker starts two model services on launch
MODEL_SERVICE_CONFIG = {
    "Qwen3-4B": {
        "port": int(os.getenv("QWEN3_4B_SERVICE_PORT", "9004")),
        "host": os.getenv("QWEN3_4B_SERVICE_HOST", "127.0.0.1"),
        "served_model_name": os.getenv("QWEN3_4B_SERVED_MODEL_NAME", "Qwen3-4B"),
        "api_key": os.getenv("LOCAL_MODEL_API_KEY", "EMPTY"),
        "lora_name": os.getenv("QWEN3_4B_LORA_NAME", "gen"),
    },
    "Qwen3-1.7B": {
        "port": int(os.getenv("QWEN3_17B_SERVICE_PORT", "9017")),
        "host": os.getenv("QWEN3_17B_SERVICE_HOST", "127.0.0.1"),
        "served_model_name": os.getenv("QWEN3_17B_SERVED_MODEL_NAME", "Qwen3-1.7B"),
        "api_key": os.getenv("LOCAL_MODEL_API_KEY", "EMPTY"),
        "lora_name": os.getenv("QWEN3_17B_LORA_NAME", "critic"),
    },
}
