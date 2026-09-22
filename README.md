# TestCase_Agent

TestCase_Agent is an intelligent test-case generation system for automotive / vehicle-side functional testing. The project provides a Web UI and APIs via Flask, and combines RAG, knowledge-graph retrieval, vector search, and local large-model services to generate test cases from requirements. It also supports reverse case generation from existing cases, classification browsing, quality evaluation, and Excel export.

> This Git repository is maintained for **source-native deployment**. `Dockerfile` and `docker-compose.yml` are kept only as a reference to the original server runtime setup and are **not** the currently recommended deployment entry point.

## Repository Scope and External Assets

The repository stores only application source code, frontend assets, Skill definitions, dependency manifests, and secret-free configuration templates. It does **not** store the following runtime assets:

- `.env`, API keys, Neo4j passwords, and other secrets;
- Qwen base models and LoRA weights;
- Neo4j data directories and database dumps;
- PDFs, Excel files, images, FAISS indexes, and pipeline intermediate artifacts;
- Logs, uploads, human-review records, and runtime caches.

Models should be archived separately outside the repository with SHA-256 recorded. After extraction, keep the following directory layout:

```text
models/
├── Qwen3-4B/
└── Qwen3-1.7B/
sft-model/
├── qwen3-4b-sft-gen/
└── qwen3-1.7b-sft-critic/
```

Before the first run, copy the configuration template and fill in secrets on the local machine only:

```bash
cp .env.example .env
chmod 600 .env
```

Python 3.10/3.11 is recommended. A native environment requires installing dependencies for both the main app and the knowledge-graph workbench:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
pip install -r 7.30_kg/requirements.txt
```

Native startup uses two processes:

```bash
# Terminal 1: knowledge-graph Streamlit workbench
cd 7.30_kg
streamlit run app.py --server.port 8501 --server.address 0.0.0.0

# Terminal 2: Flask unified frontend (start from repo root)
python app.py
```

Flask listens on `4000` by default and embeds the Streamlit workbench on `8501` via `KG_WORKBENCH_URL`.

> For the unified startup of the knowledge-graph frontend and the vehicle test-case frontend, prefer: [README_unified_frontend.md](README_unified_frontend.md).

## Main Features

- Generate test cases from requirements: enter natural-language requirements and produce structured test cases.
- RAG-enhanced generation: improve quality with Neo4j knowledge graphs, FAISS vector indexes, and similar cases.
- Local model inference: run Qwen3 generation and evaluation models via vLLM.
- Reverse test-case generation: select original cases by test type, action, or expected behavior to generate reverse / exception scenarios.
- Test-case quality evaluation: use a critic model to analyze completeness, soundness, and coverage.
- Streaming generation and refinement: return progress in real time, with auto-improve and human refine.
- Result export: export generated results to Excel.

## Tech Stack

- Backend: Flask, Flask-CORS
- Data processing: pandas, openpyxl, numpy
- Model calls: OpenAI SDK-compatible APIs, httpx, vLLM
- Retrieval augmentation: Neo4j, FAISS
- Local models: Qwen3, LoRA fine-tuned models
- Frontend: HTML, CSS, vanilla JavaScript
- Deployment: Python native deployment; Docker files are reference-only for the original server setup

## Project Structure

```text
TestCase_Agent/
├── app.py                         # Flask entry: page routes and APIs
├── case_generator.py              # Case classification, reverse generation, batch generation
├── llm_client.py                  # LLM client for local vLLM or compatible APIs
├── embedding_client.py            # Embedding client
├── kg_retriever_structured.py     # Structured knowledge-graph retrieval
├── kg_retriever_mst.py            # MST knowledge-graph retrieval
├── entity_Vector_Index.py         # Entity vector index logic
├── prompt_builder.py              # Prompt construction
├── testcase_formatter.py          # Test-case formatting
├── utils.py                       # RAG pipeline and shared utilities
├── config.py                      # Neo4j, retrieval, and embedding config
├── model_mode_config.py           # Local model and model-service config
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Application image build file
├── docker-compose.yml             # One-shot Neo4j, model services, and Flask app
├── data/
│   └── TestCase_v2.json           # Original test-case data
├── cache/
│   └── vector_index*/             # FAISS vector index cache
├── neo4j/
│   └── *.dump                     # Neo4j graph database dump files
├── models/                        # Qwen base model directory
├── sft-model/                     # LoRA / fine-tuned model directory
├── templates/                     # Flask page templates
├── static/                        # Frontend static assets
└── outputs/                       # Project notes or export artifacts
```

## Deployment

This project recommends one-shot deployment with `docker-compose up -d`. That command starts all required services from `docker-compose.yml`. You do not need to start the Neo4j container separately, and you do not need to recreate a Python environment on the host.

One-shot startup brings up:

- `neo4j`: knowledge-graph database
- `qwen3-4b-service`: Qwen3-4B case-generation model service
- `qwen3-17b-service`: Qwen3-1.7B case-evaluation / critic model service
- `app`: Flask Web application

## Pre-deployment Checklist

### 1. Prepare the base environment

The host needs:

- Docker
- docker-compose
- NVIDIA drivers
- NVIDIA Container Toolkit

Model services use the GPU; confirm containers can access the GPU.

### 2. Confirm model and data files

Before deploying, ensure these directories and files exist:

```text
models/Qwen3-4B
models/Qwen3-1.7B
sft-model/qwen3-4b-sft-gen
sft-model/qwen3-1.7b-sft-critic
data/TestCase_v2.json
cache/vector_index
cache/vector_index_(text-embedding-v4)
```

If LoRA directory names differ, update `docker-compose.yml` and `model_mode_config.py` accordingly.

### 3. Configure `.env`

Provide a `.env` file in the project root. Example:

```env
# Neo4j
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Local model service mode
MODEL_MODE=service

