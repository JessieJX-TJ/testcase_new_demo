from __future__ import annotations

import contextlib
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

from agentic_kg.paths import INCREMENTAL_SCRIPT_PATH, import_module_from_path, load_json


_INCREMENTAL = None


def load_incremental_module() -> Any:
    global _INCREMENTAL
    if _INCREMENTAL is None:
        _INCREMENTAL = import_module_from_path("agentic_incremental_extract", INCREMENTAL_SCRIPT_PATH)
    return _INCREMENTAL


def _capture_stdout(func, *args, **kwargs) -> List[str]:
    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        func(*args, **kwargs)
    return [line for line in buffer.getvalue().splitlines() if line.strip()]


def run_incremental_analysis(
    baseline_excel: str | Path,
    candidate_excel: str | Path,
    domain: str,
    domain_dir: str | Path,
    overwrite_current: bool = True,
) -> Dict[str, Any]:
    module = load_incremental_module()
    logs: List[str] = []
    logs.extend(
        _capture_stdout(
            module.initialize_current_baseline,
            excel_path=str(baseline_excel),
            domain=domain,
            domain_dir=str(domain_dir),
            overwrite=overwrite_current,
        )
    )
    logs.extend(
        _capture_stdout(
            module.process_candidate_excel,
            excel_path=str(candidate_excel),
            domain=domain,
            domain_dir=str(domain_dir),
        )
    )
    domain_path = Path(domain_dir)
    pending_add = module.load_jsonl(str(domain_path / "pending_add_triples.jsonl"))
    pending_remove = module.load_jsonl(str(domain_path / "pending_remove_triples.jsonl"))
    pending_changed = module.load_jsonl(str(domain_path / "pending_changed_triples.jsonl"))
    return {
        "domain_dir": str(domain_path),
        "logs": logs,
        "pending_add": pending_add,
        "pending_remove": pending_remove,
        "pending_changed": pending_changed,
        "summary": {
            "new_cases": sum(1 for item in pending_add if item.get("record_type") == "case_marker"),
            "add_triples": sum(1 for item in pending_add if item.get("record_type") == "triple"),
            "remove_triples": len(pending_remove),
            "changed_pairs": len(pending_changed),
        },
    }
