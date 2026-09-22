"""
LLM client - supports service mode and direct loading mode

Automatically selects the mode based on model_mode_config.py
"""

import os


from openai import OpenAI
import time
try:
    import torch
except ImportError:
    torch = None  # torch is only required in direct mode; service mode can skip it
import httpx
import random

from dotenv_loader import load_dotenv

load_dotenv(override=True)

# Import configuration
try:
    from model_mode_config import MODEL_MODE, LOCAL_MODEL_PATHS, ENABLE_MODEL_CACHE, MODEL_SERVICE_CONFIG
except ImportError:
    # Use defaults when config file is missing
    MODEL_MODE = "direct"
    LOCAL_MODEL_PATHS = {}
    ENABLE_MODEL_CACHE = True
    MODEL_SERVICE_CONFIG = {}

print(f"💡 LLM client mode: {MODEL_MODE}")

# ==================== Unified System Message ====================
# All models use the same system message for consistent prompt formatting
SYSTEM_MESSAGE = "You are an automotive testing expert skilled at first summarizing test approaches from given test cases, then generating new test cases based on those approaches."

# ==================== Service mode configuration ====================

deepseek_client = None
dashscope_client = None
siliconflow_client = None
local_model_service_clients = {}


def _get_deepseek_client() -> OpenAI:
    global deepseek_client
    if deepseek_client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("Missing environment variable DEEPSEEK_API_KEY")
        deepseek_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    return deepseek_client


def _get_dashscope_client() -> OpenAI:
    global dashscope_client
    if dashscope_client is None:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("Missing environment variable DASHSCOPE_API_KEY")
        dashscope_client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    return dashscope_client


def _get_siliconflow_client() -> OpenAI:
    global siliconflow_client
    if siliconflow_client is None:
        # 1. Load and validate API keys
        keys = os.getenv("SILICONFLOW_API_KEYS")
        api_keys = [k.strip() for k in (keys or "").split(",") if k.strip()]
        if not api_keys:
            raise ValueError("Missing environment variable SILICONFLOW_API_KEYS (comma-separated)")
        
        proxy = os.getenv("SILICONFLOW_PROXY")
        http_client = httpx.Client(
            proxy=proxy if proxy else None,
            timeout=httpx.Timeout(120.0, connect=10.0, read=90.0),
        )
        
        siliconflow_client = OpenAI(
            api_key=random.choice(api_keys), 
            base_url="https://api.siliconflow.cn/v1",
            http_client=http_client,
        )
        
    return siliconflow_client


def _get_local_model_service_client(model_name: str) -> OpenAI:
    if model_name in local_model_service_clients:
        return local_model_service_clients[model_name]

    service_conf = MODEL_SERVICE_CONFIG.get(model_name)
    if not service_conf:
        raise ValueError(f"Local model service not configured: {model_name}")

    host = service_conf.get("host", "127.0.0.1")
    port = service_conf.get("port")
    api_key = service_conf.get("api_key", "EMPTY")
    if not port:
        raise ValueError(f"Local model service port not configured: {model_name}")

    base_url = f"http://{host}:{port}/v1"
    client = OpenAI(api_key=api_key, base_url=base_url)
    local_model_service_clients[model_name] = client
    return client

# ==================== Direct mode configuration ====================

