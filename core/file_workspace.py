from __future__ import annotations
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

class FileWorkspace:
    ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".txt", ".json"}

    def __init__(self, root_dir: str):
        self.root = Path(root_dir).resolve()
        self.uploads_dir = (self.root / "uploads").resolve()
        self.artifacts_dir = (self.root / "artifacts").resolve()
        self.index_path = (self.root / "files_index.json").resolve()
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({"files": [], "artifacts": []})

    def _safe_name(self, file_name: str) -> str:
        name = os.path.basename(file_name or "").strip()
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        return name or "upload.bin"

    def _read_index(self) -> Dict[str, Any]:
        try:
            with self.index_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("files", [])
        data.setdefault("artifacts", [])
        return data

    def _write_index(self, data: Dict[str, Any]) -> None:
        with self.index_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _normalize_file_record(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "file_id": row.get("file_id", ""),
            "original_name": row.get("original_name", ""),
            "saved_name": row.get("saved_name", ""),
            "relative_path": row.get("relative_path", ""),
            "size": int(row.get("size", 0) or 0),
            "extension": row.get("extension", ""),
            "uploaded_at": row.get("uploaded_at", ""),
        }

    def save_upload(self, original_name: str, content: bytes) -> Dict[str, Any]:
        safe_name = self._safe_name(original_name)
        ext = Path(safe_name).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError("仅支持上传 csv/xlsx/xls/txt/json 文件")

        file_id = f"file_{uuid.uuid4().hex[:12]}"
        saved_name = f"{file_id}_{safe_name}"
        abs_path = (self.uploads_dir / saved_name).resolve()
        if self.uploads_dir not in abs_path.parents:
            raise ValueError("文件保存路径非法")

        abs_path.write_bytes(content)
        record = {
            "file_id": file_id,
            "original_name": original_name,
            "saved_name": saved_name,
            "relative_path": f"uploads/{saved_name}",
            "size": int(len(content)),
            "extension": ext,
            "uploaded_at": _now_iso(),
        }
        with self._lock:
            data = self._read_index()
            data["files"] = [r for r in data.get("files", []) if r.get("file_id") != file_id]
            data["files"].insert(0, record)
            self._write_index(data)
        return self._normalize_file_record(record)

    def list_files(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read_index()
            return [self._normalize_file_record(r) for r in data.get("files", [])]

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        file_id = (file_id or "").strip()
        if not file_id:
            return None
        with self._lock:
            for row in self._read_index().get("files", []):
                if row.get("file_id") == file_id:
                    item = self._normalize_file_record(row)
                    abs_path = (self.root / item["relative_path"]).resolve()
                    if not abs_path.exists():
                        return None
                    if self.uploads_dir not in abs_path.parents:
                        return None
                    item["abs_path"] = str(abs_path)
                    return item
        return None

    def resolve_file_from_query(self, query: str, fallback_file_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        text = query or ""
        match = re.search(r"\bfile[_-]?id\s*[:：]?\s*([A-Za-z0-9_-]+)\b", text, re.IGNORECASE)
        file_id = match.group(1) if match else (fallback_file_id or "")
        if not file_id:
            return None
        return self.get_file(file_id)

    def save_artifact(
        self,
        name: str,
        content: str,
        mime_type: str = "text/markdown; charset=utf-8",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        safe_name = self._safe_name(name)
        artifact_id = f"artifact_{uuid.uuid4().hex[:12]}"
        saved_name = f"{artifact_id}_{safe_name}"
        abs_path = (self.artifacts_dir / saved_name).resolve()
        if self.artifacts_dir not in abs_path.parents:
            raise ValueError("产物保存路径非法")
        abs_path.write_text(content, encoding="utf-8")
        record = {
            "id": artifact_id,
            "name": safe_name,
            "type": "file",
            "path": f"artifacts/{saved_name}",
            "url": f"/api/artifacts/{artifact_id}",
            "mime_type": mime_type,
            "metadata": dict(metadata or {}),
            "created_at": _now_iso(),
        }
        with self._lock:
            data = self._read_index()
            data["artifacts"] = [a for a in data.get("artifacts", []) if a.get("id") != artifact_id]
            data["artifacts"].insert(0, record)
            self._write_index(data)
        return record

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        artifact_id = (artifact_id or "").strip()
        if not artifact_id:
            return None
        with self._lock:
            for row in self._read_index().get("artifacts", []):
                if row.get("id") == artifact_id:
                    item = dict(row)
                    abs_path = (self.root / str(item.get("path", ""))).resolve()
                    if not abs_path.exists():
                        return None
                    if self.artifacts_dir not in abs_path.parents:
                        return None
                    item["abs_path"] = str(abs_path)
                    return item
        return None
