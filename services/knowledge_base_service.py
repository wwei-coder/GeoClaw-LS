from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict

class KnowledgeBaseService:
    def _get_knowledge_base_api(self, agent: Any) -> Any:
        return getattr(agent, "knowledge_base_facade", None) or agent

    def sync(self, agent: Any) -> Dict[str, Any]:
        kb_api = self._get_knowledge_base_api(agent)
        return kb_api.sync_knowledge_base_now()

    def status(self, agent: Any) -> Dict[str, Any]:
        kb_api = self._get_knowledge_base_api(agent)
        return kb_api.get_knowledge_base_status()

    def documents(self, agent: Any) -> Dict[str, Any]:
        kb_api = self._get_knowledge_base_api(agent)
        return {"documents": kb_api.get_document_index_stats()}

    def diagnostics(self, agent: Any, *, limit: int) -> Dict[str, Any]:
        safe_limit = max(1, min(limit, 100))
        kb_api = self._get_knowledge_base_api(agent)
        return kb_api.get_retrieval_diagnostics(limit=safe_limit)

    def rebuild(self, agent: Any) -> Dict[str, Any]:
        kb_api = self._get_knowledge_base_api(agent)
        return kb_api.rebuild_knowledge_base_now()

    def system_reset(self, agent: Any) -> Dict[str, Any]:
        agent.factory_reset()
        return {"ok": True, "message": "已触发系统重置，下一次请求将重新初始化引擎。"}

    def save_kb_upload(self, *, filename: str, content: bytes, data_dir: Path | None = None) -> Dict[str, Any]:
        raw_filename = str(filename or "").strip()
        if not content:
            raise ValueError("文件为空，请重新选择")

        if raw_filename and raw_filename != Path(raw_filename).name:
            raise ValueError("文件名非法")

        base_dir = Path(data_dir or "data").resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_name(raw_filename)
        target_path = self._reserve_unique_path(base_dir, safe_name)
        target_path.write_bytes(content)
        original_name = raw_filename or safe_name
        return {
            "ok": True,
            "file": {
                "original_name": original_name,
                "saved_name": target_path.name,
                "size": len(content),
                "relative_path": str(Path("data") / target_path.name),
            },
        }

    def _safe_name(self, file_name: str) -> str:
        name = Path(file_name or "").name.strip()
        name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name)
        return name or "knowledge.txt"

    def _reserve_unique_path(self, base_dir: Path, file_name: str) -> Path:
        candidate = (base_dir / file_name).resolve()
        if base_dir not in candidate.parents:
            raise ValueError("文件名非法")
        if not candidate.exists():
            return candidate

        stem = Path(file_name).stem or "knowledge"
        suffix = Path(file_name).suffix
        for idx in range(1, 1000):
            named = f"{stem}_{idx}{suffix}"
            next_path = (base_dir / named).resolve()
            if base_dir in next_path.parents and not next_path.exists():
                return next_path
        raise FileExistsError("同名文件过多，请先清理后重试")
