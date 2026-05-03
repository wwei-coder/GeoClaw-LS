from __future__ import annotations

import asyncio
import contextvars
import threading
import time
from typing import Any, Dict, List

from agent.runtime import AgentRequestContext
from agent.task_runner import TaskRunner
from core.agent_core import AgentCore


class _FakeBrain:
    def is_small_talk(self, _question: str) -> bool:
        return False

    def is_memory_query(self, _question: str) -> bool:
        return False


class _RuntimeRecorder:
    def __init__(self, core: AgentCore):
        self.core = core
        self.calls: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    async def run_async(self, question: str, *, file_id: str = "", files=None, task_id: str = "", run_mode: str = "sync", resumed_from=None):
        await asyncio.sleep(0.03)
        with self._lock:
            self.calls.append(
                {
                    "question": question,
                    "session_seen": self.core.get_active_session_id(),
                    "file_id": file_id,
                    "files": list(files or []),
                    "task_id": task_id,
                    "run_mode": run_mode,
                    "resumed_from": resumed_from,
                }
            )
        return {"answer": "ok", "task_id": task_id, "sources": [], "trace": ""}


class _FakeTaskStore:
    def __init__(self):
        self.records: Dict[str, Dict[str, Any]] = {}
        self.saved_session_ids: List[Any] = []
        self._lock = threading.RLock()

    def mark_interrupted_running_tasks(self, interrupted_status: str = "partial") -> None:
        _ = interrupted_status

    def save_task(self, task, session_id=None) -> None:
        with self._lock:
            self.saved_session_ids.append(session_id)
            self.records[str(task.id)] = {
                "id": str(task.id),
                "status": str(task.status or "pending"),
                "session_id": session_id,
                "user_query": str(getattr(task, "user_query", "")),
                "metadata": dict(getattr(task, "metadata", {}) or {}),
            }

    def update_task_status(self, task_id: str, status: str, final_answer: str = "") -> None:
        with self._lock:
            row = self.records.setdefault(str(task_id), {"id": str(task_id), "metadata": {}})
            row["status"] = status
            row["final_answer"] = final_answer

    def get_task_record(self, task_id: str):
        with self._lock:
            return dict(self.records.get(str(task_id), {})) or None

    def set_task_cancel_requested(self, task_id: str, value: bool) -> None:
        with self._lock:
            row = self.records.setdefault(str(task_id), {"id": str(task_id), "metadata": {}})
            row["cancel_requested"] = bool(value)


def _build_minimal_agent_core() -> AgentCore:
    core = AgentCore.__new__(AgentCore)
    core.session_id = 999
    core.short_memory = ["loaded"]
    core.pending_tool_call = None
    core._execution_lock = threading.RLock()
    core._request_session_id_var = contextvars.ContextVar("request_session_id", default=None)
    core._request_context_var = contextvars.ContextVar("request_context", default=None)
    core._active_chat_session_id = None
    core._active_cancel_event = None
    core._current_stream_callback = None
    core.active_file_id = None
    core.active_files = []
    core.brain = _FakeBrain()
    core.runtime = _RuntimeRecorder(core)
    return core


def test_chat_async_isolated_by_request_context():
    core = _build_minimal_agent_core()
    ctx1 = AgentRequestContext(session_id=101, file_id="f-1", files=[{"id": "f-1"}], run_mode="sync")
    ctx2 = AgentRequestContext(session_id=202, file_id="f-2", files=[{"id": "f-2"}], run_mode="sync")

    asyncio.run(core.chat_async("q1", request_context=ctx1))
    asyncio.run(core.chat_async("q2", request_context=ctx2))

    seen = [c["session_seen"] for c in core.runtime.calls]
    assert seen == [101, 202]
    assert core.session_id == 999
    assert core.active_file_id is None
    assert core.active_files == []


def test_chat_async_legacy_parameters_still_work():
    core = _build_minimal_agent_core()
    asyncio.run(
        core.chat_async(
            "legacy",
            session_id=303,
            file_id="legacy-file",
            files=[{"id": "legacy-file"}],
            task_id="task_legacy",
            run_mode="sync",
        )
    )
    assert core.runtime.calls[0]["session_seen"] == 303
    assert core.runtime.calls[0]["file_id"] == "legacy-file"
    assert core.runtime.calls[0]["task_id"] == "task_legacy"


def test_foreground_and_background_do_not_cross_session():
    core = _build_minimal_agent_core()
    core.task_store = _FakeTaskStore()
    runner = TaskRunner(core, max_workers=1)
    core.task_runner = runner

    bg_ctx = AgentRequestContext(session_id=11, run_mode="background", metadata={"source": "test"})
    created = runner.submit_task(message="bg", request_context=bg_ctx)
    task_id = created["task_id"]

    asyncio.run(core.chat_async("fg", request_context=AgentRequestContext(session_id=22, run_mode="sync")))

    deadline = time.time() + 3.0
    while runner.is_running(task_id) and time.time() < deadline:
        time.sleep(0.01)

    assert runner.is_running(task_id) is False
    seen = [c["session_seen"] for c in core.runtime.calls]
    assert 11 in seen and 22 in seen
    assert core.session_id == 999
    assert 11 in core.task_store.saved_session_ids

    runner.shutdown()