# Qwen3-4B generation model service
QWEN3_4B_SERVICE_HOST=127.0.0.1
QWEN3_4B_SERVICE_PORT=9004
QWEN3_4B_SERVED_MODEL_NAME=Qwen3-4B
QWEN3_4B_LORA_NAME=gen

# Qwen3-1.7B evaluation model service
QWEN3_17B_SERVICE_HOST=127.0.0.1
QWEN3_17B_SERVICE_PORT=9017
QWEN3_17B_SERVED_MODEL_NAME=Qwen3-1.7B
QWEN3_17B_LORA_NAME=critic
LOCAL_MODEL_API_KEY=EMPTY

# Embedding configuration
DASHSCOPE_API_KEY=your_dashscope_key
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_MODEL_NAME=text-embedding-v4
EMBEDDING_DIM=1024

# Optional: proxies
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=localhost,127.0.0.1,neo4j,api.siliconflow.cn,dashscope.aliyuncs.com
```

Note: LLM generation and evaluation use local vLLM services. Embedding still defaults to the DashScope OpenAI-compatible API, so `DASHSCOPE_API_KEY` is usually still required.

## One-shot Startup

From the project root:

```bash
docker-compose up -d
```

This starts all required services: Neo4j, both local model services, and the Flask app.

On first start, if the app image is missing locally, docker-compose builds the `app` image from `Dockerfile`. Later starts do not require recreating a host Python environment or running `pip install` manually.

Check service status:

```bash
docker-compose ps
```

View application logs:

```bash
docker-compose logs -f app
```

View model-service logs:

```bash
docker-compose logs -f qwen3-4b-service
docker-compose logs -f qwen3-17b-service
```

Stop services:

```bash
docker-compose down
```

## Access URLs

The app listens on port `4000` by default:

```text
http://SERVER_IP:4000/
```

Local access:

```text
http://127.0.0.1:4000/
```

The home page is now the unified Pipeline entry: stage 1 embeds the knowledge-graph workbench; later stages continue with test-case generation, batch reverse generation, and the Skills platform. The knowledge-graph workbench is served by a separate Streamlit process, default URL:

```text
http://127.0.0.1:8501
```

If the knowledge-graph service is on another host, set this before starting Flask/Docker:

```env
KG_WORKBENCH_URL=http://SERVER_IP:8501
```

The knowledge-graph frontend can also be started alone in a prepared `zjkg` environment:

```bash
cd /home/yh/TestCase_Agent_0730/7.30_kg
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Neo4j Web admin:

```text
http://SERVER_IP:7474
```

Local access:

```text
http://127.0.0.1:7474
```

## Page Entry Points

- Home: `/` — unified Pipeline shell; defaults to the knowledge-graph workbench iframe
- Test type / expected-behavior classification: `/type-expected-classification`
- Skills platform: `/skills-platform`
- STS document generation: `/sts-generation`

