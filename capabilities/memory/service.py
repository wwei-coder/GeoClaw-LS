from __future__ import annotations
import asyncio
from typing import Any, Callable, Dict, Tuple
from config_runtime import MAX_HISTORY_ROUNDS
from utils.logger import logger
from .summary import summarize_dialog

class ConversationMemoryService:
    def __init__(
        self,
        agent_core: Any,
        summarize_fn: Callable[[str], Tuple[str, Dict[str, str]]] = summarize_dialog,
    ):
        self.agent_core = agent_core
        self.summarize_fn = summarize_fn

    def render_user_preferences_block(self) -> str:
        if not self.agent_core.user_preferences:
            return ""
        prefs = []
        for k, v in self.agent_core.user_preferences.items():
            prefs.append(f"- {k}: {v}")
        return "\n\n【用户偏好与习惯】\n" + "\n".join(prefs) + "\n请严格遵守上述用户偏好。"

    def apply_post_answer_effects(self, question: str, final_answer: str) -> None:
        self.agent_core.short_memory.append(f"用户：{question}")
        self.agent_core.short_memory.append(f"助手：{final_answer}")

        sid = self.agent_core.get_active_session_id()
        try:
            self.agent_core.db_manager.add_conversation(
                self.agent_core.user_id,
                question,
                final_answer,
                session_id=sid,
            )
        except Exception as e:
            logger.error(f"[System] ⚠️ 对话保存失败 (DB Error): {e}")

        if len(self.agent_core.short_memory) >= MAX_HISTORY_ROUNDS:
            dialog_text = "\n".join(self.agent_core.short_memory)
            new_summary, new_prefs = self.summarize_fn((self.agent_core.summary_memory + "\n" + dialog_text).strip())
            if new_prefs:
                logger.info(f"[Memory] 捕捉到用户偏好更新: {new_prefs}")
                self.agent_core.user_preferences.update(new_prefs)
            if self.agent_core.summary_memory:
                logger.info("[Memory] 正在将旧摘要存入向量库...")
                self.agent_core.vector_store.add_episodic_memory(self.agent_core.summary_memory)
                self.agent_core.vector_store.save()

            self.agent_core.summary_memory = new_summary
            self.agent_core.short_memory = []
            logger.info("[SynthesisChain] Memory compressed & updated")

    async def apply_post_answer_effects_async(self, question: str, final_answer: str) -> None:
        self.agent_core.short_memory.append(f"用户：{question}")
        self.agent_core.short_memory.append(f"助手：{final_answer}")

        sid = self.agent_core.get_active_session_id()
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.agent_core.db_manager.add_conversation(
                    self.agent_core.user_id,
                    question,
                    final_answer,
                    session_id=sid,
                ),
            )
        except Exception as e:
            logger.error(f"[System] ⚠️ 对话保存失败 (DB Error): {e}")

        if len(self.agent_core.short_memory) >= MAX_HISTORY_ROUNDS:
            dialog_text = "\n".join(self.agent_core.short_memory)
            loop = asyncio.get_running_loop()

            def do_summary_update():
                return self.summarize_fn((self.agent_core.summary_memory + "\n" + dialog_text).strip())

            new_summary, new_prefs = await loop.run_in_executor(None, do_summary_update)
            if new_prefs:
                logger.info(f"[Memory] 捕捉到用户偏好更新: {new_prefs}")
                self.agent_core.user_preferences.update(new_prefs)

            if self.agent_core.summary_memory:
                logger.info("[Memory] 正在将旧摘要存入向量库...")
                await loop.run_in_executor(None, lambda: self.agent_core.vector_store.add_episodic_memory(self.agent_core.summary_memory))
                await loop.run_in_executor(None, self.agent_core.vector_store.save)

            self.agent_core.summary_memory = new_summary
            self.agent_core.short_memory = []
            logger.info("[SynthesisChain] Memory compressed & updated")
