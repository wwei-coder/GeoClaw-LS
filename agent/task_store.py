from __future__ import annotations
import json
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from utils.logger import logger
from .state import AgentStep, AgentTask, Artifact

class TaskStore:
    """Agent 任务持久化存储（基于现有 SQLite 连接）。"""

    def __init__(self, db_manager: Any):
        self.db_manager = db_manager
        self.ensure_schema()

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self.db_manager, "conn", None)
        if conn is None:
            raise RuntimeError("数据库连接不可用")
        return conn

    def _lock(self) -> Any:
        return getattr(self.db_manager, "_lock")

    def _safe_json_dumps(self, value: Any) -> str:
        def _default(obj: Any) -> Any:
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            return str(obj)

        try:
            return json.dumps(value if value is not None else {}, ensure_ascii=False, default=_default)
        except Exception:
            return "{}"

    def _safe_json_loads(self, text: Any) -> Any:
        if text is None:
            return {}
        if isinstance(text, (dict, list)):
            return text
        raw = str(text).strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        conn = self._connection()
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        cols = {str(row[1]).lower() for row in (cur.fetchall() or [])}
        if column.lower() not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def ensure_schema(self) -> None:
        with self._lock():
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    user_query TEXT,
                    status TEXT,
                    run_mode TEXT,
                    cancel_requested INTEGER DEFAULT 0,
                    resumed_from TEXT,
                    final_answer TEXT,
                    metadata_json TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_steps (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    position INTEGER,
                    tool_name TEXT,
                    instruction TEXT,
                    status TEXT,
                    retry_of TEXT,
                    attempts INTEGER DEFAULT 1,
                    cancel_requested INTEGER DEFAULT 0,
                    input_json TEXT,
                    result_json TEXT,
                    error TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY(task_id) REFERENCES agent_tasks(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    name TEXT,
                    type TEXT,
                    path TEXT,
                    url TEXT,
                    mime_type TEXT,
                    metadata_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY(task_id) REFERENCES agent_tasks(id)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_steps_task_id ON agent_steps(task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_steps_position ON agent_steps(task_id, position)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_artifacts_task_id ON agent_artifacts(task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_session_id ON agent_tasks(session_id)")
            self._ensure_column("agent_tasks", "run_mode", "run_mode TEXT")
            self._ensure_column("agent_tasks", "cancel_requested", "cancel_requested INTEGER DEFAULT 0")
            self._ensure_column("agent_tasks", "resumed_from", "resumed_from TEXT")
            self._ensure_column("agent_steps", "retry_of", "retry_of TEXT")
            self._ensure_column("agent_steps", "attempts", "attempts INTEGER DEFAULT 1")
            self._ensure_column("agent_steps", "cancel_requested", "cancel_requested INTEGER DEFAULT 0")
            conn.commit()

    def save_task(self, task: AgentTask, session_id: Optional[Any] = None) -> None:
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO agent_tasks (id, session_id, user_query, status, run_mode, cancel_requested, resumed_from, final_answer, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        session_id = excluded.session_id,
                        user_query = excluded.user_query,
                        status = excluded.status,
                        run_mode = excluded.run_mode,
                        cancel_requested = excluded.cancel_requested,
                        resumed_from = excluded.resumed_from,
                        final_answer = excluded.final_answer,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(task.id),
                        None if session_id is None else str(session_id),
                        str(task.user_query or ""),
                        str(task.status or "pending"),
                        str(task.run_mode or "sync"),
                        1 if task.cancel_requested else 0,
                        task.resumed_from,
                        str(task.final_answer or ""),
                        self._safe_json_dumps(task.metadata or {}),
                        str(task.created_at or ""),
                        str(task.updated_at or ""),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.warning(f"[TaskStore] 保存任务失败: {exc}")

    def update_task_status(self, task_id: str, status: str, final_answer: Optional[str] = None) -> None:
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                if final_answer is None:
                    cur.execute(
                        "UPDATE agent_tasks SET status = ?, updated_at = ? WHERE id = ?",
                        (str(status), datetime.utcnow().replace(microsecond=0).isoformat() + "Z", str(task_id)),
                    )
                else:
                    cur.execute(
                        "UPDATE agent_tasks SET status = ?, final_answer = ?, updated_at = ? WHERE id = ?",
                        (
                            str(status),
                            str(final_answer),
                            datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                            str(task_id),
                        ),
                    )
                conn.commit()
            except Exception as exc:
                logger.warning(f"[TaskStore] 更新任务状态失败: {exc}")

    def set_task_cancel_requested(self, task_id: str, cancel_requested: bool = True) -> None:
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE agent_tasks SET cancel_requested = ?, updated_at = ? WHERE id = ?",
                    (
                        1 if cancel_requested else 0,
                        datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                        str(task_id),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.warning(f"[TaskStore] 更新取消标记失败: {exc}")

    def save_step(self, task_id: str, step: AgentStep, position: int) -> None:
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO agent_steps (id, task_id, position, tool_name, instruction, status, retry_of, attempts, cancel_requested, input_json, result_json, error, started_at, finished_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        task_id = excluded.task_id,
                        position = excluded.position,
                        tool_name = excluded.tool_name,
                        instruction = excluded.instruction,
                        status = excluded.status,
                        retry_of = excluded.retry_of,
                        attempts = excluded.attempts,
                        cancel_requested = excluded.cancel_requested,
                        input_json = excluded.input_json,
                        result_json = excluded.result_json,
                        error = excluded.error,
                        started_at = excluded.started_at,
                        finished_at = excluded.finished_at,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        str(step.id),
                        str(task_id),
                        int(position),
                        str(step.tool_name or ""),
                        str(step.instruction or ""),
                        str(step.status or "pending"),
                        step.retry_of,
                        int(step.attempts or 1),
                        1 if step.cancel_requested else 0,
                        self._safe_json_dumps(step.input or {}),
                        self._safe_json_dumps(step.result or {}),
                        step.error,
                        step.started_at,
                        step.finished_at,
                        self._safe_json_dumps(step.metadata or {}),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.warning(f"[TaskStore] 保存步骤失败: {exc}")

    def save_artifact(self, task_id: str, artifact: Artifact) -> None:
        payload = artifact.to_dict() if hasattr(artifact, "to_dict") else dict(artifact or {})
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO agent_artifacts (id, task_id, name, type, path, url, mime_type, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        task_id = excluded.task_id,
                        name = excluded.name,
                        type = excluded.type,
                        path = excluded.path,
                        url = excluded.url,
                        mime_type = excluded.mime_type,
                        metadata_json = excluded.metadata_json,
                        created_at = excluded.created_at
                    """,
                    (
                        str(payload.get("id") or ""),
                        str(task_id),
                        str(payload.get("name") or "artifact"),
                        str(payload.get("type") or payload.get("kind") or "text"),
                        str(payload.get("path") or ""),
                        str(payload.get("url") or ""),
                        str(payload.get("mime_type") or ""),
                        self._safe_json_dumps(payload.get("metadata") or {}),
                        str(payload.get("created_at") or ""),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.warning(f"[TaskStore] 保存产物失败: {exc}")

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, session_id, user_query, status, run_mode, cancel_requested, resumed_from, final_answer, metadata_json, created_at, updated_at
                    FROM agent_tasks
                    WHERE id = ?
                    """,
                    (str(task_id),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                task = AgentTask(
                    id=str(row[0]),
                    user_query=str(row[2] or ""),
                    status=str(row[3] or "pending"),
                    run_mode=str(row[4] or "sync"),
                    cancel_requested=bool(row[5]),
                    resumed_from=row[6],
                    final_answer=str(row[7] or ""),
                    metadata=self._safe_json_loads(row[8]),
                    created_at=str(row[9] or ""),
                    updated_at=str(row[10] or ""),
                    steps=[],
                    artifacts=[],
                )
                task.metadata.setdefault("session_id", row[1])
                cur.execute(
                    """
                    SELECT id, tool_name, instruction, status, retry_of, attempts, cancel_requested, input_json, result_json, error, started_at, finished_at, metadata_json
                    FROM agent_steps
                    WHERE task_id = ?
                    ORDER BY position ASC
                    """,
                    (str(task_id),),
                )
                steps: List[AgentStep] = []
                for step_row in cur.fetchall() or []:
                    step = AgentStep(
                        id=str(step_row[0]),
                        tool_name=str(step_row[1] or ""),
                        instruction=str(step_row[2] or ""),
                        status=str(step_row[3] or "pending"),
                        retry_of=step_row[4],
                        attempts=int(step_row[5] or 1),
                        cancel_requested=bool(step_row[6]),
                        input=self._safe_json_loads(step_row[7]),
                        result=self._safe_json_loads(step_row[8]),
                        error=step_row[9],
                        started_at=step_row[10],
                        finished_at=step_row[11],
                        metadata=self._safe_json_loads(step_row[12]),
                        artifacts=[],
                    )
                    steps.append(step)
                task.steps = steps
                artifacts = self.list_artifacts(task_id=task_id, limit=500)
                task.artifacts = artifacts
                return {"task": task, "steps": steps, "artifacts": artifacts}
            except Exception as exc:
                logger.warning(f"[TaskStore] 查询任务失败: {exc}")
                return None

    def list_tasks(self, session_id: Optional[Any] = None, limit: int = 50) -> List[AgentTask]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                if session_id is None:
                    cur.execute(
                        """
                        SELECT id, session_id, user_query, status, run_mode, cancel_requested, resumed_from, final_answer, metadata_json, created_at, updated_at
                        FROM agent_tasks
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (safe_limit,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, session_id, user_query, status, run_mode, cancel_requested, resumed_from, final_answer, metadata_json, created_at, updated_at
                        FROM agent_tasks
                        WHERE session_id = ?
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (str(session_id), safe_limit),
                    )
                tasks: List[AgentTask] = []
                for row in cur.fetchall() or []:
                    tasks.append(
                        AgentTask(
                            id=str(row[0]),
                            user_query=str(row[2] or ""),
                            status=str(row[3] or "pending"),
                            run_mode=str(row[4] or "sync"),
                            cancel_requested=bool(row[5]),
                            resumed_from=row[6],
                            final_answer=str(row[7] or ""),
                            metadata=self._safe_json_loads(row[8]),
                            created_at=str(row[9] or ""),
                            updated_at=str(row[10] or ""),
                            steps=[],
                            artifacts=[],
                        )
                    )
                    tasks[-1].metadata.setdefault("session_id", row[1])
                return tasks
            except Exception as exc:
                logger.warning(f"[TaskStore] 列出任务失败: {exc}")
                return []

    def list_artifacts(self, task_id: Optional[str] = None, limit: int = 50) -> List[Artifact]:
        safe_limit = max(1, min(int(limit or 50), 500))
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                if task_id:
                    cur.execute(
                        """
                        SELECT id, task_id, name, type, path, url, mime_type, metadata_json, created_at
                        FROM agent_artifacts
                        WHERE task_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (str(task_id), safe_limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, task_id, name, type, path, url, mime_type, metadata_json, created_at
                        FROM agent_artifacts
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (safe_limit,),
                    )
                out: List[Artifact] = []
                for row in cur.fetchall() or []:
                    out.append(
                        Artifact(
                            id=str(row[0]),
                            task_id=str(row[1] or ""),
                            name=str(row[2] or "artifact"),
                            type=str(row[3] or "text"),
                            path=str(row[4] or ""),
                            url=str(row[5] or ""),
                            mime_type=str(row[6] or ""),
                            metadata=self._safe_json_loads(row[7]),
                            created_at=str(row[8] or ""),
                        )
                    )
                return out
            except Exception as exc:
                logger.warning(f"[TaskStore] 列出产物失败: {exc}")
                return []

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        if not str(artifact_id or "").strip():
            return None
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, task_id, name, type, path, url, mime_type, metadata_json, created_at
                    FROM agent_artifacts
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (str(artifact_id),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return Artifact(
                    id=str(row[0]),
                    task_id=str(row[1] or ""),
                    name=str(row[2] or "artifact"),
                    type=str(row[3] or "text"),
                    path=str(row[4] or ""),
                    url=str(row[5] or ""),
                    mime_type=str(row[6] or ""),
                    metadata=self._safe_json_loads(row[7]),
                    created_at=str(row[8] or ""),
                )
            except Exception as exc:
                logger.warning(f"[TaskStore] 获取产物失败: {exc}")
                return None

    def get_task_record(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, session_id, user_query, status, run_mode, cancel_requested, resumed_from, final_answer, metadata_json, created_at, updated_at
                    FROM agent_tasks
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (str(task_id),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": str(row[0]),
                    "session_id": row[1],
                    "user_query": str(row[2] or ""),
                    "status": str(row[3] or "pending"),
                    "run_mode": str(row[4] or "sync"),
                    "cancel_requested": bool(row[5]),
                    "resumed_from": row[6],
                    "final_answer": str(row[7] or ""),
                    "metadata": self._safe_json_loads(row[8]),
                    "created_at": str(row[9] or ""),
                    "updated_at": str(row[10] or ""),
                }
            except Exception as exc:
                logger.warning(f"[TaskStore] 获取任务记录失败: {exc}")
                return None

    def mark_interrupted_running_tasks(self, interrupted_status: str = "partial") -> int:
        safe_status = interrupted_status if interrupted_status in {"partial", "failed"} else "partial"
        with self._lock():
            try:
                conn = self._connection()
                cur = conn.cursor()
                cur.execute("SELECT id, metadata_json FROM agent_tasks WHERE status = 'running'")
                rows = cur.fetchall() or []
                updated = 0
                for task_id, metadata_json in rows:
                    metadata = self._safe_json_loads(metadata_json)
                    metadata["interrupted"] = True
                    metadata["interrupted_reason"] = "应用重启或进程中断，后台任务未能继续运行。"
                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = ?, cancel_requested = 0, metadata_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            safe_status,
                            self._safe_json_dumps(metadata),
                            datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                            str(task_id),
                        ),
                    )
                    updated += 1
                conn.commit()
                return updated
            except Exception as exc:
                logger.warning(f"[TaskStore] 标记中断任务失败: {exc}")
                return 0