if MODEL_MODE == "direct":
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    try:
        from peft import PeftModel
        PEFT_AVAILABLE = True
    except ImportError:
        PEFT_AVAILABLE = False
        print("⚠️  peft is not installed; LoRA models will not be available")
        print("   Install with: pip install peft")
    
    # Model cache
    _model_cache = {}
    _tokenizer_cache = {}
    
    def load_local_model(model_name):
        """Load a local model (full model or LoRA)."""
        import os
        
        # Check cache
        if ENABLE_MODEL_CACHE and model_name in _model_cache:
            print(f"  ✓ Loading model from cache")
            return _model_cache[model_name], _tokenizer_cache[model_name]
        
        model_config = LOCAL_MODEL_PATHS.get(model_name)
        if not model_config:
            raise ValueError(f"Model path not configured: {model_name}")
        
        # Backward-compatible config (string path)
        if isinstance(model_config, str):
            model_config = {"path": model_config, "type": "full"}
        
        model_path = model_config["path"]
        model_type = model_config.get("type", "full")
        
        # Verify path exists
        if not os.path.exists(model_path):
            raise ValueError(f"Model path does not exist: {model_path}")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"  📥 Loading model...")
        print(f"     Type: {model_type}")
        print(f"     Path: {model_path}")
        print(f"     Device: {device}")
        
        # GPU info
        if device == "cuda":
            print(f"     GPU: {torch.cuda.get_device_name(0)}")
            print(f"     VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            print(f"     ⚠️  No GPU detected; using CPU mode (slower)")
            print(f"     💡 If you have a GPU, install the CUDA build of PyTorch:")
        
        try:
            if model_type == "lora":
                # LoRA model loading
                if not PEFT_AVAILABLE:
                    raise ImportError("peft is required: pip install peft")
                
                base_model_path = model_config.get("base_model")
                if not base_model_path:
                    raise ValueError(f"LoRA model requires base_model path")
                
                if not os.path.exists(base_model_path):
                    raise ValueError(f"Base model path does not exist: {base_model_path}")
                
                print(f"     Base model: {base_model_path}")
                
                # 1. Load base model (offload when VRAM is limited)
                print(f"  📥 Loading base model...")
                import tempfile
                offload_folder = tempfile.mkdtemp()  # Temporary offload directory
                
                base_model = AutoModelForCausalLM.from_pretrained(
                    base_model_path,
                    trust_remote_code=True,
                    local_files_only=True,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                    device_map="auto" if device == "cuda" else None,
                    offload_folder=offload_folder,
                    offload_state_dict=True,
                    low_cpu_mem_usage=True
                )
                
                # 2. Load LoRA adapter
                print(f"  📥 Loading LoRA adapter...")
                model = PeftModel.from_pretrained(
                    base_model,
                    model_path,
                    local_files_only=True
                )
                
                # 3. Load tokenizer (prefer LoRA dir, else base model)
                if os.path.exists(os.path.join(model_path, "tokenizer_config.json")):
                    tokenizer = AutoTokenizer.from_pretrained(
                        model_path,
                        trust_remote_code=True,
                        local_files_only=True
                    )
                else:
                    tokenizer = AutoTokenizer.from_pretrained(
                        base_model_path,
                        trust_remote_code=True,
                        local_files_only=True
                    )
                
            else:
                # Full model loading
                tokenizer = AutoTokenizer.from_pretrained(
                    model_path,
                    trust_remote_code=True,
                    local_files_only=True
                )
                
                model = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    trust_remote_code=True,
                    local_files_only=True,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                    device_map="auto" if device == "cuda" else None,
                    low_cpu_mem_usage=True
                )
            
            if device == "cpu" and not torch.cuda.is_available():
                model = model.to(device)
            
            model.eval()
            
            # Cache model
            if ENABLE_MODEL_CACHE:
                _model_cache[model_name] = model
                _tokenizer_cache[model_name] = tokenizer
            
            print(f"  ✓ Model loaded successfully")
            
            return model, tokenizer
            
        except Exception as e:
            print(f"  ❌ Model load failed: {str(e)}")
            print(f"  💡 Please check:")
            print(f"     1. Model path is correct: {model_path}")
            if model_type == "lora":
                print(f"     2. Base model path is correct")
                print(f"     3. peft is installed: pip install peft")
            else:
                print(f"     2. Required model files exist (config.json, model.safetensors, etc.)")
            print(f"     4. Read permissions are available")
            raise
    
    def generate_with_local_model(prompt, model_name, max_tokens=2048, temperature=0.01):
        """Generate text with a local model."""
        model, tokenizer = load_local_model(model_name)
        device = next(model.parameters()).device
        
        # Build messages (unified system message)
        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt}
        ]
        
        # Apply chat template
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        # Tokenize
        inputs = tokenizer([text], return_tensors="pt").to(device)
        
        # Generate
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                top_p=0.95,
                repetition_penalty=1.1
            )
        
        # Decode
        generated_ids = outputs[0][inputs['input_ids'].shape[1]:]
        response = tokenizer.decode(generated_ids, skip_special_tokens=True)
        
        return response

