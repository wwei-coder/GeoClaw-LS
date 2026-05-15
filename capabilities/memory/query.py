from __future__ import annotations

from typing import Any, Dict

from utils.logger import logger


class MemoryQueryService:
    def __init__(self, agent_core: Any):
        self.agent_core = agent_core

    def handle(self, question: str) -> Dict[str, Any]:
        q = question or ""
        want_answer = any(k in q for k in ("你刚才说", "上一轮回答", "刚才回答", "你上次说"))
        sid = self.agent_core.get_active_session_id()
        row = self.agent_core.db_manager.get_last_conversation(self.agent_core.user_id, session_id=sid)

        if not row:
            final_answer = "无法从记录确定上一轮内容（目前还没有历史对话）。"
        else:
            last_q, last_a = row
            if want_answer:
                final_answer = f"上一轮回答是：{last_a}"
            else:
                final_answer = f"上一轮问题是：{last_q}"

        try:
            self.agent_core.db_manager.add_conversation(
                self.agent_core.user_id,
                question,
                final_answer,
                session_id=sid,
            )
        except Exception as e:
            logger.warning(f"记忆查询记录保存失败: {e}")

        return {"answer": final_answer, "confidence": 0.0, "sources": []}