The project also includes `templates/case_generation.html` and related static assets for generation by test type and action. To expose that page directly, add the corresponding route in `app.py`.

## Main APIs

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/pipeline/config` | Get unified Pipeline frontend config (e.g. KG workbench URL) |
| `POST` | `/generate` | Generate test cases from requirements |
| `POST` | `/generate-stream` | Stream test-case generation |
| `POST` | `/auto-improve-stream` | Automatically improve generation results |
| `POST` | `/refine-stream` | Refine cases from user feedback |
| `POST` | `/api/evaluate-testcase` | Evaluate test-case quality |
| `GET` | `/api/test-cases/by-type-expected` | Query cases by test type and expected behavior |
| `GET` | `/api/test-cases/by-action` | Query cases by test type and action |
| `POST` | `/api/generate-reverse-from-expected` | Generate reverse cases from expected behavior |
| `POST` | `/api/test-cases/generate-reverse` | Batch-generate reverse test cases |
| `GET` | `/api/test-cases/generation-status/<task_id>` | Query batch generation task status |
| `GET` | `/api/test-cases/reverse-results/<task_id>` | Get reverse-generation results |
| `GET` | `/api/test-cases/export-excel/<task_id>` | Export batch results to Excel |
| `POST` | `/api/export-generated-cases-excel` | Export frontend-generated results to Excel |

## Data and Indexes

- Original case data: `data/TestCase_v2.json`
- Vector index cache: `cache/vector_index`, `cache/vector_index_(text-embedding-v4)`
- Neo4j dumps: `neo4j/cardb.dump`, `neo4j/neo4j.dump`

Structured retrieval parameters can be tuned in `config.py`:

- `index_dir`: vector index directory
- `max_hops`: max hops in the knowledge graph
- `threshold`: similarity threshold
- `max_neighbors_per_testcase`: max neighbors per test case
- `max_context_testcases`: number of context cases injected at generation time

## Development and Debugging

For deploy-only runs you usually do not need a host Python environment. Install dependencies manually only for local development, debugging, or running Flask outside containers.

Local development example:

```bash
conda create -n TestCase_Agent python=3.10 -y
conda activate TestCase_Agent
pip install -r requirements.txt
python app.py
```

Syntax check:

```bash
python -m py_compile app.py case_generator.py config.py embedding_client.py llm_client.py utils.py
```

JSON parsing verification:

```bash
python test_json_parsing.py
```

## FAQ

### 1. Does `docker-compose up -d` start only Neo4j?

No. Running `docker-compose up -d` starts every service defined in `docker-compose.yml`, including Neo4j, both model services, and the Flask app. Only `docker-compose up -d neo4j` starts Neo4j alone.

### 2. Do I need to recreate a Python environment on the host?

Not for deployment. The app runs in the `app` container; Python dependencies are handled by the image. The host only needs Docker, a GPU container runtime, project files, model files, and `.env`.

### 3. Docker build cannot find `pip_packages`

The current Dockerfile is designed for offline installs from `/tmp/pip_packages`. Ensure a `pip_packages` offline dependency directory exists at the project root. For online installs, change the Dockerfile install command to:

```dockerfile
RUN pip install -r requirements.txt
```

### 4. App cannot connect to Neo4j

The `app` service uses `network_mode: "host"`, so prefer this in `.env`:

```env
NEO4J_URI=bolt://127.0.0.1:7687
```

Also confirm the `neo4j` container is running and port `7687` is not occupied.

### 5. Model services unavailable

Confirm both model containers are healthy:

```bash
docker-compose ps
docker-compose logs -f qwen3-4b-service
docker-compose logs -f qwen3-17b-service
```

Also check that model directories are complete and that model/LoRA paths in `docker-compose.yml` match the actual layout.

### 6. Embedding initialization fails

Embedding defaults to the DashScope OpenAI-compatible API and requires `DASHSCOPE_API_KEY`. If you change the embedding model, also confirm `EMBEDDING_MODEL_NAME`, `DASHSCOPE_EMBEDDING_MODEL`, and existing FAISS index dimensions stay consistent.

## Development Notes

- Page templates live in `templates/`; static assets in `static/`.
- The main RAG flow is `rag_pipeline` in `utils.py`.
- Generation and evaluation models are called through `llm_client.py`.
- Prefer adding new APIs in `app.py` and keeping JSON response shapes stable.
- When changing retrieval strategy, tune parameters in `config.py` first, then change retriever implementations.