# ==================== Unified interface ====================

def generate_testcase(prompt, model="deepseek-chat", max_tokens=None):
    """
    Generate test cases.

    Args:
        prompt: Input prompt text
        model: Model identifier (e.g. deepseek-chat, deepseek-reasoner, qwen3-8b)
        max_tokens: Max output tokens (optional; defaults vary by model)

    Returns:
        (generated test case text, elapsed time in seconds)
    """
    try:
        start_time = time.time()

        model_norm = (model or "").strip()
        if model_norm.lower() == "qwen3-8b":
            model_norm = "Qwen3-8B"
        elif model_norm.lower() == "qwen3-32b":
            model_norm = "Qwen3-32B"
        elif model_norm.lower() in ["qwen3-1.7b-critic", "qwen3-1.7b"]:
            model_norm = "Qwen3-1.7B"
        
        # Alibaba Cloud DashScope Qwen3-32B
        if model_norm == "Qwen3-32B":
            messages = [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ]

            if max_tokens is None:
                max_tokens = 8192

            dashscope_model = os.getenv("DASHSCOPE_QWEN3_32B_MODEL", "qwen3-32b")
            print(f"📝 Prompt length: {len(prompt)} characters")
            print(f"☁️  Calling Alibaba Cloud DashScope {dashscope_model} (max_tokens={max_tokens})")
            response = _get_dashscope_client().chat.completions.create(
                model=dashscope_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
                stream=False,
                extra_body={"enable_thinking": False},
            )

            elapsed_time = time.time() - start_time
            content = response.choices[0].message.content
            return content, elapsed_time

        # Alibaba Cloud DashScope Qwen3-8B
        elif model_norm == "Qwen3-8B":
            messages = [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ]

            if max_tokens is None:
                max_tokens = 8192

            dashscope_model = os.getenv("DASHSCOPE_QWEN3_8B_MODEL", "qwen3-8b")
            print(f"📝 Prompt length: {len(prompt)} characters")
            print(f"☁️  Calling Alibaba Cloud DashScope {dashscope_model} (max_tokens={max_tokens})")
            response = _get_dashscope_client().chat.completions.create(
                model=dashscope_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
                stream=False,
                extra_body={"enable_thinking": False},
            )

            elapsed_time = time.time() - start_time
            content = response.choices[0].message.content
            return content, elapsed_time
        
        # DeepSeek always uses online API
        elif model_norm in ["deepseek-chat", "deepseek-reasoner"]:
            messages = [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ]
            
            if model_norm == "deepseek-reasoner":
                api_model = "deepseek-reasoner"
                if max_tokens is None:
                    max_tokens = 4096  # Reasoner needs more tokens
                print(f"🧠 Calling DeepSeek Reasoner (max_tokens={max_tokens})")
            else:
                api_model = "deepseek-chat"
                if max_tokens is None:
                    max_tokens = 2048
                print(f"💬 Calling DeepSeek Chat (max_tokens={max_tokens})")
            
            print(f"📝 Prompt length: {len(prompt)} characters")
            response = _get_deepseek_client().chat.completions.create(
                model=api_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.01,
                stream=False
            )
            elapsed_time = time.time() - start_time
            
            # DeepSeek Reasoner may include reasoning in the response
            content = response.choices[0].message.content
            
            if model_norm == "deepseek-reasoner" and hasattr(response.choices[0].message, 'reasoning_content'):
                reasoning = response.choices[0].message.reasoning_content
                print(f"🤔 Reasoning length: {len(reasoning)} characters")
                
                if not content or content.strip() == "":
                    print(f"⚠️  content is empty; trying to extract from reasoning_content...")
                    
                    import re
                    
                    # Method 1: find JSON object
                    last_brace_start = reasoning.rfind('{')
                    if last_brace_start != -1:
                        potential_json = reasoning[last_brace_start:]
                        
                        try:
                            import json
                            result = json.loads(potential_json)
                            content = potential_json
                            print(f"✅ Extracted JSON from end of reasoning_content (length: {len(content)} characters)")
                        except:
                            json_pattern = r'\{[^{}]*"is_reasonable"[^{}]*"confidence"[^{}]*"reasoning"[^{}]*\}'
                            json_matches = re.finditer(json_pattern, reasoning, re.DOTALL)
                            matches_list = list(json_matches)
                            
                            if matches_list:
                                content = matches_list[-1].group()
                                print(f"✅ Extracted JSON from reasoning_content (length: {len(content)} characters)")
                            else:
                                print(f"❌ Could not extract JSON from reasoning_content")
                                content = reasoning
                    else:
                        print(f"❌ No JSON start marker found")
                        content = reasoning
            
            return content, elapsed_time
        
        # DashScope Qwen models
        elif model_norm in ["qwen-plus", "qwen-turbo", "qwen-max"]:
            messages = [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ]
            
            if max_tokens is None:
                max_tokens = 8192
            
            print(f"📝 Prompt length: {len(prompt)} characters")
            print(f"☁️ Calling DashScope {model} (max_tokens={max_tokens})")
            
            response = _get_dashscope_client().chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.01,
                stream=False,
                extra_body={"enable_thinking": False},
            )
            elapsed_time = time.time() - start_time
            return response.choices[0].message.content, elapsed_time

        # Qwen models: mode-dependent
        elif model_norm in ["Qwen3-4B", "Qwen3-1.7B"]:
            if MODEL_MODE == "service":
                service_conf = MODEL_SERVICE_CONFIG.get(model_norm, {})
                served_model_name = service_conf.get("served_model_name", model_norm)
                lora_name = service_conf.get("lora_name")
                if max_tokens is None:
                    max_tokens = 1536 if model_norm == "Qwen3-4B" else 1024

                client = _get_local_model_service_client(model_norm)
                messages = [
                    {"role": "system", "content": SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ]
                print(f"🧩 Calling local service model {model_norm} ({client.base_url})")
                request_kwargs = {
                    "model": served_model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                    "stream": False,
                }
                if lora_name:
                    request_kwargs["extra_body"] = {
                        "lora_request": {
                            "lora_name": lora_name,
                            "lora_int_id": 1,
                        }
                    }

                try:
                    response = client.chat.completions.create(**request_kwargs)
                    elapsed_time = time.time() - start_time
                    return response.choices[0].message.content, elapsed_time
                except Exception as local_err:
                    print(f"⚠️  Local service call failed ({model_norm}): {type(local_err).__name__}: {local_err}")
                    print(f"🔄  Falling back to Alibaba Cloud DashScope...")
                    fallback_model = os.getenv("DASHSCOPE_FALLBACK_MODEL", "qwen-plus")
                    fb_max_tokens = 8192
                    fb_messages = [
                        {"role": "system", "content": SYSTEM_MESSAGE},
                        {"role": "user", "content": prompt},
                    ]
                    print(f"☁️  Calling DashScope fallback model: {fallback_model} (max_tokens={fb_max_tokens})")
                    fb_response = _get_dashscope_client().chat.completions.create(
                        model=fallback_model,
                        messages=fb_messages,
                        max_tokens=fb_max_tokens,
                        temperature=0.1,
                        stream=False,
                        extra_body={"enable_thinking": False},
                    )
                    elapsed_time = time.time() - start_time
                    print(f"✅  Fallback call succeeded (elapsed: {elapsed_time:.2f}s)")
                    return fb_response.choices[0].message.content, elapsed_time

            if MODEL_MODE == "direct":
                content = generate_with_local_model(prompt, model_norm)
                elapsed_time = time.time() - start_time
                return content, elapsed_time

            raise ValueError(f"Unknown model mode: {MODEL_MODE}")
        
        else:
            raise ValueError(f"Unknown model: {model}")
            
    except Exception as e:
        print(f"❌ LLM call failed (model: {model}): {type(e).__name__}: {str(e)}")
        raise Exception(f"LLM API call failed (model: {model}): {str(e)}")


def clear_model_cache():
    """Clear model cache (direct mode only)."""
    if MODEL_MODE == "direct":
        global _model_cache, _tokenizer_cache
        print("Clearing model cache...")
        _model_cache.clear()
        _tokenizer_cache.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("✓ Cache cleared")
    else:
        print("⚠️ Service mode does not use a local model cache")
