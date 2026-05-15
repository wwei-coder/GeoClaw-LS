from __future__ import annotations
from typing import Any
from utils.logger import logger
from utils.ollama_client import ask_ollama
from .prompt_catalog import get_prompt_catalog

class SmallTalkService:
    def __init__(self, *, agent_core: Any, prompt_catalog: Any = None, ask_fn=ask_ollama):
        self.agent_core = agent_core
        self.prompt_catalog = prompt_catalog or get_prompt_catalog()
        self.ask_fn = ask_fn

    def handle(self, question: str):
        prompt = self.prompt_catalog.render("small_talk", question=question)
        final_answer = self.ask_fn(prompt, temperature=self.agent_core.temperature).strip()

        sid = self.agent_core.get_active_session_id()
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
