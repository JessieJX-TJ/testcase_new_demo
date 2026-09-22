import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = PROJECT_ROOT / "data" / "review"
PENDING_FILE = REVIEW_DIR / "pending_cases.json"
ACCEPTED_FILE = REVIEW_DIR / "accepted_cases.json"
REJECTED_FILE = REVIEW_DIR / "rejected_cases.json"
DOCUMENTS_FILE = REVIEW_DIR / "sts_documents.json"


class ReviewStore:
    def __init__(self):
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        for path in [PENDING_FILE, ACCEPTED_FILE, REJECTED_FILE, DOCUMENTS_FILE]:
            if not path.exists():
                path.write_text("[]", encoding="utf-8")

    def save_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        docs = self._read(DOCUMENTS_FILE)
        docs = [doc for doc in docs if doc.get("document_id") != document.get("document_id")]
        docs.append(document)
        self._write(DOCUMENTS_FILE, docs)
        return document

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        for doc in self._read(DOCUMENTS_FILE):
            if doc.get("document_id") == document_id:
                return doc
        return None

    def add_pending_cases(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pending = self._read(PENDING_FILE)
        now = datetime.now().isoformat()
        prepared = []
        for case in cases:
            item = dict(case)
            item.setdefault("case_id", f"case_{uuid.uuid4().hex[:12]}")
            item.setdefault("created_at", now)
            item["status"] = "pending_review"
            prepared.append(item)
        pending.extend(prepared)
        self._write(PENDING_FILE, pending)
        return prepared

    def list_cases(self, status: str = "pending") -> List[Dict[str, Any]]:
        if status == "accepted":
            return self._read(ACCEPTED_FILE)
        if status == "rejected":
            return self._read(REJECTED_FILE)
        return self._read(PENDING_FILE)

    def review_case(self, case_id: str, decision: str, reviewer: str = "", comment: str = "") -> Dict[str, Any]:
        if decision not in ("accepted", "rejected"):
            raise ValueError("decision must be accepted or rejected")
        pending = self._read(PENDING_FILE)
        remaining = []
        target = None
        for case in pending:
            if case.get("case_id") == case_id:
                target = case
            else:
                remaining.append(case)
        if not target:
            raise KeyError(f"case not found in pending review: {case_id}")

        target["status"] = decision
        target["reviewer"] = reviewer
        target["review_comment"] = comment
        target["review_time"] = datetime.now().isoformat()
        dest_file = ACCEPTED_FILE if decision == "accepted" else REJECTED_FILE
        dest = self._read(dest_file)
        dest.append(target)
        self._write(PENDING_FILE, remaining)
        self._write(dest_file, dest)
        return target

    def save_reviewed_case(self, case: Dict[str, Any], decision: str, reviewer: str = "", comment: str = "") -> Dict[str, Any]:
        if decision not in ("accepted", "rejected"):
            raise ValueError("decision must be accepted or rejected")
        item = dict(case or {})
        item.setdefault("case_id", f"case_{uuid.uuid4().hex[:12]}")
        item.setdefault("created_at", datetime.now().isoformat())
        item["status"] = decision
        item["reviewer"] = reviewer
        item["review_comment"] = comment
        item["review_time"] = datetime.now().isoformat()
        dest_file = ACCEPTED_FILE if decision == "accepted" else REJECTED_FILE
        dest = self._read(dest_file)
        dest.append(item)
        self._write(dest_file, dest)
        return item

    def _read(self, path: Path) -> List[Dict[str, Any]]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write(self, path: Path, data: List[Dict[str, Any]]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


review_store = ReviewStore()
