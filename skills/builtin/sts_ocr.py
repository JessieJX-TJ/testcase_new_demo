import io
import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

from dotenv_loader import load_dotenv
from ..base import BaseSkill
from .sts_text import normalize_deep, normalize_mojibake


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(str(PROJECT_ROOT / ".env"), override=False)

MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "https://mineru.net").rstrip("/")
MINERU_MODEL_VERSION = os.getenv("MINERU_MODEL_VERSION", "vlm")
MINERU_TIMEOUT_SECONDS = int(os.getenv("MINERU_TIMEOUT_SECONDS", "300"))
MINERU_POLL_INTERVAL_SECONDS = float(os.getenv("MINERU_POLL_INTERVAL_SECONDS", "2"))
MINERU_ARTIFACT_ROOT = PROJECT_ROOT / "data" / "uploads" / "sts_mineru"


class STSExtractTextFromPDFSkill(BaseSkill):
    name = "sts.extract_text_from_pdf"
    description = "Extract STS PDF content with MinerU API and return markdown text pages."
    input_schema = {
        "required": [],
        "optional": ["document_id", "pdf_path", "pdf_url", "model_version", "timeout_seconds"],
    }
    output_schema = {"format": "pages"}

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        document_id = input_data.get("document_id") or f"sts_{uuid.uuid4().hex[:12]}"
        pdf_url = (input_data.get("pdf_url") or "").strip()
        pdf_path_value = input_data.get("pdf_path")
        model_version = input_data.get("model_version") or MINERU_MODEL_VERSION
        timeout_seconds = int(input_data.get("timeout_seconds") or MINERU_TIMEOUT_SECONDS)

        if pdf_url:
            mineru_result = self._extract_from_url(pdf_url, model_version, timeout_seconds)
            source_ref = pdf_url
        else:
            pdf_path = Path(pdf_path_value or "")
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF not found: {pdf_path}")
            mineru_result = self._extract_from_local_pdf(pdf_path, document_id, model_version, timeout_seconds)
            source_ref = str(pdf_path)

        markdown, artifacts = self._download_markdown(mineru_result, document_id)
        markdown = normalize_mojibake(markdown)
        self._save_text(Path(artifacts["markdown_path"]), markdown)
        if artifacts.get("extracted_dir"):
            self._repair_extracted_text_files(Path(artifacts["extracted_dir"]))
        self._save_json(artifacts["mineru_result_json"], mineru_result)
        pages = [{
            "page": 1,
            "text": markdown,
            "source": "mineru",
            "format": "markdown",
            "artifact_path": artifacts.get("markdown_path"),
        }]
        return {
            "document_id": document_id,
            "pdf_path": str(pdf_path_value or ""),
            "pdf_url": pdf_url,
            "pages": pages,
            "ocr_engine": "mineru",
            "source_ref": source_ref,
            "mineru_artifacts": artifacts,
            "skill": self.name,
        }

    def _extract_from_url(self, pdf_url: str, model_version: str, timeout_seconds: int) -> Dict[str, Any]:
        payload = {"url": pdf_url, "model_version": model_version}
        created = self._request_json("POST", "/api/v4/extract/task", json_payload=payload)
        task_id = self._find_first(created, ("task_id", "taskId", "id"))
        if not task_id:
            raise RuntimeError(f"MinerU did not return task_id: {self._brief(created)}")
        return self._poll_result(
            endpoints=[
                f"/api/v4/extract/task/{task_id}",
                f"/api/v4/extract-result/{task_id}",
                f"/api/v4/extract-results/task/{task_id}",
            ],
            timeout_seconds=timeout_seconds,
            label=f"task {task_id}",
        )

    def _extract_from_local_pdf(
        self,
        pdf_path: Path,
        document_id: str,
        model_version: str,
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        upload_payload = {
            "model_version": model_version,
            "files": [{
                "name": pdf_path.name,
                "data_id": document_id,
                "is_ocr": True,
            }],
        }
        created = self._request_json("POST", "/api/v4/file-urls/batch", json_payload=upload_payload)
        upload_url = self._find_first(
            created,
            ("upload_url", "uploadUrl", "file_urls", "fileUrls", "url", "put_url", "putUrl"),
        )
        batch_id = self._find_first(created, ("batch_id", "batchId", "id"))
        if not upload_url:
            raise RuntimeError(f"MinerU did not return upload url: {self._brief(created)}")
        self._upload_file(upload_url, pdf_path)
        if not batch_id:
            raise RuntimeError(f"MinerU did not return batch_id: {self._brief(created)}")
        return self._poll_result(
            endpoints=[
                f"/api/v4/extract-results/batch/{batch_id}",
                f"/api/v4/file-urls/batch/{batch_id}",
                f"/api/v4/extract-result/batch/{batch_id}",
            ],
            timeout_seconds=timeout_seconds,
            label=f"batch {batch_id}",
        )

    def _request_json(
        self,
        method: str,
        path: str,
        json_payload: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        url = path if path.startswith("http") else f"{MINERU_BASE_URL}{path}"
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token()}"
        response = requests.request(method, url, headers=headers, json=json_payload, timeout=60)
        if response.status_code >= 400:
            raise RuntimeError(f"MinerU {method} {path} failed: {response.status_code} {response.text[:600]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"MinerU returned non-json response from {path}: {response.text[:600]}") from exc
        code = str(payload.get("code", "0"))
        if code not in {"0", "200", "success"} and payload.get("success") is False:
            raise RuntimeError(f"MinerU returned error from {path}: {self._brief(payload)}")
        return payload

    def _upload_file(self, upload_url: str, pdf_path: Path) -> None:
        with pdf_path.open("rb") as fh:
            response = requests.put(
                upload_url,
                data=fh,
                timeout=120,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"MinerU upload failed: {response.status_code} {response.text[:600]}")

    def _poll_result(self, endpoints: list[str], timeout_seconds: int, label: str) -> Dict[str, Any]:
        start = time.time()
        last_payload: Dict[str, Any] = {}
        while time.time() - start < timeout_seconds:
            for endpoint in endpoints:
                try:
                    payload = self._request_json("GET", endpoint)
                except RuntimeError as exc:
                    if "404" in str(exc) or "405" in str(exc):
                        continue
                    raise
                last_payload = payload
                status = str(self._find_first(payload, ("status", "state", "task_status", "taskStatus")) or "").lower()
                if status in {"failed", "fail", "error", "exception"}:
                    raise RuntimeError(f"MinerU {label} failed: {self._brief(payload)}")
                if self._find_first(payload, ("full_zip_url", "fullZipUrl", "zip_url", "zipUrl", "result_url", "resultUrl", "download_url", "downloadUrl", "file_url", "fileUrl")):
                    return payload
                if status in {"done", "success", "completed", "complete", "finished"}:
                    return payload
            time.sleep(MINERU_POLL_INTERVAL_SECONDS)
        raise TimeoutError(f"MinerU {label} timed out after {timeout_seconds}s. Last response: {self._brief(last_payload)}")

    def _download_markdown(self, mineru_result: Dict[str, Any], document_id: str) -> tuple[str, Dict[str, str]]:
        artifact_dir = MINERU_ARTIFACT_ROOT / document_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "artifact_dir": str(artifact_dir),
            "markdown_path": str(artifact_dir / "content.md"),
            "mineru_result_json": str(artifact_dir / "mineru_result.json"),
        }

        direct_markdown = self._find_first(mineru_result, ("markdown", "md", "content"))
        if isinstance(direct_markdown, str) and len(direct_markdown.strip()) > 80:
                markdown = normalize_mojibake(direct_markdown.strip())
                self._save_text(Path(artifacts["markdown_path"]), markdown)
                return markdown, artifacts

        zip_url = self._find_first(
            mineru_result,
            ("full_zip_url", "fullZipUrl", "zip_url", "zipUrl", "result_url", "resultUrl", "download_url", "downloadUrl", "file_url", "fileUrl"),
        )
        if not zip_url:
            raise RuntimeError(f"MinerU result has no markdown or zip url: {self._brief(mineru_result)}")

        response = requests.get(zip_url, timeout=120)
        if response.status_code in {401, 403}:
            response = requests.get(zip_url, headers={"Authorization": f"Bearer {self._token()}"}, timeout=120)
        if response.status_code >= 400:
            raise RuntimeError(f"MinerU result download failed: {response.status_code} {response.text[:600]}")

        content_type = response.headers.get("Content-Type", "")
        if "zip" not in content_type.lower() and not response.content.startswith(b"PK"):
            text = self._decode_bytes(response.content)
            if text.strip():
                markdown = normalize_mojibake(text.strip())
                raw_path = artifact_dir / "mineru_result.txt"
                self._save_text(raw_path, markdown)
                self._save_text(Path(artifacts["markdown_path"]), markdown)
                artifacts["raw_text_path"] = str(raw_path)
                return markdown, artifacts
            raise RuntimeError("MinerU result download is neither zip nor readable text.")

        zip_path = artifact_dir / "mineru_result.zip"
        zip_path.write_bytes(response.content)
        artifacts["zip_path"] = str(zip_path)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            extract_dir = artifact_dir / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            archive.extractall(extract_dir)
            artifacts["extracted_dir"] = str(extract_dir)
            names = archive.namelist()
            markdown_names = [name for name in names if name.lower().endswith(".md")]
            if markdown_names:
                preferred = sorted(
                    markdown_names,
                    key=lambda name: (
                        0 if any(flag in name.lower() for flag in ("full", "origin", "content")) else 1,
                        len(name),
                    ),
                )[0]
                markdown = normalize_mojibake(self._decode_bytes(archive.read(preferred)).strip())
                self._save_text(Path(artifacts["markdown_path"]), markdown)
                artifacts["source_markdown_in_zip"] = preferred
                return markdown, artifacts

            json_names = [name for name in names if name.lower().endswith(".json")]
            for name in json_names:
                text = self._text_from_json_bytes(archive.read(name))
                if text.strip():
                    markdown = normalize_mojibake(text.strip())
                    self._save_text(Path(artifacts["markdown_path"]), markdown)
                    artifacts["source_json_in_zip"] = name
                    return markdown, artifacts
        raise RuntimeError("MinerU result zip did not contain markdown or readable json text.")

    def _text_from_json_bytes(self, raw: bytes) -> str:
        try:
            payload = json.loads(self._decode_bytes(raw))
        except Exception:
            return ""
        values: list[str] = []
        for item in self._walk(payload):
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("markdown")
                if isinstance(text, str) and text.strip():
                    values.append(text.strip())
        return "\n".join(values)

    def _repair_extracted_text_files(self, extract_dir: Path) -> None:
        for path in extract_dir.rglob("*"):
            if path.suffix.lower() not in {".md", ".json", ".txt"}:
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if path.suffix.lower() == ".json":
                try:
                    payload = json.loads(raw)
                    repaired = json.dumps(normalize_deep(payload), ensure_ascii=False, indent=2)
                except Exception:
                    repaired = normalize_mojibake(raw)
            else:
                repaired = normalize_mojibake(raw)
            if repaired != raw:
                path.write_text(repaired, encoding="utf-8")

    def _token(self) -> str:
        load_dotenv(str(PROJECT_ROOT / ".env"), override=False)
        token = (
            os.getenv("MINERU_API_TOKEN")
            or os.getenv("MINERU_TOKEN")
            or os.getenv("MINERU_API_KEY")
            or ""
        ).strip()
        if not token:
            raise RuntimeError("Missing MinerU token. Please set MINERU_API_TOKEN in .env or environment.")
        return token

    def _find_first(self, payload: Any, keys: Iterable[str]) -> Optional[str]:
        key_set = {key.lower() for key in keys}
        for item in self._walk(payload):
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if key.lower() in key_set and isinstance(value, str) and value.strip():
                    return value.strip()
                if key.lower() in key_set and isinstance(value, list):
                    for sub_value in value:
                        if isinstance(sub_value, str) and sub_value.strip():
                            return sub_value.strip()
                        if isinstance(sub_value, dict):
                            nested = self._find_first(sub_value, keys)
                            if nested:
                                return nested
                if key.lower() in key_set and isinstance(value, (int, float)):
                    return str(value)
        return None

    def _walk(self, payload: Any) -> Iterable[Any]:
        yield payload
        if isinstance(payload, dict):
            for value in payload.values():
                yield from self._walk(value)
        elif isinstance(payload, list):
            for value in payload:
                yield from self._walk(value)

    def _decode_bytes(self, raw: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")

    def _save_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _save_json(self, path_value: str, payload: Dict[str, Any]) -> None:
        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _brief(self, payload: Any) -> str:
        try:
            text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            text = str(payload)
        return text[:1200]
