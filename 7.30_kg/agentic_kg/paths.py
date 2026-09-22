from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


AGENTIC_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENTIC_ROOT.parent

# ── 路径定义（新位置优先，旧位置作为 fallback） ──

# Excel 路径
_EXCEL_ROOT_NEW = PROJECT_ROOT / "pipelines" / "excel"
_EXCEL_ROOT_CURRENT = PROJECT_ROOT
_EXCEL_ROOT_OLD = PROJECT_ROOT / "excel文件处理"
EXCEL_ROOT = (
    _EXCEL_ROOT_NEW
    if _EXCEL_ROOT_NEW.exists()
    else _EXCEL_ROOT_CURRENT
    if (_EXCEL_ROOT_CURRENT / "extractor.py").exists()
    else _EXCEL_ROOT_OLD
)
EXCEL_INPUT_ROOT = (EXCEL_ROOT / "input") if (EXCEL_ROOT / "input").exists() else (_EXCEL_ROOT_OLD / "input")

_VISUAL_NEW = _EXCEL_ROOT_NEW / "extractor.py"
_VISUAL_CURRENT = _EXCEL_ROOT_CURRENT / "extractor.py"
_VISUAL_OLD = _EXCEL_ROOT_OLD / "Visualize" / "extractor.py"
VISUAL_EXTRACTOR_PATH = (
    _VISUAL_NEW
    if _VISUAL_NEW.exists()
    else _VISUAL_CURRENT
    if _VISUAL_CURRENT.exists()
    else _VISUAL_OLD
)

_INCR_NEW = _EXCEL_ROOT_NEW / "incremental.py"
_INCR_CURRENT = _EXCEL_ROOT_CURRENT / "incremental.py"
_INCR_OLD = _EXCEL_ROOT_OLD / "增量更新" / "extract.py"
INCREMENTAL_SCRIPT_PATH = (
    _INCR_NEW
    if _INCR_NEW.exists()
    else _INCR_CURRENT
    if _INCR_CURRENT.exists()
    else _INCR_OLD
)

# PDF 路径
_PDF_ROOT_NEW = PROJECT_ROOT / "pipelines" / "pdf"
_PDF_ROOT_CURRENT = PROJECT_ROOT / "pdf_pipeline"
_PDF_ROOT_OLD = PROJECT_ROOT / "pdf_kg_pipeline"
PDF_ROOT = (
    _PDF_ROOT_NEW
    if _PDF_ROOT_NEW.exists()
    else _PDF_ROOT_CURRENT
    if _PDF_ROOT_CURRENT.exists()
    else _PDF_ROOT_OLD
)

PDF_CONFIG_PATH = PDF_ROOT / "config" / "pipeline_config.json"

PDF_MANIFEST_PATH = PDF_ROOT / "data" / "manifests" / "image_manifest.json"
MEMORY_ROOT = AGENTIC_ROOT / "memory"
SKILLS_ROOT = AGENTIC_ROOT / "skills"
PENDING_SKILLS_ROOT = SKILLS_ROOT / "pending"
SKILL_REGISTRY_PATH = MEMORY_ROOT / "skill_registry.json"
WORKSPACE_HOME = MEMORY_ROOT / "paddle_home"
WORKSPACE_CACHE_ROOT = MEMORY_ROOT / "cache"


def ensure_runtime_dirs() -> None:
    for path in [MEMORY_ROOT, SKILLS_ROOT, PENDING_SKILLS_ROOT, WORKSPACE_HOME, WORKSPACE_CACHE_ROOT]:
        path.mkdir(parents=True, exist_ok=True)


def _workspace_alias_root() -> Path:
    if os.name != "nt":
        return PROJECT_ROOT
    for drive in ["K:", "L:", "M:", "N:", "Z:"]:
        root = Path(f"{drive}\\")
        agentic_dir = root / "agentic_kg"
        if root.exists():
            if agentic_dir.exists():
                return root
            continue
        try:
            subprocess.run(
                ["subst", drive, str(PROJECT_ROOT)],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            continue
        if agentic_dir.exists():
            return root
    return PROJECT_ROOT


def configure_workspace_environment() -> None:
    """Keep third-party runtime caches inside the current project workspace."""
    ensure_runtime_dirs()
    alias_root = _workspace_alias_root()
    alias_memory_root = alias_root / "agentic_kg" / "memory"
    workspace_home = str(alias_memory_root / "paddle_home")
    os.environ["HOME"] = workspace_home
    os.environ["USERPROFILE"] = workspace_home
    os.environ["XDG_CACHE_HOME"] = str(alias_memory_root / "cache")
    os.environ["PADDLE_HOME"] = str(alias_memory_root / "cache" / "paddle")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")


configure_workspace_environment()

# ── API Key ──
os.environ.setdefault("DASHSCOPE_API_KEY", "")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_local_env(env_path: Path | None = None) -> None:
    env_file = env_path or PDF_ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def import_module_from_path(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_pdf_src_to_path() -> None:
    # New location: modules directly under pipelines/pdf/
    pdf_src = str(PDF_ROOT)
    if pdf_src not in sys.path:
        sys.path.insert(0, pdf_src)
    # Legacy location: modules under pdf_kg_pipeline/src/
    legacy_src = str(PDF_ROOT / "src")
    if legacy_src not in sys.path:
        sys.path.insert(0, legacy_src)


def resolve_project_path(path_text: str | os.PathLike[str]) -> Path:
    text = str(path_text)
    candidate = Path(text)
    if candidate.exists():
        return candidate
    linux_prefix = "/home/dt/智己项目"
    if text.startswith(linux_prefix):
        mapped = PROJECT_ROOT / text[len(linux_prefix) :].lstrip("/\\")
        if mapped.exists():
            return mapped
    marker = "智己项目/"
    normalized = text.replace("\\", "/")
    if marker in normalized:
        mapped = PROJECT_ROOT / normalized.split(marker, 1)[1]
        if mapped.exists():
            return mapped
    return candidate


def sanitize_filename(value: str) -> str:
    bad_chars = '<>:"/\\|?*'
    cleaned = "".join("_" if char in bad_chars else char for char in value).strip()
    return cleaned or "unnamed"
